"""t103 AC-002 / AC-004: inventory, equivalence mapping, fail-before-write, and DDL/DML rollback."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)

REVISION_BEFORE = "f1a2b3c4d5e6"
REVISION_HEAD = "a10300160001"
WIN_SET = "a" * 64

PLAYWRIGHT_DEFAULTS_AND_TRANSLATE = [
    "--disable-background-networking",
    "--disable-backgrounding-occluded-windows",
    "--disable-client-side-phishing-detection",
    "--disable-component-extensions-with-background-pages",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--metrics-recording-only",
    "--no-default-browser-check",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-translate",
]

REMOVED_PROFILE_KEYS = (
    "humanize",
    "human_preset",
    "auto_launch",
    "allow_3p_cookies",
    "transparent_proxy",
    "portable_cookies",
    "launch_args",
)


def _seed_pre_0016_db(db: Path) -> None:
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_BEFORE)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO font_set_assets (platform, set_id, source, source_version,"
            " file_count, total_bytes, integrity, state, revision, state_seq,"
            " verified_at, audited_at, created_at, updated_at)"
            " VALUES ('windows', ?, 'fixture', 'v1', 1, 100, '{}', 'verified', 1, 1,"
            " '2026-01-01T00:00:00+00:00', NULL, '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00')",
            (WIN_SET,),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    display_number: int,
    *,
    locale: str | None = "en-US",
    geoip: bool = True,
    launch_args: list[str] | str | None = None,
    extension_paths: list[str] | None = None,
    current_config_version: int = 1,
    humanize: bool = True,
    human_preset: str = "careful",
    auto_launch: bool = True,
    allow_3p_cookies: bool = False,
    transparent_proxy: bool = True,
    portable_cookies: bool = False,
    bound_version: int = 1,
    runtime_instance_id: str | None = None,
    desired_state: str = "stopped",
) -> None:
    raw_la = (
        launch_args
        if isinstance(launch_args, str)
        else json.dumps(launch_args if launch_args is not None else [])
    )
    raw_ep = json.dumps(extension_paths if extension_paths is not None else [])
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO profiles ("
        "id, display_number, name, fingerprint_seed, group_id, proxy_id,"
        " timezone, locale, screen_width, screen_height, humanize, human_preset,"
        " geoip, clipboard_sync, auto_launch, color_scheme, fingerprint_platform,"
        " font_set_id, include_cjk_fonts, launch_args, extension_paths,"
        " allow_3p_cookies, set_google_default, capture_preview, restore_session,"
        " transparent_proxy, portable_cookies, notes, user_data_dir, sort_order,"
        " current_config_version, created_at, updated_at"
        ") VALUES (?,?,?,?,NULL,NULL,NULL,?,1920,1080,?,?,?,?,?,'light','windows',?,1,?,?,?,1,1,1,?,?,NULL,?,0,?,?,?)",
        (
            profile_id,
            display_number,
            f"Prof-{profile_id}",
            100000 + display_number,
            locale,
            int(humanize),
            human_preset,
            int(geoip),
            1,
            int(auto_launch),
            WIN_SET,
            raw_la,
            raw_ep,
            int(allow_3p_cookies),
            int(transparent_proxy),
            int(portable_cookies),
            f"/data/profiles/{profile_id}/profile",
            current_config_version,
            now,
            now,
        ),
    )
    conn.execute(
        "INSERT INTO profile_runtimes ("
        "profile_id, desired_state, observed_state, runtime_instance_id,"
        " config_version, failure_count, restart_blocked, updated_at, state_revision"
        ") VALUES (?, ?, ?, ?, ?, 0, 0, ?, 4)",
        (
            profile_id,
            desired_state,
            "running" if runtime_instance_id else "stopped",
            runtime_instance_id,
            bound_version,
            now,
        ),
    )


def _insert_version(
    conn: sqlite3.Connection,
    row_id: str,
    profile_id: str,
    version: int,
    *,
    wrapped: bool = True,
    proxy_cred_rev: int | None = None,
    locale: str | None = "en-US",
    geoip: bool = True,
    launch_args: list[str] | None = None,
    extension_paths: list[str] | None = None,
    raw_override: str | None = None,
) -> None:
    cfg: dict[str, Any] = {
        "name": f"Prof-{profile_id}-v{version}",
        "fingerprint_seed": 100000 + version,
        "group_id": None,
        "proxy_id": None,
        "timezone": None,
        "locale": locale,
        "screen_width": 1920,
        "screen_height": 1080,
        "humanize": True,
        "human_preset": "careful",
        "geoip": geoip,
        "clipboard_sync": True,
        "auto_launch": True,
        "color_scheme": "light",
        "fingerprint_platform": "windows",
        "font_set_id": WIN_SET,
        "include_cjk_fonts": locale == "zh-CN",
        "launch_args": launch_args if launch_args is not None else [],
        "extension_paths": extension_paths if extension_paths is not None else [],
        "allow_3p_cookies": False,
        "set_google_default": True,
        "capture_preview": True,
        "restore_session": True,
        "transparent_proxy": True,
        "portable_cookies": False,
        "notes": f"v{version}",
        "sort_order": 0,
    }
    payload: Any = (
        {"config": cfg, "proxy_credential_revision": proxy_cred_rev}
        if wrapped
        else cfg
    )
    raw = raw_override if raw_override is not None else json.dumps(payload)
    conn.execute(
        "INSERT INTO profile_config_versions (id, profile_id, version, snapshot, created_at)"
        " VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (row_id, profile_id, version, raw),
    )


def _db_fingerprint(
    db: Path,
) -> tuple[list[str], list[tuple], list[tuple], list[tuple], str]:
    conn = sqlite3.connect(db)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        cols = conn.execute("PRAGMA table_info(profiles)").fetchall()
        profiles = conn.execute("SELECT * FROM profiles ORDER BY id").fetchall()
        versions = conn.execute(
            "SELECT * FROM profile_config_versions ORDER BY id"
        ).fetchall()
        stamp = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        return tables, cols, profiles, versions, stamp
    finally:
        conn.close()


def test_0016_is_single_head(tmp_path: Path) -> None:
    cfg = get_alembic_config(tmp_path / "head.db")
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == [REVISION_HEAD]


def test_readonly_inventory_classifies_all_dispositions_and_language_matrix(
    tmp_path: Path,
) -> None:
    from cbrowser.adapters.database.launch_args_migration import (
        audit_launch_args_database,
    )

    db = tmp_path / "inventory.db"
    _seed_pre_0016_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_profile(
            conn,
            "p-redundant",
            1,
            locale="en-US",
            geoip=True,
            launch_args=[
                *PLAYWRIGHT_DEFAULTS_AND_TRANSLATE,
                "--disable-blink-features=AutomationControlled",
            ],
            extension_paths=["/ext/keep-unchanged"],
        )
        _insert_version(
            conn,
            "v-redundant",
            "p-redundant",
            1,
            wrapped=True,
            proxy_cred_rev=5,
            locale="en-US",
            geoip=True,
            launch_args=[
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",
                "--lang=zh-CN",
                "--accept-lang=fr-FR,fr",
            ],
            extension_paths=["/ext/keep-unchanged"],
        )
        _insert_profile(
            conn,
            "p-geoip-first",
            2,
            locale=None,
            geoip=True,
            launch_args=["--lang=zh-CN", "--lang=en-US", "--mute-audio"],
        )
        _insert_version(
            conn,
            "v-nogeoip-last",
            "p-geoip-first",
            1,
            wrapped=False,
            locale=None,
            geoip=False,
            launch_args=["--lang=en-US", "--lang=zh-CN"],
        )
        _insert_version(
            conn,
            "v-accept-dup",
            "p-geoip-first",
            2,
            wrapped=True,
            proxy_cred_rev=9,
            locale=None,
            geoip=False,
            launch_args=[
                "--accept-lang=en-US,en",
                "--accept-lang=zh-CN,zh",
            ],
        )
        _insert_profile(
            conn,
            "p-geoip-accept-only",
            3,
            locale=None,
            geoip=True,
            launch_args=["--accept-lang=en-US,en", "--accept-lang=zh-CN,zh"],
        )
        conn.commit()

        inv = audit_launch_args_database(conn)
        assert not inv.blocking_errors
        assert len(inv.profiles) == 3
        assert len(inv.snapshots) == 3

        prof_geo_acc = inv.profile_by_id["p-geoip-accept-only"]
        assert prof_geo_acc.resolved_locale == "zh-CN"
        assert any(
            d.arg == "--accept-lang=zh-CN,zh"
            and d.category == "等价映射"
            and d.action == "promote_accept_lang_to_locale"
            for d in prof_geo_acc.dispositions
        )

        prof_red = inv.profile_by_id["p-redundant"]
        assert prof_red.resolved_mute_audio is False
        assert prof_red.resolved_locale == "en-US"
        assert {d.category for d in prof_red.dispositions} == {"冗余"}
        assert any(
            d.arg == "--disable-blink-features=AutomationControlled"
            and d.category == "冗余"
            for d in prof_red.dispositions
        )

        snap_red = inv.snapshot_by_id["v-redundant"]
        assert snap_red.resolved_mute_audio is True
        assert snap_red.resolved_locale == "en-US"
        assert any(
            d.arg == "--mute-audio" and d.category == "等价映射"
            for d in snap_red.dispositions
        )
        assert any(
            d.arg == "--lang=zh-CN" and d.category == "等价映射"
            for d in snap_red.dispositions
        )

        prof_geo = inv.profile_by_id["p-geoip-first"]
        assert prof_geo.resolved_locale == "zh-CN"
        assert prof_geo.resolved_mute_audio is True

        snap_last = inv.snapshot_by_id["v-nogeoip-last"]
        assert snap_last.resolved_locale == "zh-CN"
        assert snap_last.resolved_mute_audio is False

        snap_acc = inv.snapshot_by_id["v-accept-dup"]
        assert snap_acc.resolved_locale == "zh-CN"
    finally:
        conn.close()


def test_readonly_inventory_marks_need_adjudication_on_conflicts_and_unknowns(
    tmp_path: Path,
) -> None:
    from cbrowser.adapters.database.launch_args_migration import (
        audit_launch_args_database,
    )

    db = tmp_path / "inventory_block.db"
    _seed_pre_0016_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_profile(
            conn,
            "p-conflict",
            1,
            locale=None,
            geoip=False,
            launch_args=["--lang=zh-CN", "--accept-lang=en-US,en"],
        )
        _insert_profile(
            conn,
            "p-geoip-conflict",
            2,
            locale=None,
            geoip=True,
            launch_args=["--lang=zh-CN", "--accept-lang=en-US,en"],
        )
        _insert_version(
            conn,
            "v-unknown-flat",
            "p-conflict",
            1,
            wrapped=False,
            locale="en-US",
            geoip=True,
            launch_args=["--load-extension=/tmp/evil"],
        )
        conn.commit()

        inv = audit_launch_args_database(conn)
        assert len(inv.blocking_errors) == 3

        prof_conf = inv.profile_by_id["p-conflict"]
        assert prof_conf.resolved_locale is None
        assert len(prof_conf.dispositions) == 2
        assert all(d.category == "需裁决" for d in prof_conf.dispositions)
        assert all(d.action == "block_migration" for d in prof_conf.dispositions)

        prof_geo_conf = inv.profile_by_id["p-geoip-conflict"]
        assert prof_geo_conf.resolved_locale is None
        assert all(d.category == "需裁决" for d in prof_geo_conf.dispositions)

        snap_unk = inv.snapshot_by_id["v-unknown-flat"]
        assert any(
            d.arg == "--load-extension=/tmp/evil"
            and d.category == "需裁决"
            and d.action == "block_migration"
            for d in snap_unk.dispositions
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "case_name,locale,geoip,launch_args,raw_snap,wrapped",
    [
        ("geoip_first_out_of_enum", None, True, ["--lang=ja-JP", "--lang=en-US"], None, True),
        ("nogeoip_last_out_of_enum", None, False, ["--lang=en-US", "--lang=ja-JP"], None, True),
        ("nogeoip_multilang_accept", None, False, ["--accept-lang=en-US,zh-CN"], None, True),
        ("nogeoip_out_enum_accept", None, False, ["--accept-lang=fr-FR,fr"], None, True),
        ("geoip_out_enum_accept_no_lang", None, True, ["--accept-lang=ja-JP,ja"], None, True),
        ("nogeoip_lang_accept_conflict", None, False, ["--lang=zh-CN", "--accept-lang=en-US,en"], None, True),
        ("geoip_lang_accept_conflict", None, True, ["--lang=zh-CN", "--accept-lang=en-US,en"], None, True),
        ("unknown_flag_wrapped", "en-US", True, ["--load-extension=/tmp/evil"], None, True),
        ("unknown_flag_flat", "en-US", True, ["--load-extension=/tmp/evil"], None, False),
        ("corrupt_snapshot_json_wrapped", "en-US", True, [], "{not-json", True),
        ("corrupt_snapshot_json_flat", "en-US", True, [], '"not-an-object"', False),
    ],
)
def test_unresolved_or_corrupt_entries_block_with_zero_writes(
    tmp_path: Path,
    case_name: str,
    locale: str | None,
    geoip: bool,
    launch_args: list[str],
    raw_snap: str | None,
    wrapped: bool,
) -> None:
    db = tmp_path / f"{case_name}.db"
    _seed_pre_0016_db(db)
    conn = sqlite3.connect(db)
    try:
        # Put one unresolved case in current row if not snapshot corrupt, AND also test snapshot
        row_args = launch_args if raw_snap is None and "snapshot" not in case_name else []
        _insert_profile(
            conn,
            "p-block",
            1,
            locale=locale if row_args else "en-US",
            geoip=geoip,
            launch_args=row_args,
        )
        _insert_version(
            conn,
            "v-block",
            "p-block",
            1,
            wrapped=wrapped,
            proxy_cred_rev=2,
            locale=locale,
            geoip=geoip,
            launch_args=launch_args,
            raw_override=raw_snap,
        )
        conn.commit()
    finally:
        conn.close()

    before = _db_fingerprint(db)
    with pytest.raises(RuntimeError, match="p-block"):
        command.upgrade(get_alembic_config(db), "head")
    after = _db_fingerprint(db)
    assert after == before


@pytest.mark.parametrize("phase", ["mid_ddl", "mid_dml"])
def test_mid_migration_fault_rolls_back_schema_rows_snapshots_and_stamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    from cbrowser.adapters.database import launch_args_migration

    db = tmp_path / f"fault-{phase}.db"
    _seed_pre_0016_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_profile(
            conn,
            "p-atomic",
            1,
            locale="en-US",
            geoip=True,
            launch_args=["--mute-audio", "--disable-sync"],
            extension_paths=["/ext/dir1"],
        )
        _insert_version(
            conn,
            "v-atomic",
            "p-atomic",
            1,
            wrapped=True,
            proxy_cred_rev=3,
            locale="en-US",
            geoip=True,
            launch_args=["--mute-audio", "--no-first-run"],
            extension_paths=["/ext/dir1"],
        )
        conn.commit()
    finally:
        conn.close()

    before = _db_fingerprint(db)

    if phase == "mid_ddl":
        orig_apply = launch_args_migration.apply_launch_args_profile_updates

        def fail_after_ddl(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("injected mid-DDL fault")

        assert orig_apply is not None
        monkeypatch.setattr(
            launch_args_migration, "apply_launch_args_profile_updates", fail_after_ddl
        )
    else:
        orig_rewrite = launch_args_migration.rewrite_profile_snapshots_for_launch_args

        def fail_mid_dml(*args: Any, **kwargs: Any) -> None:
            orig_rewrite(*args, **kwargs)
            raise RuntimeError("injected mid-DML fault")

        monkeypatch.setattr(
            launch_args_migration,
            "rewrite_profile_snapshots_for_launch_args",
            fail_mid_dml,
        )

    with pytest.raises(RuntimeError, match="injected mid-"):
        command.upgrade(get_alembic_config(db), "head")

    after = _db_fingerprint(db)
    assert after == before
    assert not any(t.startswith("_alembic_tmp_") for t in after[0])

    # Retry after fault clears must succeed cleanly without _alembic_tmp_profiles collision
    monkeypatch.undo()
    run_database_migrations(db)
    tables, cols, _, _, stamp = _db_fingerprint(db)
    assert stamp == REVISION_HEAD
    assert not any(t.startswith("_alembic_tmp_") for t in tables)
    assert "mute_audio" in {c[1] for c in cols}


def test_async_sqlite_migration_atomicity_and_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cbrowser.adapters.database import launch_args_migration

    db = tmp_path / "async_fault.db"
    _seed_pre_0016_db(db)
    conn = sqlite3.connect(db)
    try:
        _insert_profile(
            conn,
            "p-async",
            1,
            locale="en-US",
            geoip=True,
            launch_args=["--mute-audio"],
        )
        conn.commit()
    finally:
        conn.close()

    before = _db_fingerprint(db)

    def fail_mid(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("async injected mid-DDL fault")

    monkeypatch.setattr(launch_args_migration, "apply_launch_args_profile_updates", fail_mid)
    cfg = get_alembic_config(db)
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db.resolve()}")
    with pytest.raises(RuntimeError, match="async injected mid-DDL fault"):
        command.upgrade(cfg, "head")

    after = _db_fingerprint(db)
    assert after == before
    assert not any(t.startswith("_alembic_tmp_") for t in after[0])

    monkeypatch.undo()
    command.upgrade(cfg, "head")
    tables, cols, _, _, stamp = _db_fingerprint(db)
    assert stamp == REVISION_HEAD
    assert not any(t.startswith("_alembic_tmp_") for t in tables)
    assert "mute_audio" in {c[1] for c in cols}


def test_migration_preserves_state_is_idempotent_and_supports_backup_restore_drill(
    tmp_path: Path,
) -> None:
    from cbrowser.adapters.database.launch_args_migration import (
        transform_migrated_config_dict,
    )
    from cbrowser.domain.models import ProfileConfig

    db = tmp_path / "full-upgrade.db"
    _seed_pre_0016_db(db)
    user_data = tmp_path / "user-data-keep"
    user_data.mkdir()
    cookies = user_data / "Cookies"
    cookies.write_bytes(b"cookie-bytes-intact")

    conn = sqlite3.connect(db)
    try:
        _insert_profile(
            conn,
            "p-running",
            10,
            locale=None,
            geoip=True,
            launch_args=["--mute-audio", "--lang=zh-CN", "--no-first-run"],
            extension_paths=["/ext/alpha", "/ext/beta"],
            current_config_version=2,
            bound_version=1,
            runtime_instance_id="inst_live_1",
            desired_state="running",
        )
        conn.execute(
            "UPDATE profiles SET user_data_dir = ? WHERE id = 'p-running'",
            (str(user_data),),
        )
        _insert_version(
            conn,
            "v1-wrap",
            "p-running",
            1,
            wrapped=True,
            proxy_cred_rev=11,
            locale="en-US",
            geoip=True,
            launch_args=[],
            extension_paths=["/ext/alpha"],
        )
        _insert_version(
            conn,
            "v2-flat",
            "p-running",
            2,
            wrapped=False,
            locale=None,
            geoip=False,
            launch_args=["--mute-audio", "--accept-lang=zh-CN,zh", "--disable-translate"],
            extension_paths=["/ext/alpha", "/ext/beta"],
        )
        conn.commit()
    finally:
        conn.close()

    pre_backup = tmp_path / "pre_0016_backup.db"
    shutil.copyfile(db, pre_backup)

    run_database_migrations(db)
    assert cookies.read_bytes() == b"cookie-bytes-intact"

    conn = sqlite3.connect(db)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        for gone in REMOVED_PROFILE_KEYS:
            assert gone not in cols
        assert "mute_audio" in cols
        assert "extension_paths" in cols

        row = conn.execute(
            "SELECT locale, mute_audio, extension_paths, current_config_version "
            "FROM profiles WHERE id = 'p-running'"
        ).fetchone()
        assert row == ("zh-CN", 1, json.dumps(["/ext/alpha", "/ext/beta"]), 2)

        rt = conn.execute(
            "SELECT desired_state, observed_state, runtime_instance_id, config_version, state_revision "
            "FROM profile_runtimes WHERE profile_id = 'p-running'"
        ).fetchone()
        assert rt == ("running", "running", "inst_live_1", 1, 4)

        v1_raw = conn.execute(
            "SELECT snapshot FROM profile_config_versions WHERE id = 'v1-wrap'"
        ).fetchone()[0]
        v1 = json.loads(v1_raw)
        assert v1["proxy_credential_revision"] == 11
        for gone in REMOVED_PROFILE_KEYS:
            assert gone not in v1["config"]
        assert v1["config"]["mute_audio"] is False
        assert v1["config"]["extension_paths"] == ["/ext/alpha"]
        assert ProfileConfig.model_validate(v1["config"]).mute_audio is False

        v2_raw = conn.execute(
            "SELECT snapshot FROM profile_config_versions WHERE id = 'v2-flat'"
        ).fetchone()[0]
        v2 = json.loads(v2_raw)
        assert "config" not in v2
        for gone in REMOVED_PROFILE_KEYS:
            assert gone not in v2
        assert v2["mute_audio"] is True
        assert v2["locale"] == "zh-CN"
        assert v2["extension_paths"] == ["/ext/alpha", "/ext/beta"]
        assert ProfileConfig.model_validate(v2).mute_audio is True

        # Recomputing snapshot transform yields zero drift.
        assert transform_migrated_config_dict(v1["config"]) == (v1["config"], [])
        assert transform_migrated_config_dict(v2) == (v2, [])
    finally:
        conn.close()

    once = _db_fingerprint(db)
    run_database_migrations(db)
    twice = _db_fingerprint(db)
    assert twice == once

    # Restore pre-upgrade backup drill brings back pre-0016 stamp & schema cleanly
    shutil.copyfile(pre_backup, db)
    _tables, cols, _, _, stamp = _db_fingerprint(db)
    assert stamp == REVISION_BEFORE
    col_names = {c[1] for c in cols}
    for old_col in REMOVED_PROFILE_KEYS:
        assert old_col in col_names
    assert "mute_audio" not in col_names
    assert cookies.read_bytes() == b"cookie-bytes-intact"
