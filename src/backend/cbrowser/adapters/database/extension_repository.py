"""t104: persistence for managed extension assets and profile/bound-version reference tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cbrowser.adapters.database.models import (
    ExtensionAssetModel,
    ProfileConfigVersionModel,
    ProfileModel,
    ProfileRuntimeModel,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import ExtensionUsedByEntry, utc_now_iso

ACTIVE_BINDING_STATES = frozenset({"starting", "running", "stopping"})


@dataclass(frozen=True)
class ExtensionAssetRecord:
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
    integrity: dict
    state: str
    created_at: str
    updated_at: str

    @property
    def verified(self) -> bool:
        return self.state == "verified"

    @property
    def problems(self) -> list[str]:
        return [str(p) for p in self.integrity.get("problems", [])]

    @property
    def has_icon(self) -> bool:
        return bool(self.icon_relpath)


def _snapshot(row: ExtensionAssetModel) -> ExtensionAssetRecord:
    return ExtensionAssetRecord(
        id=row.id,
        chromium_id=row.chromium_id,
        name=row.name,
        version=row.version,
        manifest_version=row.manifest_version,
        description=row.description,
        package_format=row.package_format,
        identity_source=row.identity_source,
        manifest_key_sha256=row.manifest_key_sha256,
        archive_sha256=row.archive_sha256,
        icon_relpath=row.icon_relpath,
        file_count=row.file_count,
        total_bytes=row.total_bytes,
        integrity=json.loads(row.integrity or "{}"),
        state=row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _decode_extension_id_list(raw_ids: str | None) -> list[str]:
    if not raw_ids:
        return []
    try:
        parsed = json.loads(raw_ids)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str) and item]


def _extract_extension_ids(snapshot_json: str | None) -> list[str]:
    if not snapshot_json:
        return []
    try:
        parsed = json.loads(snapshot_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []
    cfg = parsed.get("config") if isinstance(parsed.get("config"), dict) else parsed
    raw = cfg.get("extension_ids") if isinstance(cfg, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str) and item]


class ExtensionAssetRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def get(self, asset_id: str) -> ExtensionAssetRecord | None:
        async with self._session_maker() as session:
            row = await session.get(ExtensionAssetModel, asset_id)
            return _snapshot(row) if row is not None else None

    async def get_many(self, asset_ids: list[str]) -> dict[str, ExtensionAssetRecord]:
        if not asset_ids:
            return {}
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(ExtensionAssetModel).where(ExtensionAssetModel.id.in_(asset_ids))
                )
            ).scalars().all()
            return {row.id: _snapshot(row) for row in rows}

    async def list_all(self) -> list[ExtensionAssetRecord]:
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(ExtensionAssetModel).order_by(
                        ExtensionAssetModel.name,
                        ExtensionAssetModel.version,
                        ExtensionAssetModel.id,
                    )
                )
            ).scalars().all()
            return [_snapshot(row) for row in rows]

    async def upsert_verified(
        self,
        *,
        asset_id: str,
        chromium_id: str,
        name: str,
        version: str,
        manifest_version: int,
        description: str | None,
        package_format: str,
        identity_source: str,
        manifest_key_sha256: str,
        archive_sha256: str,
        icon_relpath: str | None,
        file_count: int,
        total_bytes: int,
        integrity: dict,
        state: str = "verified",
    ) -> tuple[ExtensionAssetRecord, bool]:
        """Insert or reuse a verified asset record atomically; returns (record, created)."""
        async with self._session_maker() as session, write_transaction(session):
            now = utc_now_iso()
            existing = await session.get(ExtensionAssetModel, asset_id)
            if existing is not None:
                if existing.state == "verified":
                    return _snapshot(existing), False
                existing.chromium_id = chromium_id
                existing.name = name
                existing.version = version
                existing.manifest_version = manifest_version
                existing.description = description
                existing.package_format = package_format
                existing.identity_source = identity_source
                existing.manifest_key_sha256 = manifest_key_sha256
                existing.archive_sha256 = archive_sha256
                existing.icon_relpath = icon_relpath
                existing.file_count = file_count
                existing.total_bytes = total_bytes
                existing.integrity = json.dumps(integrity, sort_keys=True)
                existing.state = state
                existing.updated_at = now
                await session.flush()
                return _snapshot(existing), False

            row = ExtensionAssetModel(
                id=asset_id,
                chromium_id=chromium_id,
                name=name,
                version=version,
                manifest_version=manifest_version,
                description=description,
                package_format=package_format,
                identity_source=identity_source,
                manifest_key_sha256=manifest_key_sha256,
                archive_sha256=archive_sha256,
                icon_relpath=icon_relpath,
                file_count=file_count,
                total_bytes=total_bytes,
                integrity=json.dumps(integrity, sort_keys=True),
                state=state,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            return _snapshot(row), True

    @staticmethod
    def _mark_ref(
        refs: dict[str, dict[str, str]],
        target_ids: set[str] | None,
        asset_id: str,
        profile_id: str,
        kind: str,
    ) -> None:
        if target_ids is not None and asset_id not in target_ids:
            return
        per_asset = refs.setdefault(asset_id, {})
        prev = per_asset.get(profile_id)
        if prev is None:
            per_asset[profile_id] = kind
        elif prev != kind:
            per_asset[profile_id] = "both"

    @classmethod
    async def _collect_profile_refs(
        cls,
        session: AsyncSession,
        refs: dict[str, dict[str, str]],
        target_ids: set[str] | None,
    ) -> None:
        profile_rows = (
            await session.execute(select(ProfileModel.id, ProfileModel.extension_ids))
        ).all()
        for pid, raw_ids in profile_rows:
            for ext_id in _decode_extension_id_list(raw_ids):
                cls._mark_ref(refs, target_ids, ext_id, str(pid), "current")

    @classmethod
    async def _collect_bound_runtime_refs(
        cls,
        session: AsyncSession,
        refs: dict[str, dict[str, str]],
        target_ids: set[str] | None,
    ) -> None:
        bound_runtimes = (
            await session.execute(
                select(
                    ProfileRuntimeModel.profile_id,
                    ProfileRuntimeModel.config_version,
                    ProfileRuntimeModel.runtime_instance_id,
                    ProfileRuntimeModel.desired_state,
                    ProfileRuntimeModel.observed_state,
                )
            )
        ).all()
        bound_pairs = [
            (str(pid), int(ver))
            for pid, ver, instance_id, desired, observed in bound_runtimes
            if instance_id is not None or desired == "running" or observed in ACTIVE_BINDING_STATES
        ]
        if not bound_pairs:
            return
        snap_rows = (
            await session.execute(
                select(ProfileConfigVersionModel.profile_id, ProfileConfigVersionModel.snapshot).where(
                    tuple_(
                        ProfileConfigVersionModel.profile_id,
                        ProfileConfigVersionModel.version,
                    ).in_(bound_pairs)
                )
            )
        ).all()
        for pid, snap in snap_rows:
            for ext_id in _extract_extension_ids(snap):
                cls._mark_ref(refs, target_ids, ext_id, str(pid), "bound")

    @classmethod
    async def _reference_map(
        cls, session: AsyncSession, target_ids: set[str] | None = None
    ) -> dict[str, dict[str, str]]:
        """Map asset_id -> {profile_id: 'current' | 'bound' | 'both'} across current & bound versions."""
        refs: dict[str, dict[str, str]] = {}
        await cls._collect_profile_refs(session, refs, target_ids)
        await cls._collect_bound_runtime_refs(session, refs, target_ids)
        return refs

    async def usage_counts(self) -> dict[str, int]:
        async with self._session_maker() as session:
            refs = await self._reference_map(session)
            return {asset_id: len(per_profile) for asset_id, per_profile in refs.items()}

    async def get_used_by(self, asset_id: str) -> list[ExtensionUsedByEntry] | None:
        async with self._session_maker() as session:
            existing = await session.get(ExtensionAssetModel, asset_id)
            if existing is None:
                return None
            refs = await self._reference_map(session, {asset_id})
            per_asset = refs.get(asset_id, {})
            if not per_asset:
                return []
            profile_meta = {
                str(pid): (str(name), int(num))
                for pid, name, num in (
                    await session.execute(
                        select(
                            ProfileModel.id, ProfileModel.name, ProfileModel.display_number
                        ).where(ProfileModel.id.in_(list(per_asset)))
                    )
                ).all()
            }
            observed = {
                str(pid): state
                for pid, state in (
                    await session.execute(
                        select(
                            ProfileRuntimeModel.profile_id,
                            ProfileRuntimeModel.observed_state,
                        ).where(ProfileRuntimeModel.profile_id.in_(list(per_asset)))
                    )
                ).all()
            }
            entries: list[ExtensionUsedByEntry] = []
            for pid in sorted(per_asset):
                name, num = profile_meta.get(pid, (pid, 0))
                entries.append(
                    ExtensionUsedByEntry(
                        profile_id=pid,
                        profile_name=name,
                        display_number=num,
                        kind=per_asset[pid],  # type: ignore[arg-type]
                        observed_state=observed.get(pid),
                    )
                )
            return entries

    async def delete_if_unused(self, asset_id: str) -> tuple[str, int]:
        """Atomically delete ``asset_id`` only when unreferenced; returns (status, used_by_count)."""
        async with self._session_maker() as session, write_transaction(session):
            existing = await session.get(ExtensionAssetModel, asset_id)
            if existing is None:
                return "not_found", 0
            refs = await self._reference_map(session, {asset_id})
            used = refs.get(asset_id, {})
            if used:
                return "in_use", len(used)
            await session.execute(
                delete(ExtensionAssetModel).where(ExtensionAssetModel.id == asset_id)
            )
            return "deleted", 0
