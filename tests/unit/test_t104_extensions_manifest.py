"""t104 AC-001 unit tests: CRX3/CRX2/ZIP parsing, key derivation, and directory integrity."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from cbrowser.extensions.manifest import (
    ExtensionPackageError,
    crx_id_from_pubkey_der,
    parse_extension_archive,
    verify_extension_directory,
)


def _generate_rsa_pub_der(tmp_path: Path, name: str = "key") -> tuple[Path, bytes, str, str]:
    priv = tmp_path / f"{name}.pem"
    pub = tmp_path / f"{name}.der"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(priv), "2048"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(priv), "-pubout", "-outform", "DER", "-out", str(pub)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    der = pub.read_bytes()
    b64 = base64.b64encode(der).decode("ascii")
    cid = crx_id_from_pubkey_der(der)
    return priv, der, b64, cid


def _pb_ld(field_num: int, payload: bytes) -> bytes:
    out = bytearray()
    for val in ((field_num << 3) | 2, len(payload)):
        while True:
            byte = val & 0x7F
            val >>= 7
            out.append(byte | (0x80 if val else 0))
            if not val:
                break
    return bytes(out) + payload


def _make_zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in entries.items():
            zf.writestr(rel, data)
    return buf.getvalue()


def _make_crx3_bytes(zip_bytes: bytes, *, pub_der: bytes, priv_pem: Path | None = None, extra_pub_der: bytes | None = None) -> bytes:
    crx_id = hashlib.sha256(pub_der).digest()[:16]
    signed_header_data = _pb_ld(1, crx_id)
    sig = b"dummy-sig"
    if priv_pem is not None:
        msg = b"Crx3 SignedData\x00" + struct.pack("<I", len(signed_header_data)) + signed_header_data + zip_bytes
        sig = subprocess.check_output(["openssl", "dgst", "-sha256", "-sign", str(priv_pem)], input=msg)
    header = b""
    if extra_pub_der is not None:
        header += _pb_ld(2, _pb_ld(1, extra_pub_der) + _pb_ld(2, b"other-sig"))
    header += _pb_ld(2, _pb_ld(1, pub_der) + _pb_ld(2, sig))
    header += _pb_ld(10000, signed_header_data)
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + zip_bytes


def test_parse_zip_with_key_and_localized_manifest(tmp_path: Path) -> None:
    _, _, b64, expected_cid = _generate_rsa_pub_der(tmp_path)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"icon"
    zip_bytes = _make_zip_bytes(
        {
            "pkg/manifest.json": json.dumps(
                {
                    "manifest_version": 3,
                    "name": "__MSG_extName__",
                    "version": "1.2.3",
                    "default_locale": "en",
                    "icons": {"128": "images/icon128.png"},
                    "key": b64,
                }
            ).encode(),
            "pkg/_locales/en/messages.json": json.dumps(
                {"extName": {"message": "Synth Vault"}}
            ).encode(),
            "pkg/images/icon128.png": png_bytes,
        }
    )
    pkg = parse_extension_archive(zip_bytes, "synth.zip")
    assert pkg.name == "Synth Vault"
    assert pkg.version == "1.2.3"
    assert pkg.chromium_id == expected_cid
    assert pkg.package_format == "zip"
    assert pkg.identity_source == "manifest_key"
    assert pkg.icon_relpath == "images/icon128.png"
    assert "manifest.json" in pkg.files


def test_parse_crx3_selects_matching_proof_and_injects_key(tmp_path: Path) -> None:
    priv, pub_der, _, expected_cid = _generate_rsa_pub_der(tmp_path, "main")
    _, extra_der, _, _ = _generate_rsa_pub_der(tmp_path, "rotated")
    zip_bytes = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {
                    "manifest_version": 3,
                    "name": "Bitwarden Test",
                    "version": "2026.11.0",
                }
            ).encode(),
        }
    )
    crx = _make_crx3_bytes(zip_bytes, pub_der=pub_der, priv_pem=priv, extra_pub_der=extra_der)
    pkg = parse_extension_archive(crx, "bitwarden.crx")
    assert pkg.package_format == "crx3"
    assert pkg.identity_source == "crx3_header"
    assert pkg.chromium_id == expected_cid
    materialized_mf = json.loads(pkg.files["manifest.json"].decode())
    assert materialized_mf["key"] == base64.b64encode(pub_der).decode("ascii")


def test_parse_rejects_missing_key_zip_corrupt_archive_and_traversal(tmp_path: Path) -> None:
    no_key_zip = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": "NoKey", "version": "1.0.0"}
            ).encode()
        }
    )
    with pytest.raises(ExtensionPackageError) as exc_nokey:
        parse_extension_archive(no_key_zip, "nokey.zip")
    assert exc_nokey.value.code == "indeterminate_extension_identity"

    bad_manifest_zip = _make_zip_bytes({"manifest.json": b"{bad json"})
    with pytest.raises(ExtensionPackageError) as exc_mf:
        parse_extension_archive(bad_manifest_zip, "bad.zip")
    assert exc_mf.value.code == "invalid_extension_manifest"

    with pytest.raises(ExtensionPackageError) as exc_corrupt:
        parse_extension_archive(b"Cr24\x03\x00\x00\x00bad", "broken.crx")
    assert exc_corrupt.value.code == "corrupt_extension_archive"

    _, _, b64, _ = _generate_rsa_pub_der(tmp_path)
    trav_zip = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": "T", "version": "1.0", "key": b64}
            ).encode(),
            "../evil.txt": b"boom",
        }
    )
    with pytest.raises(ExtensionPackageError) as exc_trav:
        parse_extension_archive(trav_zip, "trav.zip")
    assert exc_trav.value.code == "invalid_extension_archive"


def test_verify_extension_directory_detects_tampering(tmp_path: Path) -> None:
    _, _, b64, expected_cid = _generate_rsa_pub_der(tmp_path)
    zip_bytes = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": "Check", "version": "1.0.0", "key": b64}
            ).encode(),
            "bg.js": b"console.log(1);",
        }
    )
    pkg = parse_extension_archive(zip_bytes, "check.zip")
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    for rel, content in pkg.files.items():
        dest = ext_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    ok_verdict = verify_extension_directory(
        ext_dir,
        expected_asset_id=pkg.asset_id,
        expected_chromium_id=expected_cid,
        expected_file_hashes=pkg.file_hashes,
    )
    assert ok_verdict["ok"] is True

    (ext_dir / "bg.js").write_bytes(b"console.log(2);")
    bad_verdict = verify_extension_directory(
        ext_dir,
        expected_asset_id=pkg.asset_id,
        expected_chromium_id=expected_cid,
        expected_file_hashes=pkg.file_hashes,
    )
    assert bad_verdict["ok"] is False
    assert any("mismatch" in p or "modified" in p for p in bad_verdict["problems"])


def test_unpack_rejects_zip_bomb_with_forged_file_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os as _os
    import zipfile as _zf
    import cbrowser.extensions.manifest as mf_mod

    _, _, b64, _ = _generate_rsa_pub_der(tmp_path)
    # 1) Real ZIP whose compressed member expands well beyond budget -> rejected via budget guard.
    payload = b"".join(_os.urandom(128) + b"A" * 1024 for _ in range(16))
    raw_zip = _make_zip_bytes(
        {
            "manifest.json": json.dumps(
                {"manifest_version": 3, "name": "Bomb", "version": "1.0.0", "key": b64}
            ).encode(),
            "big.bin": payload,
        }
    )
    # 2) Forging header file_size (len(payload) -> 1) cannot slip past bounded open/CRC checks.
    actual_le = struct.pack("<I", len(payload))
    forged_le = struct.pack("<I", 1)
    assert raw_zip.count(actual_le) >= 2
    forged_zip = raw_zip.replace(actual_le, forged_le)
    with _zf.ZipFile(io.BytesIO(forged_zip), "r") as zf:
        assert zf.getinfo("big.bin").file_size == 1

    monkeypatch.setattr(mf_mod, "MAX_EXTENSION_UNPACKED_BYTES", 4096)
    with pytest.raises(ExtensionPackageError) as exc_over:
        parse_extension_archive(raw_zip, "overbudget.zip")
    assert exc_over.value.code == "invalid_extension_archive"
    assert "budget" in exc_over.value.message

    with pytest.raises(ExtensionPackageError) as exc_forged:
        parse_extension_archive(forged_zip, "bomb.zip")
    assert exc_forged.value.code in ("corrupt_extension_archive", "invalid_extension_archive")

    # 3) Direct streaming-budget proof: if a decompressor stream ignores declared file_size=1
    #    and emits > remaining bytes, _read_bounded_zip_entry halts immediately without reading all bytes.
    total_read = 0

    class _TrackingStream:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self, n=-1):
            nonlocal total_read
            take = min(n if n and n > 0 else 100_000, max(0, 100_000 - total_read))
            total_read += take
            return b"Z" * take

    class _StreamZip:
        def open(self, _info, _mode="r"):
            return _TrackingStream()

    fake_info = _zf.ZipInfo("big.bin")
    fake_info.file_size = 1
    with pytest.raises(ExtensionPackageError) as exc_stream:
        mf_mod._read_bounded_zip_entry(_StreamZip(), fake_info, remaining=4096)
    assert exc_stream.value.code == "invalid_extension_archive"
    assert "budget" in exc_stream.value.message
    assert total_read == 4097
