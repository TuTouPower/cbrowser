"""t104 AC-002 unit tests: Alembic 0017 managed extensions migration & fail-before-write audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from cbrowser.adapters.database.migrations import (
    BUSINESS_TABLES,
    get_alembic_config,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.extensions.manifest import (
    ExtensionPackageError,
    crx_id_from_pubkey_der,
    materialize_extension_directory,
    parse_extension_archive,
)
from tests.unit.test_t103_launch_args_migration import (
    WIN_SET,
    _db_fingerprint,
)
from tests.unit.test_t104_extensions_manifest import (
    _generate_rsa_pub_der,
    _make_crx3_bytes,
    _make_zip_bytes,
)

REVISION_0016 = "a10300160001"
REVISION_HEAD = "e10400170001"


def _insert_0016_profile(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    display_number: int,
    extension_paths: list[str] | None = None,
    current_config_version: int = 1,
    mute_audio: bool = False,
) -> None:
    now = "2026-01-01T00:00:00+00:00"
    raw_ep = json.dumps(extension_paths if extension_paths is not None else [])
    conn.execute(
        "INSERT INTO profiles ("
        "id, display_number, name, fingerprint_seed, group_id, proxy_id,"
        " timezone, locale, screen_width, screen_height,"
        " geoip, clipboard_sync, color_scheme, fingerprint_platform,"
        " font_set_id, include_cjk_fonts, extension_paths,"
        " set_google_default, capture_preview, restore_session, mute_audio,"
        " notes, user_data_dir, sort_order, current_config_version, created_at, updated_at"
        ") VALUES (?,?,?,?,NULL,NULL,NULL,'en-US',1920,1080,1,1,'light','windows',?,1,?,1,1,1,?,NULL,?,0,?,?,?)",
        (
            profile_id,
            display_number,
            f"Prof-{profile_id}",
            100000 + display_number,
            WIN_SET,
            raw_ep,
            int(mute_audio),
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
        ") VALUES (?, 'stopped', 'stopped', NULL, ?, 0, 0, ?, 1)",
        (profile_id, current_config_version, now),
    )


def _insert_0016_version(
    conn: sqlite3.Connection,
    *,
    row_id: str,
    profile_id: str,
    version: int,
    wrapped: bool = True,
    proxy_cred_rev: int | None = None,
    extension_paths: list[str] | None = None,
    raw_override: str | None = None,
) -> None:
    cfg = {
        "name": f"Prof-{profile_id}-v{version}",
        "fingerprint_seed": 100000 + version,
        "group_id": None,
        "proxy_id": None,
        "timezone": None,
        "locale": "en-US",
        "screen_width": 1920,
        "screen_height": 1080,
        "geoip": True,
        "clipboard_sync": True,
        "color_scheme": "light",
        "fingerprint_platform": "windows",
        "font_set_id": WIN_SET,
        "include_cjk_fonts": False,
        "extension_paths": extension_paths if extension_paths is not None else [],
        "set_google_default": True,
        "capture_preview": True,
        "restore_session": True,
        "mute_audio": False,
        "notes": f"v{version}",
        "sort_order": 0,
    }
    payload = (
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


def _seed_0016_db(
    db: Path,
    *,
    profile_rows: list[dict],
    version_rows: list[dict],
) -> None:
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0016)
    conn = sqlite3.connect(db)
    try:
        for p in profile_rows:
            _insert_0016_profile(conn, **p)
        for v in version_rows:
            _insert_0016_version(conn, **v)
        conn.commit()
    finally:
        conn.close()


def _build_legacy_and_managed(
    base_dir: Path,
    *,
    key_name: str,
    ext_name: str,
    version: str = "1.0.0",
    with_metadata_dir: bool = False,
) -> tuple[Path, str, str]:
    priv, pub_der, b64, cid = _generate_rsa_pub_der(base_dir, key_name)
    entries = {
        "manifest.json": json.dumps(
            {
                "manifest_version": 3,
                "name": ext_name,
                "version": version,
                "key": b64,
            }
        ).encode(),
        "bg.js": f"console.log('{ext_name}-{version}');\n".encode(),
    }
    zip_bytes = _make_zip_bytes(entries)
    crx_bytes = _make_crx3_bytes(zip_bytes, pub_der=pub_der, priv_pem=priv)
    pkg = parse_extension_archive(crx_bytes, f"{ext_name}.crx")

    managed_dir = base_dir / "extensions" / pkg.asset_id
    materialize_extension_directory(pkg, managed_dir)

    legacy_dir = base_dir / f"legacy_{key_name}_{version}"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in entries.items():
        (legacy_dir / rel).write_bytes(content)
    if with_metadata_dir:
        meta = legacy_dir / "_metadata"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "computed_hashes.json").write_text('{"file_hashes":[]}', encoding="utf-8")

    return legacy_dir, pkg.asset_id, cid


def test_0017_is_single_head_and_business_tables_updated(tmp_path: Path) -> None:
    cfg = get_alembic_config(tmp_path / "head.db")
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == [REVISION_HEAD]
    assert "extension_assets" in BUSINESS_TABLES


def test_empty_extension_paths_upgrade_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CBROWSER_DATA_ROOT", str(tmp_path))
    db = tmp_path / "db" / "empty.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    _seed_0016_db(
        db,
        profile_rows=[
            {"profile_id": "p1", "display_number": 1, "extension_paths": []},
        ],
        version_rows=[
            {
                "row_id": "v1",
                "profile_id": "p1",
                "version": 1,
                "wrapped": True,
                "proxy_cred_rev": 7,
                "extension_paths": [],
            },
            {
                "row_id": "v2",
                "profile_id": "p1",
                "version": 2,
                "wrapped": False,
                "extension_paths": [],
            },
        ],
    )
    cfg = get_alembic_config(db)
    command.upgrade(cfg, "head")
    # Re-running upgrade to head is an explicit idempotent no-op.
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        assert "extension_paths" not in cols
        assert "allow_extensions" in cols
        assert "extension_ids" in cols

        row = conn.execute(
            "SELECT allow_extensions, extension_ids FROM profiles WHERE id = 'p1'"
        ).fetchone()
        assert row == (0, "[]")

        v1 = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v1'"
            ).fetchone()[0]
        )
        assert v1["proxy_credential_revision"] == 7
        assert "extension_paths" not in v1["config"]
        assert v1["config"]["allow_extensions"] is False
        assert v1["config"]["extension_ids"] == []

        v2 = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v2'"
            ).fetchone()[0]
        )
        assert "extension_paths" not in v2
        assert v2["allow_extensions"] is False
        assert v2["extension_ids"] == []
    finally:
        conn.close()


def test_verified_mapped_upgrade_preserves_order_id_continuity_and_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    monkeypatch.setenv("CBROWSER_DATA_ROOT", str(tmp_path))
    legacy_a, asset_a, cid_a = _build_legacy_and_managed(
        tmp_path, key_name="ext_a", ext_name="Ext A", version="1.0.0", with_metadata_dir=True
    )
    legacy_b, asset_b, cid_b = _build_legacy_and_managed(
        tmp_path, key_name="ext_b", ext_name="Ext B", version="2.1.0"
    )
    pre_key_b64 = json.loads((legacy_a / "manifest.json").read_text(encoding="utf-8"))["key"]
    pre_id_a = crx_id_from_pubkey_der(base64.b64decode(pre_key_b64))
    assert pre_id_a == cid_a

    # Simulate persisted Chromium Local Extension Settings for pre-migration ID.
    storage_dir = tmp_path / "profiles" / "p1" / "profile" / "Default" / "Local Extension Settings" / pre_id_a
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "CURRENT").write_text("MANIFEST-000001\n", encoding="utf-8")

    db = tmp_path / "db" / "mapped.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    _seed_0016_db(
        db,
        profile_rows=[
            {
                "profile_id": "p1",
                "display_number": 1,
                "extension_paths": [str(legacy_a), str(legacy_b)],
                "current_config_version": 2,
            },
        ],
        version_rows=[
            {
                "row_id": "v1",
                "profile_id": "p1",
                "version": 1,
                "wrapped": True,
                "proxy_cred_rev": 9,
                "extension_paths": [str(legacy_a)],
            },
            {
                "row_id": "v2",
                "profile_id": "p1",
                "version": 2,
                "wrapped": False,
                "extension_paths": [str(legacy_a), str(legacy_b)],
            },
        ],
    )
    cfg = get_alembic_config(db)
    command.upgrade(cfg, "head")
    # Non-empty migration is idempotent across repeated upgrade("head") runs.
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    try:
        p_row = conn.execute(
            "SELECT allow_extensions, extension_ids, user_data_dir, current_config_version "
            "FROM profiles WHERE id = 'p1'"
        ).fetchone()
        assert p_row == (1, json.dumps([asset_a, asset_b]), "/data/profiles/p1/profile", 2)

        rt_row = conn.execute(
            "SELECT config_version, desired_state, observed_state "
            "FROM profile_runtimes WHERE profile_id = 'p1'"
        ).fetchone()
        assert rt_row == (2, "stopped", "stopped")

        v1 = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v1'"
            ).fetchone()[0]
        )
        assert v1["proxy_credential_revision"] == 9
        assert "extension_paths" not in v1["config"]
        assert v1["config"]["allow_extensions"] is True
        assert v1["config"]["extension_ids"] == [asset_a]
        ProfileConfig.model_validate(v1["config"])

        v2 = json.loads(
            conn.execute(
                "SELECT snapshot FROM profile_config_versions WHERE id = 'v2'"
            ).fetchone()[0]
        )
        assert "extension_paths" not in v2
        assert v2["allow_extensions"] is True
        assert v2["extension_ids"] == [asset_a, asset_b]
        ProfileConfig.model_validate(v2)

        adopted = conn.execute(
            "SELECT id, chromium_id, state FROM extension_assets ORDER BY id"
        ).fetchall()
        assert (asset_a, cid_a, "verified") in adopted
        assert (asset_b, cid_b, "verified") in adopted
    finally:
        conn.close()

    # Post-migration materialized manifest keeps exact pre-migration chrome.runtime.id & storage.
    post_mf = json.loads(
        (tmp_path / "extensions" / asset_a / "manifest.json").read_text(encoding="utf-8")
    )
    post_id_a = crx_id_from_pubkey_der(base64.b64decode(post_mf["key"]))
    assert post_id_a == pre_id_a
    assert (storage_dir / "CURRENT").is_file()


@pytest.mark.parametrize(
    ("scenario", "expected_tokens"),
    [
        ("missing_legacy_dir", ("p1", "version 1", "分类=缺失")),
        ("missing_managed_catalog_match", ("p1", "version 1", "分类=缺失")),
        ("ambiguous_candidates", ("p1", "version 1", "分类=歧义")),
        ("ambiguous_duplicate_cid_in_snapshot", ("p1", "version 1", "分类=歧义")),
        ("missing_manifest_key_continuity", ("p1", "version 1", "分类=无法保持扩展 ID 连续性")),
        ("historical_snapshot_blocker_with_clean_current_profile", ("p1", "version 1", "分类=缺失")),
        ("corrupt_snapshot_json", ("p1", "version 1", "corrupt snapshot JSON")),
    ],
)
def test_blockers_fail_before_write_with_zero_db_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_tokens: tuple[str, ...],
) -> None:
    monkeypatch.setenv("CBROWSER_DATA_ROOT", str(tmp_path))
    db = tmp_path / "db" / f"{scenario}.db"
    db.parent.mkdir(parents=True, exist_ok=True)

    prof_paths: list[str] = []
    ver_paths: list[str] = []
    raw_override: str | None = None

    if scenario == "missing_legacy_dir":
        prof_paths = [str(tmp_path / "does_not_exist")]
        ver_paths = [str(tmp_path / "does_not_exist")]
    elif scenario == "missing_managed_catalog_match":
        legacy, asset_id, _ = _build_legacy_and_managed(
            tmp_path, key_name="unmanaged", ext_name="Unmanaged", version="1.0.0"
        )
        # Remove from managed directory so catalog lacks match.
        import shutil
        shutil.rmtree(tmp_path / "extensions" / asset_id)
        prof_paths = [str(legacy)]
        ver_paths = [str(legacy)]
    elif scenario == "ambiguous_candidates":
        import base64

        legacy_v1, _, cid1 = _build_legacy_and_managed(
            tmp_path, key_name="same", ext_name="SameExt", version="1.0.0"
        )
        # Reuse exact same key pair (same.der) to stage a second managed version 2.0.0.
        same_der = (tmp_path / "same.der").read_bytes()
        b64_same = base64.b64encode(same_der).decode("ascii")
        pkg2 = parse_extension_archive(
            _make_zip_bytes(
                {
                    "manifest.json": json.dumps(
                        {"manifest_version": 3, "name": "SameExt", "version": "2.0.0", "key": b64_same}
                    ).encode(),
                    "bg.js": b"console.log(2);\n",
                }
            ),
            "v2.zip",
        )
        assert pkg2.chromium_id == cid1
        materialize_extension_directory(pkg2, tmp_path / "extensions" / pkg2.asset_id)
        # Legacy path claims version 3.0.0 with SAME key -> two managed candidates for same chromium_id -> ambiguous!
        legacy_v3 = tmp_path / "legacy_v3"
        legacy_v3.mkdir(parents=True, exist_ok=True)
        (legacy_v3 / "manifest.json").write_text(
            json.dumps({"manifest_version": 3, "name": "SameExt", "version": "3.0.0", "key": b64_same}),
            encoding="utf-8",
        )
        (legacy_v3 / "bg.js").write_text("console.log(3);\n", encoding="utf-8")
        prof_paths = [str(legacy_v3)]
        ver_paths = [str(legacy_v3)]
        assert legacy_v1.exists()
    elif scenario == "ambiguous_duplicate_cid_in_snapshot":
        import base64

        legacy_v1, _, cid1 = _build_legacy_and_managed(
            tmp_path, key_name="dupkey", ext_name="DupExt", version="1.0.0"
        )
        b64_dup = base64.b64encode((tmp_path / "dupkey.der").read_bytes()).decode("ascii")
        pkg_v2 = parse_extension_archive(
            _make_zip_bytes(
                {
                    "manifest.json": json.dumps(
                        {"manifest_version": 3, "name": "DupExt", "version": "2.0.0", "key": b64_dup}
                    ).encode(),
                    "bg.js": b"console.log('v2');\n",
                }
            ),
            "dup_v2.zip",
        )
        assert pkg_v2.chromium_id == cid1
        materialize_extension_directory(pkg_v2, tmp_path / "extensions" / pkg_v2.asset_id)
        legacy_v2 = tmp_path / "legacy_dupkey_2.0.0"
        legacy_v2.mkdir(parents=True, exist_ok=True)
        for rel, content in pkg_v2.files.items():
            (legacy_v2 / rel).write_bytes(content)
        # Same snapshot binds two paths resolving to the same chromium_id -> blocked as ambiguous!
        prof_paths = [str(legacy_v1), str(legacy_v2)]
        ver_paths = [str(legacy_v1), str(legacy_v2)]
    elif scenario == "missing_manifest_key_continuity":
        unkeyed = tmp_path / "legacy_unkeyed"
        unkeyed.mkdir(parents=True, exist_ok=True)
        (unkeyed / "manifest.json").write_text(
            json.dumps({"manifest_version": 3, "name": "NoKey", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (unkeyed / "bg.js").write_text("console.log('nokey');\n", encoding="utf-8")
        prof_paths = [str(unkeyed)]
        ver_paths = [str(unkeyed)]
    elif scenario == "historical_snapshot_blocker_with_clean_current_profile":
        # Current profile cleared extensions, but historical v1 still references missing dir!
        prof_paths = []
        ver_paths = [str(tmp_path / "gone_in_v1")]
    elif scenario == "corrupt_snapshot_json":
        raw_override = "{not-valid-json"

    _seed_0016_db(
        db,
        profile_rows=[
            {"profile_id": "p1", "display_number": 1, "extension_paths": prof_paths},
        ],
        version_rows=[
            {
                "row_id": "v1",
                "profile_id": "p1",
                "version": 1,
                "wrapped": True,
                "extension_paths": ver_paths,
                "raw_override": raw_override,
            },
        ],
    )
    before = _db_fingerprint(db)
    cfg = get_alembic_config(db)
    with pytest.raises(RuntimeError) as exc:
        command.upgrade(cfg, "head")
    detail = str(exc.value)
    for token in expected_tokens:
        assert token in detail, f"{scenario}: expected {token!r} in {detail!r}"
    after = _db_fingerprint(db)
    assert after == before, f"{scenario}: expected zero writes on migration block"
