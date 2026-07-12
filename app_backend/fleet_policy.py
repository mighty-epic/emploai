from __future__ import annotations

from typing import Optional


MIN_WORKER_DEVICE_KEY_CHARS = 8
MAX_DISPLAY_NAME_CHARS = 160
MAX_DEVICE_PLATFORM_CHARS = 80
MAX_DEVICE_KEY_CHARS = 256
FLEET_PREVIEW_MODE = "screen_summary_or_low_rate_preview"
MIN_FLEET_ENROLLMENT_TTL_SECONDS = 60
MAX_FLEET_ENROLLMENT_TTL_SECONDS = 60 * 60 * 24
# Directly paired Fleet desktops remain authorized until the manager removes
# their worker. A zero expiry is already treated as durable by the session store.
FLEET_WORKER_SESSION_TTL_SECONDS = 0


def normalize_worker_enrollment_identity(
    *,
    device_name: Optional[str],
    device_platform: Optional[str],
    device_key: Optional[str],
) -> dict[str, Optional[str]]:
    clean_key = str(device_key or "").strip()[:MAX_DEVICE_KEY_CHARS]
    if len(clean_key) < MIN_WORKER_DEVICE_KEY_CHARS:
        raise ValueError(
            f"Worker enrollment requires a stable device_key of at least {MIN_WORKER_DEVICE_KEY_CHARS} characters"
        )
    return {
        "device_name": str(device_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
        "device_platform": str(device_platform or "").strip()[:MAX_DEVICE_PLATFORM_CHARS] or None,
        "device_key": clean_key,
    }


def ensure_worker_key_not_manager_key(*, worker_device_key: str, manager_device_key: Optional[str]) -> None:
    clean_worker_key = str(worker_device_key or "").strip()
    clean_manager_key = str(manager_device_key or "").strip()
    if clean_worker_key and clean_manager_key and clean_worker_key == clean_manager_key:
        raise ValueError("Worker enrollment must use a worker-specific device_key, not the manager desktop key")


def normalize_fleet_enrollment_ttl(ttl_seconds: Optional[int], default_seconds: int) -> int:
    try:
        ttl = int(ttl_seconds or default_seconds)
    except (TypeError, ValueError):
        ttl = int(default_seconds)
    return min(MAX_FLEET_ENROLLMENT_TTL_SECONDS, max(MIN_FLEET_ENROLLMENT_TTL_SECONDS, ttl))


def preview_dispatch_target(worker: dict) -> Optional[str]:
    return str(worker.get("machine_desktop_id") or worker.get("desktop_id") or "").strip() or None
