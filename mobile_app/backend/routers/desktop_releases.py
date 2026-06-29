from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from mobile_app.backend.desktop_release_manifest import (
    load_desktop_release_manifest,
    resolve_desktop_release_asset_path,
)


router = APIRouter(tags=["desktop-releases"])


@router.get("/api/releases/desktop/windows/latest")
async def desktop_windows_latest_release() -> dict:
    return load_desktop_release_manifest()


@router.get("/releases/desktop/windows/{asset_name}")
async def desktop_windows_release_asset(asset_name: str) -> FileResponse:
    asset_path, clean_name = resolve_desktop_release_asset_path(asset_name)
    return FileResponse(
        asset_path,
        media_type="application/octet-stream",
        filename=clean_name,
    )
