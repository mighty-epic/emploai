from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from packaging.version import InvalidVersion, Version


RELEASE_INFO_FILENAME = "release_info.json"
UPDATE_STATE_FILENAME = "release_state.json"
UPDATES_DIRNAME = "updates"
DEFAULT_REPO = "mighty-epic/emploai-releases"
DEFAULT_PRIMARY_ASSET = "EmploAI.msi"
DEFAULT_PORTABLE_ASSET = "EmploAI-portable.zip"
DEFAULT_CHANNEL = "beta"
DEFAULT_INTERVAL_HOURS = 12
GITHUB_API_ROOT = "https://api.github.com"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    release_tag: str
    msi_version: str
    channel: str
    github_repo: str
    primary_asset: str
    portable_asset: str
    update_check_interval_hours: int


@dataclass(frozen=True)
class AvailableUpdate:
    version: str
    tag_name: str
    asset_name: str
    asset_url: str
    published_at: str | None


def serialize_available_update(update: AvailableUpdate | None) -> dict[str, Any] | None:
    if update is None:
        return None
    return {
        "version": update.version,
        "tagName": update.tag_name,
        "assetName": update.asset_name,
        "assetUrl": update.asset_url,
        "publishedAt": update.published_at,
    }


def _default_release_info() -> ReleaseInfo:
    return ReleaseInfo(
        version="0.0.0-beta.0",
        release_tag="v0.0.0-beta.0",
        msi_version="0.0.0",
        channel=DEFAULT_CHANNEL,
        github_repo=DEFAULT_REPO,
        primary_asset=DEFAULT_PRIMARY_ASSET,
        portable_asset=DEFAULT_PORTABLE_ASSET,
        update_check_interval_hours=DEFAULT_INTERVAL_HOURS,
    )


def load_release_info(bundle_root: Path) -> ReleaseInfo:
    info_path = bundle_root / "deploy" / "windows" / RELEASE_INFO_FILENAME
    if not info_path.exists():
        return _default_release_info()

    try:
        raw = json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return _default_release_info()

    defaults = _default_release_info()
    raw_interval = raw.get("update_check_interval_hours")
    if raw_interval in (None, ""):
        interval_hours = defaults.update_check_interval_hours
    else:
        interval_hours = int(raw_interval)

    return ReleaseInfo(
        version=str(raw.get("version") or defaults.version),
        release_tag=str(raw.get("release_tag") or defaults.release_tag),
        msi_version=str(raw.get("msi_version") or defaults.msi_version),
        channel=str(raw.get("channel") or defaults.channel),
        github_repo=str(raw.get("github_repo") or defaults.github_repo),
        primary_asset=str(raw.get("primary_asset") or defaults.primary_asset),
        portable_asset=str(raw.get("portable_asset") or defaults.portable_asset),
        update_check_interval_hours=interval_hours,
    )


def _release_state_path(home: Path) -> Path:
    return home / UPDATE_STATE_FILENAME


def load_release_state(home: Path) -> dict[str, Any]:
    path = _release_state_path(home)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_release_state(home: Path, state: dict[str, Any]) -> None:
    path = _release_state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _normalize_release_version(raw: str) -> Version:
    candidate = raw.strip()
    if candidate.lower().startswith("v"):
        candidate = candidate[1:]
    candidate = re.sub(r"(?i)-beta[.\-]?(\d+)", r"b\1", candidate)
    candidate = re.sub(r"(?i)-alpha[.\-]?(\d+)", r"a\1", candidate)
    candidate = re.sub(r"(?i)-rc[.\-]?(\d+)", r"rc\1", candidate)
    return Version(candidate)


def _parse_iso8601(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def should_check_for_updates(home: Path, interval_hours: int, *, force: bool = False) -> bool:
    if force:
        return True
    if interval_hours <= 0:
        return True
    state = load_release_state(home)
    last_checked_at = _parse_iso8601(state.get("last_checked_at"))
    if last_checked_at is None:
        return True
    return datetime.now(timezone.utc) - last_checked_at >= timedelta(hours=interval_hours)


def _find_matching_asset(release: dict[str, Any], *, primary_asset: str, portable_asset: str) -> Optional[dict[str, Any]]:
    assets = release.get("assets") or []
    for expected in (primary_asset, portable_asset):
        for asset in assets:
            if asset.get("name") == expected and asset.get("browser_download_url"):
                return asset
    return None


def find_available_update(info: ReleaseInfo) -> Optional[AvailableUpdate]:
    response = requests.get(
        f"{GITHUB_API_ROOT}/repos/{info.github_repo}/releases",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "EmploAI-Updater",
        },
        timeout=12,
    )
    response.raise_for_status()
    releases = response.json()

    current_version = _normalize_release_version(info.version)
    best: tuple[Version, AvailableUpdate] | None = None

    for release in releases:
        if release.get("draft"):
            continue

        prerelease = bool(release.get("prerelease"))
        if info.channel == "beta" and not prerelease:
            continue
        if info.channel != "beta" and prerelease:
            continue

        tag_name = str(release.get("tag_name") or "")
        if not tag_name:
            continue

        try:
            version = _normalize_release_version(tag_name)
        except InvalidVersion:
            continue

        if version <= current_version:
            continue

        asset = _find_matching_asset(
            release,
            primary_asset=info.primary_asset,
            portable_asset=info.portable_asset,
        )
        if not asset:
            continue

        candidate = AvailableUpdate(
            version=str(version),
            tag_name=tag_name,
            asset_name=str(asset["name"]),
            asset_url=str(asset["browser_download_url"]),
            published_at=release.get("published_at"),
        )
        if best is None or version > best[0]:
            best = (version, candidate)

    return best[1] if best else None


def _download_update_asset(home: Path, update: AvailableUpdate) -> Path:
    updates_dir = home / UPDATES_DIRNAME
    updates_dir.mkdir(parents=True, exist_ok=True)
    target_path = updates_dir / update.asset_name

    with requests.get(
        update.asset_url,
        headers={"User-Agent": "EmploAI-Updater"},
        stream=True,
        timeout=30,
    ) as response:
        response.raise_for_status()
        with open(target_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return target_path


def _default_restart_executable() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(local_appdata) / "Programs" / "EmploAI" / "EmploAI.exe"


def _write_update_script(home: Path, installer_path: Path, restart_executable: Path) -> Path:
    updates_dir = home / UPDATES_DIRNAME
    updates_dir.mkdir(parents=True, exist_ok=True)
    script_path = updates_dir / "apply_update_and_restart.cmd"
    script_path.write_text(
        "\r\n".join(
            [
                "@echo off",
                "setlocal",
                "timeout /t 2 /nobreak >nul",
                f'msiexec.exe /i "{installer_path}" /passive /norestart',
                "set MSI_EXIT=%ERRORLEVEL%",
                'if "%MSI_EXIT%"=="0" goto relaunch',
                'if "%MSI_EXIT%"=="1641" goto relaunch',
                'if "%MSI_EXIT%"=="3010" goto relaunch',
                "exit /b %MSI_EXIT%",
                ":relaunch",
                "timeout /t 2 /nobreak >nul",
                f'if exist "{restart_executable}" start "" "{restart_executable}"',
                "exit /b 0",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    return script_path


def _launch_msi_update(home: Path, installer_path: Path, restart_executable: Path) -> None:
    script_path = _write_update_script(home, installer_path, restart_executable)
    creationflags = 0
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= int(getattr(subprocess, flag_name, 0))
    subprocess.Popen(
        ["cmd.exe", "/c", str(script_path)],
        close_fds=True,
        creationflags=creationflags,
    )


def check_for_updates(home: Path, bundle_root: Path, *, force: bool = False) -> dict[str, Any]:
    info = load_release_info(bundle_root)
    state = load_release_state(home)
    result: dict[str, Any] = {
        "ok": True,
        "currentVersion": info.version,
        "releaseTag": info.release_tag,
        "channel": info.channel,
        "repo": info.github_repo,
        "intervalHours": info.update_check_interval_hours,
        "checked": False,
        "updateAvailable": False,
        "update": None,
        "lastCheckedAt": state.get("last_checked_at"),
        "lastError": state.get("last_error"),
    }

    if not should_check_for_updates(home, info.update_check_interval_hours, force=force):
        return result

    state["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    result["checked"] = True
    result["lastCheckedAt"] = state["last_checked_at"]

    try:
        update = find_available_update(info)
    except Exception as exc:
        state["last_error"] = str(exc)
        save_release_state(home, state)
        result["ok"] = False
        result["lastError"] = str(exc)
        return result

    state.pop("last_error", None)
    save_release_state(home, state)
    result["lastError"] = None
    result["updateAvailable"] = update is not None
    result["update"] = serialize_available_update(update)
    return result


def install_available_update(
    home: Path,
    update: AvailableUpdate,
    *,
    restart_executable: Path | None = None,
) -> dict[str, Any]:
    installer_path = _download_update_asset(home, update)
    if installer_path.suffix.lower() != ".msi":
        return {
            "ok": False,
            "launched": False,
            "update": serialize_available_update(update),
            "installerPath": str(installer_path),
            "message": f"Downloaded update asset to {installer_path}. Launch it manually to update.",
        }

    restart_path = restart_executable or _default_restart_executable()
    _launch_msi_update(home, installer_path, restart_path)
    return {
        "ok": True,
        "launched": True,
        "update": serialize_available_update(update),
        "installerPath": str(installer_path),
        "restartExecutable": str(restart_path),
        "message": "The updater has started. EmploAI will exit so the MSI can replace the current install, then restart on the new version.",
    }


def install_latest_update(
    home: Path,
    bundle_root: Path,
    *,
    restart_executable: Path | None = None,
) -> dict[str, Any]:
    info = load_release_info(bundle_root)
    try:
        update = find_available_update(info)
    except Exception as exc:
        return {
            "ok": False,
            "launched": False,
            "update": None,
            "message": str(exc),
        }

    if update is None:
        return {
            "ok": True,
            "launched": False,
            "update": None,
            "message": "No newer release was found.",
        }

    return install_available_update(
        home,
        update,
        restart_executable=restart_executable,
    )


def maybe_install_update(
    home: Path,
    bundle_root: Path,
    *,
    args: set[str],
    restart_executable: Path | None = None,
) -> bool:
    if "--skip-update-check" in args or os.getenv("EMPLOAI_SKIP_UPDATE_CHECK", "").strip():
        return False

    force = "--check-updates" in args or "--force-update-check" in args
    status = check_for_updates(home, bundle_root, force=force)
    if not status.get("checked") and not force:
        return False

    if not status.get("ok", False):
        if force:
            print(f"Update check failed: {status.get('lastError')}")
        return False

    update_payload = status.get("update")
    if not update_payload:
        if force:
            print("No newer release was found.")
        return False

    update = AvailableUpdate(
        version=str(update_payload["version"]),
        tag_name=str(update_payload["tagName"]),
        asset_name=str(update_payload["assetName"]),
        asset_url=str(update_payload["assetUrl"]),
        published_at=update_payload.get("publishedAt"),
    )

    print(f"Update available: {update.tag_name} ({update.asset_name})")
    choice = input("Install update now? [Y/n]: ").strip().lower()
    if choice not in {"", "y", "yes"}:
        return False

    result = install_available_update(
        home,
        update,
        restart_executable=restart_executable,
    )
    message = str(result.get("message") or "").strip()
    if result.get("installerPath"):
        print(f"Launching installer: {result['installerPath']}")
    if message:
        print(message)
    return bool(result.get("launched"))
