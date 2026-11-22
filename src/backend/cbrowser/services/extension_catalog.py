"""Managed extension asset catalog service: upload, validation, icon lookup, and deletion."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from cbrowser.adapters.database.extension_repository import (
    ExtensionAssetRecord,
    ExtensionAssetRepository,
)
from cbrowser.domain.models import ExtensionUsedByEntry
from cbrowser.extensions.manifest import (
    ALLOWED_ICON_EXTENSIONS,
    EXTENSION_ASSET_ID_RE,
    ExtensionPackageError,
    extract_directory_metadata,
    materialize_extension_directory,
    parse_extension_archive,
    resolve_extensions_root,
    verify_extension_directory,
)

LOGGER = logging.getLogger("cbrowser.services.extension_catalog")
# Per-(extensions_root, asset_id) lock map keyed by running event loop so concurrent
# import_bytes / delete_asset calls on the same asset never interleave disk & DB writes.
_ASSET_LOCKS: dict[tuple[int, str, str], asyncio.Lock] = {}


def _shared_asset_lock(root: Path | None, asset_id: str) -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    root_key = str(root.resolve()) if root is not None else ""
    key = (loop_id, root_key, asset_id)
    lock = _ASSET_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _ASSET_LOCKS[key] = lock
    return lock


class ExtensionNotFoundError(Exception):
    pass


class ExtensionInUseError(Exception):
    def __init__(self, asset_id: str, used_by_count: int) -> None:
        super().__init__(
            f"Extension {asset_id} is referenced by {used_by_count} profile(s)"
        )
        self.asset_id = asset_id
        self.used_by_count = used_by_count


class ExtensionBindingError(ValueError):
    """Raised when Profile extension_ids fail catalog/integrity/ID-uniqueness validation."""


class ExtensionCatalogService:
    """Authoritative control-plane owner for uploaded/imported browser extensions."""

    def __init__(
        self,
        repo: ExtensionAssetRepository,
        extensions_root: Path | str | None = None,
        *,
        data_root: Path | str | None = None,
    ) -> None:
        self._repo = repo
        self._extensions_root = resolve_extensions_root(
            data_root=data_root, extensions_root=extensions_root
        )

    @property
    def extensions_root(self) -> Path | None:
        return self._extensions_root

    def root_configured(self) -> bool:
        return self._extensions_root is not None

    def directory_for(self, asset_id: str) -> Path:
        if self._extensions_root is None:
            raise ExtensionPackageError(
                "extensions_not_configured", "Managed extension storage root is not configured"
            )
        if not EXTENSION_ASSET_ID_RE.fullmatch(asset_id):
            raise ExtensionPackageError("invalid_extension_id", f"Invalid extension asset id: {asset_id!r}")
        return self._extensions_root / asset_id

    async def import_bytes(
        self, raw: bytes, filename: str | None = None
    ) -> tuple[ExtensionAssetRecord, bool]:
        if self._extensions_root is None:
            raise ExtensionPackageError(
                "extensions_not_configured", "Managed extension storage root is not configured"
            )
        pkg = await asyncio.to_thread(parse_extension_archive, raw, filename)
        async with _shared_asset_lock(self._extensions_root, pkg.asset_id):
            target_dir = self.directory_for(pkg.asset_id)
            created_dir = not target_dir.exists()
            await asyncio.to_thread(materialize_extension_directory, pkg, target_dir)
            verdict = await asyncio.to_thread(
                verify_extension_directory,
                target_dir,
                expected_asset_id=pkg.asset_id,
                expected_chromium_id=pkg.chromium_id,
                expected_file_hashes=pkg.file_hashes,
            )
            if not verdict["ok"]:
                if created_dir:
                    await asyncio.to_thread(shutil.rmtree, target_dir, True)
                raise ExtensionPackageError(
                    "corrupt_extension_archive",
                    "Materialized extension directory failed integrity verification: "
                    + "; ".join(verdict["problems"]),
                )
            integrity_payload = {
                "ok": True,
                "problems": [],
                "manifest_sha256": pkg.manifest_sha256,
                "tree_sha256": pkg.asset_id,
                "file_hashes": pkg.file_hashes,
            }
            try:
                record, created = await self._repo.upsert_verified(
                    asset_id=pkg.asset_id,
                    chromium_id=pkg.chromium_id,
                    name=pkg.name,
                    version=pkg.version,
                    manifest_version=pkg.manifest_version,
                    description=pkg.description,
                    package_format=pkg.package_format,
                    identity_source=pkg.identity_source,
                    manifest_key_sha256=pkg.manifest_key_sha256,
                    archive_sha256=pkg.archive_sha256,
                    icon_relpath=pkg.icon_relpath,
                    file_count=pkg.file_count,
                    total_bytes=pkg.total_bytes,
                    integrity=integrity_payload,
                    state="verified",
                )
            except BaseException:
                if created_dir:
                    await asyncio.to_thread(shutil.rmtree, target_dir, True)
                raise
            return record, created

    async def list_assets(self) -> tuple[list[ExtensionAssetRecord], dict[str, int]]:
        records = await self._repo.list_all()
        counts = await self._repo.usage_counts()
        return records, counts

    async def get_asset(self, asset_id: str) -> tuple[ExtensionAssetRecord, int] | None:
        record = await self._repo.get(asset_id)
        if record is None:
            return None
        counts = await self._repo.usage_counts()
        return record, counts.get(asset_id, 0)

    async def get_used_by(self, asset_id: str) -> list[ExtensionUsedByEntry] | None:
        return await self._repo.get_used_by(asset_id)

    async def get_icon_file(self, asset_id: str) -> tuple[Path, str] | None:
        record = await self._repo.get(asset_id)
        if record is None or not record.icon_relpath or self._extensions_root is None:
            return None
        ext_dir = self.directory_for(asset_id).resolve()
        candidate = (ext_dir / record.icon_relpath).resolve()
        if not candidate.is_relative_to(ext_dir) or candidate.is_symlink() or not candidate.is_file():
            return None
        media_type = ALLOWED_ICON_EXTENSIONS.get(candidate.suffix.lower())
        if media_type is None:
            return None
        return candidate, media_type

    async def delete_asset(self, asset_id: str) -> None:
        if not EXTENSION_ASSET_ID_RE.fullmatch(asset_id):
            raise ExtensionNotFoundError(asset_id)
        async with _shared_asset_lock(self._extensions_root, asset_id):
            status, used_by_count = await self._repo.delete_if_unused(asset_id)
            if status == "not_found":
                raise ExtensionNotFoundError(asset_id)
            if status == "in_use":
                raise ExtensionInUseError(asset_id, used_by_count)
            if self._extensions_root is not None:
                ext_dir = self._extensions_root / asset_id
                if ext_dir.exists() and not ext_dir.is_symlink():
                    await asyncio.to_thread(shutil.rmtree, ext_dir, True)

    async def validate_binding(self, extension_ids: list[str]) -> list[ExtensionAssetRecord]:
        """Validate referenced extension asset ids before binding them to a Profile."""
        if not extension_ids:
            return []
        by_id = await self._repo.get_many(extension_ids)
        ordered: list[ExtensionAssetRecord] = []
        seen_chromium_ids: dict[str, str] = {}
        for asset_id in extension_ids:
            record = by_id.get(asset_id)
            if record is None:
                raise ExtensionBindingError(
                    f"Managed extension asset {asset_id} does not exist"
                )
            if not record.verified:
                raise ExtensionBindingError(
                    f"Managed extension asset {asset_id} failed verification"
                )
            if self._extensions_root is not None:
                ext_dir = self._extensions_root / asset_id
                verdict = await asyncio.to_thread(
                    verify_extension_directory,
                    ext_dir,
                    expected_asset_id=record.id,
                    expected_chromium_id=record.chromium_id,
                    expected_file_hashes=record.integrity.get("file_hashes"),
                )
                if not verdict["ok"]:
                    raise ExtensionBindingError(
                        f"Managed extension asset {asset_id} directory invalid: "
                        + "; ".join(verdict["problems"])
                    )
            if record.chromium_id in seen_chromium_ids:
                other = seen_chromium_ids[record.chromium_id]
                raise ExtensionBindingError(
                    f"Extensions {other} and {asset_id} share Chromium ID {record.chromium_id}"
                )
            seen_chromium_ids[record.chromium_id] = asset_id
            ordered.append(record)
        return ordered

    @staticmethod
    def _inspect_candidate_dir(entry: Path) -> tuple[dict, str, str | None, str | None] | None:
        verdict = verify_extension_directory(entry, expected_asset_id=entry.name)
        if not verdict["ok"] or not isinstance(verdict.get("manifest"), dict):
            LOGGER.warning(
                "Skipping unreadable/unverified extension directory %s: %s",
                entry.name,
                verdict.get("problems"),
            )
            return None
        name, desc, icon_relpath = extract_directory_metadata(
            entry, verdict["manifest"], verdict["file_hashes"]
        )
        return verdict, name, desc, icon_relpath

    @staticmethod
    def _scan_candidate_dirs(root: Path, existing_ids: set[str]) -> list[Path]:
        return [
            entry
            for entry in sorted(root.iterdir())
            if not entry.is_symlink()
            and entry.is_dir()
            and EXTENSION_ASSET_ID_RE.fullmatch(entry.name)
            and entry.name not in existing_ids
        ]

    async def adopt_existing(self) -> None:
        """Adopt pre-staged verified extension directories found under ``extensions_root``."""
        if self._extensions_root is None or not await asyncio.to_thread(
            self._extensions_root.is_dir
        ):
            return
        existing_records = {r.id for r in await self._repo.list_all()}
        candidates = await asyncio.to_thread(
            self._scan_candidate_dirs, self._extensions_root, existing_records
        )
        for entry in candidates:
            async with _shared_asset_lock(self._extensions_root, entry.name):
                inspected = await asyncio.to_thread(self._inspect_candidate_dir, entry)
                if inspected is None:
                    continue
                verdict, name, desc, icon_relpath = inspected
                mf = verdict["manifest"]
                manifest_sha = verdict["file_hashes"].get("manifest.json", "")
                await self._repo.upsert_verified(
                    asset_id=entry.name,
                    chromium_id=verdict["chromium_id"],
                    name=name,
                    version=str(mf.get("version", ""))[:64],
                    manifest_version=int(mf["manifest_version"]),
                    description=desc,
                    package_format="zip",
                    identity_source="manifest_key",
                    manifest_key_sha256=verdict["manifest_key_sha256"] or "",
                    archive_sha256=entry.name,
                    icon_relpath=icon_relpath,
                    file_count=int(verdict["file_count"]),
                    total_bytes=int(verdict["total_bytes"]),
                    integrity={
                        "ok": True,
                        "problems": [],
                        "manifest_sha256": manifest_sha,
                        "tree_sha256": entry.name,
                        "file_hashes": verdict["file_hashes"],
                    },
                    state="verified",
                )
