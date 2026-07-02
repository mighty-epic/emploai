from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def empty_fleet_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_identity_id": None,
        "selected_chat_by_identity": {},
        "active_identity_version": 0,
        "active_identity_updated_at": None,
    }


def normalize_fleet_state(value: Any) -> Dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    base = empty_fleet_state()
    base.update({key: raw.get(key, base[key]) for key in base})
    if not isinstance(base.get("selected_chat_by_identity"), dict):
        base["selected_chat_by_identity"] = {}
    base["selected_chat_by_identity"] = {
        str(key): (str(val).strip() if val else None)
        for key, val in dict(base.get("selected_chat_by_identity") or {}).items()
        if str(key or "").strip()
    }
    try:
        base["active_identity_version"] = int(base.get("active_identity_version") or 0)
    except Exception:
        base["active_identity_version"] = 0
    return base


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
