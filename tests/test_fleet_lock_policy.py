from __future__ import annotations

import pytest

from app_backend.fleet_lock_policy import (
    DEFAULT_FLEET_LOCK_TTL_SECONDS,
    FLEET_LOCK_RELEASE_REQUIRED_ERROR,
    FLEET_LOCK_REQUIRED_ERROR,
    MAX_FLEET_LOCK_ID_CHARS,
    MAX_FLEET_LOCK_KIND_CHARS,
    MAX_FLEET_LOCK_TTL_SECONDS,
    MIN_FLEET_LOCK_TTL_SECONDS,
    fleet_lock_owner_matches,
    normalize_fleet_lock_claim,
    normalize_fleet_lock_release,
    normalize_fleet_lock_ttl,
)


def test_normalize_fleet_lock_claim_trims_limits_and_copies_metadata():
    metadata = {"reason": "write"}

    claim = normalize_fleet_lock_claim(
        resource_kind=f" workspace {'x' * 120}",
        resource_id=f" workspace-alpha {'y' * 320}",
        owner_kind=" worker ",
        owner_id=f" worker-1 {'z' * 320}",
        task_id=" task-123 ",
        ttl_seconds=5,
        metadata=metadata,
    )
    metadata["reason"] = "changed"

    assert claim.resource_kind == f"workspace {'x' * 120}"[:MAX_FLEET_LOCK_KIND_CHARS]
    assert claim.resource_id == f"workspace-alpha {'y' * 320}"[:MAX_FLEET_LOCK_ID_CHARS]
    assert claim.owner_kind == "worker"
    assert claim.owner_id == f"worker-1 {'z' * 320}"[:MAX_FLEET_LOCK_ID_CHARS]
    assert claim.task_id == "task-123"
    assert claim.ttl_seconds == MIN_FLEET_LOCK_TTL_SECONDS
    assert claim.metadata == {"reason": "write"}


def test_normalize_fleet_lock_claim_rejects_missing_required_fields():
    with pytest.raises(ValueError, match=FLEET_LOCK_REQUIRED_ERROR):
        normalize_fleet_lock_claim(
            resource_kind="workspace",
            resource_id="workspace-alpha",
            owner_kind="worker",
            owner_id=" ",
        )


def test_normalize_fleet_lock_ttl_preserves_store_bounds():
    assert normalize_fleet_lock_ttl(0) == DEFAULT_FLEET_LOCK_TTL_SECONDS
    assert normalize_fleet_lock_ttl(1) == MIN_FLEET_LOCK_TTL_SECONDS
    assert normalize_fleet_lock_ttl(999999) == MAX_FLEET_LOCK_TTL_SECONDS


def test_normalize_fleet_lock_release_accepts_lock_id_or_resource_identity():
    by_id = normalize_fleet_lock_release(lock_id=" lock-1 ", owner_kind=" worker ", owner_id=" worker-1 ")
    by_resource = normalize_fleet_lock_release(
        resource_kind=" workspace ",
        resource_id=" workspace-alpha ",
        owner_kind="worker",
    )

    assert by_id.lock_id == "lock-1"
    assert by_id.owner_kind == "worker"
    assert by_id.owner_id == "worker-1"
    assert by_resource.lock_id == ""
    assert by_resource.resource_kind == "workspace"
    assert by_resource.resource_id == "workspace-alpha"


def test_normalize_fleet_lock_release_rejects_missing_identity():
    with pytest.raises(ValueError, match=FLEET_LOCK_RELEASE_REQUIRED_ERROR):
        normalize_fleet_lock_release(resource_kind="workspace")


def test_fleet_lock_owner_matches_normalized_claim_owner():
    claim = normalize_fleet_lock_claim(
        resource_kind="workspace",
        resource_id="workspace-alpha",
        owner_kind="worker",
        owner_id="worker-1",
    )

    assert fleet_lock_owner_matches(
        existing_owner_kind="worker",
        existing_owner_id="worker-1",
        owner_kind=claim.owner_kind,
        owner_id=claim.owner_id,
    )
    assert not fleet_lock_owner_matches(
        existing_owner_kind="worker",
        existing_owner_id="worker-2",
        owner_kind=claim.owner_kind,
        owner_id=claim.owner_id,
    )
