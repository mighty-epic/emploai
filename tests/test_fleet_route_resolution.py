from __future__ import annotations

import pytest

from app_backend.fleet_route_resolution import FleetRouteResolutionError, resolve_manager_delegation_route


def _snapshot(schema_version: int = 3):
    return {
        "workers": [
            {"worker_id": "worker-extra", "instance_id": "identity-extra", "display_name": "Research", "is_default": False},
            {"worker_id": "worker-default", "instance_id": "identity-default", "display_name": "Default Worker", "is_default": True},
        ],
        "desktops": [{"desktop_id": "child-vps", "display_name": "Windows VPS"}],
        "connection_permissions": [
            {
                "desktop_id": "child-vps",
                "source": "paired_desktop",
                "capabilities": {
                    "schema_version": schema_version,
                    "targets": [
                        {"role": "manager", "target_kind": "manager", "identity_id": "child-manager", "display_name": "VPS Manager"},
                        {"role": "worker", "target_kind": "worker", "identity_id": "child-worker", "target_selector": "child-worker", "display_name": "VPS Worker", "is_default": True},
                    ],
                },
            }
        ],
    }


def test_auto_routes_unqualified_work_to_local_default_worker():
    route = resolve_manager_delegation_route(_snapshot())
    assert route.route_kind == "local_worker"
    assert route.worker_id == "worker-default"


def test_named_child_routes_to_published_default_worker():
    route = resolve_manager_delegation_route(_snapshot(), computer="Windows VPS")
    assert route.route_kind == "child_worker"
    assert route.computer_id == "child-vps"
    assert route.identity_id == "child-worker"


def test_child_coordination_routes_to_child_manager():
    route = resolve_manager_delegation_route(_snapshot(), scope="child", computer="Windows VPS", target_role="manager")
    assert route.route_kind == "child_manager"
    assert route.identity_id == "child-manager"


def test_published_child_identity_routes_without_requiring_computer_selector():
    route = resolve_manager_delegation_route(_snapshot(), identity="child-worker")
    assert route.scope == "child"
    assert route.route_kind == "child_worker"
    assert route.computer_id == "child-vps"
    assert route.identity_id == "child-worker"


def test_older_child_requires_update_for_automatic_worker_route():
    with pytest.raises(FleetRouteResolutionError) as error:
        resolve_manager_delegation_route(_snapshot(schema_version=2), computer="Windows VPS")
    assert error.value.code == "child_update_required"
