from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from app_backend.company_runtime_context import require_company_record


@dataclass(frozen=True)
class AutomationExecutionSession:
    session: Any
    chat_target: str
    identity_id: Optional[str]
    created: bool = False


def _clean(value: object) -> str:
    return str(value or "").strip()


def _identity_for(
    identities: Sequence[Mapping[str, Any]],
    identity_id: Optional[str],
) -> Optional[Mapping[str, Any]]:
    clean_id = _clean(identity_id)
    if not clean_id:
        return None
    return next(
        (item for item in identities if _clean(item.get("identity_id")) == clean_id),
        None,
    )


def _validate_session_owner(
    session: Any,
    *,
    identity: Optional[Mapping[str, Any]],
    identity_id: Optional[str],
) -> Optional[str]:
    requested_id = _clean(identity_id)
    session_id = _clean(getattr(session, "fleet_identity_id", None))
    if not requested_id:
        return session_id or None
    if session_id and session_id != requested_id:
        raise ValueError("The selected chat belongs to a different entity")
    if not session_id and str((identity or {}).get("role") or "").strip().lower() not in {"", "manager"}:
        raise ValueError("The selected chat is not owned by the selected entity")
    return requested_id


def resolve_existing_automation_session(
    *,
    bridge: Any,
    identities: Sequence[Mapping[str, Any]],
    session_id: Optional[str],
    identity_id: Optional[str],
    company_id: Optional[str] = None,
    include_legacy: bool = False,
) -> AutomationExecutionSession:
    clean_session_id = _clean(session_id)
    if not clean_session_id:
        raise ValueError("Choose an existing chat")
    identity = _identity_for(identities, identity_id)
    if _clean(identity_id) and identity is None:
        raise ValueError("The selected entity is no longer available")
    try:
        session = bridge.get_session(clean_session_id)
    except KeyError as exc:
        raise ValueError("The selected chat is no longer available") from exc
    try:
        require_company_record(
            session,
            company_id=company_id,
            include_legacy=include_legacy,
            message="The selected chat belongs to a different company",
        )
    except LookupError as exc:
        raise ValueError(str(exc)) from exc
    owner_id = _validate_session_owner(session, identity=identity, identity_id=identity_id)
    return AutomationExecutionSession(
        session=session,
        chat_target="existing",
        identity_id=owner_id,
    )


def resolve_new_automation_session(
    *,
    bridge: Any,
    identities: Sequence[Mapping[str, Any]],
    active_identity_id: Optional[str],
    automation_name: str,
    identity_id: Optional[str],
    model: Optional[str],
    variant: Optional[str],
    permission_mode: Optional[str],
    reusable_session_id: Optional[str] = None,
    company_id: Optional[str] = None,
    include_legacy: bool = False,
) -> AutomationExecutionSession:
    clean_identity_id = _clean(identity_id) or _clean(active_identity_id)
    identity = _identity_for(identities, clean_identity_id)
    if identity is None:
        raise ValueError("Choose an entity for this automation")
    clean_model = _clean(model)
    if not clean_model:
        raise ValueError("Choose a model for the new automation chat")

    reusable_id = _clean(reusable_session_id)
    if reusable_id:
        try:
            session = bridge.get_session(reusable_id)
        except KeyError:
            session = None
        if session is not None:
            try:
                require_company_record(
                    session,
                    company_id=company_id,
                    include_legacy=include_legacy,
                    message="The reusable automation chat belongs to a different company",
                )
            except LookupError:
                session = None
        if session is not None:
            _validate_session_owner(session, identity=identity, identity_id=clean_identity_id)
            session = bridge.update_session_model_config(
                reusable_id,
                model=clean_model,
                variant=_clean(variant) or None,
            )
            return AutomationExecutionSession(
                session=session,
                chat_target="new",
                identity_id=clean_identity_id,
            )

    identity_role = _clean(identity.get("role")).lower() or None
    identity_metadata = {
        **dict(identity.get("metadata") or {}),
        "enabled_tool_packs": list(identity.get("enabled_tool_packs") or []),
        "tool_profile": identity.get("tool_profile"),
        "is_default": bool(identity.get("is_default")),
    }
    session = bridge.create_session(
        f"Automation · {_clean(automation_name)[:120] or 'Scheduled task'}",
        model=clean_model,
        variant=_clean(variant) or None,
        enabled_tool_packs=list(identity.get("enabled_tool_packs") or []),
        security_permission_mode=permission_mode,
        headless_eligible=True,
        fleet_identity_id=clean_identity_id,
        fleet_identity_role=identity_role,
        fleet_worker_id=_clean(identity.get("worker_id")) or None,
        fleet_identity_metadata=identity_metadata,
        company_id=_clean(company_id) or None,
        activate=False,
    )
    return AutomationExecutionSession(
        session=session,
        chat_target="new",
        identity_id=clean_identity_id,
        created=True,
    )
