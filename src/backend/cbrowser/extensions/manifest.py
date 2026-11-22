"""Managed extension package parsing, cryptographic ID derivation, and verification.

Pure Python stdlib (zero runtime dependencies beyond core Python).
Follows ADR 029 / s029 / d055:
- Supports ``.crx`` (CRX3 / CRX2) and ``.zip`` packages.
- Extracts RSA/ECDSA DER public key from CRX headers (matching CRX3
  ``SignedHeaderData.crx_id`` across multiple proofs) or validates
  ``manifest.json["key"]`` on ZIP packages, deriving canonical 32-char
  Chromium extension IDs (``[a-p]{32}``).
- Ensures materialized managed directories carry normalized ``manifest.json["key"]``
  so Chromium runtime IDs remain identical regardless of mount path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXTENSIONS_DIR_NAME = "extensions"
EXTENSION_MOUNT_ROOT = Path("/run/cbrowser/extensions")
EXTENSION_UNAVAILABLE = "extension_unavailable"
EXTENSION_ASSET_ID_RE = re.compile(r"^[a-f0-9]{64}$")
CHROMIUM_EXTENSION_ID_RE = re.compile(r"^[a-p]{32}$")
_ARCHIVE_ID_FILE_MODE = 0o640
_DIR_MODE = 0o750

MAX_EXTENSION_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXTENSION_UNPACKED_BYTES = 256 * 1024 * 1024
MAX_EXTENSION_FILES = 10_000
MAX_ICON_BYTES = 2 * 1024 * 1024

ALLOWED_ICON_EXTENSIONS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
_MSG_PLACEHOLDER_RE = re.compile(r"^__MSG_([A-Za-z0-9_@]+)__$")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")


class ExtensionPackageError(ValueError):
    """Structured rejection for malformed, insecure, or unidentifiable extensions."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedExtensionPackage:
    asset_id: str
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
    manifest_sha256: str
    file_hashes: dict[str, str]
    files: dict[str, bytes]


def crx_id_from_pubkey_der(pubkey_der: bytes) -> str:
    """Derive Chromium 32-char extension ID from ASN.1 DER SubjectPublicKeyInfo bytes."""
    if not isinstance(pubkey_der, (bytes, bytearray)) or len(pubkey_der) < 32:
        raise ExtensionPackageError(
            "indeterminate_extension_identity",
            "Extension public key must be valid DER-encoded bytes (>= 32 bytes)",
        )
    if pubkey_der[0] != 0x30:
        raise ExtensionPackageError(
            "indeterminate_extension_identity",
            "Extension public key is not a valid ASN.1 DER SEQUENCE",
        )
    digest = hashlib.sha256(pubkey_der).digest()[:16]
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in digest)


def parse_manifest_key(key_b64: Any) -> tuple[bytes, str]:
    """Decode ``manifest.json["key"]`` and return ``(pubkey_der, chromium_id)``."""
    if not isinstance(key_b64, str) or not key_b64.strip():
        raise ExtensionPackageError(
            "indeterminate_extension_identity",
            "Missing or empty manifest public key",
        )
    cleaned = "".join(key_b64.split())
    try:
        der = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError):
        raise ExtensionPackageError(
            "indeterminate_extension_identity",
            "Manifest public key is not valid base64",
        ) from None
    return der, crx_id_from_pubkey_der(der)


def _read_varint(buf: bytes, idx: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while idx < len(buf) and shift <= 63:
        b = buf[idx]
        idx += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, idx
        shift += 7
    raise ExtensionPackageError("corrupt_extension_archive", "Truncated CRX3 protobuf varint")


def _parse_proto_ld_fields(buf: bytes) -> list[tuple[int, bytes]]:
    """Decode length-delimited & varint fields from a CRX3 protobuf message."""
    idx = 0
    out: list[tuple[int, bytes]] = []
    while idx < len(buf):
        tag, idx = _read_varint(buf, idx)
        field_num, wire_type = tag >> 3, tag & 7
        if wire_type == 2:
            length, idx = _read_varint(buf, idx)
            if idx + length > len(buf):
                raise ExtensionPackageError(
                    "corrupt_extension_archive", "Truncated CRX3 protobuf field"
                )
            out.append((field_num, buf[idx : idx + length]))
            idx += length
        elif wire_type == 0:
            _, idx = _read_varint(buf, idx)
        else:
            raise ExtensionPackageError(
                "corrupt_extension_archive",
                f"Unsupported CRX3 protobuf wire type {wire_type}",
            )
    return out


def _crx3_signed_id(fields: list[tuple[int, bytes]]) -> str:
    signed_data = next((val for fn, val in fields if fn == 10000), None)
    if signed_data is None:
        raise ExtensionPackageError(
            "corrupt_extension_archive", "CRX3 header missing signed_header_data"
        )
    signed_fields = _parse_proto_ld_fields(signed_data)
    raw_crx_id = next((val for fn, val in signed_fields if fn == 1), None)
    if raw_crx_id is None or len(raw_crx_id) != 16:
        raise ExtensionPackageError(
            "indeterminate_extension_identity", "CRX3 header missing valid 16-byte crx_id"
        )
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in raw_crx_id)


def _find_crx3_proof_key(fields: list[tuple[int, bytes]], target_id: str) -> bytes:
    for fn, proof_bytes in fields:
        if fn not in (2, 3):  # sha256_with_rsa / sha256_with_ecdsa
            continue
        pk = next((val for pfn, val in _parse_proto_ld_fields(proof_bytes) if pfn == 1), None)
        if pk is None:
            continue
        try:
            derived = crx_id_from_pubkey_der(pk)
        except ExtensionPackageError:
            continue
        if derived == target_id:
            return pk
    raise ExtensionPackageError(
        "indeterminate_extension_identity",
        "CRX3 header has no public key proof matching signed crx_id",
    )


def _select_crx3_pubkey(header: bytes) -> tuple[bytes, str]:
    fields = _parse_proto_ld_fields(header)
    target_id = _crx3_signed_id(fields)
    return _find_crx3_proof_key(fields, target_id), target_id


def extract_crx_archive(raw: bytes) -> tuple[str, bytes, bytes, str]:
    """Parse CRX2/CRX3 header and return ``(format, zip_bytes, pubkey_der, chromium_id)``."""
    if len(raw) < 12 or raw[:4] != b"Cr24":
        raise ExtensionPackageError("corrupt_extension_archive", "Invalid CRX magic header")
    version = struct.unpack("<I", raw[4:8])[0]
    if version == 3:
        header_len = struct.unpack("<I", raw[8:12])[0]
        if 12 + header_len > len(raw) or header_len == 0:
            raise ExtensionPackageError("corrupt_extension_archive", "Invalid CRX3 header length")
        header = raw[12 : 12 + header_len]
        zip_bytes = raw[12 + header_len :]
        pk, chromium_id = _select_crx3_pubkey(header)
        return "crx3", zip_bytes, pk, chromium_id
    if version == 2:
        if len(raw) < 16:
            raise ExtensionPackageError("corrupt_extension_archive", "Truncated CRX2 header")
        pk_len, sig_len = struct.unpack("<II", raw[8:16])
        offset = 16 + pk_len + sig_len
        if pk_len == 0 or offset > len(raw):
            raise ExtensionPackageError("corrupt_extension_archive", "Invalid CRX2 header lengths")
        pk = raw[16 : 16 + pk_len]
        zip_bytes = raw[offset:]
        chromium_id = crx_id_from_pubkey_der(pk)
        return "crx2", zip_bytes, pk, chromium_id
    raise ExtensionPackageError(
        "corrupt_extension_archive", f"Unsupported CRX format version {version}"
    )


def _normalize_zip_relpath(raw_name: str) -> str:
    if "\\" in raw_name or raw_name.startswith("/") or raw_name.startswith("~"):
        raise ExtensionPackageError(
            "invalid_extension_archive", f"Unsafe archive entry path: {raw_name!r}"
        )
    parts = [p for p in raw_name.split("/") if p]
    if not parts or any(p in (".", "..") or ":" in p for p in parts):
        raise ExtensionPackageError(
            "invalid_extension_archive", f"Invalid archive entry path: {raw_name!r}"
        )
    return "/".join(parts)


def _read_bounded_zip_entry(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, remaining: int
) -> bytes:
    """Stream one ZIP entry while enforcing actual decompressed byte budget ``remaining``."""
    chunks: list[bytes] = []
    read_bytes = 0
    try:
        with zf.open(info, "r") as stream:
            while True:
                to_read = min(65536, remaining - read_bytes + 1)
                chunk = stream.read(to_read)
                if not chunk:
                    break
                read_bytes += len(chunk)
                if read_bytes > remaining:
                    raise ExtensionPackageError(
                        "invalid_extension_archive",
                        "Extension unpacked size exceeds allowed budget",
                    )
                chunks.append(chunk)
    except (zipfile.BadZipFile, RuntimeError, EOFError, *zlib_error):
        raise ExtensionPackageError(
            "corrupt_extension_archive",
            f"Corrupt extension entry: {info.filename!r}",
        ) from None
    return b"".join(chunks)


def unpack_safe_zip_entries(zip_bytes: bytes) -> dict[str, bytes]:
    """Validate and extract regular files from a ZIP payload with traversal/bomb guards."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except (zipfile.BadZipFile, OSError):
        raise ExtensionPackageError(
            "corrupt_extension_archive", "Corrupt extension archive (invalid ZIP)"
        ) from None

    files: dict[str, bytes] = {}
    total_uncompressed = 0
    with zf:
        infos = zf.infolist()
        if not infos:
            raise ExtensionPackageError("corrupt_extension_archive", "Extension archive is empty")
        if len(infos) > MAX_EXTENSION_FILES:
            raise ExtensionPackageError(
                "invalid_extension_archive", "Extension archive exceeds maximum entry count"
            )
        for info in infos:
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ExtensionPackageError(
                    "invalid_extension_archive",
                    f"Symlinks are forbidden in extensions: {info.filename!r}",
                )
            if info.is_dir():
                continue
            rel = _normalize_zip_relpath(info.filename)
            remaining = MAX_EXTENSION_UNPACKED_BYTES - total_uncompressed
            if info.file_size > remaining:
                raise ExtensionPackageError(
                    "invalid_extension_archive",
                    "Extension unpacked size exceeds allowed budget",
                )
            content = _read_bounded_zip_entry(zf, info, remaining)
            total_uncompressed += len(content)
            files[rel] = content

    if not files:
        raise ExtensionPackageError("invalid_extension_archive", "Extension contains no files")
    return _normalize_manifest_root(files)


try:
    import zlib
    zlib_error: tuple[type[BaseException], ...] = (zlib.error,)
except ImportError:  # pragma: no cover
    zlib_error = ()


def _normalize_manifest_root(files: dict[str, bytes]) -> dict[str, bytes]:
    if "manifest.json" in files:
        return files
    top_dirs = {path.split("/", 1)[0] for path in files if "/" in path}
    if len(top_dirs) == 1 and all("/" in path for path in files):
        prefix = next(iter(top_dirs)) + "/"
        stripped = {path[len(prefix) :]: data for path, data in files.items()}
        if "manifest.json" in stripped:
            return stripped
    raise ExtensionPackageError(
        "invalid_extension_manifest", "Extension package is missing manifest.json"
    )


def load_locale_messages(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    locales: dict[str, dict[str, Any]] = {}
    for rel, data in files.items():
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "_locales" and parts[2] == "messages.json":
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                locales[parts[1]] = parsed
    return locales


def _locale_search_order(
    locales: Mapping[str, dict[str, Any]],
    default_locale: str | None,
) -> list[str]:
    order: list[str] = []
    if default_locale and default_locale in locales:
        order.append(default_locale)
    for fallback in ("en", "en_US", "en_GB"):
        if fallback in locales and fallback not in order:
            order.append(fallback)
    for loc in sorted(locales):
        if loc not in order:
            order.append(loc)
    return order


def resolve_i18n_field(
    value: Any,
    locales: Mapping[str, dict[str, Any]],
    default_locale: str | None,
) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    match = _MSG_PLACEHOLDER_RE.fullmatch(stripped)
    if not match:
        return stripped
    msg_key = match.group(1)
    for loc in _locale_search_order(locales, default_locale):
        entry = locales[loc].get(msg_key) or next(
            (v for k, v in locales[loc].items() if k.lower() == msg_key.lower()),
            None,
        )
        if isinstance(entry, dict) and isinstance(entry.get("message"), str):
            resolved = entry["message"].strip()
            if resolved:
                return resolved
    return stripped


def _collect_icon_candidates(manifest: Mapping[str, Any]) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []

    def _collect(mapping: Any) -> None:
        if isinstance(mapping, str):
            candidates.append((0, mapping))
        elif isinstance(mapping, Mapping):
            for size_key, rel in mapping.items():
                if not isinstance(rel, str):
                    continue
                try:
                    size_score = int(str(size_key))
                except ValueError:
                    size_score = 0
                candidates.append((size_score, rel))

    _collect(manifest.get("icons"))
    for action_key in ("action", "browser_action", "page_action"):
        action = manifest.get(action_key)
        if isinstance(action, Mapping):
            _collect(action.get("default_icon"))
    return candidates


def _icon_priority_key(item: tuple[int, str]) -> tuple[int, int, str]:
    sz, rel = item
    if sz == 128:
        return (0, 0, rel)
    if sz in (96, 64, 48, 32):
        return (1, -sz, rel)
    return (2, -sz, rel)


def pick_icon_relpath(manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> str | None:
    for _, raw_rel in sorted(_collect_icon_candidates(manifest), key=_icon_priority_key):
        try:
            rel = _normalize_zip_relpath(raw_rel.lstrip("./"))
        except ExtensionPackageError:
            continue
        suffix = Path(rel).suffix.lower()
        data = files.get(rel)
        if data is not None and suffix in ALLOWED_ICON_EXTENSIONS and len(data) <= MAX_ICON_BYTES:
            return rel
    return None


def extract_directory_metadata(
    directory: Path,
    manifest: Mapping[str, Any],
    file_relpaths: Iterable[str],
) -> tuple[str, str | None, str | None]:
    """Read only ``_locales`` & declared icon bytes from ``directory`` to resolve metadata."""
    rel_set = set(file_relpaths)
    needed_rels: set[str] = {
        rel
        for rel in rel_set
        if len(rel.split("/")) == 3 and rel.startswith("_locales/") and rel.endswith("/messages.json")
    }
    for _, raw_rel in _collect_icon_candidates(manifest):
        try:
            rel = _normalize_zip_relpath(raw_rel.lstrip("./"))
        except ExtensionPackageError:
            continue
        if rel in rel_set and Path(rel).suffix.lower() in ALLOWED_ICON_EXTENSIONS:
            needed_rels.add(rel)

    selected_files: dict[str, bytes] = {}
    root = Path(directory)
    for rel in sorted(needed_rels):
        candidate = root / rel
        try:
            if candidate.is_file() and not candidate.is_symlink():
                selected_files[rel] = candidate.read_bytes()
        except OSError:
            continue

    locales = load_locale_messages(selected_files)
    default_locale = (
        manifest.get("default_locale")
        if isinstance(manifest.get("default_locale"), str)
        else None
    )
    name = (
        resolve_i18n_field(manifest.get("name"), locales, default_locale)
        or str(manifest.get("name", ""))
    )[:255]
    desc = resolve_i18n_field(manifest.get("description"), locales, default_locale)
    icon_relpath = pick_icon_relpath(manifest, selected_files)
    return name, desc, icon_relpath


def compute_tree_identity(files: Mapping[str, bytes]) -> tuple[str, dict[str, str], int, int]:
    """Compute immutable SHA-256 tree ID, per-file hashes, file count, and byte sum."""
    file_hashes: dict[str, str] = {}
    total_bytes = 0
    for rel in sorted(files):
        data = files[rel]
        file_hashes[rel] = hashlib.sha256(data).hexdigest()
        total_bytes += len(data)
    canonical = json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tree_sha256 = hashlib.sha256(canonical).hexdigest()
    return tree_sha256, file_hashes, len(file_hashes), total_bytes


def _decode_archive_envelope(
    raw: bytes, filename: str | None
) -> tuple[str, str, bytes, bytes | None, str | None]:
    if raw[:4] == b"Cr24":
        package_format, zip_bytes, crx_pubkey, crx_id = extract_crx_archive(raw)
        return package_format, f"{package_format}_header", zip_bytes, crx_pubkey, crx_id
    if raw[:2] == b"PK" or (filename and filename.lower().endswith(".zip")):
        return "zip", "manifest_key", raw, None, None
    raise ExtensionPackageError(
        "corrupt_extension_archive",
        "Unsupported extension format; expected valid .crx or .zip archive",
    )


def _load_manifest_dict(files: Mapping[str, bytes]) -> dict[str, Any]:
    manifest_bytes = files.get("manifest.json")
    if manifest_bytes is None:
        raise ExtensionPackageError("invalid_extension_manifest", "Missing manifest.json")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise ExtensionPackageError(
            "invalid_extension_manifest", "manifest.json is not valid UTF-8 JSON"
        ) from None
    if not isinstance(manifest, dict):
        raise ExtensionPackageError(
            "invalid_extension_manifest", "manifest.json root must be a JSON object"
        )
    mv = manifest.get("manifest_version")
    if type(mv) is not int or mv not in (2, 3):
        raise ExtensionPackageError(
            "invalid_extension_manifest", "manifest_version must be 2 or 3"
        )
    version = manifest.get("version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version.strip()):
        raise ExtensionPackageError(
            "invalid_extension_manifest",
            "manifest.json version must be a valid dotted Chromium version",
        )
    return manifest


def _resolve_package_identity(
    manifest: dict[str, Any],
    files: dict[str, bytes],
    crx_pubkey: bytes | None,
    crx_id: str | None,
) -> tuple[bytes, str]:
    manifest_key_raw = manifest.get("key")
    if crx_pubkey is None or crx_id is None:
        return parse_manifest_key(manifest_key_raw)
    if manifest_key_raw is not None:
        key_der, manifest_crx_id = parse_manifest_key(manifest_key_raw)
        if manifest_crx_id != crx_id:
            raise ExtensionPackageError(
                "indeterminate_extension_identity",
                "CRX header key conflicts with manifest.json key",
            )
        return key_der, crx_id
    updated = dict(manifest)
    updated["key"] = base64.b64encode(crx_pubkey).decode("ascii")
    files["manifest.json"] = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return crx_pubkey, crx_id


def parse_extension_archive(raw: bytes, filename: str | None = None) -> ParsedExtensionPackage:
    """Parse, validate, and normalize an uploaded ``.zip`` or ``.crx`` extension package."""
    if not raw:
        raise ExtensionPackageError("corrupt_extension_archive", "Empty extension payload")
    if len(raw) > MAX_EXTENSION_ARCHIVE_BYTES:
        raise ExtensionPackageError(
            "archive_too_large",
            f"Extension archive exceeds {MAX_EXTENSION_ARCHIVE_BYTES} bytes",
        )
    archive_sha256 = hashlib.sha256(raw).hexdigest()
    package_format, identity_source, zip_bytes, crx_pubkey, crx_id = _decode_archive_envelope(
        raw, filename
    )
    files = dict(unpack_safe_zip_entries(zip_bytes))
    manifest = _load_manifest_dict(files)
    default_locale = (
        manifest.get("default_locale")
        if isinstance(manifest.get("default_locale"), str)
        else None
    )
    locales = load_locale_messages(files)
    name = resolve_i18n_field(manifest.get("name"), locales, default_locale)
    if not name:
        raise ExtensionPackageError(
            "invalid_extension_manifest", "manifest.json must declare a non-empty name"
        )
    version = str(manifest["version"]).strip()
    description = resolve_i18n_field(manifest.get("description"), locales, default_locale)
    key_der, chromium_id = _resolve_package_identity(manifest, files, crx_pubkey, crx_id)

    manifest_key_sha256 = hashlib.sha256(key_der).hexdigest()
    manifest_sha256 = hashlib.sha256(files["manifest.json"]).hexdigest()
    icon_relpath = pick_icon_relpath(manifest, files)
    asset_id, file_hashes, file_count, total_bytes = compute_tree_identity(files)
    return ParsedExtensionPackage(
        asset_id=asset_id,
        chromium_id=chromium_id,
        name=name[:255],
        version=version[:64],
        manifest_version=int(manifest["manifest_version"]),
        description=description,
        package_format=package_format,
        identity_source=identity_source,
        manifest_key_sha256=manifest_key_sha256,
        archive_sha256=archive_sha256,
        icon_relpath=icon_relpath,
        file_count=file_count,
        total_bytes=total_bytes,
        manifest_sha256=manifest_sha256,
        file_hashes=file_hashes,
        files=files,
    )


def materialize_extension_directory(pkg: ParsedExtensionPackage, target_dir: Path) -> None:
    """Atomically extract verified extension files into ``target_dir``."""
    target_dir = Path(target_dir)
    if target_dir.exists():
        return
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = target_dir.parent / f".staging-{pkg.asset_id[:16]}-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        for rel, content in pkg.files.items():
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            dest.chmod(_ARCHIVE_ID_FILE_MODE)
        for root_dir, dirs, _files in os.walk(staging, followlinks=False):
            os.chmod(root_dir, _DIR_MODE)
            for d in dirs:
                os.chmod(Path(root_dir) / d, _DIR_MODE)
        staging.chmod(_DIR_MODE)
        staging.replace(target_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _scan_extension_directory(resolved: Path) -> tuple[dict[str, bytes], list[str]]:
    problems: list[str] = []
    disk_files: dict[str, bytes] = {}
    total_bytes = 0
    for root_dir, dirnames, filenames in os.walk(resolved, followlinks=False):
        base = Path(root_dir)
        for d in dirnames:
            if (base / d).is_symlink():
                problems.append(f"symlink forbidden in extension directory: {d}")
        for name in sorted(filenames):
            candidate = base / name
            if candidate.is_symlink():
                problems.append(f"symlink forbidden in extension directory: {name}")
                continue
            rel = candidate.relative_to(resolved).as_posix()
            try:
                data = candidate.read_bytes()
            except OSError as exc:
                problems.append(f"unreadable file {rel}: {type(exc).__name__}")
                continue
            disk_files[rel] = data
            total_bytes += len(data)
            if total_bytes > MAX_EXTENSION_UNPACKED_BYTES:
                problems.append("unpacked extension size exceeds budget")
                return disk_files, problems
            if len(disk_files) > MAX_EXTENSION_FILES:
                problems.append("extension file count exceeds budget")
                return disk_files, problems
    return disk_files, problems


def _validate_manifest_bytes(
    manifest_raw: bytes | None,
) -> tuple[dict[str, Any] | None, str | None, str | None, list[str]]:
    if manifest_raw is None:
        return None, None, None, ["manifest.json is missing"]
    try:
        parsed = json.loads(manifest_raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None, None, None, ["manifest.json is invalid UTF-8 JSON"]
    if not isinstance(parsed, dict):
        return None, None, None, ["manifest.json must be a JSON object"]

    problems: list[str] = []
    mv = parsed.get("manifest_version")
    if type(mv) is not int or mv not in (2, 3):
        problems.append("manifest_version must be 2 or 3")
    if not isinstance(parsed.get("name"), str) or not parsed["name"].strip():
        problems.append("manifest name is missing or empty")
    ver = parsed.get("version")
    if not isinstance(ver, str) or not _VERSION_RE.fullmatch(ver.strip()):
        problems.append("manifest version is missing or invalid")
    chromium_id: str | None = None
    manifest_key_sha256: str | None = None
    if parsed.get("key") is None:
        problems.append("manifest key is missing")
    else:
        try:
            key_der, chromium_id = parse_manifest_key(parsed.get("key"))
            manifest_key_sha256 = hashlib.sha256(key_der).hexdigest()
        except ExtensionPackageError as exc:
            problems.append(str(exc))
    return parsed, chromium_id, manifest_key_sha256, problems


def _check_expected_hashes(
    expected_file_hashes: Mapping[str, str], file_hashes: dict[str, str]
) -> list[str]:
    expected_map = dict(expected_file_hashes)
    missing = sorted(set(expected_map) - set(file_hashes))
    extra = sorted(set(file_hashes) - set(expected_map))
    changed = sorted(
        k for k in set(expected_map) & set(file_hashes) if expected_map[k] != file_hashes[k]
    )
    problems: list[str] = []
    if missing:
        problems.append(f"missing files: {', '.join(missing[:5])}")
    if extra:
        problems.append(f"unexpected files: {', '.join(extra[:5])}")
    if changed:
        problems.append(f"modified files: {', '.join(changed[:5])}")
    return problems


def verify_extension_directory(
    directory: Path,
    *,
    expected_asset_id: str | None = None,
    expected_chromium_id: str | None = None,
    expected_file_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify an unpacked extension directory on disk for integrity and key identity."""
    resolved = Path(directory)
    if resolved.is_symlink() or not resolved.is_dir():
        return {
            "ok": False,
            "problems": ["extension directory is missing"],
            "chromium_id": None,
            "tree_sha256": None,
            "file_count": 0,
            "total_bytes": 0,
            "file_hashes": {},
        }

    disk_files, problems = _scan_extension_directory(resolved)
    manifest, chromium_id, manifest_key_sha256, mf_problems = _validate_manifest_bytes(
        disk_files.get("manifest.json")
    )
    problems.extend(mf_problems)

    tree_sha256, file_hashes, file_count, total_bytes = compute_tree_identity(disk_files)
    if expected_asset_id is not None and tree_sha256 != expected_asset_id:
        problems.append("extension tree hash mismatch")
    if expected_chromium_id is not None and chromium_id != expected_chromium_id:
        problems.append("extension chromium_id mismatch")
    if expected_file_hashes is not None:
        problems.extend(_check_expected_hashes(expected_file_hashes, file_hashes))

    return {
        "ok": len(problems) == 0,
        "problems": problems,
        "chromium_id": chromium_id,
        "manifest_key_sha256": manifest_key_sha256,
        "manifest": manifest,
        "tree_sha256": tree_sha256,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "file_hashes": file_hashes,
    }


def resolve_extensions_root(
    *,
    data_root: Path | str | None = None,
    extensions_root: Path | str | None = None,
    db_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve managed extension storage root without silently inventing unrelated paths."""
    env = os.environ if environ is None else environ
    if extensions_root is not None and str(extensions_root) != "":
        return Path(extensions_root).resolve()
    raw_ext = env.get("CBROWSER_EXTENSIONS_DIR")
    if raw_ext:
        return Path(raw_ext).resolve()
    if data_root is not None and str(data_root) != "":
        return Path(data_root).resolve() / EXTENSIONS_DIR_NAME
    raw_data = env.get("CBROWSER_DATA_ROOT")
    if raw_data:
        return Path(raw_data).resolve() / EXTENSIONS_DIR_NAME
    if db_path is not None and str(db_path) not in ("", ":memory:"):
        return Path(db_path).resolve().parent / EXTENSIONS_DIR_NAME
    return None
