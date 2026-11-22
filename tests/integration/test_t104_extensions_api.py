"""t104 AC-001 / AC-002 integration tests: managed extension upload, 409 delete guard, Profile bindings & 422s."""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.api.app import create_app
from tests.unit.test_t104_extensions_manifest import (
    _generate_rsa_pub_der,
    _make_crx3_bytes,
    _make_zip_bytes,
)


@pytest.fixture
def ext_api(tmp_path: Path):
    db_file = tmp_path / "ext.db"
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    sup_file = tmp_path / "sup.token"
    sup_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    sup_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        data_root=data_root,
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
        yield client, db_file, data_root


def _make_sample_crx(tmp_path: Path, *, name_key: str, ext_name: str, version: str = "1.0.0", with_icon: bool = True):
    priv, pub_der, b64, cid = _generate_rsa_pub_der(tmp_path, name_key)
    _, extra_pub, _, _ = _generate_rsa_pub_der(tmp_path, f"{name_key}_extra")
    manifest = {
        "manifest_version": 3,
        "name": ext_name,
        "version": version,
        "description": f"Description for {ext_name}",
    }
    entries: dict[str, bytes] = {}
    if with_icon:
        manifest["icons"] = {"48": "icon.png"}
        entries["icon.png"] = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    entries["manifest.json"] = json.dumps(manifest).encode()
    entries["bg.js"] = f"// {ext_name}\n".encode()
    zip_bytes = _make_zip_bytes(entries)
    crx_bytes = _make_crx3_bytes(zip_bytes, pub_der=pub_der, priv_pem=priv, extra_pub_der=extra_pub)
    return crx_bytes, cid, zip_bytes, b64


def test_upload_rejections_dedup_icon_and_delete(ext_api, tmp_path: Path) -> None:
    client, _, data_root = ext_api

    assert client.post("/api/v1/extensions", content=b"").status_code == 422
    assert client.post("/api/v1/extensions", content=b"not-a-zip-or-crx").status_code == 422

    # Keyless ZIP has indeterminate Chrome ID -> rejected 422
    keyless_zip = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": "NoKey", "version": "1.0.0"}
            ).encode(),
            "bg.js": b"1;",
        }
    )
    assert client.post("/api/v1/extensions?filename=nokey.zip", content=keyless_zip).status_code == 422

    # Invalid manifest_version -> 422
    _, _, b64, _ = _generate_rsa_pub_der(tmp_path, "bad_mv")
    bad_mv = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 1, "name": "Old", "version": "1.0.0", "key": b64}
            ).encode(),
        }
    )
    assert client.post("/api/v1/extensions?filename=old.zip", content=bad_mv).status_code == 422

    # Valid CRX3 upload -> 201, metadata + PNG icon + security headers
    crx_bytes, expected_cid, _, _ = _make_sample_crx(tmp_path, name_key="alpha", ext_name="Alpha Vault", version="2.4.1")
    up1 = client.post("/api/v1/extensions?filename=alpha.crx", content=crx_bytes)
    assert up1.status_code == 201, up1.text
    meta = up1.json()
    asset_id = meta["id"]
    assert len(asset_id) == 64
    assert meta["chromium_id"] == expected_cid
    assert meta["name"] == "Alpha Vault"
    assert meta["version"] == "2.4.1"
    assert meta["package_format"] == "crx3"
    assert meta["has_icon"] is True
    assert client.get("/api/v1/extensions").json()["items"][0]["id"] == asset_id
    assert meta["icon_url"] == f"/api/v1/extensions/{asset_id}/icon"
    assert meta["integrity"]["ok"] is True
    assert meta["used_by_count"] == 0

    # Duplicate upload -> idempotent 200
    up2 = client.post("/api/v1/extensions?filename=alpha.crx", content=crx_bytes)
    assert up2.status_code == 200
    assert up2.json()["id"] == asset_id

    icon_resp = client.get(meta["icon_url"])
    assert icon_resp.status_code == 200
    assert icon_resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in icon_resp.headers["content-security-policy"]

    used_by = client.get(f"/api/v1/extensions/{asset_id}/used-by")
    assert used_by.status_code == 200
    assert used_by.json() == {"asset_id": asset_id, "entries": []}

    # Unused asset deletes cleanly and removes unpacked directory
    assert client.delete(f"/api/v1/extensions/{asset_id}").status_code == 204
    assert not (data_root / "extensions" / asset_id).exists()
    assert client.get(f"/api/v1/extensions/{asset_id}").status_code == 404


def test_delete_409_protection_current_and_bound_runtime_version(ext_api, tmp_path: Path) -> None:
    client, db_file, _ = ext_api
    crx_a, _, _, _ = _make_sample_crx(tmp_path, name_key="a", ext_name="Ext A")
    crx_b, _, _, _ = _make_sample_crx(tmp_path, name_key="b", ext_name="Ext B")
    id_a = client.post("/api/v1/extensions?filename=a.crx", content=crx_a).json()["id"]
    id_b = client.post("/api/v1/extensions?filename=b.crx", content=crx_b).json()["id"]

    p1 = client.post(
        "/api/v1/profiles",
        json={"name": "P1", "allow_extensions": True, "extension_ids": [id_a]},
    )
    assert p1.status_code == 201, p1.text
    pid = p1.json()["id"]

    # Current reference blocks deletion with 409
    del_a = client.delete(f"/api/v1/extensions/{id_a}")
    assert del_a.status_code == 409
    assert del_a.json()["error"] == "extension_in_use"
    used_a = client.get(f"/api/v1/extensions/{id_a}/used-by").json()["entries"]
    assert len(used_a) == 1 and used_a[0]["kind"] == "current" and used_a[0]["profile_id"] == pid

    # Bind runtime v1 active/running while patching profile to v2=[id_b]
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "UPDATE profile_runtimes SET desired_state='running', observed_state='running', "
            "runtime_instance_id='inst_1', config_version=1 WHERE profile_id=?",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()

    patch = client.patch(f"/api/v1/profiles/{pid}", json={"extension_ids": [id_b]})
    assert patch.status_code == 200, patch.text
    assert patch.json()["current_config_version"] == 2
    assert patch.json()["extension_ids"] == [id_b]

    # id_a is NO LONGER in current config, yet bound v1 still protects it with 409!
    del_a_bound = client.delete(f"/api/v1/extensions/{id_a}")
    assert del_a_bound.status_code == 409
    used_bound = client.get(f"/api/v1/extensions/{id_a}/used-by").json()["entries"]
    assert used_bound[0]["kind"] == "bound"
    # id_b is protected via current config
    assert client.delete(f"/api/v1/extensions/{id_b}").status_code == 409

    # Stop runtime -> bound reference clears -> id_a deletes cleanly while id_b remains protected
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "UPDATE profile_runtimes SET desired_state='stopped', observed_state='stopped', "
            "runtime_instance_id=NULL WHERE profile_id=?",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()

    assert client.delete(f"/api/v1/extensions/{id_a}").status_code == 204

    # PATCH extension_ids=null clears list -> unbinds id_b -> delete succeeds 204
    cleared = client.patch(f"/api/v1/profiles/{pid}", json={"extension_ids": None, "allow_extensions": False})
    assert cleared.status_code == 200
    assert cleared.json()["allow_extensions"] is False
    assert cleared.json()["extension_ids"] == []
    assert client.delete(f"/api/v1/extensions/{id_b}").status_code == 204


def test_profile_contracts_reject_legacy_extension_paths_duplicates_and_bad_ids(
    ext_api, tmp_path: Path
) -> None:
    client, _, _ = ext_api

    # Legacy extension_paths strictly rejected on POST (422)
    bad_post = client.post(
        "/api/v1/profiles",
        json={"name": "Legacy", "extension_paths": ["/opt/ext"]},
    )
    assert bad_post.status_code == 422

    # Clean profile defaults
    p = client.post("/api/v1/profiles", json={"name": "DefaultOff"}).json()
    assert p["allow_extensions"] is False
    assert p["extension_ids"] == []
    pid = p["id"]

    # Legacy extension_paths strictly rejected on PATCH (422)
    assert client.patch(f"/api/v1/profiles/{pid}", json={"extension_paths": []}).status_code == 422
    # Null allow_extensions strictly rejected on PATCH (422)
    assert client.patch(f"/api/v1/profiles/{pid}", json={"allow_extensions": None}).status_code == 422
    # Non-existent asset ID -> 422
    missing = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"allow_extensions": True, "extension_ids": ["f" * 64]},
    )
    assert missing.status_code == 422

    # Upload v1 and v2 of SAME key (same Chromium ID) -> simultaneous bind rejected 422
    priv, pub_der, b64, _ = _generate_rsa_pub_der(tmp_path, "shared")
    crx_v1 = _make_crx3_bytes(
        _make_zip_bytes({"manifest.json": json.dumps({"manifest_version": 3, "name": "S", "version": "1.0", "key": b64}).encode()}),
        pub_der=pub_der,
        priv_pem=priv,
    )
    crx_v2 = _make_crx3_bytes(
        _make_zip_bytes({"manifest.json": json.dumps({"manifest_version": 3, "name": "S", "version": "2.0", "key": b64}).encode()}),
        pub_der=pub_der,
        priv_pem=priv,
    )
    id1 = client.post("/api/v1/extensions?filename=s1.crx", content=crx_v1).json()["id"]
    id2 = client.post("/api/v1/extensions?filename=s2.crx", content=crx_v2).json()["id"]
    dup_cid = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"allow_extensions": True, "extension_ids": [id1, id2]},
    )
    assert dup_cid.status_code == 422
    assert client.patch(
        f"/api/v1/profiles/{pid}",
        json={"extension_ids": [id1, id1]},
    ).status_code == 422

    # Preserve order across distinct Chromium IDs
    crx_other, _, _, _ = _make_sample_crx(tmp_path, name_key="other", ext_name="Other")
    id3 = client.post("/api/v1/extensions?filename=other.crx", content=crx_other).json()["id"]
    ok = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"allow_extensions": True, "extension_ids": [id3, id1]},
    )
    assert ok.status_code == 200
    assert ok.json()["extension_ids"] == [id3, id1]

    dup_prof = client.post(f"/api/v1/profiles/{pid}/duplicate", json={"name": "Copy"})
    assert dup_prof.status_code == 201
    assert dup_prof.json()["allow_extensions"] is True
    assert dup_prof.json()["extension_ids"] == [id3, id1]


def test_startup_adopts_pre_staged_verified_extension_directory(tmp_path: Path) -> None:
    db_file = tmp_path / "adopt.db"
    data_root = tmp_path / "data"
    run_database_migrations(db_file)
    crx_bytes, cid, _, _ = _make_sample_crx(tmp_path, name_key="pre", ext_name="PreStaged")
    from cbrowser.extensions.manifest import materialize_extension_directory, parse_extension_archive

    pkg = parse_extension_archive(crx_bytes, "pre.crx")
    materialize_extension_directory(pkg, data_root / "extensions" / pkg.asset_id)

    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    sup_file = tmp_path / "sup.token"
    sup_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    sup_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        data_root=data_root,
        admin_password_file=admin_file,
        supervisor_token_file=sup_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        items = client.get("/api/v1/extensions").json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == pkg.asset_id
        assert items[0]["chromium_id"] == cid


def test_patch_allow_extensions_only_and_missing_profile_returns_expected_status(
    ext_api,
) -> None:
    client, _, _ = ext_api
    created = client.post("/api/v1/profiles", json={"name": "FreeModeToggle"})
    assert created.status_code == 201
    pid = created.json()["id"]

    # Patching only {"allow_extensions": true} (Free Mode toggle) succeeds cleanly with 200.
    toggled = client.patch(f"/api/v1/profiles/{pid}", json={"allow_extensions": True})
    assert toggled.status_code == 200
    assert toggled.json()["allow_extensions"] is True
    assert toggled.json()["extension_ids"] == []

    # Non-existent profile returns 404 (never 500 AttributeError/UnboundLocalError).
    missing_free = client.patch(
        "/api/v1/profiles/missing-profile-id",
        json={"allow_extensions": True},
    )
    assert missing_free.status_code == 404

    missing_platform = client.patch(
        "/api/v1/profiles/missing-profile-id",
        json={"fingerprint_platform": "windows", "allow_extensions": True},
    )
    assert missing_platform.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_delete_import_and_profile_binding_preserve_invariants(
    tmp_path: Path,
) -> None:
    import asyncio
    from cbrowser.adapters.database.extension_repository import ExtensionAssetRepository
    from cbrowser.adapters.database.migrations import run_database_migrations
    from cbrowser.adapters.database.repository import ProfileRepository
    from cbrowser.adapters.database.session import create_engine_and_maker
    from cbrowser.domain.models import ProfileConfig
    from cbrowser.services.extension_catalog import (
        ExtensionCatalogService,
        ExtensionInUseError,
    )
    from cbrowser.services.profile_service import (
        ProfileService,
        ReferenceValidationError,
    )

    db_file = tmp_path / "race.db"
    data_root = tmp_path / "data"
    run_database_migrations(db_file)
    crx_bytes, _, _, _ = _make_sample_crx(tmp_path, name_key="race", ext_name="RaceExt")

    engine, sm = create_engine_and_maker(db_file)
    try:
        cat_a = ExtensionCatalogService(ExtensionAssetRepository(sm), data_root=data_root)
        cat_b = ExtensionCatalogService(ExtensionAssetRepository(sm), data_root=data_root)
        svc = ProfileService(ProfileRepository(sm), data_root=data_root)
        svc.set_extension_catalog(cat_a)

        rec, created = await cat_a.import_bytes(crx_bytes, "race.crx")
        assert created is True
        asset_id = rec.id

        # 1. Concurrent delete_asset vs import_bytes across catalog instances must leave DB & disk consistent.
        for _ in range(5):
            await cat_a.import_bytes(crx_bytes, "race.crx")
            res_del, res_imp = await asyncio.gather(
                cat_a.delete_asset(asset_id),
                cat_b.import_bytes(crx_bytes, "race.crx"),
                return_exceptions=True,
            )
            assert res_del is None
            assert not isinstance(res_imp, BaseException)
            live = await cat_a.get_asset(asset_id)
            on_disk = (data_root / "extensions" / asset_id / "manifest.json").is_file()
            if live is not None:
                assert on_disk, "Verified DB record must never lose its on-disk directory"
            else:
                assert not on_disk

        # 2. Concurrent delete_asset vs create_profile referencing asset_id must never leave a dangling profile.
        await cat_a.import_bytes(crx_bytes, "race.crx")
        prof_cfg = ProfileConfig(
            name="ConcurrentBind",
            allow_extensions=True,
            extension_ids=[asset_id],
        )
        out_create, out_delete = await asyncio.gather(
            svc.create_profile(prof_cfg),
            cat_b.delete_asset(asset_id),
            return_exceptions=True,
        )
        if isinstance(out_create, ReferenceValidationError):
            assert out_delete is None
            assert await cat_a.get_asset(asset_id) is None
        else:
            assert not isinstance(out_create, BaseException)
            assert isinstance(out_delete, ExtensionInUseError)
            assert await cat_a.get_asset(asset_id) is not None
    finally:
        await engine.dispose()
