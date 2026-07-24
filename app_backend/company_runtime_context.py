from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from app_backend.request_company_context import requested_company_id
from shared.fleet_connection import load_fleet_connection
from shared.memory import migrate_legacy_memory_to_company
from shared.runtime_paths import runtime_home


logger = logging.getLogger(__name__)


def resolve_local_company_runtime(
    *,
    auth: Mapping[str, Any],
    company_store: Any,
    fleet_store: Any,
    company_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve and reconcile the selected local company below UI routing."""

    user_id = int(auth.get("user_id") or 0)
    device_id = str(auth.get("device_id") or auth.get("desktop_id") or "").strip()
    if not device_id:
        # Access tokens issued by current desktop builds always include a device
        # identity. Keep pre-device local sessions on one deterministic migration
        # computer instead of dropping their Company context. Remote sessions must
        # still prove the paired computer they represent.
        if str(auth.get("auth_kind") or "") == "remote_session" or user_id <= 0:
            return None
        device_id = f"legacy-local-user:{user_id}"
    device_name = str(
        auth.get("device_name")
        or auth.get("desktop_name")
        or "EmploAI Desktop"
    ).strip()
    desktop = fleet_store.ensure_standalone_manager_desktop(
        user_id=user_id,
        display_name=device_name,
        device_platform=str(auth.get("device_platform") or "desktop-electron"),
        device_key=(
            f"local-app:{device_id}"
            if str(auth.get("auth_kind") or "") != "remote_session"
            else None
        ),
    )
    computer_id = str(desktop.get("desktop_id") or "").strip()
    requested_id = str(company_id or "").strip()
    active_company_id = requested_id or company_store.active_company_id(
        computer_id=computer_id
    )

    if not active_company_id:
        snapshot = fleet_store.get_fleet_snapshot(
            user_id=user_id,
            desktop_id=computer_id,
        )
        identities = list(snapshot.get("identities") or [])
        manager = next(
            (item for item in identities if str(item.get("role") or "") == "manager"),
            None,
        )
        default_worker = next(
            (
                item
                for item in identities
                if str(item.get("role") or "") == "worker" and bool(item.get("is_default"))
            ),
            None,
        )
        company = company_store.ensure_default_company(
            computer_id=computer_id,
            computer_name=device_name,
            manager_identity=manager,
            default_worker_identity=default_worker,
        )
        active_company_id = str(company.get("company_id") or "")
    else:
        company = company_store.get_company(active_company_id)
        if not any(
            str(item.get("computer_id") or "") == computer_id
            and str(item.get("status") or "active") == "active"
            for item in list(company.get("memberships") or [])
        ):
            return None

    home = runtime_home()
    connection = load_fleet_connection(home) if home else {}
    membership_bundle = (
        connection.get("companyMembership")
        if isinstance(connection.get("companyMembership"), Mapping)
        else None
    )
    if membership_bundle:
        company_store.import_member_company(
            bundle=membership_bundle,
            local_computer_id=computer_id,
            local_computer_name=str(desktop.get("display_name") or device_name),
        )

    pairs_by_company: Dict[str, Dict[str, Any]] = {}
    for summary in company_store.list_companies(computer_id=computer_id):
        scoped_company_id = str(summary.get("company_id") or "").strip()
        if not scoped_company_id:
            continue
        scoped_company = company_store.get_company(scoped_company_id)
        scoped_membership = next(
            (
                item
                for item in list(scoped_company.get("memberships") or [])
                if str(item.get("computer_id") or "") == computer_id
                and str(item.get("status") or "active") == "active"
            ),
            None,
        )
        if not scoped_membership:
            continue
        scoped_pair = fleet_store.ensure_company_membership_identities(
            user_id=user_id,
            desktop_id=computer_id,
            company_id=scoped_company_id,
            company_name=str(
                dict(scoped_company.get("manifest") or {}).get("display_name")
                or device_name
            ),
            membership_role=str(
                scoped_membership.get("membership_role") or "worker_node"
            ),
            adopt_unscoped=bool(
                str(
                    (scoped_company.get("migration") or {}).get("state") or ""
                )
                == "legacy_compatibility"
            ),
        )
        company_store.reconcile_membership_identities(
            company_id=scoped_company_id,
            computer_id=computer_id,
            manager_identity=scoped_pair["manager_identity"],
            default_worker_identity=scoped_pair["default_worker_identity"],
        )
        if (
            str((scoped_company.get("migration") or {}).get("state") or "")
            == "legacy_compatibility"
            and str(scoped_membership.get("membership_role") or "")
            == "root_controller"
        ):
            home = runtime_home()
            manager_identity_id = str(
                scoped_pair["manager_identity"].get("identity_id") or ""
            ).strip()
            if home is not None and manager_identity_id:
                try:
                    migrate_legacy_memory_to_company(
                        home,
                        company_id=scoped_company_id,
                        identity_id=manager_identity_id,
                    )
                except Exception:
                    # The Company remains in compatibility mode and can retry;
                    # memory migration must not make the whole runtime unavailable.
                    logger.warning(
                        "Legacy memory could not be migrated to Company %s.",
                        scoped_company_id,
                        exc_info=True,
                    )
        pairs_by_company[scoped_company_id] = scoped_pair

    company = company_store.get_company(active_company_id)
    membership = next(
        (
            item
            for item in list(company.get("memberships") or [])
            if str(item.get("computer_id") or "") == computer_id
        ),
        None,
    )
    if not membership:
        return None
    pair = pairs_by_company.get(active_company_id)
    if not pair:
        return None
    return {
        "user_id": user_id,
        "computer_id": computer_id,
        "computer_name": str(desktop.get("display_name") or device_name),
        "company_id": active_company_id,
        "company": company,
        "membership": next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "") == computer_id
            ),
            membership,
        ),
        "manager_identity": pair["manager_identity"],
        "default_worker_identity": pair["default_worker_identity"],
    }


def selected_company_scope(
    *,
    auth: Mapping[str, Any],
    company_store: Any,
    fleet_store: Any,
) -> Dict[str, Any]:
    """Return the active Company boundary for a local or paired desktop."""

    explicit_company_id = requested_company_id()
    is_remote = str(auth.get("auth_kind") or "") == "remote_session"
    if is_remote:
        computer_id = str(auth.get("desktop_id") or "").strip()
        company_id = explicit_company_id or (
            company_store.active_company_id(computer_id=computer_id) if computer_id else None
        )
        if not company_id:
            return {}
        company = company_store.get_company(company_id)
        if not any(
            str(item.get("computer_id") or "") == computer_id
            and str(item.get("status") or "active") == "active"
            for item in list(company.get("memberships") or [])
        ):
            return {}
        runtime: Dict[str, Any] = {
            "user_id": int(auth.get("user_id") or 0),
            "computer_id": computer_id,
            "company_id": str(company_id),
            "company": company,
        }
    else:
        runtime = resolve_local_company_runtime(
            auth=auth,
            company_store=company_store,
            fleet_store=fleet_store,
            company_id=explicit_company_id,
        ) or {}
        if not runtime:
            return {}
        company = runtime["company"]

    include_legacy = (
        str((company.get("migration") or {}).get("state") or "")
        == "legacy_compatibility"
    )
    runtime["include_legacy"] = include_legacy
    runtime["company_computer_ids"] = (
        None
        if include_legacy
        else [
            str(item.get("computer_id") or "")
            for item in list(company.get("memberships") or [])
            if str(item.get("status") or "active") == "active"
            and str(item.get("computer_id") or "").strip()
        ]
    )
    return runtime


def record_company_id(record: Any) -> str:
    if isinstance(record, Mapping):
        direct = record.get("company_id")
        metadata = record.get("metadata")
    else:
        direct = getattr(record, "company_id", None)
        metadata = getattr(record, "metadata", None)
    if direct:
        return str(direct).strip()
    if isinstance(metadata, Mapping):
        return str(metadata.get("company_id") or "").strip()
    return ""


def company_record_matches(
    record: Any,
    *,
    company_id: Optional[str],
    include_legacy: bool,
) -> bool:
    clean_company_id = str(company_id or "").strip()
    if not clean_company_id:
        return True
    value = record_company_id(record)
    return value == clean_company_id or (include_legacy and not value)


def require_company_record(
    record: Any,
    *,
    company_id: Optional[str],
    include_legacy: bool,
    message: str = "Record not found in the selected company",
) -> Any:
    if not company_record_matches(
        record,
        company_id=company_id,
        include_legacy=include_legacy,
    ):
        raise LookupError(message)
    return record
