from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


MAX_FLEET_LOCK_KIND_CHARS = 80
MAX_FLEET_LOCK_ID_CHARS = 256
MIN_FLEET_LOCK_TTL_SECONDS = 30
MAX_FLEET_LOCK_TTL_SECONDS = 60 * 60 * 24
DEFAULT_FLEET_LOCK_TTL_SECONDS = 300
FLEET_LOCK_REQUIRED_ERROR = "resource_kind, resource_id, owner_kind, and owner_id are required"
FLEET_LOCK_RELEASE_REQUIRED_ERROR = "lock_id or resource_kind/resource_id is required"
FLEET_LOCK_CONFLICT_ERROR = "Fleet resource is already locked by another owner"


@dataclass(frozen=True)
class FleetLockClaim:
    resource_kind: str
    resource_id: str
    owner_kind: str
    owner_id: str
    task_id: Optional[str]
    ttl_seconds: int
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class FleetLockRelease:
    lock_id: str
    resource_kind: str
    resource_id: str
    owner_kind: str
    owner_id: str


def _clean(value: Optional[str], max_chars: Optional[int] = None) -> str:
    clean_value = str(value or "").strip()
    if max_chars is not None:
        return clean_value[:max_chars]
    return clean_value


def normalize_fleet_lock_ttl(ttl_seconds: Optional[int]) -> int:
    ttl_value = int(ttl_seconds or DEFAULT_FLEET_LOCK_TTL_SECONDS)
    return max(MIN_FLEET_LOCK_TTL_SECONDS, min(MAX_FLEET_LOCK_TTL_SECONDS, ttl_value))


def normalize_fleet_lock_claim(
    *,
    resource_kind: str,
    resource_id: str,
    owner_kind: str,
    owner_id: str,
    task_id: Optional[str] = None,
    ttl_seconds: int = DEFAULT_FLEET_LOCK_TTL_SECONDS,
    metadata: Optional[Dict[str, Any]] = None,
) -> FleetLockClaim:
    claim = FleetLockClaim(
        resource_kind=_clean(resource_kind, MAX_FLEET_LOCK_KIND_CHARS),
        resource_id=_clean(resource_id, MAX_FLEET_LOCK_ID_CHARS),
        owner_kind=_clean(owner_kind, MAX_FLEET_LOCK_KIND_CHARS),
        owner_id=_clean(owner_id, MAX_FLEET_LOCK_ID_CHARS),
        task_id=_clean(task_id) or None,
        ttl_seconds=normalize_fleet_lock_ttl(ttl_seconds),
        metadata=dict(metadata or {}),
    )
    if not claim.resource_kind or not claim.resource_id or not claim.owner_kind or not claim.owner_id:
        raise ValueError(FLEET_LOCK_REQUIRED_ERROR)
    return claim


def normalize_fleet_lock_release(
    *,
    lock_id: Optional[str] = None,
    resource_kind: Optional[str] = None,
    resource_id: Optional[str] = None,
    owner_kind: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> FleetLockRelease:
    release = FleetLockRelease(
        lock_id=_clean(lock_id),
        resource_kind=_clean(resource_kind),
        resource_id=_clean(resource_id),
        owner_kind=_clean(owner_kind),
        owner_id=_clean(owner_id),
    )
    if not release.lock_id and (not release.resource_kind or not release.resource_id):
        raise ValueError(FLEET_LOCK_RELEASE_REQUIRED_ERROR)
    return release


def fleet_lock_owner_matches(
    *,
    existing_owner_kind: Any,
    existing_owner_id: Any,
    owner_kind: str,
    owner_id: str,
) -> bool:
    return str(existing_owner_kind or "") == owner_kind and str(existing_owner_id or "") == owner_id
