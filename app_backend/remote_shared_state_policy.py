from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


FLEET_SELECTION_FIELDS = (
    "active_identity_id",
    "selected_chat_by_identity",
    "active_identity_version",
    "active_identity_updated_at",
)


def empty_fleet_selection() -> Dict[str, Any]:
    return {
        "active_identity_id": None,
        "selected_chat_by_identity": {},
        "active_identity_version": 0,
        "active_identity_updated_at": None,
    }


def normalize_fleet_selection(value: Any) -> Dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    selection = empty_fleet_selection()
    selection.update({key: raw.get(key, selection[key]) for key in FLEET_SELECTION_FIELDS})
    if not isinstance(selection.get("selected_chat_by_identity"), dict):
        selection["selected_chat_by_identity"] = {}
    selection["selected_chat_by_identity"] = {
        str(key): (str(val).strip() if val else None)
        for key, val in dict(selection.get("selected_chat_by_identity") or {}).items()
        if str(key or "").strip()
    }
    try:
        selection["active_identity_version"] = int(selection.get("active_identity_version") or 0)
    except Exception:
        selection["active_identity_version"] = 0
    return selection


def empty_fleet_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        **empty_fleet_selection(),
        "selection_by_desktop": {},
    }


def normalize_fleet_state(value: Any) -> Dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    base = empty_fleet_state()
    base.update({key: raw.get(key, base[key]) for key in base})
    base.update(normalize_fleet_selection(base))
    raw_by_desktop = base.get("selection_by_desktop")
    base["selection_by_desktop"] = {
        str(desktop_id): normalize_fleet_selection(selection)
        for desktop_id, selection in dict(raw_by_desktop if isinstance(raw_by_desktop, dict) else {}).items()
        if str(desktop_id or "").strip()
    }
    return base


def fleet_selection_for_desktop(value: Any, desktop_id: str | None) -> Dict[str, Any]:
    fleet = normalize_fleet_state(value)
    clean_desktop_id = str(desktop_id or "").strip()
    if clean_desktop_id:
        stored = fleet["selection_by_desktop"].get(clean_desktop_id)
        if stored is not None:
            return normalize_fleet_selection(stored)
    return normalize_fleet_selection(fleet)


def store_fleet_selection_for_desktop(
    value: Any,
    desktop_id: str | None,
    selection: Any,
) -> Dict[str, Any]:
    fleet = normalize_fleet_state(value)
    normalized = normalize_fleet_selection(selection)
    clean_desktop_id = str(desktop_id or "").strip()
    if clean_desktop_id:
        by_desktop = dict(fleet.get("selection_by_desktop") or {})
        by_desktop[clean_desktop_id] = normalized
        fleet["selection_by_desktop"] = by_desktop
    # Keep the legacy top-level fields as a compatibility mirror. Scoped
    # readers use selection_by_desktop and therefore cannot overwrite another
    # computer's selected identity merely by polling its Fleet snapshot.
    for key in FLEET_SELECTION_FIELDS:
        fleet[key] = normalized[key]
    return fleet


def project_groups_from_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for session in sessions:
        workspace = str(session.get("workspace") or "").strip()
        if not workspace:
            workspace = "workspace://default"
        label = Path(workspace).name or workspace
        group = groups.setdefault(
            workspace,
            {
                "path": workspace,
                "label": label,
                "session_ids": [],
                "pinned": False,
                "collapsed": False,
            },
        )
        session_id = str(session.get("id") or "").strip()
        if session_id:
            group["session_ids"].append(session_id)
    ordered = list(groups.values())
    ordered.sort(key=lambda item: (str(item.get("label") or "").casefold(), str(item.get("path") or "").casefold()))
    return ordered


def empty_sidebar_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "projectOrder": [],
        "projects": {},
        "sessionMeta": {},
        "selectedProjectPath": None,
        "lastSelectedProjectPath": None,
    }
