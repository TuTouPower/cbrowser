"""t103 AC-001 / AC-002 / AC-004 integration tests: strict 422s, mute_audio, N vs N+1 upgrade adoption & Supervisor snapshot.json."""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from alembic import command
from fastapi.testclient import TestClient

from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)
from cbrowser.api.app import create_app
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator
from tests.unit.test_t103_launch_args_migration import (
    REVISION_BEFORE,
    WIN_SET,
    _insert_profile,
    _insert_version,
)

REMOVED_FIELD_CASES = [
    ("humanize", True),
    ("human_preset", "careful"),
    ("auto_launch", True),
    ("allow_3p_cookies", False),
    ("transparent_proxy", True),
    ("portable_cookies", False),
    ("launch_args", ["--no-first-run"]),
]


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "cleanup.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    sup_file = tmp_path / "sup.token"
    sup_token = secrets.token_urlsafe(32)
    sup_file.write_text(sup_token, encoding="utf-8")
    sup_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_file,
        supervisor_token_file=sup_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        client.headers.update(
            {
                "X-CSRF-Token": login.json()["csrf_token"],
                "Origin": "https://127.0.0.1:56661",
            }
        )
        yield client, db_file, sup_token


@pytest.mark.parametrize("field,value", REMOVED_FIELD_CASES)
def test_create_and_update_reject_removed_fields_with_422_and_zero_writes(
    api_client, field: str, value
) -> None:
    client, _, _ = api_client

    bad_create = client.post("/api/v1/profiles", json={"name": "Bad", field: value})
    assert bad_create.status_code == 422, bad_create.text
    body = bad_create.json()
    assert any(field in str(d.get("loc", [])) for d in body.get("details", [])), body
    assert client.get("/api/v1/profiles").json() == []

    good_create = client.post("/api/v1/profiles", json={"name": "Clean"})
    assert good_create.status_code == 201, good_create.text
    created = good_create.json()
    pid = created["id"]
    assert created["mute_audio"] is False
    assert created["clipboard_sync"] is True
    assert created["set_google_default"] is True
    assert created["restore_session"] is True
    assert created["capture_preview"] is True
    assert created["geoip"] is True
    assert created["locale"] == "en-US"
    assert created["timezone"] is None
    assert created["screen_width"] == 1920
    assert created["screen_height"] == 1080
    assert created["color_scheme"] == "light"
    assert created["extension_paths"] == []
    for gone, _ in REMOVED_FIELD_CASES:
        assert gone not in created

    for method in ("patch", "put"):
        bad_upd = getattr(client, method)(
            f"/api/v1/profiles/{pid}", json={field: value}
        )
        assert bad_upd.status_code == 422, bad_upd.text
        upd_body = bad_upd.json()
        assert any(
            field in str(d.get("loc", [])) for d in upd_body.get("details", [])
        ), upd_body

    versions = client.get(f"/api/v1/profiles/{pid}/versions").json()
    assert [v["version"] for v in versions] == [1]


@pytest.mark.asyncio
async def test_mute_audio_defaults_versioning_and_n_vs_n_plus_1_upgrade_supervisor_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from cbrowser.api.runtime_coordinator import ReconcileOutcome, RuntimeCoordinator
    from cbrowser.api.v1.deps import get_profile_service
    from cbrowser.font_sets import import_font_set
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator
    from docker_doubles import FakeDockerAdapter

    # Stage a real verified font set on disk so SupervisorCore._validate_font_set executes end-to-end
    font_names = (
        "arial.ttf", "calibri.ttf", "cour.ttf", "georgia.ttf", "tahoma.ttf",
        "times.ttf", "trebuc.ttf", "verdana.ttf", "calibrib.ttf", "calibrii.ttf",
        "calibriz.ttf", "cambria.ttc", "cambriab.ttf", "Candara.ttf", "consola.ttf",
        "constan.ttf", "corbel.ttf",
    )
    font_src = tmp_path / "font_src" / "windows"
    font_src.mkdir(parents=True, exist_ok=True)
    for fname in font_names:
        (font_src / fname).write_bytes(b"font-bytes-" + fname.encode("utf-8"))
    fonts_root = tmp_path / "fonts"
    win_set = import_font_set("windows", [font_src], "t103-1.0", root=fonts_root)["set_id"]
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))

    data_root = (tmp_path / "data").resolve()
    (data_root / "engine_cache" / "geoip").mkdir(parents=True, exist_ok=True)
    source_user_dir = data_root / "profiles" / "p-upg" / "profile"
    source_user_dir.mkdir(parents=True, exist_ok=True)
    (source_user_dir / "Cookies").write_bytes(b"cookie-state-v2")

    db_file = tmp_path / "upgrade_n_np1.db"
    cfg = get_alembic_config(db_file)
    command.upgrade(cfg, REVISION_BEFORE)

    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO font_set_assets (platform, set_id, source, source_version,"
            " file_count, total_bytes, integrity, state, revision, state_seq,"
            " verified_at, audited_at, created_at, updated_at)"
            " VALUES ('windows', ?, 'fixture', 'v1', 17, 100, '{}', 'verified', 1, 1,"
            " '2026-01-01T00:00:00+00:00', NULL, '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00')",
            (win_set,),
        )
        _insert_profile(
            conn,
            "p-upg",
            42,
            locale="zh-CN",
            geoip=True,
            launch_args=["--mute-audio", "--disable-sync"],
            extension_paths=["/opt/ext"],
            current_config_version=2,
            bound_version=1,
            runtime_instance_id="inst_old_running",
            desired_state="running",
        )
        conn.execute(
            "UPDATE profiles SET screen_width = 1600, font_set_id = ?, user_data_dir = ? WHERE id = 'p-upg'",
            (win_set, str(source_user_dir)),
        )
        # v1 (bound N=1): 1280px wide, not muted, old keys still in snapshot
        _insert_version(
            conn,
            "v1-row",
            "p-upg",
            1,
            wrapped=True,
            locale="en-US",
            launch_args=[],
            extension_paths=[],
        )
        v1_snap = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v1-row'"
            ).fetchone()[0]
        )
        v1_snap["config"]["screen_width"] = 1280
        v1_snap["config"]["font_set_id"] = win_set
        conn.execute(
            "UPDATE profile_config_versions SET snapshot = ? WHERE id = 'v1-row'",
            (json.dumps(v1_snap),),
        )
        # v2 (current N+1=2): 1600px wide, --mute-audio -> mute_audio=True
        _insert_version(
            conn,
            "v2-row",
            "p-upg",
            2,
            wrapped=True,
            locale="zh-CN",
            launch_args=["--mute-audio", "--disable-translate"],
            extension_paths=["/opt/ext"],
        )
        v2_snap = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v2-row'"
            ).fetchone()[0]
        )
        v2_snap["config"]["screen_width"] = 1600
        v2_snap["config"]["font_set_id"] = win_set
        conn.execute(
            "UPDATE profile_config_versions SET snapshot = ? WHERE id = 'v2-row'",
            (json.dumps(v2_snap),),
        )
        conn.commit()
    finally:
        conn.close()

    # Old pre-upgrade snapshot.json left on disk for the running old browser container
    runtime_dir = data_root / "runtime" / "p-upg"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    old_disk_snapshot = {
        "id": "snap-old",
        "profile_id": "p-upg",
        "version": 1,
        "config": {
            "name": "Prof-p-upg-v1",
            "screen_width": 1280,
            "screen_height": 1080,
            "clipboard_sync": True,
            "humanize": True,
            "auto_launch": False,
        },
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (runtime_dir / "snapshot.json").write_text(
        json.dumps(old_disk_snapshot), encoding="utf-8"
    )

    run_database_migrations(db_file)

    # Verify adapter adoption readers tolerate the old in-container snapshot.json without ProfileConfig failures
    real_validator = PathValidator(data_root=data_root, socket_root=data_root / "sockets")
    real_adapter = DockerAdapter(
        path_validator=real_validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=object(),
        browser_image="sha256:" + "0" * 64,
        stream_image="sha256:" + "0" * 64,
        policy_image="sha256:" + "0" * 64,
        deployment_instance_id="test-inst",
    )
    assert real_adapter._bound_snapshot_geometry("p-upg", runtime_dir / "snapshot.json") == (
        1280,
        1080,
    )

    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    sup_token = secrets.token_urlsafe(32)
    sup_file = tmp_path / "sup.token"
    sup_file.write_text(sup_token, encoding="utf-8")
    sup_file.chmod(0o600)
    agent_key = tmp_path / "agent.key"
    agent_key.write_text("01234567890123456789012345678901", encoding="utf-8")
    agent_key.chmod(0o600)

    api_app = create_app(
        db_path=db_file,
        data_root=data_root,
        admin_password_file=admin_file,
        supervisor_token_file=sup_file,
    )

    async with api_app.router.lifespan_context(api_app):
        api_transport = httpx.ASGITransport(app=api_app)
        async with (
            httpx.AsyncClient(
                transport=api_transport,
                base_url="https://127.0.0.1:56661",
            ) as api_client,
            httpx.AsyncClient(
                transport=api_transport,
                base_url="http://api",
            ) as sup_to_api,
        ):
            login = await api_client.post("/api/v1/auth/login", json={"password": admin_pass})
            assert login.status_code == 200
            api_client.headers.update(
                {
                    "X-CSRF-Token": login.json()["csrf_token"],
                    "Origin": "https://127.0.0.1:56661",
                }
            )

            # Running state still shows bound version 1 while current version is 2 (pending apply)
            rt = (await api_client.get("/api/v1/profiles/p-upg/runtime")).json()
            assert rt["desired_state"] == "running"
            assert rt["runtime_instance_id"] == "inst_old_running"
            assert rt["config_version"] == 1
            prof = (await api_client.get("/api/v1/profiles/p-upg")).json()
            assert prof["current_config_version"] == 2
            assert prof["mute_audio"] is True

            # Reading historical v1 snapshot returns migrated v1 cleanly
            v1 = (await api_client.get("/api/v1/profiles/p-upg/versions/1")).json()
            assert v1["config"]["screen_width"] == 1280
            assert v1["config"]["mute_audio"] is False

            # Config-only clone keeps source binding N=1 & desired_state=running; clone starts stopped at v1
            dup = await api_client.post(
                "/api/v1/profiles/p-upg/duplicate",
                json={"include_browser_state": False, "name": "Clone-v2"},
            )
            assert dup.status_code == 201, dup.text
            clone_data = dup.json()
            assert clone_data["screen_width"] == 1600
            assert clone_data["mute_audio"] is True
            assert clone_data["current_config_version"] == 1

            clone_rt = (await api_client.get(f"/api/v1/profiles/{clone_data['id']}/runtime")).json()
            assert clone_rt["desired_state"] == "stopped"
            assert clone_rt["observed_state"] == "stopped"
            assert clone_rt["runtime_instance_id"] is None
            assert clone_rt["config_version"] == 1

            rt_after_dup = (await api_client.get("/api/v1/profiles/p-upg/runtime")).json()
            assert rt_after_dup["desired_state"] == "running"
            assert rt_after_dup["runtime_instance_id"] == "inst_old_running"
            assert rt_after_dup["config_version"] == 1

            # Stateful clone is rejected with 409 while source is still running/bound
            dup_running = await api_client.post(
                "/api/v1/profiles/p-upg/duplicate",
                json={"include_browser_state": True, "name": "Clone-Running-Reject"},
            )
            assert dup_running.status_code == 409, dup_running.text

            # Wire REAL SupervisorCore + create_control_app (only Docker/container I/O stubbed)
            class _AdapterDouble(FakeDockerAdapter):
                manage_ownership = False

                def __init__(self, root: Path) -> None:
                    super().__init__(root, resource_prefix="cb-t103")
                    self.dirs = {
                        "profile": root / "profiles" / "p-upg" / "profile",
                        "runtime": root / "runtime" / "p-upg",
                        "events": root / "events" / "p-upg",
                        "exchange": root / "exchange" / "p-upg",
                        "x11": root / "runtime" / "p-upg" / "x11",
                        "pulse": root / "runtime" / "p-upg" / "pulse",
                    }
                    for d in self.dirs.values():
                        d.mkdir(parents=True, exist_ok=True)
                    self.create_profile_network = AsyncMock()
                    self.attach_profile_infrastructure = MagicMock(return_value={})
                    self.teardown_profile = AsyncMock()
                    self.cleanup_profile_processes = MagicMock()
                    self.ensure_runtime_cache = AsyncMock()

                    stream_c = MagicMock()
                    stream_c.id = "s_t103"
                    stream_c.name = "cb-t103-0042-stream"
                    stream_c.status = "running"
                    stream_c.reload = MagicMock()
                    self.start_stream_container = AsyncMock(return_value=stream_c)
                    self.start_browser_container = AsyncMock(side_effect=self._launch_browser)

                def prepare_profile_directories(self, _pid: str) -> dict[str, Path]:
                    return self.dirs

                def _launch_browser(
                    self, profile_id: str, runtime_instance_id: str, snapshot_json_path: Path
                ) -> MagicMock:
                    snap_on_disk = json.loads(Path(snapshot_json_path).read_text(encoding="utf-8"))
                    (self.dirs["runtime"] / "x11" / "X99").touch()
                    (self.dirs["runtime"] / "pulse" / "pulse.sock").touch()
                    (self.dirs["runtime"] / "Xauthority").touch()
                    (self.dirs["runtime"] / "agent.sock").touch()
                    (self.dirs["runtime"] / "runner_info.json").write_text(
                        json.dumps(
                            {
                                "profile_id": profile_id,
                                "runtime_instance_id": runtime_instance_id,
                                "config_version": snap_on_disk["version"],
                                "browser_pid": 23456,
                            }
                        ),
                        encoding="utf-8",
                    )
                    browser_c = MagicMock()
                    browser_c.id = "b_t103"
                    browser_c.name = "cb-t103-0042-browser"
                    return browser_c

            sup_adapter = _AdapterDouble(data_root)
            events = SimpleNamespace(
                drain_runtime_events=AsyncMock(return_value=0),
                forward_exit_event=AsyncMock(),
                emit_event=AsyncMock(),
            )
            gateway = SimpleNamespace(
                has_foreground_viewers=AsyncMock(return_value=True),
                disconnect_viewers=AsyncMock(),
            )
            core = SupervisorCore(
                docker_adapter=sup_adapter,
                port_allocator=PortAllocator(30000, 30010),
                event_forwarder=events,
                api_client=sup_to_api,
                gateway_url="ws://supervisor-host-gw:18097",
                token_file=sup_file,
                agent_key_file=agent_key,
                gateway_control=gateway,
            )
            sup_app = create_control_app(core, sup_file)
            sup_base_transport = httpx.ASGITransport(app=sup_app)

            recorded_coordinator_starts: list[dict] = []

            class _RecordingSupervisorTransport(httpx.AsyncBaseTransport):
                async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                    if request.url.path == "/supervisor/v1/profiles/start":
                        recorded_coordinator_starts.append(json.loads(request.content))
                    return await sup_base_transport.handle_async_request(request)

            profile_service = api_app.dependency_overrides[get_profile_service]()
            coordinator = RuntimeCoordinator(
                supervisor_url="http://supervisor",
                supervisor_token=sup_token,
                profile_service=profile_service,
                transport=_RecordingSupervisorTransport(),
            )

            try:
                async with httpx.AsyncClient(
                    transport=sup_base_transport, base_url="http://supervisor"
                ) as sup_client:
                    # 1. Stop & unbind pre-existing inst_old_running cleanly -> bound_version stays N=1, observed=stopped
                    stop_pre = await api_client.post("/api/v1/profiles/p-upg/stop")
                    assert stop_pre.status_code == 200, stop_pre.text
                    obs_pre = await sup_to_api.post(
                        "/api/v1/internal/supervisor/runtimes/observed?profile_id=p-upg",
                        headers={"Authorization": f"Bearer {sup_token}"},
                        json={
                            "runtime_instance_id": "inst_old_running",
                            "observed_state": "stopped",
                            "config_version": 1,
                            "reason": "stop_requested",
                        },
                    )
                    assert obs_pre.status_code == 200, obs_pre.text

                    # 2. Stateful duplicate after stop & unbind copies user data + N+1 config; clone starts stopped/v1
                    state_dup = await api_client.post(
                        "/api/v1/profiles/p-upg/duplicate",
                        json={"include_browser_state": True, "name": "Clone-With-State"},
                    )
                    assert state_dup.status_code == 201, state_dup.text
                    state_clone = state_dup.json()
                    assert state_clone["current_config_version"] == 1
                    assert state_clone["screen_width"] == 1600
                    assert state_clone["mute_audio"] is True
                    assert state_clone["user_data_dir"] != str(source_user_dir)
                    assert (Path(state_clone["user_data_dir"]) / "Cookies").read_bytes() == b"cookie-state-v2"

                    state_clone_rt = (
                        await api_client.get(f"/api/v1/profiles/{state_clone['id']}/runtime")
                    ).json()
                    assert state_clone_rt["desired_state"] == "stopped"
                    assert state_clone_rt["observed_state"] == "stopped"
                    assert state_clone_rt["runtime_instance_id"] is None
                    assert state_clone_rt["config_version"] == 1

                    # Source profile history and user data stay intact
                    src_after = (await api_client.get("/api/v1/profiles/p-upg")).json()
                    assert src_after["current_config_version"] == 2
                    src_versions = (await api_client.get("/api/v1/profiles/p-upg/versions")).json()
                    assert [v["version"] for v in src_versions] == [1, 2]
                    assert (source_user_dir / "Cookies").read_bytes() == b"cookie-state-v2"

                    # 3. Explicit start of bound version N=1 exercises real SupervisorCore.start_profile snapshot writer
                    start_intent_1 = await api_client.patch(
                        "/api/v1/profiles/p-upg/runtime/desired-state",
                        json={"desired_state": "running"},
                    )
                    assert start_intent_1.status_code == 200, start_intent_1.text
                    res1 = await sup_client.post(
                        "/supervisor/v1/profiles/start",
                        headers={"Authorization": f"Bearer {sup_token}"},
                        json={"profile_id": "p-upg", "profile_number": 42, "config_version": 1},
                    )
                    assert res1.status_code == 200, res1.text
                    disk_v1 = json.loads((runtime_dir / "snapshot.json").read_text(encoding="utf-8"))
                    assert disk_v1["version"] == 1
                    assert disk_v1["config"]["screen_width"] == 1280
                    assert disk_v1["config"]["mute_audio"] is False
                    for gone, _ in REMOVED_FIELD_CASES:
                        assert gone not in disk_v1["config"]

                    # Stop & unbind again -> bound_version remains N=1 while current_config_version is N+1=2
                    stop_api = await api_client.post("/api/v1/profiles/p-upg/stop")
                    assert stop_api.status_code == 200, stop_api.text
                    stop_sup = await sup_client.post(
                        "/supervisor/v1/profiles/stop",
                        headers={"Authorization": f"Bearer {sup_token}"},
                        json={
                            "profile_id": "p-upg",
                            "runtime_instance_id": res1.json()["runtime_instance_id"],
                            "operation_id": "stop-v1",
                        },
                    )
                    assert stop_sup.status_code == 200, stop_sup.text
                    stopped_rt = (await api_client.get("/api/v1/profiles/p-upg/runtime")).json()
                    assert stopped_rt["desired_state"] == "stopped"
                    assert stopped_rt["observed_state"] == "stopped"
                    assert stopped_rt["runtime_instance_id"] is None
                    assert stopped_rt["config_version"] == 1

                # 4. Real RuntimeCoordinator reconciles bound N=1 < current N+1=2 -> selects config_version=2
                start_intent_2 = await api_client.patch(
                    "/api/v1/profiles/p-upg/runtime/desired-state",
                    json={"desired_state": "running"},
                )
                assert start_intent_2.status_code == 200, start_intent_2.text
                outcome = await coordinator.reconcile_profile_now("p-upg")
                assert outcome is ReconcileOutcome.CONVERGED
                assert len(recorded_coordinator_starts) == 1
                assert recorded_coordinator_starts[0]["config_version"] == 2

                disk_v2 = json.loads((runtime_dir / "snapshot.json").read_text(encoding="utf-8"))
                assert disk_v2["version"] == 2
                assert disk_v2["config"]["screen_width"] == 1600
                assert disk_v2["config"]["mute_audio"] is True
                for gone, _ in REMOVED_FIELD_CASES:
                    assert gone not in disk_v2["config"]

                converged_rt = (await api_client.get("/api/v1/profiles/p-upg/runtime")).json()
                assert converged_rt["desired_state"] == "running"
                assert converged_rt["observed_state"] == "running"
                assert converged_rt["config_version"] == 2
            finally:
                await coordinator.stop()
