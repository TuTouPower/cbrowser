"""Managed Chromium extension library endpoints (t104)."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from cbrowser.adapters.database.extension_repository import ExtensionAssetRecord
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.auth.dependencies import require_csrf_and_origin, require_user_session
from cbrowser.domain.models import (
    ErrorResponse,
    ExtensionAssetListResponse,
    ExtensionAssetResponse,
    ExtensionIntegrity,
    ExtensionUsedByResponse,
)
from cbrowser.extensions.manifest import (
    EXTENSION_ASSET_ID_RE,
    MAX_EXTENSION_ARCHIVE_BYTES,
    ExtensionPackageError,
)
from cbrowser.services.extension_catalog import (
    ExtensionCatalogService,
    ExtensionInUseError,
    ExtensionNotFoundError,
)
from cbrowser.services.profile_service import ProfileService

LOGGER = logging.getLogger("cbrowser.api.v1.extensions")

extensions_router = APIRouter(
    prefix="/api/v1/extensions",
    tags=["extensions"],
)


def _catalog(
    request: Request,
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ExtensionCatalogService:
    catalog = getattr(request.app.state, "extension_catalog", None)
    if catalog is None:
        catalog = service.extension_catalog()
    return catalog


def _to_response(
    record: ExtensionAssetRecord, used_by_count: int
) -> ExtensionAssetResponse:
    return ExtensionAssetResponse(
        id=record.id,
        chromium_id=record.chromium_id,
        name=record.name,
        version=record.version,
        manifest_version=record.manifest_version,
        description=record.description,
        package_format=record.package_format,
        identity_source=record.identity_source,
        manifest_key_sha256=record.manifest_key_sha256,
        archive_sha256=record.archive_sha256,
        has_icon=record.has_icon,
        icon_url=f"/api/v1/extensions/{record.id}/icon" if record.has_icon else None,
        file_count=record.file_count,
        total_bytes=record.total_bytes,
        integrity=ExtensionIntegrity(
            ok=bool(record.integrity.get("ok", record.verified)),
            problems=[str(p) for p in record.integrity.get("problems", [])],
        ),
        state=record.state,
        used_by_count=used_by_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _read_upload_bytes(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header",
            ) from None
        if declared > MAX_EXTENSION_ARCHIVE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "extension_archive_too_large",
                    "message": (
                        f"Extension archive exceeds maximum size of "
                        f"{MAX_EXTENSION_ARCHIVE_BYTES} bytes"
                    ),
                },
            )
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_EXTENSION_ARCHIVE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "extension_archive_too_large",
                    "message": (
                        f"Extension archive exceeds maximum size of "
                        f"{MAX_EXTENSION_ARCHIVE_BYTES} bytes"
                    ),
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@extensions_router.get(
    "",
    response_model=ExtensionAssetListResponse,
    dependencies=[Depends(require_user_session)],
)
async def list_extensions(
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
) -> ExtensionAssetListResponse:
    records, counts = await catalog.list_assets()
    return ExtensionAssetListResponse(
        items=[_to_response(rec, counts.get(rec.id, 0)) for rec in records]
    )


@extensions_router.post(
    "",
    response_model=ExtensionAssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_and_origin)],
    responses={
        status.HTTP_200_OK: {
            "model": ExtensionAssetResponse,
            "description": "Identical extension asset already present",
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "Extension archive exceeds maximum upload size",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "Malformed archive, invalid manifest.json, or indeterminate Chromium ID",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Managed extension storage root not configured",
        },
    },
)
async def upload_extension(
    request: Request,
    response: Response,
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
    filename: Annotated[str | None, Query(max_length=255)] = None,
) -> ExtensionAssetResponse:
    if not catalog.root_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Managed extension storage root is not configured",
        )
    raw = await _read_upload_bytes(request)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "empty_extension_archive",
                "message": "Extension upload body is empty",
            },
        )
    safe_name = os.path.basename(filename.strip()) if filename and filename.strip() else None
    try:
        record, created = await catalog.import_bytes(raw, safe_name)
    except ExtensionPackageError as exc:
        if exc.code == "extensions_not_configured":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=exc.message,
            ) from None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    fetched = await catalog.get_asset(record.id)
    used_by_count = fetched[1] if fetched is not None else 0
    if not created:
        response.status_code = status.HTTP_200_OK
    return _to_response(record, used_by_count)


@extensions_router.get(
    "/{asset_id}",
    response_model=ExtensionAssetResponse,
    dependencies=[Depends(require_user_session)],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Extension asset not found",
        },
    },
)
async def get_extension(
    asset_id: str,
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
) -> ExtensionAssetResponse:
    if not EXTENSION_ASSET_ID_RE.fullmatch(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension {asset_id} not found",
        )
    fetched = await catalog.get_asset(asset_id)
    if fetched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension {asset_id} not found",
        )
    record, used_by_count = fetched
    return _to_response(record, used_by_count)


@extensions_router.get(
    "/{asset_id}/used-by",
    response_model=ExtensionUsedByResponse,
    dependencies=[Depends(require_user_session)],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Extension asset not found",
        },
    },
)
async def get_extension_used_by(
    asset_id: str,
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
) -> ExtensionUsedByResponse:
    if not EXTENSION_ASSET_ID_RE.fullmatch(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension {asset_id} not found",
        )
    entries = await catalog.get_used_by(asset_id)
    if entries is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension {asset_id} not found",
        )
    return ExtensionUsedByResponse(asset_id=asset_id, entries=entries)


@extensions_router.get(
    "/{asset_id}/icon",
    dependencies=[Depends(require_user_session)],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Extension asset or icon not found",
        },
    },
)
async def get_extension_icon(
    asset_id: str,
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
) -> Response:
    if not EXTENSION_ASSET_ID_RE.fullmatch(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension icon for {asset_id} not found",
        )
    resolved = await catalog.get_icon_file(asset_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension icon for {asset_id} not found",
        )
    path, media_type = resolved
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "public, max-age=86400, immutable",
        },
    )


@extensions_router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_and_origin)],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Extension asset not found",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Extension asset is referenced by one or more profiles",
        },
    },
)
async def delete_extension(
    asset_id: str,
    catalog: Annotated[ExtensionCatalogService, Depends(_catalog)],
) -> None:
    try:
        await catalog.delete_asset(asset_id)
    except ExtensionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension {asset_id} not found",
        ) from None
    except ExtensionInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "extension_in_use",
                "used_by_count": exc.used_by_count,
                "message": str(exc),
            },
        ) from None
