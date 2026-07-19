from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional


@dataclass(frozen=True)
class ResolvedFleetRoute:
    scope: str
    route_kind: str
    computer_id: Optional[str]
    computer_name: Optional[str]
    identity_id: Optional[str]
    identity_name: str
    identity_role: str
    worker_id: Optional[str] = None
    target_selector: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "route_kind": self.route_kind,
            "computer_id": self.computer_id,
            "computer_name": self.computer_name,
            "identity_id": self.identity_id,
            "identity_name": self.identity_name,
            "identity_role": self.identity_role,
            "worker_id": self.worker_id,
            "target_selector": self.target_selector,
        }


class FleetRouteResolutionError(ValueError):
    def __init__(self, message: str, *, code: str = "route_not_found"):
        super().__init__(message)
        self.code = code


def resolve_manager_delegation_route(
    snapshot: Mapping[str, Any],
    *,
    scope: str = "auto",
    computer: Optional[str] = None,
    identity: Optional[str] = None,
    target_role: str = "auto",
) -> ResolvedFleetRoute:
    clean_scope = str(scope or "auto").strip().lower()
    if clean_scope not in {"auto", "local", "child"}:
        raise FleetRouteResolutionError("scope must be auto, local, or child", code="invalid_scope")
    clean_role = str(target_role or "auto").strip().lower()
    if clean_role not in {"auto", "manager", "worker"}:
        raise FleetRouteResolutionError("target_role must be auto, manager, or worker", code="invalid_target_role")

    computer_state = _find_child_computer(snapshot, computer) if computer else None
    if clean_scope == "auto":
        clean_scope = "child" if computer_state or _identity_matches_child(snapshot, identity) else "local"
    if clean_scope == "local":
        return _resolve_local(snapshot, identity=identity, target_role=clean_role)
    return _resolve_child(snapshot, computer_state=computer_state, computer=computer, identity=identity, target_role=clean_role)


def _resolve_local(
    snapshot: Mapping[str, Any],
    *,
    identity: Optional[str],
    target_role: str,
) -> ResolvedFleetRoute:
    workers = [item for item in list(snapshot.get("workers") or []) if isinstance(item, Mapping)]
    if target_role == "manager":
        raise FleetRouteResolutionError(
            "A local manager does not delegate back to itself; answer this request directly.",
            code="local_manager_route",
        )
    selected = _match(identity, workers, ("worker_id", "instance_id", "display_name")) if identity else None
    if identity and not selected:
        raise FleetRouteResolutionError("The requested local worker identity was not found.")
    if not selected:
        selected = next((item for item in workers if bool(item.get("is_default"))), None)
    if not selected:
        raise FleetRouteResolutionError("This computer has no default worker.", code="default_worker_missing")
    return ResolvedFleetRoute(
        scope="local",
        route_kind="local_worker",
        computer_id=str(selected.get("machine_desktop_id") or "").strip() or None,
        computer_name="This computer",
        identity_id=str(selected.get("instance_id") or "").strip() or None,
        identity_name=str(selected.get("display_name") or "Default Worker"),
        identity_role="worker",
        worker_id=str(selected.get("worker_id") or "").strip() or None,
        target_selector=str(selected.get("instance_id") or selected.get("worker_id") or "").strip() or None,
    )


def _resolve_child(
    snapshot: Mapping[str, Any],
    *,
    computer_state: Optional[Mapping[str, Any]],
    computer: Optional[str],
    identity: Optional[str],
    target_role: str,
) -> ResolvedFleetRoute:
    state = computer_state or _child_for_identity(snapshot, identity)
    if not state:
        raise FleetRouteResolutionError(
            "Choose a directly connected child computer or one of its published identities.",
            code="computer_not_found",
        )
    capabilities = dict(state.get("capabilities") or {})
    targets = [item for item in list(capabilities.get("targets") or []) if isinstance(item, Mapping)]
    selected = _match(identity, targets, ("identity_id", "target_selector", "display_name")) if identity else None
    if identity and not selected:
        raise FleetRouteResolutionError("That identity is not published by the selected child computer.")
    if not selected and target_role == "manager":
        selected = next((item for item in targets if str(item.get("role") or item.get("target_kind") or "") == "manager"), None)
    if not selected:
        if int(capabilities.get("schema_version") or 0) < 3:
            raise FleetRouteResolutionError(
                "Update EmploAI on this child computer before using automatic worker routing.",
                code="child_update_required",
            )
        selected = next(
            (
                item for item in targets
                if str(item.get("role") or item.get("target_kind") or "") == "worker" and bool(item.get("is_default"))
            ),
            None,
        )
    if not selected:
        raise FleetRouteResolutionError("The child computer has no published default worker.", code="default_worker_missing")
    role = str(selected.get("role") or selected.get("target_kind") or "worker").strip().lower()
    computer_id = str(state.get("desktop_id") or "").strip()
    return ResolvedFleetRoute(
        scope="child",
        route_kind=f"child_{role}",
        computer_id=computer_id,
        computer_name=str(state.get("display_name") or computer_id),
        identity_id=str(selected.get("identity_id") or "").strip() or None,
        identity_name=str(selected.get("display_name") or role.title()),
        identity_role=role,
        target_selector=str(selected.get("target_selector") or selected.get("identity_id") or "").strip() or None,
    )


def _child_states(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item for item in list(snapshot.get("connection_permissions") or [])
        if isinstance(item, Mapping) and str(item.get("source") or "") == "paired_desktop"
    ]


def _find_child_computer(snapshot: Mapping[str, Any], selector: Optional[str]) -> Optional[Mapping[str, Any]]:
    needle = str(selector or "").strip().casefold()
    if not needle:
        return None
    desktop_names = {
        str(item.get("desktop_id") or ""): str(item.get("display_name") or "")
        for item in list(snapshot.get("desktops") or []) if isinstance(item, Mapping)
    }
    matches = [
        state for state in _child_states(snapshot)
        if needle in {
            str(state.get("desktop_id") or "").casefold(),
            desktop_names.get(str(state.get("desktop_id") or ""), "").casefold(),
            str(state.get("desktop_name") or "").casefold(),
        }
    ]
    if len(matches) != 1:
        return None
    state = dict(matches[0])
    state.setdefault("display_name", desktop_names.get(str(state.get("desktop_id") or "")))
    return state


def _child_for_identity(snapshot: Mapping[str, Any], selector: Optional[str]) -> Optional[Mapping[str, Any]]:
    needle = str(selector or "").strip().casefold()
    if not needle:
        return None
    matches = []
    for state in _child_states(snapshot):
        targets = list((state.get("capabilities") or {}).get("targets") or [])
        if _match(needle, targets, ("identity_id", "target_selector", "display_name")):
            matches.append(state)
    return matches[0] if len(matches) == 1 else None


def _identity_matches_child(snapshot: Mapping[str, Any], selector: Optional[str]) -> bool:
    return _child_for_identity(snapshot, selector) is not None


def _match(selector: Optional[str], items: Iterable[Mapping[str, Any]], fields: Iterable[str]) -> Optional[Mapping[str, Any]]:
    needle = str(selector or "").strip().casefold()
    if not needle:
        return None
    matches = [
        item for item in items
        if needle in {str(item.get(field) or "").strip().casefold() for field in fields}
    ]
    return matches[0] if len(matches) == 1 else None
