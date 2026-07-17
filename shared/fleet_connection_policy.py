"""Permission state for a directly paired Fleet computer.

The paired computer owns this policy.  A manager may request a change, but it
cannot grant itself additional access.  The state lives beside the durable
Yggdrasil connection and contains no chats, identities, or provider data.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any, Mapping

from shared.fleet_connection import load_fleet_connection, write_fleet_connection


PERMISSION_KEYS = (
    "delegate_manager",
    "delegate_workers",
    "create_workers",
    "manage_runtime",
    "manage_updates",
)

DEFAULT_CONNECTION_PERMISSIONS: dict[str, bool] = {
    "delegate_manager": True,
    "delegate_workers": True,
    "create_workers": False,
    "manage_runtime": True,
    "manage_updates": True,
}


def normalize_connection_permissions(value: Mapping[str, Any] | None) -> dict[str, bool]:
    raw = dict(value or {})
    return {
        key: bool(raw[key]) if key in raw else default
        for key, default in DEFAULT_CONNECTION_PERMISSIONS.items()
    }


def connection_policy_view(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    connection = dict(payload or {})
    pending = connection.get("pendingPermissionRequest")
    if not isinstance(pending, dict):
        pending = None
    last_decision = connection.get("lastPermissionDecision")
    if not isinstance(last_decision, dict):
        last_decision = None
    return {
        "permissions": normalize_connection_permissions(connection.get("permissions") if isinstance(connection.get("permissions"), dict) else None),
        "pendingRequest": dict(pending) if pending else None,
        "lastDecision": dict(last_decision) if last_decision else None,
        "updatedAt": connection.get("permissionsUpdatedAt"),
    }


def load_connection_policy(home: Path) -> dict[str, Any]:
    return connection_policy_view(load_fleet_connection(home))


def set_connection_permissions(
    home: Path,
    permissions: Mapping[str, Any],
    *,
    source: str = "local_user",
) -> dict[str, Any]:
    connection = load_fleet_connection(home)
    if not connection:
        raise RuntimeError("This desktop is not paired to a Fleet manager")
    connection["permissions"] = normalize_connection_permissions(permissions)
    connection["permissionsUpdatedAt"] = int(time.time())
    connection["permissionsUpdatedBy"] = str(source or "local_user")[:80]
    write_fleet_connection(home=home, payload=connection)
    return connection_policy_view(connection)


def record_permission_request(
    home: Path,
    *,
    requested: Mapping[str, Any],
    reason: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    connection = load_fleet_connection(home)
    if not connection:
        raise RuntimeError("This desktop is not paired to a Fleet manager")
    request = {
        "requestId": str(request_id or f"fpr_{secrets.token_hex(8)}"),
        "requested": normalize_connection_permissions(requested),
        "reason": str(reason or "").strip()[:1000] or None,
        "status": "pending",
        "createdAt": int(time.time()),
    }
    connection["pendingPermissionRequest"] = request
    write_fleet_connection(home=home, payload=connection)
    return connection_policy_view(connection)


def decide_permission_request(
    home: Path,
    *,
    request_id: str,
    approve: bool,
) -> dict[str, Any]:
    connection = load_fleet_connection(home)
    if not connection:
        raise RuntimeError("This desktop is not paired to a Fleet manager")
    pending = connection.get("pendingPermissionRequest")
    if not isinstance(pending, dict) or str(pending.get("requestId") or "") != str(request_id or ""):
        raise ValueError("The permission request is no longer pending")
    now = int(time.time())
    if approve:
        connection["permissions"] = normalize_connection_permissions(
            pending.get("requested") if isinstance(pending.get("requested"), dict) else None
        )
        connection["permissionsUpdatedAt"] = now
        connection["permissionsUpdatedBy"] = "local_approval"
    decision = {
        **dict(pending),
        "status": "approved" if approve else "denied",
        "decidedAt": now,
    }
    connection["lastPermissionDecision"] = decision
    connection.pop("pendingPermissionRequest", None)
    write_fleet_connection(home=home, payload=connection)
    return connection_policy_view(connection)


def policy_signature(policy: Mapping[str, Any]) -> str:
    return json.dumps(dict(policy or {}), sort_keys=True, separators=(",", ":"))
