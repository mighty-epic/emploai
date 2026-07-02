from __future__ import annotations

import json
import hashlib
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
DEFAULT_UPDATE_MANIFEST_URL = ""


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
    update_manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL


@dataclass(frozen=True)
class AvailableUpdate:
    version: str
    tag_name: str
    asset_name: str
    asset_url: str
    published_at: str | None
    sha256: str | None = None


def serialize_available_update(update: AvailableUpdate | None) -> dict[str, Any] | None:
    if update is None:
        return None
    return {
        "version": update.version,
        "tagName": update.tag_name,
        "assetName": update.asset_name,
        "assetUrl": update.asset_url,
        "publishedAt": update.published_at,
        "sha256": update.sha256,
    }


def _normalize_sha256(value: Any) -> str | None:
    digest = str(value or "").strip().lower()
    if not digest:
        return None
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid update asset SHA-256 digest")
    return digest


def _safe_update_asset_name(asset_name: str) -> str:
    clean_name = str(asset_name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", clean_name):
        raise ValueError("Unsafe update asset name")
    if not clean_name.lower().endswith((".msi", ".zip")):
        raise ValueError("Unsupported update asset type")
    return clean_name


def _deserialize_cached_update(payload: Any, *, current_version: Version) -> AvailableUpdate | None:
    if not isinstance(payload, dict):
        return None
    raw_version = str(payload.get("version") or payload.get("tagName") or payload.get("tag_name") or "").strip()
    if not raw_version:
        return None
    try:
        parsed_version = _normalize_release_version(raw_version)
    except InvalidVersion:
        return None
    if parsed_version <= current_version:
        return None

    try:
        asset_name = _safe_update_asset_name(str(payload.get("assetName") or payload.get("asset_name") or "").strip())
        sha256 = _normalize_sha256(payload.get("sha256"))
    except ValueError:
        return None
    asset_url = str(payload.get("assetUrl") or payload.get("asset_url") or "").strip()
    if not asset_name or not asset_url:
        return None

    tag_name = str(payload.get("tagName") or payload.get("tag_name") or raw_version).strip()
    if tag_name and not tag_name.lower().startswith("v"):
        tag_name = f"v{tag_name}"
    return AvailableUpdate(
        version=raw_version,
        tag_name=tag_name,
        asset_name=asset_name,
        asset_url=asset_url,
        published_at=payload.get("publishedAt") or payload.get("published_at"),
        sha256=sha256,
    )


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
        update_manifest_url=DEFAULT_UPDATE_MANIFEST_URL,
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
        update_manifest_url=str(raw.get("update_manifest_url") or defaults.update_manifest_url).strip(),
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

    def _pre_release_replacement(prefix: str):
        def _replace(match: re.Match[str]) -> str:
            suffix = f"{prefix}{match.group(1)}"
            if match.group(2):
                suffix = f"{suffix}.post{match.group(2)}"
            return suffix

        return _replace

    candidate = re.sub(r"(?i)-beta[.\-]?(\d+)(?:[.\-](\d+))?", _pre_release_replacement("b"), candidate)
    candidate = re.sub(r"(?i)-alpha[.\-]?(\d+)(?:[.\-](\d+))?", _pre_release_replacement("a"), candidate)
    candidate = re.sub(r"(?i)-rc[.\-]?(\d+)(?:[.\-](\d+))?", _pre_release_replacement("rc"), candidate)
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


def _manifest_releases(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    releases = payload.get("releases")
    if isinstance(releases, list):
        return [item for item in releases if isinstance(item, dict)]
    latest = payload.get("latest") or payload.get("release") or payload.get("update")
    return [latest] if isinstance(latest, dict) else []


def _manifest_asset(release: dict[str, Any], *, primary_asset: str, portable_asset: str) -> Optional[dict[str, Any]]:
    assets = release.get("assets")
    if isinstance(assets, list):
        asset = _find_matching_asset({"assets": assets}, primary_asset=primary_asset, portable_asset=portable_asset)
        if asset is None:
            return None
        return {
            "name": asset.get("name"),
            "browser_download_url": asset.get("browser_download_url"),
            "sha256": asset.get("sha256"),
        }

    asset_name = str(release.get("assetName") or release.get("asset_name") or primary_asset).strip()
    asset_url = str(
        release.get("assetUrl")
        or release.get("asset_url")
        or release.get("downloadUrl")
        or release.get("download_url")
        or ""
    ).strip()
    if not asset_url:
        return None
    if asset_name not in {primary_asset, portable_asset}:
        lower_asset_name = asset_name.lower()
        lower_asset_url = asset_url.lower()
        if not (lower_asset_name.endswith(".msi") or lower_asset_url.endswith(".msi")):
            return None
    return {
        "name": asset_name,
        "browser_download_url": asset_url,
        "sha256": release.get("sha256"),
    }


def find_available_update_from_manifest(info: ReleaseInfo) -> Optional[AvailableUpdate]:
    if not info.update_manifest_url:
        return None
    response = requests.get(
        info.update_manifest_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EmploAI-Updater",
        },
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()

    current_version = _normalize_release_version(info.version)
    best: tuple[Version, AvailableUpdate] | None = None

    for release in _manifest_releases(payload):
        channel = str(release.get("channel") or payload.get("channel") or info.channel).strip()
        if channel and channel != info.channel:
            continue

        tag_name = str(release.get("tagName") or release.get("tag_name") or release.get("releaseTag") or "").strip()
        raw_version = str(release.get("version") or tag_name).strip()
        if not tag_name and raw_version:
            tag_name = raw_version if raw_version.lower().startswith("v") else f"v{raw_version}"
        if not raw_version:
            continue

        try:
            version = _normalize_release_version(raw_version)
        except InvalidVersion:
            continue

        if version <= current_version:
            continue

        asset = _manifest_asset(
            release,
            primary_asset=info.primary_asset,
            portable_asset=info.portable_asset,
        )
        if not asset:
            continue

        try:
            asset_name = _safe_update_asset_name(str(asset["name"]))
            sha256 = _normalize_sha256(asset.get("sha256"))
        except ValueError:
            continue

        candidate = AvailableUpdate(
            version=str(version),
            tag_name=tag_name,
            asset_name=asset_name,
            asset_url=str(asset["browser_download_url"]),
            published_at=release.get("publishedAt") or release.get("published_at"),
            sha256=sha256,
        )
        if best is None or version > best[0]:
            best = (version, candidate)

    return best[1] if best else None


def find_available_update_from_github(info: ReleaseInfo) -> Optional[AvailableUpdate]:
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

        try:
            asset_name = _safe_update_asset_name(str(asset["name"]))
        except ValueError:
            continue

        candidate = AvailableUpdate(
            version=str(version),
            tag_name=tag_name,
            asset_name=asset_name,
            asset_url=str(asset["browser_download_url"]),
            published_at=release.get("published_at"),
        )
        if best is None or version > best[0]:
            best = (version, candidate)

    return best[1] if best else None


def find_available_update(info: ReleaseInfo) -> Optional[AvailableUpdate]:
    if info.update_manifest_url:
        try:
            return find_available_update_from_manifest(info)
        except Exception:
            pass
    return find_available_update_from_github(info)


def _download_update_asset(home: Path, update: AvailableUpdate) -> Path:
    updates_dir = home / UPDATES_DIRNAME
    updates_dir.mkdir(parents=True, exist_ok=True)
    target_path = updates_dir / _safe_update_asset_name(update.asset_name)
    expected_sha256 = _normalize_sha256(update.sha256)
    hasher = hashlib.sha256()

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
                    hasher.update(chunk)
                    handle.write(chunk)
    if expected_sha256 and hasher.hexdigest().lower() != expected_sha256:
        try:
            target_path.unlink()
        except OSError:
            pass
        raise ValueError("Downloaded update asset SHA-256 did not match the release manifest")
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
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, flag_name, 0))
    subprocess.Popen(
        ["cmd.exe", "/c", str(script_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


def check_for_updates(home: Path, bundle_root: Path, *, force: bool = False) -> dict[str, Any]:
    info = load_release_info(bundle_root)
    state = load_release_state(home)
    current_version = _normalize_release_version(info.version)
    cached_update = _deserialize_cached_update(
        state.get("last_available_update"),
        current_version=current_version,
    )
    result: dict[str, Any] = {
        "ok": True,
        "currentVersion": info.version,
        "releaseTag": info.release_tag,
        "channel": info.channel,
        "repo": info.github_repo,
        "manifestUrl": info.update_manifest_url,
        "source": "manifest" if info.update_manifest_url else "github",
        "intervalHours": info.update_check_interval_hours,
        "checked": False,
        "updateAvailable": False,
        "update": None,
        "lastCheckedAt": state.get("last_checked_at"),
        "lastError": state.get("last_error"),
    }

    if not should_check_for_updates(home, info.update_check_interval_hours, force=force):
        if cached_update is not None:
            result["updateAvailable"] = True
            result["update"] = serialize_available_update(cached_update)
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
    if update is not None:
        state["last_available_update"] = serialize_available_update(update)
    else:
        state.pop("last_available_update", None)
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
