"""t104 Pass 3 unit tests: Supervisor extension mounts, Runner 4-state launch, and restore_point."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import scripts.restore_point as rp
from cbrowser.domain.models import ProfileConfig
from cbrowser.extensions.manifest import (
    EXTENSION_UNAVAILABLE,
    materialize_extension_directory,
    parse_extension_archive,
)
from cbrowser.runtime_agent.runner import BrowserRunner, ExtensionUnavailableError
from cbrowser.runtime_agent.stealth_launch import launch_stealth_persistent_context
from cbrowser.supervisor.core import ExtensionUnavailableError as SupExtUnavailableError
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.storage_layout import MountPlanner
from cbrowser.supervisor.volume_spec import extension_mount, stream_volumes
from tests.unit.test_t104_extensions_manifest import (
    _generate_rsa_pub_der,
    _make_crx3_bytes,
    _make_zip_bytes,
)


def _stage_managed_ext(data_root: Path, key_root: Path, *, key_name: str, ext_name: str, version: str = "1.0.0") -> tuple[str, str]:
    priv, pub_der, b64, cid = _generate_rsa_pub_der(key_root, key_name)
    zip_bytes = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": ext_name, "version": version, "key": b64}
            ).encode(),
            "bg.js": f"console.log('{ext_name}');\n".encode(),
        }
    )
    crx = _make_crx3_bytes(zip_bytes, pub_der=pub_der, priv_pem=priv)
    pkg = parse_extension_archive(crx, f"{ext_name}.crx")
    materialize_extension_directory(pkg, data_root / "extensions" / pkg.asset_id)
    return pkg.asset_id, cid


def _planner(tmp_path: Path) -> MountPlanner:
    return MountPlanner(
        resource_prefix="cbrowser-test",
        data_root=tmp_path / "data",
        socket_root=tmp_path / "sockets",
        fonts_root=tmp_path / "fonts",
    )


def test_extension_mount_ro_and_fail_closed(tmp_path: Path) -> None:
    asset_id, _ = _stage_managed_ext(tmp_path / "data", tmp_path, key_name="ext1", ext_name="Ext1")
    planner = _planner(tmp_path)
    assert planner.extensions_root == (tmp_path / "data" / "extensions").resolve()

    mount = extension_mount(planner=planner, asset_id=asset_id)
    assert mount["Type"] == "volume"
    assert mount["ReadOnly"] is True
    assert mount["Target"] == f"/run/cbrowser/extensions/{asset_id}"
    assert mount["VolumeOptions"]["Subpath"] == f"extensions/{asset_id}"

    # Tampered file on disk fails closed
    (tmp_path / "data" / "extensions" / asset_id / "bg.js").write_text("tampered", encoding="utf-8")
    with pytest.raises(PathSecurityError):
        extension_mount(planner=planner, asset_id=asset_id)

    # Missing extension fails closed
    with pytest.raises(PathSecurityError):
        extension_mount(planner=planner, asset_id="f" * 64)


def test_docker_adapter_mounts_only_when_allow_extensions_and_stream_isolated(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    data_root = tmp_path / "data"
    fonts_root = tmp_path / "fonts"
    sockets_root = tmp_path / "sockets"
    engine_cache = data_root / "engine-cache"
    geoip = engine_cache / "geoip"
    for d in (fonts_root / "windows" / ("a" * 64), sockets_root, geoip):
        d.mkdir(parents=True, exist_ok=True)
    asset_a, _ = _stage_managed_ext(data_root, tmp_path, key_name="da", ext_name="DA")

    validator = PathValidator(data_root, socket_root=sockets_root)
    old_fonts = __import__("os").environ.get("CBROWSER_FONTS_DIR")
    __import__("os").environ["CBROWSER_FONTS_DIR"] = str(fonts_root)
    try:
        adapter = DockerAdapter(
            path_validator=validator,
            engine_cache_dir=engine_cache,
            docker_client=MagicMock(),
            browser_image="sha256:" + "1" * 64,
            stream_image="sha256:" + "2" * 64,
            policy_image="sha256:" + "3" * 64,
            deployment_instance_id="test-inst",
        )
    finally:
        if old_fonts is None:
            __import__("os").environ.pop("CBROWSER_FONTS_DIR", None)
        else:
            __import__("os").environ["CBROWSER_FONTS_DIR"] = old_fonts

    container = MagicMock()
    container.id = "cid_1"
    adapter.client.containers.run = MagicMock(return_value=container)
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=data_root / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    from tests.unit.policy_agent_test_support import PolicyAgentTestRig

    rig = PolicyAgentTestRig()
    rig.install_on(adapter)
    rig.stub_ensure(adapter)

    dirs = adapter.prepare_profile_directories("prof1")
    adapter.remember_profile_number("prof1", 1)
    snap_path = dirs["runtime"] / "snapshot.json"

    import asyncio

    # 1. allow_extensions=False (even with stale extension_ids): zero extension mounts!
    snap_path.write_text(
        json.dumps(
            {
                "version": 1,
                "config": {
                    "fingerprint_platform": "windows",
                    "font_set_id": "a" * 64,
                    "allow_extensions": False,
                    "extension_ids": [asset_a],
                },
            }
        ),
        encoding="utf-8",
    )
    asyncio.run(
        adapter.start_browser_container(
            profile_id="prof1",
            runtime_instance_id="inst_off",
            snapshot_json_path=snap_path,
        )
    )
    off_targets = {m["Target"] for m in adapter.client.containers.run.call_args.kwargs["mounts"]}
    assert f"/run/cbrowser/extensions/{asset_a}" not in off_targets

    # 2. allow_extensions=True: extension mounted read-only at fixed container path
    snap_path.write_text(
        json.dumps(
            {
                "version": 1,
                "config": {
                    "fingerprint_platform": "windows",
                    "font_set_id": "a" * 64,
                    "allow_extensions": True,
                    "extension_ids": [asset_a],
                },
            }
        ),
        encoding="utf-8",
    )
    asyncio.run(
        adapter.start_browser_container(
            profile_id="prof1",
            runtime_instance_id="inst_on",
            snapshot_json_path=snap_path,
        )
    )
    ext_mounts = [
        m
        for m in adapter.client.containers.run.call_args.kwargs["mounts"]
        if m["Target"] == f"/run/cbrowser/extensions/{asset_a}"
    ]
    assert len(ext_mounts) == 1
    assert ext_mounts[0]["ReadOnly"] is True

    # 3. Stream container receives ZERO extension mounts
    s_vols = stream_volumes(
        planner=adapter.mount_planner,
        x11_socket=dirs["runtime"] / "x11" / "X99",
        xauth_file=dirs["runtime"] / "Xauthority",
        pulse_dir=dirs["runtime"] / "pulse",
        secret_file=dirs["runtime"] / "secret.txt",
        selkies_file=dirs["runtime"] / "selkies.json",
    )
    assert not any("/extensions" in m["Target"] for m in s_vols)


@pytest.mark.asyncio
async def test_supervisor_core_preflight_refuses_corrupt_bound_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "fonts"))
    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    asset_id, _ = _stage_managed_ext(root, tmp_path, key_name="sup", ext_name="SupExt")
    (root / "extensions" / asset_id / "bg.js").write_text("tampered", encoding="utf-8")

    monkeypatch.setattr("cbrowser.supervisor.core.font_sets.get_font_set", lambda _p, _s: (tmp_path / "fonts", {"platform": "windows"}))
    monkeypatch.setattr("cbrowser.supervisor.core.font_sets.check_font_set", lambda _d: {"ok": True})

    validator = PathValidator(root)
    dirs = {"runtime": root / "runtime" / "p1"}
    dirs["runtime"].mkdir(parents=True)
    adapter = SimpleNamespace(
        validator=validator,
        manage_ownership=False,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        start_browser_container=AsyncMock(),
        start_stream_container=AsyncMock(),
        teardown_profile=AsyncMock(),
        ensure_runtime_cache=AsyncMock(),
    )
    events = SimpleNamespace(
        drain_runtime_events=AsyncMock(return_value=0),
        forward_exit_event=AsyncMock(),
        emit_event=AsyncMock(),
    )
    key_file = tmp_path / "agent.key"
    key_file.write_text("k" * 32, encoding="utf-8")
    key_file.chmod(0o600)

    observed_payloads: list[dict] = []

    def _handler(request):
        if request.url.path.endswith("/state/snapshot"):
            return httpx.Response(
                200,
                json={
                    "api_epoch": "t104-epoch",
                    "profiles": [
                        {
                            "profile_id": "p1",
                            "display_number": 1,
                            "desired_state": "running",
                            "observed_state": "stopped",
                            "runtime_instance_id": None,
                            "config_version": 1,
                            "failure_count": 0,
                            "restart_blocked": False,
                            "last_exit_event_id": None,
                            "backoff_started_at": None,
                            "next_retry_at": None,
                            "updated_at": "2026-01-01T00:00:00+00:00",
                            "state_revision": 1,
                        }
                    ],
                    "next_cursor": None,
                },
            )
        if request.url.path.endswith("/runtimes/observed"):
            observed_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"status": "ok", "desired_state": "running", "restart_blocked": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler), base_url="http://api") as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=events,
            api_client=api,
            token_file=None,
            agent_key_file=key_file,
        )
        with pytest.raises(SupExtUnavailableError) as exc:
            await core.start_profile(
                "p1",
                ProfileConfig(
                    name="p1",
                    fingerprint_platform="windows",
                    font_set_id="a" * 64,
                    allow_extensions=True,
                    extension_ids=[asset_id],
                ),
            )
        assert str(exc.value) == EXTENSION_UNAVAILABLE
    assert len(observed_payloads) == 1
    assert observed_payloads[0]["observed_state"] == "error"
    assert observed_payloads[0]["reason"] == "extension_unavailable"
    adapter.start_browser_container.assert_not_awaited()


@pytest.mark.asyncio
async def test_stealth_launch_extension_flag_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class _FakePW:
        def __init__(self):
            self.chromium = SimpleNamespace(launch_persistent_context=self._launch)
            self.stopped = False

        async def _launch(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(pages=[], close=AsyncMock())

        async def stop(self):
            self.stopped = True

    monkeypatch.setattr("cbrowser.runtime_agent.stealth_launch.ensure_binary", lambda **_kw: str(tmp_path / "chrome"))
    monkeypatch.setattr("cbrowser.runtime_agent.stealth_launch.maybe_resolve_geoip", lambda _g, _p, tz, loc, _a: (tz, loc, None))
    monkeypatch.setattr("cbrowser.runtime_agent.stealth_launch.seed_widevine_hint", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: SimpleNamespace(start=AsyncMock(return_value=_FakePW())),
    )

    # 1. Off state: ignores only default stealth switches; does NOT strip --disable-extensions
    ctx_off = await launch_stealth_persistent_context(
        tmp_path / "p_off", headless=False, allow_extensions=False, extension_paths=["/should/ignore"]
    )
    await ctx_off.close()
    assert "--disable-extensions" not in calls[-1]["ignore_default_args"]
    assert not any(a.startswith("--load-extension") for a in calls[-1]["args"])

    # 2. Free mode: allow_extensions=True, empty paths -> strips --disable-extensions, zero load paths
    ctx_free = await launch_stealth_persistent_context(
        tmp_path / "p_free", headless=False, allow_extensions=True, extension_paths=None
    )
    await ctx_free.close()
    assert "--disable-extensions" in calls[-1]["ignore_default_args"]
    assert "--disable-component-extensions-with-background-pages" in calls[-1]["ignore_default_args"]
    assert not any(a.startswith("--load-extension") for a in calls[-1]["args"])

    # 3. Managed mode: strips --disable-extensions and sets --load-extension & --disable-extensions-except
    p1, p2 = str(tmp_path / "e1"), str(tmp_path / "e2")
    ctx_managed = await launch_stealth_persistent_context(
        tmp_path / "p_managed", headless=False, allow_extensions=True, extension_paths=[p1, p2]
    )
    await ctx_managed.close()
    assert "--disable-extensions" in calls[-1]["ignore_default_args"]
    assert f"--load-extension={p1},{p2}" in calls[-1]["args"]
    assert f"--disable-extensions-except={p1},{p2}" in calls[-1]["args"]


@pytest.mark.asyncio
async def test_runner_resolves_and_verifies_extensions_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset_id, _ = _stage_managed_ext(tmp_path / "mnt_src", tmp_path, key_name="run", ext_name="RunExt")
    ext_mount_root = tmp_path / "mnt_src" / "extensions"
    launched: list[dict] = []

    async def fake_launch(user_data_dir, **kwargs):
        launched.append({"user_data_dir": user_data_dir, **kwargs})
        pid_file = Path(user_data_dir).parent / "run" / "chrome.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("99999", encoding="utf-8")
        return SimpleNamespace(pages=[], new_page=AsyncMock())

    monkeypatch.setattr("cbrowser.runtime_agent.runner.launch_stealth_persistent_context", fake_launch)
    monkeypatch.setattr("cbrowser.runtime_agent.runner.seed_widevine_hint", lambda *_a, **_kw: None)
    monkeypatch.setattr("cbrowser.runtime_agent.runner.profile_font_dirs", lambda *_a, **_kw: [tmp_path / "f"])
    monkeypatch.setattr("cbrowser.runtime_agent.runner.prepare_profile_fontconfig", lambda *_a, **_kw: tmp_path / "fonts.conf")
    monkeypatch.setattr("cbrowser.runtime_agent.runner.verify_mounted_font_set", lambda **_kw: {"status": "verified"})

    async def _run_case(name: str, allow: bool, ext_ids: list[str]) -> BrowserRunner:
        run_root = tmp_path / name
        (run_root / "fonts").mkdir(parents=True, exist_ok=True)
        snap = run_root / "snapshot.json"
        snap.write_text(
            json.dumps(
                {
                    "id": name,
                    "profile_id": "prof1",
                    "version": 1,
                    "config": {
                        "name": name,
                        "fingerprint_platform": "windows",
                        "font_set_id": "a" * 64,
                        "geoip": False,
                        "allow_extensions": allow,
                        "extension_ids": ext_ids,
                    },
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        r = BrowserRunner(
            "prof1",
            f"inst_{name}",
            snap,
            run_root / "run",
            run_root / "profile",
            events_dir=run_root / "events",
            engine_cache_dir=run_root / "engine",
            extension_mount_root=ext_mount_root,
        )
        chrome_bin = run_root / "engine" / "chrome"
        chrome_bin.parent.mkdir(parents=True, exist_ok=True)
        chrome_bin.write_text("", encoding="utf-8")
        monkeypatch.setattr(r, "resolve_engine_binary", lambda cb=chrome_bin: cb)
        monkeypatch.setattr(r, "setup_pulse", lambda rr=run_root: (rr / "pulse.sock", rr / "pulse.cookie"))
        monkeypatch.setattr(r, "setup_display", lambda *_a, **_kw: None)
        (run_root / "run").mkdir(parents=True, exist_ok=True)
        (run_root / "run" / "chrome.pid").write_text("99999", encoding="utf-8")
        (run_root / "profile").mkdir(parents=True, exist_ok=True)
        (run_root / "profile" / "DevToolsActivePort").write_text("9222\n/devtools/browser/x\n", encoding="utf-8")
        monkeypatch.setattr(r, "_resolve_browser_version", AsyncMock(return_value=("Chrome/146", "UA")))
        monkeypatch.setattr(r, "_apply_native_color_scheme", lambda *_a, **_kw: None)
        monkeypatch.setattr(r, "_configure_window", AsyncMock())

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *_e):
                return False

            def read(self) -> bytes:
                return b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/x"}'

        monkeypatch.setattr(
            "cbrowser.runtime_agent.runner.urllib.request.urlopen",
            lambda *_a, **_kw: _FakeResp(),
        )
        monkeypatch.setattr("cbrowser.runtime_agent.runner.CdpGuard", lambda _p: SimpleNamespace(start=AsyncMock(return_value=19222)))
        monkeypatch.setattr("cbrowser.runtime_agent.runner.run_search_defaults_initialization", AsyncMock(return_value="disabled"))
        monkeypatch.setattr("cbrowser.runtime_agent.runner.asyncio.create_task", lambda c: (c.close() or None) if hasattr(c, "close") else None)
        await r.start()
        return r

    await _run_case("off_with_ids", False, [asset_id])
    assert launched[-1]["allow_extensions"] is False
    assert launched[-1]["extension_paths"] is None

    await _run_case("free_mode", True, [])
    assert launched[-1]["allow_extensions"] is True
    assert launched[-1]["extension_paths"] is None

    await _run_case("managed_mode", True, [asset_id])
    assert launched[-1]["allow_extensions"] is True
    assert launched[-1]["extension_paths"] == [str(ext_mount_root / asset_id)]

    # Tampered mounted directory fails closed before Chrome launch
    (ext_mount_root / asset_id / "bg.js").write_text("tamper", encoding="utf-8")
    before_len = len(launched)
    with pytest.raises(ExtensionUnavailableError):
        await _run_case("tampered", True, [asset_id])
    assert len(launched) == before_len


def test_restore_point_backs_up_verifies_and_restores_extensions(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    db_path = tmp_path / "db" / "cbrowser.db"
    db_path.parent.mkdir(parents=True)
    asset_id, _ = _stage_managed_ext(data_root, tmp_path, key_name="rp", ext_name="RPExt")
    # Leftover staging dirs or non-managed directories under extensions/ must be skipped by create_point.
    staging_leftover = data_root / "extensions" / ".staging-abandoned-999"
    staging_leftover.mkdir(parents=True)
    (staging_leftover / "junk.txt").write_text("stale", encoding="utf-8")
    non_asset_dir = data_root / "extensions" / "not_a_64hex_id"
    non_asset_dir.mkdir(parents=True)
    (non_asset_dir / "note.txt").write_text("skip", encoding="utf-8")
    prof_dir = data_root / "profiles" / "p1" / "profile"
    prof_dir.mkdir(parents=True)
    (prof_dir / "Preferences").write_text('{"x":1}', encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version VALUES ('b2c3d4e5f601')")
        conn.execute(
            "CREATE TABLE profiles (id TEXT PRIMARY KEY, user_data_dir TEXT, current_config_version INTEGER)"
        )
        conn.execute(
            "INSERT INTO profiles VALUES ('p1', ?, 1)",
            (str(prof_dir),),
        )
        conn.execute(
            "CREATE TABLE profile_runtimes (profile_id TEXT PRIMARY KEY, desired_state TEXT, observed_state TEXT, runtime_instance_id TEXT, config_version INTEGER)"
        )
        conn.execute("INSERT INTO profile_runtimes VALUES ('p1', 'stopped', 'stopped', NULL, 1)")
        conn.commit()
    finally:
        conn.close()

    point_dir = tmp_path / "backup_point"
    rp.create_point(
        SimpleNamespace(
            db=str(db_path),
            data_root=str(data_root),
            out=str(point_dir),
            secrets_dir=None,
            label="t104",
        )
    )
    manifest = rp.validate_point(point_dir)
    assert [e["id"] for e in manifest["extensions"]] == [asset_id]

    # Mutate live extensions (delete original + add unrelated extra dir)
    (data_root / "extensions" / asset_id / "bg.js").unlink()
    extra_dir = data_root / "extensions" / ("b" * 64)
    extra_dir.mkdir(parents=True)
    (extra_dir / "manifest.json").write_text("{}", encoding="utf-8")

    # Restore recovers original managed extension and removes uncaptured extra dir
    assert (
        rp.restore_point(
            SimpleNamespace(
                point=str(point_dir),
                db=str(db_path),
                data_root=str(data_root),
                journal=None,
            )
        )
        == 0
    )
    assert (data_root / "extensions" / asset_id / "bg.js").is_file()
    assert not extra_dir.exists()


def test_cleanup_browser_stops_gracefully_before_force_remove(tmp_path: Path) -> None:
    events: list[str] = []
    browser = SimpleNamespace(
        name="cbrowser-0005-browser",
        status="running",
        labels={
            "com.cbrowser.prefix": "cbrowser",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "browser",
            "com.cbrowser.profile-id": "p1",
            "com.cbrowser.profile-number": "0005",
        },
        stop=lambda timeout=8: events.append(f"stop:{timeout}"),
        remove=lambda force=False: events.append(f"remove:{force}"),
    )
    client = SimpleNamespace(containers=SimpleNamespace(get=lambda _name: browser))
    (tmp_path / "data" / "engine" / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        path_validator=PathValidator(tmp_path / "data"),
        engine_cache_dir=tmp_path / "data" / "engine",
        docker_client=client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        resource_prefix="cbrowser",
    )
    adapter.cleanup_container_by_name("cbrowser-0005-browser")
    assert events == ["stop:8", "remove:True"]
