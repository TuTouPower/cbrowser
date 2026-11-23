"""t107: the new domain boundaries are directly callable and testable."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.restore_point import (
    RestorePointError,
    _assert_compatible_schema,
    _restore_paths,
    _switch_item,
)
from cbrowser.adapters.database.extension_paths_migration import (
    TrustedManagedExtension,
    _classify_managed_candidates,
)
from cbrowser.adapters.database.models import ProfileModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import Profile, ProfileConfig
from cbrowser.services.extension_catalog import ExtensionBindingError
from cbrowser.services.profile_service import (
    InvalidFontSetBindingError,
    ProfileService,
    ReferenceValidationError,
)
from cbrowser.supervisor.core import (
    ExtensionUnavailableError,
    FontSetUnavailableError,
    LifecycleConflictError,
    ProxyCredentialsChangedError,
    SupervisorCore,
)


def _config() -> ProfileConfig:
    return ProfileConfig(
        name="Alpha",
        fingerprint_seed=101,
        group_id=None,
        proxy_id=None,
        timezone="Asia/Tokyo",
        locale="en-US",
        screen_width=1920,
        screen_height=1080,
        geoip=False,
        clipboard_sync=True,
        color_scheme="light",
        fingerprint_platform="windows",
        font_set_id=None,
        include_cjk_fonts=False,
        allow_extensions=True,
        extension_ids=["a" * 64],
        set_google_default=True,
        capture_preview=True,
        restore_session=True,
        mute_audio=True,
        notes="note",
        sort_order=3,
    )


def test_config_orm_projection_covers_every_config_field() -> None:
    cfg = _config()
    model = ProfileModel(
        id="p1",
        display_number=1,
        user_data_dir="/data/p1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        current_config_version=1,
        **{
            name: (json.dumps(getattr(cfg, name)) if name == "extension_ids" else getattr(cfg, name))
            for name in ProfileConfig.model_fields
        },
    )
    read_back = ProfileRepository._profile_config_from_model(model)
    assert read_back == cfg

    target = SimpleNamespace(capture_preview_epoch=0)
    ProfileRepository._apply_config_to_model(target, cfg, cfg, 7, "2026-01-02T00:00:00Z")
    for name in ProfileConfig.model_fields:
        expected = json.dumps(getattr(cfg, name)) if name == "extension_ids" else getattr(cfg, name)
        assert getattr(target, name) == expected
    assert target.current_config_version == 7
    assert target.updated_at == "2026-01-02T00:00:00Z"


def _asset(
    asset_id: str,
    *,
    cid: str = "cid",
    version: str = "1.0.0",
    key_sha: str = "key",
    tree_sha: str = "tree",
    core: dict | None = None,
) -> TrustedManagedExtension:
    return TrustedManagedExtension(
        id=asset_id,
        chromium_id=cid,
        name=asset_id,
        version=version,
        manifest_version=3,
        description=None,
        package_format="crx3",
        identity_source="key",
        manifest_key_sha256=key_sha,
        archive_sha256="archive",
        icon_relpath=None,
        file_count=1,
        total_bytes=1,
        integrity={},
        state="verified",
        file_hashes={},
        normalized_core_hashes=core if core is not None else {"a": "1"},
    )


@pytest.mark.parametrize(
    ("info", "catalog", "expected"),
    [
        (
            {"chromium_id": "cid", "key_sha256": "key", "version": "1.0.0", "tree_sha256": "tree", "core_hashes": {"a": "1"}},
            {"one": _asset("tree")},
            "exact",
        ),
        (
            {"chromium_id": "cid", "key_sha256": "key", "version": "1.0.0", "tree_sha256": "other", "core_hashes": {"a": "1"}},
            {"one": _asset("one")},
            "core",
        ),
        (
            {"chromium_id": "cid", "key_sha256": "key", "version": "3.0.0", "tree_sha256": "tree", "core_hashes": {"a": "1"}},
            {"one": _asset("one"), "two": _asset("two", version="2.0.0")},
            "ambiguous_cid",
        ),
        (
            {"chromium_id": "cid", "key_sha256": "key", "version": "1.0.0", "tree_sha256": "other", "core_hashes": {"a": "9"}},
            {"one": _asset("one")},
            "digest_mismatch",
        ),
    ],
)
def test_managed_candidate_classification(info, catalog, expected) -> None:
    kind, matched, _peers = _classify_managed_candidates(info, catalog)
    assert kind == expected
    if expected in ("exact", "core"):
        assert len(matched) == 1
        assert matched[0].chromium_id == "cid"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ProxyCredentialsChangedError(), "proxy_credentials_changed"),
        (FontSetUnavailableError(), "font_set_unavailable"),
        (ExtensionUnavailableError(), "extension_unavailable"),
        (RuntimeError("x"), "startup_failure"),
    ],
)
def test_start_failure_reason_mapping(error, reason) -> None:
    assert SupervisorCore._start_failure_reason(error) == reason


def test_start_session_precheck_is_independent() -> None:
    core = SupervisorCore.__new__(SupervisorCore)
    running = SimpleNamespace(
        observed_state="running",
        desired_state="running",
        runtime_instance_id="inst_run",
    )
    stale = SimpleNamespace(
        observed_state="stopped",
        desired_state="stopped",
        runtime_instance_id="inst_stale",
    )
    core._sessions = {"p1": running}
    assert core._start_session_precheck("p1") == (running, None)
    core._sessions = {"p1": stale}
    assert core._start_session_precheck("p1") == (None, stale)
    core._sessions = {
        "p1": SimpleNamespace(
            observed_state="stopping",
            desired_state="stopped",
            runtime_instance_id="inst",
        )
    }
    with pytest.raises(LifecycleConflictError):
        core._start_session_precheck("p1")
    core._sessions = {}
    assert core._start_session_precheck("p1") == (None, None)


def test_restore_paths_and_schema_guard_are_independent(tmp_path: Path) -> None:
    args = SimpleNamespace(
        point=str(tmp_path / "point"),
        db=str(tmp_path / "db.sqlite"),
        data_root=str(tmp_path / "data"),
        journal=str(tmp_path / "journal.json"),
    )
    point, db, data_root, journal = _restore_paths(args)
    assert (point, db, data_root, journal) == (
        tmp_path / "point",
        tmp_path / "db.sqlite",
        tmp_path / "data",
        tmp_path / "journal.json",
    )
    _assert_compatible_schema(db, {"db": {"schema_stamp": "x"}})
    db.write_bytes(b"sqlite")
    with pytest.raises(RestorePointError):
        _assert_compatible_schema(db, {"db": {"schema_stamp": "other"}})


def test_switch_item_renames_live_and_writes_journal(tmp_path: Path) -> None:
    live = tmp_path / "live"
    staged = tmp_path / "staged"
    previous = tmp_path / "previous"
    live.write_text("old")
    staged.write_text("new")
    journal_path = tmp_path / "journal.json"
    journal = {"version": 1, "phase": "switching", "items": []}
    item = {
        "kind": "db",
        "id": "control-db",
        "live_path": str(live),
        "staged_path": str(staged),
        "previous_path": str(previous),
        "state": "pending",
        "sidecars": True,
    }
    _switch_item(item, journal_path, journal, {"profiles": []})
    assert previous.read_text() == "old"
    assert live.read_text() == "new"
    assert item["state"] == "switched"
    assert json.loads(journal_path.read_text())["items"] == []


class _FakeRepo:
    def __init__(self, groups=None, proxies=None):
        self.groups = groups or {}
        self.proxies = proxies or {}
        self.group_calls: list[str] = []
        self.proxy_calls: list[str] = []

    async def get_group(self, group_id: str):
        self.group_calls.append(group_id)
        return self.groups.get(group_id)

    async def get_proxy(self, proxy_id: str):
        self.proxy_calls.append(proxy_id)
        return self.proxies.get(proxy_id)


class _FakeFontCatalog:
    def __init__(self, *, root: bool = True, default: str | None = "fs_mac", verified: bool = True):
        self.root = root
        self.default = default
        self.verified = verified
        self.asset_calls: list[tuple[str, str | None]] = []

    def root_configured(self) -> bool:
        return self.root

    async def default_set_id(self, platform: str) -> str | None:
        return self.default

    async def get_asset(self, platform: str, font_set_id: str | None):
        self.asset_calls.append((platform, font_set_id))
        return None if font_set_id is None else SimpleNamespace(verified=self.verified)


class _FakeExtensionCatalog:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[list[str]] = []

    async def validate_binding(self, ids: list[str]) -> None:
        self.calls.append(ids)
        if self.error is not None:
            raise self.error


def _profile() -> Profile:
    return Profile(
        id="p1",
        display_number=1,
        config=_config(),
        user_data_dir="/data/p1",
        current_config_version=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _service(repo) -> ProfileService:
    return ProfileService(repo)


@pytest.mark.asyncio
async def test_validate_patch_references_directly() -> None:
    repo = _FakeRepo()
    service = _service(repo)
    with pytest.raises(ReferenceValidationError) as exc:
        await service._validate_patch_references(
            {"group_id": "missing_g", "proxy_id": "missing_p"}
        )
    assert [item["loc"] for item in exc.value.details] == [
        ["body", "group_id"],
        ["body", "proxy_id"],
    ]
    assert repo.group_calls == ["missing_g"]
    assert repo.proxy_calls == ["missing_p"]

    repo.group_calls.clear()
    repo.proxy_calls.clear()
    await service._validate_patch_references({"group_id": None, "proxy_id": None})
    assert repo.group_calls == []
    assert repo.proxy_calls == []


@pytest.mark.asyncio
async def test_validate_patch_extensions_directly() -> None:
    current = _profile()
    catalog = _FakeExtensionCatalog()
    service = _service(_FakeRepo())
    service.set_extension_catalog(catalog)

    await service._validate_patch_extensions(current, {"allow_extensions": True})
    assert catalog.calls == [["a" * 64]]

    await service._validate_patch_extensions(
        current, {"extension_ids": ["b" * 64]}
    )
    assert catalog.calls[-1] == ["b" * 64]

    await service._validate_patch_extensions(current, {"notes": "x"})
    assert len(catalog.calls) == 2

    failing = _FakeExtensionCatalog(ExtensionBindingError("blocked"))
    service.set_extension_catalog(failing)
    with pytest.raises(ReferenceValidationError):
        await service._validate_patch_extensions(
            current, {"extension_ids": ["c" * 64]}
        )


@pytest.mark.asyncio
async def test_resolve_platform_binding_directly() -> None:
    current = _profile()
    catalog = _FakeFontCatalog()
    service = _service(_FakeRepo())
    service.set_font_catalog(catalog)

    patch_dict, patch_data = await service._resolve_platform_binding(
        current, {"fingerprint_platform": "macos"}, _config()
    )
    assert patch_dict["font_set_id"] == "fs_mac"
    assert patch_data.font_set_id == "fs_mac"
    assert catalog.asset_calls == [("macos", "fs_mac")]

    catalog.default = None
    with pytest.raises(InvalidFontSetBindingError):
        await service._resolve_platform_binding(
            current, {"fingerprint_platform": "macos"}, _config()
        )

    same_platform_patch, _ = await service._resolve_platform_binding(
        current, {"font_set_id": "fs_other"}, _config()
    )
    assert same_platform_patch["font_set_id"] == "fs_other"
