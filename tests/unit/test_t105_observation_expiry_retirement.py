"""t105 AC-005: migration 0018 retires the observation expiry column."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.script import ScriptDirectory

from cbrowser.adapters.database.migrations import get_alembic_config

REVISION_0017 = "e10400170001"
REVISION_HEAD = "b2c3d4e5f601"


def test_migration_0018_drops_expires_at_and_keeps_history(tmp_path: Path) -> None:
    db = tmp_path / "observation_expiry.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0017)

    conn = sqlite3.connect(db)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(proxy_egress_observations)")
        }
        assert "expires_at" in columns
        conn.execute(
            "INSERT INTO proxy_egress_observations ("
            "id, proxy_id, endpoint_fingerprint, credential_revision, perspective,"
            " egress_ip, country_code, country_name, city, latency_ms, source,"
            " status, error_code, observed_at, expires_at, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "obs-1",
                "proxy-1",
                "fp",
                1,
                "browser",
                "203.0.113.7",
                "JP",
                "Japan",
                "Tokyo",
                619,
                "local_geoip",
                "ok",
                None,
                "2026-11-20T15:31:57+00:00",
                "2026-11-21T15:31:57+00:00",
                "2026-11-20T15:31:57+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(get_alembic_config(db), "head")

    assert ScriptDirectory.from_config(get_alembic_config(db)).get_heads() == [
        REVISION_HEAD
    ]
    conn = sqlite3.connect(db)
    try:
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == REVISION_HEAD
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(proxy_egress_observations)")
        }
        assert "expires_at" not in columns
        rows = conn.execute(
            "SELECT id, latency_ms, country_code, city FROM proxy_egress_observations"
        ).fetchall()
        assert rows == [("obs-1", 619, "JP", "Tokyo")]
    finally:
        conn.close()
