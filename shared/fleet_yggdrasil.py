from __future__ import annotations

import base64
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from shared.fleet_connection import write_fleet_connection
from shared.subprocess_utils import hidden_subprocess_kwargs


PAIRING_TOKEN_PREFIX = "emploai-yggdrasil-v1."
YGGDRASIL_EXE_ENV = "EMPLOAI_YGGDRASIL_EXE"
YGGDRASIL_CTL_ENV = "EMPLOAI_YGGDRASILCTL_EXE"
DEFAULT_PAIRING_TTL_SECONDS = 30 * 60
YGGDRASIL_GITHUB_RELEASES_API = "https://api.github.com/repos/yggdrasil-network/yggdrasil-go/releases/latest"
YGGDRASIL_PUBLIC_PEERS_URL = "https://publicpeers.neilalexander.dev/"
DEFAULT_PUBLIC_PEER_LIMIT = 3
FALLBACK_PUBLIC_PEERS = (
    "tls://vpn.itrus.su:7992",
    "quic://vpn.itrus.su:7993",
    "tls://ygg-msk-1.averyan.ru:8362",
)


def _runtime_yggdrasil_dir(home: Path) -> Path:
    return home / "fleet-yggdrasil"


def _tools_yggdrasil_dir(home: Path) -> Path:
    return home / "tools" / "yggdrasil"


def _path_from_env(name: str) -> Path | None:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _candidate_program_files(names: tuple[str, ...]) -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = str(os.getenv(env_name, "") or "").strip()
        if not root:
            continue
        for name in names:
            candidates.append(Path(root) / "Yggdrasil" / name)
            candidates.append(Path(root) / "Yggdrasil Network" / name)
    return candidates


def _existing_first(paths: list[Path]) -> Path | None:
    for path in paths:
        try:
            if path.exists() and path.is_file():
                return path
        except OSError:
            continue
    return None


def resolve_yggdrasil_binary(home: Path) -> Path | None:
    exe_name = "yggdrasil.exe" if os.name == "nt" else "yggdrasil"
    env_path = _path_from_env(YGGDRASIL_EXE_ENV)
    if env_path:
        return env_path
    found = shutil.which(exe_name)
    if found:
        return Path(found)
    return _existing_first(
        [
            _tools_yggdrasil_dir(home) / exe_name,
            _runtime_yggdrasil_dir(home) / exe_name,
            *_candidate_program_files((exe_name,)),
        ]
    )


def resolve_yggdrasilctl_binary(home: Path) -> Path | None:
    exe_name = "yggdrasilctl.exe" if os.name == "nt" else "yggdrasilctl"
    env_path = _path_from_env(YGGDRASIL_CTL_ENV)
    if env_path:
        return env_path
    found = shutil.which(exe_name)
    if found:
        return Path(found)
    return _existing_first(
        [
            _tools_yggdrasil_dir(home) / exe_name,
            _runtime_yggdrasil_dir(home) / exe_name,
            *_candidate_program_files((exe_name,)),
        ]
    )


def normalize_yggdrasil_ipv6(value: str) -> str:
    cleaned = str(value or "").strip().strip("[]")
    if not cleaned or ":" not in cleaned:
        return ""
    try:
        parsed = socket.inet_pton(socket.AF_INET6, cleaned)
        return socket.inet_ntop(socket.AF_INET6, parsed)
    except OSError:
        return ""


def manager_url_for_yggdrasil(ipv6_address: str, port: int) -> str:
    normalized = normalize_yggdrasil_ipv6(ipv6_address)
    if not normalized:
        raise ValueError("A valid Yggdrasil IPv6 address is required")
    return f"http://[{normalized}]:{int(port)}"


def parse_yggdrasil_self(output: str) -> dict[str, str]:
    raw = str(output or "").strip()
    if not raw:
        return {}
    candidates: list[Mapping[str, Any]] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, Mapping):
            candidates.append(parsed)
            response = parsed.get("response")
            if isinstance(response, Mapping):
                candidates.append(response)
    except Exception:
        pass

    for candidate in candidates:
        address = normalize_yggdrasil_ipv6(
            str(
                candidate.get("address")
                or candidate.get("ipv6_address")
                or candidate.get("IPv6 address")
                or ""
            )
        )
        public_key = str(
            candidate.get("public_key")
            or candidate.get("box_pub_key")
            or candidate.get("Public key")
            or ""
        ).strip()
        if address:
            return {"address": address, "public_key": public_key}

    address_match = re.search(
        r"(?:IPv6\s+address|address)\s*[:=]\s*([0-9a-fA-F:]{8,})",
        raw,
        flags=re.IGNORECASE,
    )
    public_key_match = re.search(
        r"(?:Public\s+key|box_pub_key|public_key)\s*[:=]\s*([0-9a-fA-F]{32,})",
        raw,
        flags=re.IGNORECASE,
    )
    address = normalize_yggdrasil_ipv6(address_match.group(1) if address_match else "")
    if not address:
        for token in re.findall(r"\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){2,}\b", raw):
            address = normalize_yggdrasil_ipv6(token)
            if address:
                break
    if not address:
        return {}
    return {
        "address": address,
        "public_key": public_key_match.group(1).strip() if public_key_match else "",
    }


def query_yggdrasil_self(home: Path, *, timeout_seconds: float = 4.0) -> dict[str, str]:
    ctl = resolve_yggdrasilctl_binary(home)
    if not ctl:
        return {}
    commands = ([str(ctl), "-json", "getSelf"], [str(ctl), "getSelf"])
    for command in commands:
        try:
            completed = subprocess.run(
                list(command),
                check=False,
                capture_output=True,
                text=True,
                timeout=max(1.0, timeout_seconds),
                **hidden_subprocess_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        parsed = parse_yggdrasil_self((completed.stdout or "") + "\n" + (completed.stderr or ""))
        if parsed.get("address"):
            return parsed
    return {}


def yggdrasil_status(home: Path) -> dict[str, Any]:
    yggdrasil = resolve_yggdrasil_binary(home)
    yggdrasilctl = resolve_yggdrasilctl_binary(home)
    self_info = query_yggdrasil_self(home) if yggdrasilctl else {}
    running = bool(self_info.get("address"))
    return {
        "available": bool(yggdrasil or yggdrasilctl),
        "running": running,
        "address": self_info.get("address") or None,
        "public_key": self_info.get("public_key") or None,
        "yggdrasilPath": str(yggdrasil) if yggdrasil else None,
        "yggdrasilctlPath": str(yggdrasilctl) if yggdrasilctl else None,
        "installHint": yggdrasil_install_hint(),
    }


def yggdrasil_install_hint() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        asset = "x64.msi" if machine in {"amd64", "x86_64"} else "arm64.msi"
        return f"Install or bundle the Yggdrasil Windows {asset}, then rerun this command."
    if system == "darwin":
        asset = "macos-arm64.pkg" if "arm" in machine else "macos-amd64.pkg"
        return f"Install or bundle the Yggdrasil {asset}, then rerun this command."
    return "Install yggdrasil and yggdrasilctl from your OS packages or bundle the release binary."


def _request_url_bytes(url: str, *, timeout_seconds: float = 30.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "EmploAI-Yggdrasil-Bootstrap"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _machine_asset_pattern() -> str:
    machine = platform.machine().lower()
    if os.name == "nt":
        if machine in {"amd64", "x86_64"}:
            return "x64.msi"
        if "arm" in machine or "aarch64" in machine:
            return "arm64.msi"
        return "x86.msi"
    if platform.system().lower() == "darwin":
        return "macos-arm64.pkg" if ("arm" in machine or "aarch64" in machine) else "macos-amd64.pkg"
    if machine in {"amd64", "x86_64"}:
        return "amd64.deb"
    if "arm" in machine or "aarch64" in machine:
        return "arm64.deb"
    return ".deb"


def select_release_asset(assets: list[Mapping[str, Any]], *, pattern: str | None = None) -> dict[str, Any]:
    target = (pattern or _machine_asset_pattern()).lower()
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        if name.endswith(target):
            url = str(asset.get("browser_download_url") or "").strip()
            if url:
                return dict(asset)
    raise RuntimeError(f"No Yggdrasil release asset matched {target!r}")


def latest_release_asset(*, pattern: str | None = None) -> dict[str, Any]:
    parsed = json.loads(_request_url_bytes(YGGDRASIL_GITHUB_RELEASES_API, timeout_seconds=20.0).decode("utf-8"))
    assets = parsed.get("assets") if isinstance(parsed, dict) else []
    if not isinstance(assets, list):
        assets = []
    asset = select_release_asset([item for item in assets if isinstance(item, Mapping)], pattern=pattern)
    return {
        "tag_name": str(parsed.get("tag_name") or "").strip() if isinstance(parsed, dict) else "",
        "name": str(asset.get("name") or ""),
        "size": int(asset.get("size") or 0),
        "browser_download_url": str(asset.get("browser_download_url") or ""),
    }


def download_yggdrasil_installer(home: Path, *, force: bool = False) -> dict[str, Any]:
    asset = latest_release_asset()
    target_dir = _tools_yggdrasil_dir(home)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / str(asset["name"])
    expected_size = int(asset.get("size") or 0)
    if target_path.exists() and target_path.stat().st_size > 0 and not force:
        return {"downloaded": False, "path": str(target_path), "asset": asset}
    data = _request_url_bytes(str(asset["browser_download_url"]), timeout_seconds=120.0)
    if expected_size and len(data) < max(1024, expected_size // 2):
        raise RuntimeError(f"Downloaded Yggdrasil installer is unexpectedly small: {len(data)} bytes")
    target_path.write_bytes(data)
    return {"downloaded": True, "path": str(target_path), "asset": asset}


def _run_command(command: list[str], *, timeout_seconds: float = 120.0) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, timeout_seconds),
        **hidden_subprocess_kwargs(),
    )
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def install_yggdrasil_installer(installer_path: Path) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Automatic Yggdrasil install is currently implemented for Windows MSI packages only")
    path = Path(installer_path).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"Yggdrasil installer does not exist: {path}")
    return _run_command(
        ["msiexec.exe", "/i", str(path), "/passive", "/norestart"],
        timeout_seconds=240.0,
    )


def yggdrasil_config_path() -> Path | None:
    if os.name == "nt":
        root = os.getenv("ALLUSERSPROFILE") or os.getenv("ProgramData") or r"C:\ProgramData"
        return Path(root) / "Yggdrasil" / "yggdrasil.conf"
    if platform.system().lower() == "darwin":
        return Path("/etc/yggdrasil.conf")
    return Path("/etc/yggdrasil.conf")


def fetch_public_peers(*, limit: int = DEFAULT_PUBLIC_PEER_LIMIT) -> list[str]:
    try:
        text = _request_url_bytes(YGGDRASIL_PUBLIC_PEERS_URL, timeout_seconds=15.0).decode("utf-8", errors="replace")
    except Exception:
        return list(FALLBACK_PUBLIC_PEERS[:max(1, limit)])
    peers: list[str] = []
    for match in re.findall(r"\b(?:tls|quic)://[^\s`\"'<>),]+", text):
        peer = match.strip().rstrip(".")
        if peer not in peers:
            peers.append(peer)
        if len(peers) >= max(1, limit):
            break
    return peers or list(FALLBACK_PUBLIC_PEERS[:max(1, limit)])


def render_peers_block(peers: list[str], *, indent: str = "") -> str:
    clean = [str(peer or "").strip() for peer in peers if str(peer or "").strip()]
    return (
        f"{indent}Peers: [\n"
        + "\n".join(f"{indent}  {peer}" for peer in clean)
        + f"\n{indent}]"
    )


def _peer_block_matches(config_text: str) -> list[re.Match[str]]:
    inline_pattern = re.compile(r"(?m)^(?P<indent>[ \t]*)Peers:\s*\[\s*\]\s*$")
    multiline_pattern = re.compile(
        r"(?ms)^(?P<indent>[ \t]*)Peers:\s*\[\s*\n.*?^(?P=indent)\]\s*$"
    )
    matches = [*inline_pattern.finditer(config_text), *multiline_pattern.finditer(config_text)]
    return sorted(matches, key=lambda match: match.start())


def update_yggdrasil_peers_config(config_text: str, peers: list[str]) -> tuple[str, bool]:
    clean_peers = [str(peer or "").strip() for peer in peers if str(peer or "").strip()]
    if not clean_peers:
        return config_text, False
    matches = _peer_block_matches(config_text)
    if matches:
        primary = matches[0]
        indent = primary.groupdict().get("indent") or ""
        block = render_peers_block(clean_peers, indent=indent)
        primary_text = primary.group(0).strip()
        duplicates = matches[1:]
        if all(peer in primary_text for peer in clean_peers) and not duplicates:
            return config_text, False

        updated = config_text
        for duplicate in reversed(duplicates):
            updated = updated[: duplicate.start()] + updated[duplicate.end() :]
        updated = updated[: primary.start()] + block + updated[primary.end() :]
        return updated.rstrip() + "\n", True

    root_close = list(re.finditer(r"(?m)^}\s*$", config_text))
    if root_close:
        close = root_close[-1]
        key_indent_match = re.search(r"(?m)^(?P<indent>[ \t]+)[A-Za-z][A-Za-z0-9]*:\s*", config_text)
        indent = key_indent_match.group("indent") if key_indent_match else "  "
        block = render_peers_block(clean_peers, indent=indent)
        prefix = config_text[: close.start()].rstrip()
        suffix = config_text[close.start() :]
        return f"{prefix}\n\n{block}\n{suffix.rstrip()}\n", True

    suffix = "" if config_text.endswith("\n") else "\n"
    return f"{config_text}{suffix}\n{render_peers_block(clean_peers)}\n", True


def configure_yggdrasil_public_peers(*, limit: int = DEFAULT_PUBLIC_PEER_LIMIT) -> dict[str, Any]:
    config_path = yggdrasil_config_path()
    if not config_path:
        raise RuntimeError("Could not resolve Yggdrasil configuration path")
    if not config_path.exists():
        raise RuntimeError(f"Yggdrasil configuration file does not exist yet: {config_path}")
    peers = fetch_public_peers(limit=limit)
    original = config_path.read_text(encoding="utf-8", errors="replace")
    updated, changed = update_yggdrasil_peers_config(original, peers)
    if changed:
        config_path.write_text(updated, encoding="utf-8")
    return {"configured": changed, "path": str(config_path), "peers": peers}


def start_yggdrasil_service() -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Automatic Yggdrasil service start is currently implemented for Windows only")
    query = _run_command(["sc.exe", "query", "Yggdrasil"], timeout_seconds=15.0)
    if query["returncode"] != 0:
        return {"started": False, "query": query, "start": None}
    if "RUNNING" in f"{query.get('stdout', '')}\n{query.get('stderr', '')}":
        return {"started": False, "alreadyRunning": True, "query": query, "start": None}
    start = _run_command(["sc.exe", "start", "Yggdrasil"], timeout_seconds=45.0)
    return {"started": start["returncode"] == 0, "query": query, "start": start}


def restart_yggdrasil_service() -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Automatic Yggdrasil service restart is currently implemented for Windows only")
    stop = _run_command(["sc.exe", "stop", "Yggdrasil"], timeout_seconds=45.0)
    time.sleep(1.0)
    start = _run_command(["sc.exe", "start", "Yggdrasil"], timeout_seconds=45.0)
    return {"stopped": stop["returncode"] == 0, "started": start["returncode"] == 0, "stop": stop, "start": start}


def bootstrap_yggdrasil(
    home: Path,
    *,
    install: bool = True,
    start: bool = True,
    configure_default_peers: bool = True,
    force_download: bool = False,
    peer_limit: int = DEFAULT_PUBLIC_PEER_LIMIT,
) -> dict[str, Any]:
    before = yggdrasil_status(home)
    result: dict[str, Any] = {
        "ok": True,
        "before": before,
        "download": None,
        "install": None,
        "peers": None,
        "service": None,
        "after": before,
        "warnings": [],
    }
    if not before.get("available") and install:
        download = download_yggdrasil_installer(home, force=force_download)
        result["download"] = download
        install_result = install_yggdrasil_installer(Path(str(download["path"])))
        result["install"] = install_result
        if int(install_result.get("returncode") or 0) not in {0, 3010}:
            result["ok"] = False
            result["warnings"].append("Yggdrasil installer did not complete successfully.")
            result["after"] = yggdrasil_status(home)
            return result
    if configure_default_peers:
        try:
            peer_result = configure_yggdrasil_public_peers(limit=peer_limit)
            result["peers"] = peer_result
            if peer_result.get("configured"):
                try:
                    result["serviceRestart"] = restart_yggdrasil_service()
                except Exception as exc:
                    result["warnings"].append(f"Yggdrasil service restart failed after peer update: {exc}")
        except Exception as exc:
            result["warnings"].append(f"Yggdrasil peer configuration skipped: {exc}")
    if start:
        try:
            result["service"] = start_yggdrasil_service()
        except Exception as exc:
            result["warnings"].append(f"Yggdrasil service start failed: {exc}")
    deadline = time.time() + 8
    after = yggdrasil_status(home)
    while start and not after.get("running") and time.time() < deadline:
        time.sleep(0.5)
        after = yggdrasil_status(home)
    result["after"] = after
    if not after.get("available"):
        result["ok"] = False
    if start and not after.get("running"):
        result["ok"] = False
        result["warnings"].append("Yggdrasil is installed or available, but it is not running yet.")
    return result


def _b64url_json(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64url_json(value: str) -> dict[str, Any]:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    parsed = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Pairing token payload must be an object")
    return parsed


def encode_pairing_token(payload: Mapping[str, Any]) -> str:
    return f"{PAIRING_TOKEN_PREFIX}{_b64url_json(payload)}"


def decode_pairing_token(token: str) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw.startswith(PAIRING_TOKEN_PREFIX):
        raise ValueError("Unsupported EmploAI Fleet pairing token")
    payload = _unb64url_json(raw[len(PAIRING_TOKEN_PREFIX):])
    if payload.get("version") != 1 or payload.get("transport") != "yggdrasil":
        raise ValueError("Unsupported EmploAI Fleet pairing payload")
    manager_url = str(payload.get("manager_url") or "").strip().rstrip("/")
    enrollment_token = str(payload.get("enrollment_token") or "").strip()
    if not manager_url.startswith("http://[") or "]:" not in manager_url:
        raise ValueError("Pairing token does not contain a Yggdrasil manager URL")
    if not enrollment_token:
        raise ValueError("Pairing token does not contain a Fleet enrollment token")
    payload["manager_url"] = manager_url
    payload["enrollment_token"] = enrollment_token
    return payload


def build_pairing_payload(
    *,
    manager_url: str,
    manager_yggdrasil_ip: str,
    enrollment_token: str,
    expires_in_seconds: int,
    display_name: str | None = None,
    manager_public_key: str | None = None,
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "version": 1,
        "transport": "yggdrasil",
        "manager_url": str(manager_url or "").strip().rstrip("/"),
        "manager_yggdrasil_ip": normalize_yggdrasil_ipv6(manager_yggdrasil_ip),
        "manager_public_key": str(manager_public_key or "").strip() or None,
        "enrollment_token": str(enrollment_token or "").strip(),
        "display_name": str(display_name or "").strip() or None,
        "created_at": now,
        "expires_at": now + max(1, int(expires_in_seconds or DEFAULT_PAIRING_TTL_SECONDS)),
    }


def request_json(
    *,
    url: str,
    method: str = "GET",
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(dict(payload)).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url=url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method.upper()} {url} failed with HTTP {exc.code}: {detail}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method.upper()} {url} returned a non-object response")
    return parsed


def complete_worker_enrollment(
    *,
    pairing_token: str,
    home: Path,
    device_name: str,
    device_platform: str,
    device_key: str,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    payload = decode_pairing_token(pairing_token)
    manager_url = str(payload["manager_url"]).rstrip("/")
    completed = request_json(
        url=f"{manager_url}/api/fleet/enrollments/complete",
        method="POST",
        payload={
            "enrollment_token": payload["enrollment_token"],
            "device_name": device_name,
            "device_platform": device_platform,
            "device_key": device_key,
        },
        timeout_seconds=timeout_seconds,
    )
    write_remote_worker_session(home=home, manager_url=manager_url, completed=completed, pairing_payload=payload)
    return completed


def write_remote_worker_session(
    *,
    home: Path,
    manager_url: str,
    completed: Mapping[str, Any],
    pairing_payload: Mapping[str, Any],
) -> Path:
    from shared.fleet_connection_policy import DEFAULT_CONNECTION_PERMISSIONS

    token = str(completed.get("session_token") or "").strip()
    if not token:
        raise RuntimeError("Fleet enrollment did not return a worker session token")
    payload = {
        "apiBaseUrl": str(manager_url or "").strip().rstrip("/"),
        "managerUrl": str(manager_url or "").strip().rstrip("/"),
        "sessionToken": token,
        "userId": int(completed.get("user_id") or 0),
        "desktop": completed.get("desktop") or {},
        "worker": completed.get("worker") or {},
        "transport": {
            "kind": "yggdrasil",
            "managerYggdrasilIp": pairing_payload.get("manager_yggdrasil_ip"),
            "managerPublicKey": pairing_payload.get("manager_public_key"),
            "pairedAt": int(time.time()),
        },
        "connectionVersion": 2,
        "permissions": dict(DEFAULT_CONNECTION_PERMISSIONS),
        "permissionsUpdatedAt": int(time.time()),
        "permissionsUpdatedBy": "pairing_default",
    }
    return write_fleet_connection(home=home, payload=payload)
