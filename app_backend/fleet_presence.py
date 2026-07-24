from __future__ import annotations

import time
from typing import Optional


FLEET_STALE_SECONDS = 10
FLEET_OFFLINE_SECONDS = 60
FLEET_CONNECTED_STATUSES = frozenset({"connected", "online"})


def desktop_presence_status(
    status: object,
    last_heartbeat_at: Optional[float],
    *,
    now: Optional[float] = None,
) -> str:
    """Resolve persisted computer presence against its latest Fleet heartbeat."""

    normalized = str(status or "offline").strip().lower() or "offline"
    if normalized not in FLEET_CONNECTED_STATUSES:
        return normalized
    try:
        heartbeat_at = float(last_heartbeat_at or 0)
    except (TypeError, ValueError):
        heartbeat_at = 0.0
    if heartbeat_at <= 0:
        return "offline"
    current_time = time.time() if now is None else float(now)
    if max(0.0, current_time - heartbeat_at) >= FLEET_OFFLINE_SECONDS:
        return "offline"
    return normalized

