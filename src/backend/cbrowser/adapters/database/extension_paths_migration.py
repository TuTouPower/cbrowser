"""Read-only inventory, continuity checks, and forward migration from extension_paths (t104).

Scans both ``profiles`` rows and historical ``profile_config_versions`` snapshots
(flat and ``{"config": ..., "proxy_credential_revision": ...}`` wrapped) BEFORE
any schema or row write:

- ``empty`` (``[]``): migrates cleanly to ``allow_extensions=False``, ``extension_ids=[]``.
- ``verified_mapped``: resolves each legacy path to a single verified managed
  extension asset with matching trusted public-key identity and verified content
  AND guarantees pre-migration ``chrome.runtime.id`` + local storage continuity,
  migrating to ``allow_extensions=True``, ``extension_ids=[...]``.
- ``missing`` / ``ambiguous`` / ``id_continuity_lost`` / corrupt payloads: fails
  closed before any write with explicit profile ID + snapshot version + path
  diagnostics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from cbrowser.extensions.manifest import (
    EXTENSION_ASSET_ID_RE,
    ExtensionPackageError,
    compute_tree_identity,
    extract_directory_metadata,
    parse_manifest_key,
    resolve_extensions_root,
    verify_extension_directory,
)


@dataclass(frozen=True)
class TrustedManagedExtension:
    id: str
    chromium_id: str
    name: str
    version: str
    manifest_version: int
    description: str | None
    package_format: str
    identity_source: str
    manifest_key_sha256: str
    archive_sha256: str
    icon_relpath: str | None
    file_count: int
    total_bytes: int
    integrity: dict[str, Any]
    state: str
    file_hashes: dict[str, str]
    normalized_core_hashes: dict[str, str]


@dataclass(frozen=True)
class ProfileExtensionPlan:
    profile_id: str
    allow_extensions: bool
    extension_ids: list[str]
    needs_update: bool


@dataclass(frozen=True)
class SnapshotExtensionPlan:
    row_id: str
    profile_id: str
    version: int
    raw_outer: dict[str, Any]
    is_wrapped: bool
    allow_extensions: bool
    extension_ids: list[str]
    needs_rewrite: bool


@dataclass(frozen=True)
class ExtensionMigrationInventory:
    extensions_root: Path | None
    trusted_assets: dict[str, TrustedManagedExtension]
    profile_plans: list[ProfileExtensionPlan] = field(default_factory=list)
    snapshot_plans: list[SnapshotExtensionPlan] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)


def _core_file_hashes(file_hashes: dict[str, str]) -> dict[str, str]:
    """Strip Chromium-generated ``_metadata/`` entries when comparing legacy unpacked trees."""
    return {
        k: v
        for k, v in file_hashes.items()
        if not k.startswith("_metadata/") and k != "manifest.json"
    }


def _connection_extensions_root(conn: sa.Connection) -> Path | None:
    db_file = conn.engine.url.database if getattr(conn, "engine", None) else None
    return resolve_extensions_root(db_path=db_file)


def _load_trusted_asset_from_dir(ext_dir: Path) -> TrustedManagedExtension | None:
    verdict = verify_extension_directory(ext_dir, expected_asset_id=ext_dir.name)
    if not verdict["ok"] or not isinstance(verdict.get("manifest"), dict):
        return None
    mf = verdict["manifest"]
    file_hashes: dict[str, str] = verdict["file_hashes"]
    name, desc, icon_relpath = extract_directory_metadata(ext_dir, mf, file_hashes)
    integrity = {
        "ok": True,
        "problems": [],
        "manifest_sha256": file_hashes.get("manifest.json", ""),
        "tree_sha256": ext_dir.name,
        "file_hashes": file_hashes,
    }
    return TrustedManagedExtension(
        id=ext_dir.name,
        chromium_id=str(verdict["chromium_id"]),
        name=name[:255],
        version=str(mf.get("version", ""))[:64],
        manifest_version=int(mf["manifest_version"]),
        description=desc,
        package_format="zip",
        identity_source="manifest_key",
        manifest_key_sha256=str(verdict["manifest_key_sha256"] or ""),
        archive_sha256=ext_dir.name,
        icon_relpath=icon_relpath,
        file_count=int(verdict["file_count"]),
        total_bytes=int(verdict["total_bytes"]),
        integrity=integrity,
        state="verified",
        file_hashes=file_hashes,
        normalized_core_hashes=_core_file_hashes(file_hashes),
    )


def _trusted_asset_from_db_row(
    row: Any, extensions_root: Path | None
) -> TrustedManagedExtension | None:
    (
        aid, cid, name, ver, mv, desc, fmt, id_src, key_sha, arch_sha,
        icon_rel, f_cnt, t_bytes, integ_raw, state
    ) = row
    try:
        integ = json.loads(integ_raw or "{}")
    except ValueError:
        integ = {}
    f_hashes = integ.get("file_hashes") if isinstance(integ.get("file_hashes"), dict) else {}
    if not f_hashes:
        if extensions_root is not None and (extensions_root / str(aid)).is_dir():
            return _load_trusted_asset_from_dir(extensions_root / str(aid))
        return None
    normalized_hashes = {str(k): str(v) for k, v in f_hashes.items()}
    return TrustedManagedExtension(
        id=str(aid),
        chromium_id=str(cid),
        name=str(name),
        version=str(ver),
        manifest_version=int(mv),
        description=desc,
        package_format=str(fmt),
        identity_source=str(id_src),
        manifest_key_sha256=str(key_sha),
        archive_sha256=str(arch_sha),
        icon_relpath=icon_rel,
        file_count=int(f_cnt),
        total_bytes=int(t_bytes),
        integrity=integ,
        state=str(state),
        file_hashes=normalized_hashes,
        normalized_core_hashes=_core_file_hashes(normalized_hashes),
    )


def _table_exists(conn: sa.Connection, table_name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = :name"
        ),
        {"name": table_name},
    ).fetchone()
    return row is not None


def _table_columns(conn: sa.Connection, table_name: str) -> set[str]:
    rows = conn.execute(sa.text(f'PRAGMA table_info("{table_name}")')).fetchall()
    return {str(r[1]) for r in rows}


def _scan_managed_extension_dirs(extensions_root: Path | None) -> dict[str, TrustedManagedExtension]:
    assets: dict[str, TrustedManagedExtension] = {}
    if extensions_root is None or not extensions_root.is_dir():
        return assets
    for child in sorted(extensions_root.iterdir()):
        if (
            child.is_symlink()
            or not child.is_dir()
            or not EXTENSION_ASSET_ID_RE.fullmatch(child.name)
        ):
            continue
        loaded = _load_trusted_asset_from_dir(child)
        if loaded is not None:
            assets[loaded.id] = loaded
    return assets


def load_trusted_managed_catalog(
    conn: sa.Connection,
    extensions_root: Path | None,
) -> dict[str, TrustedManagedExtension]:
    assets = _scan_managed_extension_dirs(extensions_root)
    if not _table_exists(conn, "extension_assets"):
        return assets
    rows = conn.execute(
        sa.text(
            "SELECT id, chromium_id, name, version, manifest_version, description, "
            "package_format, identity_source, manifest_key_sha256, archive_sha256, "
            "icon_relpath, file_count, total_bytes, integrity, state "
            "FROM extension_assets WHERE state = 'verified'"
        )
    ).fetchall()
    for row in rows:
        loaded = _trusted_asset_from_db_row(row, extensions_root)
        if loaded is not None:
            assets[loaded.id] = loaded
    return assets


def _inspect_legacy_directory(
    raw_path: str,
    context_label: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, f"{context_label}: missing/blank legacy extension_paths entry {raw_path!r}"
    legacy_dir = Path(raw_path)
    if legacy_dir.is_symlink() or not legacy_dir.is_dir():
        return (
            None,
            f"{context_label}: missing legacy extension directory {raw_path!r} (分类=缺失)",
        )
    mf_path = legacy_dir / "manifest.json"
    if not mf_path.is_file() or mf_path.is_symlink():
        return (
            None,
            f"{context_label}: missing manifest.json in {raw_path!r} (分类=缺失)",
        )
    try:
        manifest = json.loads(mf_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return (
            None,
            f"{context_label}: invalid manifest.json in {raw_path!r} (分类=缺失)",
        )
    if not isinstance(manifest, dict):
        return (
            None,
            f"{context_label}: non-object manifest.json in {raw_path!r} (分类=缺失)",
        )
    if not isinstance(manifest.get("key"), str) or not manifest["key"].strip():
        return (
            None,
            f"{context_label}: {raw_path!r} lacks manifest key; chrome.runtime.id "
            "cannot remain continuous under managed mount paths (分类=无法保持扩展 ID 连续性)",
        )
    try:
        key_der, chromium_id = parse_manifest_key(manifest["key"])
    except ExtensionPackageError as exc:
        return (
            None,
            f"{context_label}: {raw_path!r} has invalid manifest key ({exc}); "
            "cannot preserve chrome.runtime.id continuity (分类=无法保持扩展 ID 连续性)",
        )

    verdict = verify_extension_directory(legacy_dir)
    if not verdict["ok"]:
        return (
            None,
            f"{context_label}: legacy directory {raw_path!r} failed integrity checks: "
            + "; ".join(verdict["problems"])
            + " (分类=缺失)",
        )

    return {
        "chromium_id": chromium_id,
        "key_sha256": hashlib.sha256(key_der).hexdigest(),
        "version": str(manifest.get("version", "")).strip(),
        "tree_sha256": verdict["tree_sha256"],
        "file_hashes": verdict["file_hashes"],
        "core_hashes": _core_file_hashes(verdict["file_hashes"]),
    }, None


def _same_identity_assets(
    catalog: dict[str, TrustedManagedExtension],
    cid: str,
    key_sha: str,
    version: str,
) -> list[TrustedManagedExtension]:
    return [
        asset
        for asset in catalog.values()
        if asset.chromium_id == cid
        and asset.manifest_key_sha256 == key_sha
        and asset.version == version
    ]


def _core_matching_assets(
    assets: list[TrustedManagedExtension], core_hashes: Any
) -> list[TrustedManagedExtension]:
    return [a for a in assets if a.normalized_core_hashes == core_hashes]


def _classify_managed_candidates(
    info: dict[str, Any], catalog: dict[str, TrustedManagedExtension]
) -> tuple[str, list[TrustedManagedExtension], list[TrustedManagedExtension]]:
    """Pure identity classification, independent of path/message formatting."""
    cid = str(info["chromium_id"])
    key_sha = str(info["key_sha256"])
    ver = str(info["version"])
    same_identity = _same_identity_assets(catalog, cid, key_sha, ver)
    if not same_identity:
        same_cid = [a for a in catalog.values() if a.chromium_id == cid]
        return (
            "ambiguous_cid" if len(same_cid) > 1 else "missing",
            [],
            same_cid,
        )
    exact = [a for a in same_identity if a.id == info["tree_sha256"]]
    if len(exact) == 1 and len(same_identity) == 1:
        return "exact", exact, same_identity
    if len(exact) > 1:
        return "ambiguous_exact", [], same_identity
    core_matched = _core_matching_assets(same_identity, info["core_hashes"])
    if len(core_matched) == 1:
        return "core", core_matched, same_identity
    if len(core_matched) > 1 or len(same_identity) > 1:
        return "ambiguous", [], core_matched or same_identity
    return "digest_mismatch", [], same_identity


def _match_legacy_entry(
    raw_path: str,
    context_label: str,
    catalog: dict[str, TrustedManagedExtension],
) -> tuple[str | None, str | None, str | None]:
    """Classify and resolve one legacy path -> ``(asset_id, chromium_id, error)``."""
    info, inspect_err = _inspect_legacy_directory(raw_path, context_label)
    if inspect_err is not None or info is None:
        return None, None, inspect_err

    cid, ver = str(info["chromium_id"]), str(info["version"])
    kind, matched, peers = _classify_managed_candidates(info, catalog)
    if kind == "exact" or kind == "core":
        return matched[0].id, cid, None
    if kind == "missing" or kind == "ambiguous_cid":
        if len(peers) > 1:
            return (
                None,
                None,
                f"{context_label}: ambiguous managed candidates for {raw_path!r} "
                f"(chromium_id={cid}, candidates={sorted(a.id for a in peers)}) (分类=歧义)",
            )
        return (
            None,
            None,
            f"{context_label}: missing verified managed asset for {raw_path!r} "
            f"(chromium_id={cid}, version={ver!r}) (分类=缺失)",
        )
    if kind == "ambiguous_exact":
        return (
            None,
            None,
            f"{context_label}: ambiguous exact managed matches for {raw_path!r} (分类=歧义)",
        )
    if kind == "ambiguous":
        return (
            None,
            None,
            f"{context_label}: ambiguous managed assets matching {raw_path!r} "
            f"(chromium_id={cid}, version={ver!r}, matches={len(peers)}) (分类=歧义)",
        )
    return (
        None,
        None,
        f"{context_label}: artifact digest mismatch against managed asset for {raw_path!r} (分类=缺失)",
    )

def _resolve_extension_list(
    raw_paths: Any,
    context_label: str,
    catalog: dict[str, TrustedManagedExtension],
) -> tuple[bool, list[str], list[str]]:
    if raw_paths is None:
        return False, [], []
    if not isinstance(raw_paths, list):
        return False, [], [f"{context_label}: invalid non-list extension_paths payload"]
    if not raw_paths:
        return False, [], []

    asset_ids: list[str] = []
    seen_cids: dict[str, str] = {}
    errors: list[str] = []
    for raw_item in raw_paths:
        if not isinstance(raw_item, str):
            errors.append(f"{context_label}: non-string extension_paths entry {raw_item!r}")
            continue
        asset_id, cid, err = _match_legacy_entry(raw_item, context_label, catalog)
        if err is not None:
            errors.append(err)
            continue
        assert asset_id is not None and cid is not None
        if cid in seen_cids:
            errors.append(
                f"{context_label}: ambiguous duplicate Chromium ID {cid} across {seen_cids[cid]!r} and {raw_item!r} (分类=歧义)"
            )
            continue
        seen_cids[cid] = raw_item
        if asset_id not in asset_ids:
            asset_ids.append(asset_id)

    if errors:
        return False, [], errors
    return True, asset_ids, []


def _parse_json_paths(raw: Any, context_label: str) -> tuple[Any, str | None]:
    if raw is None or raw == "":
        return [], None
    if isinstance(raw, list):
        return raw, None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return None, f"{context_label}: corrupt JSON in extension_paths"
    if not isinstance(parsed, list):
        return None, f"{context_label}: extension_paths JSON must decode to a list"
    return parsed, None


def _audit_profiles_table(
    conn: sa.Connection,
    catalog: dict[str, TrustedManagedExtension],
) -> tuple[list[ProfileExtensionPlan], list[str]]:
    profile_cols = _table_columns(conn, "profiles")
    if "extension_paths" not in profile_cols:
        prof_rows = conn.execute(
            sa.text("SELECT id, allow_extensions, extension_ids FROM profiles ORDER BY id")
        ).fetchall()
        return [
            ProfileExtensionPlan(
                profile_id=str(pid),
                allow_extensions=bool(allow_ext),
                extension_ids=json.loads(raw_ids or "[]") if isinstance(raw_ids, str) else [],
                needs_update=False,
            )
            for pid, allow_ext, raw_ids in prof_rows
        ], []

    blocking_errors: list[str] = []
    profile_plans: list[ProfileExtensionPlan] = []
    prof_rows = conn.execute(sa.text("SELECT id, extension_paths FROM profiles ORDER BY id")).fetchall()
    for pid, raw_ext in prof_rows:
        parsed, parse_err = _parse_json_paths(raw_ext, f"profile {pid}")
        if parse_err is not None:
            blocking_errors.append(parse_err)
            continue
        allow_ext, ext_ids, errs = _resolve_extension_list(
            parsed, f"profile {pid} (current)", catalog
        )
        if errs:
            blocking_errors.extend(errs)
            continue
        profile_plans.append(
            ProfileExtensionPlan(
                profile_id=str(pid),
                allow_extensions=allow_ext,
                extension_ids=ext_ids,
                needs_update=True,
            )
        )
    return profile_plans, blocking_errors


def _audit_single_snapshot_row(
    row_id: str,
    pid: str,
    ver: int,
    raw_snap: Any,
    catalog: dict[str, TrustedManagedExtension],
) -> tuple[SnapshotExtensionPlan | None, list[str]]:
    ctx = f"profile {pid} version {ver} (snapshot {row_id})"
    try:
        outer = json.loads(raw_snap)
    except (TypeError, ValueError):
        return None, [f"{ctx}: corrupt snapshot JSON"]
    if not isinstance(outer, dict):
        return None, [f"{ctx}: snapshot JSON is not an object"]
    is_wrapped = "config" in outer
    cfg = outer["config"] if is_wrapped else outer
    if not isinstance(cfg, dict):
        return None, [f"{ctx}: wrapped snapshot config is not an object"]

    if "extension_paths" in cfg:
        allow_ext, ext_ids, errs = _resolve_extension_list(cfg.get("extension_paths"), ctx, catalog)
        if errs:
            return None, errs
        return SnapshotExtensionPlan(
            row_id=row_id,
            profile_id=pid,
            version=ver,
            raw_outer=outer,
            is_wrapped=is_wrapped,
            allow_extensions=allow_ext,
            extension_ids=ext_ids,
            needs_rewrite=True,
        ), []

    needs_spurious_clean = is_wrapped and any(
        k in outer for k in ("extension_paths", "allow_extensions", "extension_ids")
    )
    return SnapshotExtensionPlan(
        row_id=row_id,
        profile_id=pid,
        version=ver,
        raw_outer=outer,
        is_wrapped=is_wrapped,
        allow_extensions=bool(cfg.get("allow_extensions", False)),
        extension_ids=list(cfg.get("extension_ids") or []),
        needs_rewrite=needs_spurious_clean
        or "allow_extensions" not in cfg
        or "extension_ids" not in cfg,
    ), []


def audit_extension_paths_database(
    conn: sa.Connection,
    *,
    extensions_root: Path | None = None,
) -> ExtensionMigrationInventory:
    """Read-only inventory & validation of all profiles and historical snapshots."""
    resolved_root = extensions_root if extensions_root is not None else _connection_extensions_root(conn)
    catalog = load_trusted_managed_catalog(conn, resolved_root)
    profile_plans, blocking_errors = _audit_profiles_table(conn, catalog)
    snapshot_plans: list[SnapshotExtensionPlan] = []
    ver_rows = conn.execute(
        sa.text(
            "SELECT id, profile_id, version, snapshot "
            "FROM profile_config_versions ORDER BY profile_id, version"
        )
    ).fetchall()
    for row_id, pid, ver, raw_snap in ver_rows:
        plan, errs = _audit_single_snapshot_row(str(row_id), str(pid), int(ver), raw_snap, catalog)
        if errs:
            blocking_errors.extend(errs)
        elif plan is not None:
            snapshot_plans.append(plan)

    return ExtensionMigrationInventory(
        extensions_root=resolved_root,
        trusted_assets=catalog,
        profile_plans=profile_plans,
        snapshot_plans=snapshot_plans,
        blocking_errors=blocking_errors,
    )


def seed_trusted_assets_table(
    conn: sa.Connection, trusted_assets: dict[str, TrustedManagedExtension]
) -> None:
    """Adopt verified on-disk managed assets into ``extension_assets`` idempotently."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    for asset in trusted_assets.values():
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO extension_assets "
                "(id, chromium_id, name, version, manifest_version, description, "
                "package_format, identity_source, manifest_key_sha256, archive_sha256, "
                "icon_relpath, file_count, total_bytes, integrity, state, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :ver, :mv, :desc, :fmt, :id_src, :ksha, :asha, "
                ":icon, :fcnt, :tbytes, :integ, :state, :created_at, :updated_at)"
            ),
            {
                "id": asset.id,
                "cid": asset.chromium_id,
                "name": asset.name,
                "ver": asset.version,
                "mv": asset.manifest_version,
                "desc": asset.description,
                "fmt": asset.package_format,
                "id_src": asset.identity_source,
                "ksha": asset.manifest_key_sha256,
                "asha": asset.archive_sha256,
                "icon": asset.icon_relpath,
                "fcnt": asset.file_count,
                "tbytes": asset.total_bytes,
                "integ": json.dumps(asset.integrity, sort_keys=True),
                "state": asset.state,
                "created_at": now,
                "updated_at": now,
            },
        )


def apply_extension_migration(
    conn: sa.Connection,
    inventory: ExtensionMigrationInventory,
) -> None:
    """Apply planned profile and snapshot rewrites after DDL updates."""
    for plan in inventory.profile_plans:
        if not plan.needs_update:
            continue
        conn.execute(
            sa.text(
                "UPDATE profiles SET allow_extensions = :allow, extension_ids = :ext_ids "
                "WHERE id = :pid"
            ),
            {
                "allow": 1 if plan.allow_extensions else 0,
                "ext_ids": json.dumps(plan.extension_ids),
                "pid": plan.profile_id,
            },
        )

    for snap in inventory.snapshot_plans:
        if not snap.needs_rewrite:
            continue
        outer = dict(snap.raw_outer)
        if snap.is_wrapped:
            for spurious in ("extension_paths", "allow_extensions", "extension_ids"):
                outer.pop(spurious, None)
            cfg = dict(outer["config"])
            cfg.pop("extension_paths", None)
            cfg["allow_extensions"] = snap.allow_extensions
            cfg["extension_ids"] = list(snap.extension_ids)
            outer["config"] = cfg
        else:
            outer.pop("extension_paths", None)
            outer["allow_extensions"] = snap.allow_extensions
            outer["extension_ids"] = list(snap.extension_ids)
        conn.execute(
            sa.text(
                "UPDATE profile_config_versions SET snapshot = :snap WHERE id = :row_id"
            ),
            {"snap": json.dumps(outer), "row_id": snap.row_id},
        )
