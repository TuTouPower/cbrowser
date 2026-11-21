"""t098: HTTP contract for the collection runtime projection.

- GET /profiles/collection rows carry the runtime projection.
- GET /profiles/runtime-summary is gone (404): row state no longer
  comes from an all-profiles summary.
- GET /profiles/runtime-alerts is the compact coordinator-error read
  model (only errored profiles), and the collection row itself
  carries the same error for its page.
- GET /proxies/{id}/used-by entries carry the target's observed
  state with the reference data.
- The single-runtime response and the collection projection share
  the same state_revision fence value for the same write.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import ProfileRuntimeModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileConfig
from fastapi.testclient import TestClient

ORIGIN = "https://127.0.0.1:56661"


class _StubCoordinator:
    """Minimal coordinator surface the router/service read."""

    def __init__(self) -> None:
        self.errors: dict[str, str] = {}

    def last_error_profile_ids(self) -> list[str]:
        return sorted(self.errors)

    def get_last_error(self, profile_id, runtime=None):
        return self.errors.get(profile_id)


@pytest.fixture
def api_env(tmp_path: Path):
    db_file = tmp_path / "t098_api.db"
    run_database_migrations(db_file)
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")
    app = create_app(db_path=db_file, admin_password_file=admin_pwd_file)

    async def _seed() -> dict:
        engine, session_maker = create_engine_and_maker(db_file)
        repo = ProfileRepository(session_maker)
        proxy = await repo.create_proxy(
            {
                "name": "px-t098",
                "scheme": "http",
                "host": "t098.example.com",
                "port": 8080,
                "username": "user",
                "password": "s3cret-pw",
            }
        )
        p_run = await repo.create_profile(
            ProfileConfig(name="env-run", proxy_id=proxy.id)
        )
        await repo.bind_runtime_instance(
            p_run.id, "inst-run", config_version=1
        )
        async with session_maker() as session:
            row = await session.get(ProfileRuntimeModel, p_run.id)
            row.observed_state = "running"
            await session.commit()
        p_idle = await repo.create_profile(
            ProfileConfig(name="env-idle", proxy_id=proxy.id)
        )
        await engine.dispose()
        return {"proxy": proxy.id, "p_run": p_run.id, "p_idle": p_idle.id}

    seeded = asyncio.run(_seed())
    with TestClient(app, base_url=ORIGIN) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": admin_pwd}
        )
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ORIGIN,
        }
        yield {
            "app": app,
            "client": client,
            "headers": headers,
            **seeded,
        }


def _collection_by_id(api_env):
    resp = api_env["client"].get(
        "/api/v1/profiles/collection", headers=api_env["headers"]
    )
    assert resp.status_code == 200
    return {item["id"]: item for item in resp.json()["items"]}


def test_collection_rows_carry_runtime_projection(api_env):
    by_id = _collection_by_id(api_env)
    run_rt = by_id[api_env["p_run"]]["runtime"]
    assert run_rt["observed_state"] == "running"
    assert run_rt["runtime_instance_id"] == "inst-run"
    assert run_rt["config_version"] == 1
    assert run_rt["state_revision"] >= 1
    idle_rt = by_id[api_env["p_idle"]]["runtime"]
    assert idle_rt["observed_state"] == "stopped"


def test_runtime_summary_endpoint_removed(api_env):
    resp = api_env["client"].get(
        "/api/v1/profiles/runtime-summary", headers=api_env["headers"]
    )
    assert resp.status_code == 404


def test_runtime_alerts_and_row_error(api_env):
    stub = _StubCoordinator()
    stub.errors[api_env["p_idle"]] = "coordinator exploded"
    api_env["app"].state.coordinator = stub

    resp = api_env["client"].get(
        "/api/v1/profiles/runtime-alerts", headers=api_env["headers"]
    )
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert entries == [
        {
            "profile_id": api_env["p_idle"],
            "last_coordinator_error": "coordinator exploded",
        }
    ]

    by_id = _collection_by_id(api_env)
    assert (
        by_id[api_env["p_idle"]]["runtime"]["last_coordinator_error"]
        == "coordinator exploded"
    )
    assert (
        by_id[api_env["p_run"]]["runtime"]["last_coordinator_error"]
        is None
    )

    stub.errors.clear()
    resp = api_env["client"].get(
        "/api/v1/profiles/runtime-alerts", headers=api_env["headers"]
    )
    assert resp.json()["entries"] == []


def test_used_by_entries_carry_observed_state(api_env):
    resp = api_env["client"].get(
        f"/api/v1/proxies/{api_env['proxy']}/used-by",
        headers=api_env["headers"],
    )
    assert resp.status_code == 200
    by_id = {e["profile_id"]: e for e in resp.json()["entries"]}
    assert by_id[api_env["p_run"]]["observed_state"] == "running"
    assert by_id[api_env["p_idle"]]["observed_state"] == "stopped"


def test_single_runtime_and_projection_share_revision(api_env):
    resp = api_env["client"].get(
        f"/api/v1/profiles/{api_env['p_run']}/runtime",
        headers=api_env["headers"],
    )
    assert resp.status_code == 200
    single_revision = resp.json()["state_revision"]
    by_id = _collection_by_id(api_env)
    assert (
        by_id[api_env["p_run"]]["runtime"]["state_revision"]
        == single_revision
    )
