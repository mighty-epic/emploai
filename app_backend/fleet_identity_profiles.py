from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from shared.tool_packs import (
    PACK_APP_RUNTIME,
    PACK_BROWSER_ISOLATED,
    PACK_INTERACTIVE_DESKTOP,
    PACK_MANAGER_CORE,
    PACK_SCHEDULER,
    PACK_WEB_RESEARCH,
    PACK_WORKSPACE_READ,
    PACK_WORKSPACE_WRITE,
    normalize_enabled_tool_packs,
)


MANAGER_TOOL_PROFILE = "manager_core"
DEFAULT_WORKER_TOOL_PROFILE = "default_execution"
DEFAULT_WORKER_DISPLAY_NAME = "Default Worker"

MANAGER_TOOL_PACKS: List[str] = [PACK_MANAGER_CORE]
DEFAULT_WORKER_TOOL_PACKS: List[str] = [
    PACK_INTERACTIVE_DESKTOP,
    PACK_BROWSER_ISOLATED,
    PACK_WORKSPACE_READ,
    PACK_WORKSPACE_WRITE,
    PACK_WEB_RESEARCH,
]

MANAGER_CAPABILITY_TAGS = ["orchestration", "memory", "automations", "scheduler"]
DEFAULT_WORKER_CAPABILITY_TAGS = ["desktop", "browser", "workspace", "web"]


def manager_identity_metadata(existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = dict(existing or {})
    enabled_tool_packs = role_locked_tool_packs(
        role="manager",
        requested=metadata.get("enabled_tool_packs") or MANAGER_TOOL_PACKS,
    )
    metadata.update(
        {
            "tool_profile": MANAGER_TOOL_PROFILE,
            "enabled_tool_packs": enabled_tool_packs,
            "capability_tags": _manager_capability_tags_for_packs(enabled_tool_packs),
            "protected": True,
            "published_upstream": bool(metadata.get("published_upstream", True)),
        }
    )
    return metadata


def default_worker_metadata(existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = dict(existing or {})
    metadata.update(
        {
            "created_by": "system_identity_reconciler",
            "is_default": True,
            "protected": True,
            "tool_profile": DEFAULT_WORKER_TOOL_PROFILE,
            "enabled_tool_packs": list(DEFAULT_WORKER_TOOL_PACKS),
            "capability_tags": list(DEFAULT_WORKER_CAPABILITY_TAGS),
            "published_upstream": bool(metadata.get("published_upstream", True)),
        }
    )
    return metadata


def additional_worker_metadata(existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = dict(existing or {})
    metadata["is_default"] = False
    metadata["protected"] = bool(metadata.get("protected", False))
    metadata.setdefault("tool_profile", "custom_execution")
    packs = normalize_enabled_tool_packs(metadata.get("enabled_tool_packs") or DEFAULT_WORKER_TOOL_PACKS)
    metadata["enabled_tool_packs"] = [pack for pack in packs if pack != PACK_MANAGER_CORE]
    metadata.setdefault("capability_tags", _capability_tags_for_packs(metadata["enabled_tool_packs"]))
    metadata["published_upstream"] = bool(metadata.get("published_upstream", True))
    return metadata


def role_locked_tool_packs(
    *,
    role: Optional[str],
    requested: Optional[Iterable[str]] = None,
    identity_metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    clean_role = str(role or "").strip().lower()
    metadata = dict(identity_metadata or {})
    if clean_role == "manager":
        configured = metadata.get("enabled_tool_packs")
        packs = normalize_enabled_tool_packs(configured if configured is not None else requested)
        return [PACK_MANAGER_CORE, *[pack for pack in packs if pack != PACK_MANAGER_CORE]]
    if clean_role == "worker":
        configured = metadata.get("enabled_tool_packs")
        packs = normalize_enabled_tool_packs(configured if configured is not None else requested)
        if not packs:
            packs = list(DEFAULT_WORKER_TOOL_PACKS)
        return [pack for pack in packs if pack != PACK_MANAGER_CORE]
    return normalize_enabled_tool_packs(list(requested or []))


def identity_public_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    value = dict(metadata or {})
    return {
        "is_default": bool(value.get("is_default")),
        "protected": bool(value.get("protected")),
        "tool_profile": str(value.get("tool_profile") or "").strip() or None,
        "enabled_tool_packs": normalize_enabled_tool_packs(value.get("enabled_tool_packs") or []),
        "capability_tags": [str(item) for item in list(value.get("capability_tags") or []) if str(item).strip()],
        "published_upstream": bool(value.get("published_upstream", True)),
    }


def _capability_tags_for_packs(packs: Iterable[str]) -> List[str]:
    enabled = set(packs)
    tags: List[str] = []
    if PACK_INTERACTIVE_DESKTOP in enabled:
        tags.append("desktop")
    if PACK_BROWSER_ISOLATED in enabled:
        tags.append("browser")
    if PACK_WORKSPACE_READ in enabled or PACK_WORKSPACE_WRITE in enabled:
        tags.append("workspace")
    if PACK_WEB_RESEARCH in enabled:
        tags.append("web")
    if PACK_SCHEDULER in enabled:
        tags.append("scheduler")
    if PACK_APP_RUNTIME in enabled:
        tags.append("runtime")
    return tags


def _manager_capability_tags_for_packs(packs: Iterable[str]) -> List[str]:
    return list(dict.fromkeys([*MANAGER_CAPABILITY_TAGS, *_capability_tags_for_packs(packs)]))
