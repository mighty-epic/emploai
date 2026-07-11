"""Local Fleet worker connection state.

This file replaces the former account-session reuse.  A connection is valid
only when it was issued by a directly paired Yggdrasil Fleet manager.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping


FLEET_CONNECTION_FILENAME = "fleet-connection.json"
LEGACY_ACCOUNT_SESSION_FILENAME = "remote-account-session.json"


def fleet_connection_path(home: Path) -> Path:
    return Path(home).expanduser().resolve() / FLEET_CONNECTION_FILENAME


def _is_yggdrasil_connection(payload: Mapping[str, Any]) -> bool:
    transport = payload.get("transport") if isinstance(payload.get("transport"), dict) else {}
    manager_url = str(payload.get("managerUrl") or payload.get("apiBaseUrl") or "").strip()
    session_token = str(payload.get("sessionToken") or "").strip()
    return bool(
        str((transport or {}).get("kind") or "").strip().lower() == "yggdrasil"
        and manager_url.startswith("http://")
        and session_token
    )


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def load_fleet_connection(home: Path, *, migrate_legacy: bool = True) -> Dict[str, Any]:
    home = Path(home).expanduser().resolve()
    path = fleet_connection_path(home)
    payload = _read_json(path)
    if _is_yggdrasil_connection(payload):
        return payload

    if not migrate_legacy:
        return {}
    legacy_path = home / LEGACY_ACCOUNT_SESSION_FILENAME
    legacy_payload = _read_json(legacy_path)
    if not _is_yggdrasil_connection(legacy_payload):
        return {}

    written = write_fleet_connection(home=home, payload=legacy_payload)
    try:
        legacy_path.unlink()
    except OSError:
        pass
    return _read_json(written)


def fleet_connection_configured(home: Path) -> bool:
    return bool(load_fleet_connection(home))


def write_fleet_connection(*, home: Path, payload: Mapping[str, Any]) -> Path:
    normalized = dict(payload or {})
    if not _is_yggdrasil_connection(normalized):
        raise ValueError("Fleet connections must be issued through Yggdrasil pairing")
    manager_url = str(normalized.get("managerUrl") or normalized.get("apiBaseUrl") or "").strip().rstrip("/")
    normalized["managerUrl"] = manager_url
    normalized["apiBaseUrl"] = manager_url

    path = fleet_connection_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
