from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


LOCAL_WORKER_CREATION_SOURCES = frozenset(
    {
        "desktop_user_request",
        "mobile_user_request",
        "manager_chat_user_request",
        "paired_manager_request",
    }
)


def validate_local_worker_creation(
    *,
    display_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Accept only named worker identities with an explicit user/parent origin."""

    name = str(display_name or "").strip()
    if not name:
        raise ValueError("A worker name is required")

    clean_metadata = dict(metadata or {})
    source = str(clean_metadata.get("created_by") or "").strip().lower()
    if source not in LOCAL_WORKER_CREATION_SOURCES:
        raise PermissionError(
            "Worker creation requires an explicit local-user or paired-manager request"
        )
    clean_metadata["created_by"] = source
    return name, clean_metadata
