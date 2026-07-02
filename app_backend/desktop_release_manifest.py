from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import HTTPException

from shared.runtime_paths import auth_store_root


DESKTOP_RELEASE_MANIFEST_ENV = "EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH"
DESKTOP_RELEASE_ASSET_DIR_ENV = "EMPLOAI_DESKTOP_RELEASE_ASSET_DIR"
DESKTOP_RELEASE_ALLOWED_HOSTS_ENV = "EMPLOAI_DESKTOP_RELEASE_ALLOWED_HOSTS"
DESKTOP_RELEASE_MANIFEST_FILENAME = "desktop_windows_release_manifest.json"
DESKTOP_RELEASE_ASSET_DIRNAME = "desktop_windows_releases"
DESKTOP_RELEASE_ROUTE_PREFIX = "/releases/desktop/windows/"
DESKTOP_RELEASE_ASSET_TYPES = (".msi", ".zip")


def desktop_release_manifest_path() -> Path:
    configured = os.getenv(DESKTOP_RELEASE_MANIFEST_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (auth_store_root() / DESKTOP_RELEASE_MANIFEST_FILENAME).resolve()


def desktop_release_asset_dir() -> Path:
    configured = os.getenv(DESKTOP_RELEASE_ASSET_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (auth_store_root() / DESKTOP_RELEASE_ASSET_DIRNAME).resolve()


def desktop_release_allowed_hosts() -> set[str]:
    configured = os.getenv(DESKTOP_RELEASE_ALLOWED_HOSTS_ENV, "").strip()
    hosts = [item.strip().lower() for item in configured.split(",") if item.strip()] if configured else ["api.kraitos.app"]
    return {host for host in hosts if host}


def _clean_desktop_release_asset_name(
    asset_name: Any,
    *,
    status_code: int,
    invalid_name_detail: str,
    invalid_type_detail: str,
) -> str:
    clean_name = str(asset_name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", clean_name):
        raise HTTPException(status_code=status_code, detail=invalid_name_detail)
    if not clean_name.lower().endswith(DESKTOP_RELEASE_ASSET_TYPES):
        raise HTTPException(status_code=status_code, detail=invalid_type_detail)
    return clean_name


def validate_desktop_release_asset_name(asset_name: Any) -> str:
    return _clean_desktop_release_asset_name(
        asset_name,
        status_code=500,
        invalid_name_detail="Desktop release manifest contains an invalid asset name",
        invalid_type_detail="Desktop release manifest asset type is not allowed",
    )


def validate_desktop_release_asset_url(asset_url: Any, *, asset_name: str) -> str:
    clean_url = str(asset_url or "").strip()
    parsed = urlparse(clean_url)
    host = str(parsed.hostname or "").lower()
    allowed_hosts = desktop_release_allowed_hosts()
    if parsed.scheme != "https" or host not in allowed_hosts:
        raise HTTPException(status_code=500, detail="Desktop release manifest contains an unsafe asset URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise HTTPException(status_code=500, detail="Desktop release manifest asset URL must not contain params, query, or fragment")
    if not parsed.path.startswith(DESKTOP_RELEASE_ROUTE_PREFIX):
        raise HTTPException(status_code=500, detail="Desktop release manifest asset URL path is not allowed")
    url_name = Path(parsed.path).name
    if validate_desktop_release_asset_name(url_name) != asset_name:
        raise HTTPException(status_code=500, detail="Desktop release manifest asset URL does not match asset name")
    return clean_url


def validate_desktop_release_sha256(value: Any) -> str:
    digest = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HTTPException(status_code=500, detail="Desktop release manifest contains an invalid SHA-256 digest")
    return digest


def validate_desktop_release_manifest(payload: Dict[str, Any]) -> Dict[str, Any]:
    releases = payload.get("releases")
    if isinstance(releases, list):
        release_items = [item for item in releases if isinstance(item, dict)]
        if len(release_items) != len(releases):
            raise HTTPException(status_code=500, detail="Desktop release manifest releases must be JSON objects")
    else:
        release = payload.get("latest") or payload.get("release") or payload.get("update")
        release_items = [release] if isinstance(release, dict) else []

    if not release_items:
        raise HTTPException(status_code=500, detail="Desktop release manifest does not contain a release")

    for release in release_items:
        assets = release.get("assets")
        if isinstance(assets, list):
            if not assets:
                raise HTTPException(status_code=500, detail="Desktop release manifest release has no assets")
            for asset in assets:
                if not isinstance(asset, dict):
                    raise HTTPException(status_code=500, detail="Desktop release manifest assets must be JSON objects")
                asset_name = validate_desktop_release_asset_name(asset.get("name") or asset.get("assetName"))
                validate_desktop_release_asset_url(
                    asset.get("browser_download_url") or asset.get("assetUrl") or asset.get("asset_url"),
                    asset_name=asset_name,
                )
                validate_desktop_release_sha256(asset.get("sha256"))
            continue

        asset_name = validate_desktop_release_asset_name(release.get("assetName") or release.get("asset_name"))
        validate_desktop_release_asset_url(
            release.get("assetUrl")
            or release.get("asset_url")
            or release.get("downloadUrl")
            or release.get("download_url"),
            asset_name=asset_name,
        )
        validate_desktop_release_sha256(release.get("sha256"))
    return payload


def load_desktop_release_manifest() -> Dict[str, Any]:
    path = desktop_release_manifest_path()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Desktop release manifest is not configured")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Desktop release manifest is invalid") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="Desktop release manifest must be a JSON object")
    return validate_desktop_release_manifest(payload)


def resolve_desktop_release_asset_path(asset_name: Any) -> tuple[Path, str]:
    clean_name = _clean_desktop_release_asset_name(
        asset_name,
        status_code=404,
        invalid_name_detail="Release asset was not found",
        invalid_type_detail="Release asset was not found",
    )
    asset_dir = desktop_release_asset_dir()
    asset_path = (asset_dir / clean_name).resolve()
    try:
        asset_path.relative_to(asset_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Release asset was not found") from exc
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Release asset was not found")
    return asset_path, clean_name
