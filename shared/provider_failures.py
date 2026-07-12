from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from shared.provider_errors import ProviderErrorInfo


FAILED_TURN_REPLAY_LIMIT = 12


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    user_message: str
    provider_id: str
    model_id: str
    retryable: bool
    provider_status_code: Optional[int] = None
    run_id: Optional[str] = None
    recovery_actions: list[str] = field(default_factory=list)
    reset_at: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    blocked_until: Optional[str] = None
    scope: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "code": self.code,
            "user_message": self.user_message,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "retryable": self.retryable,
            "recovery_actions": list(self.recovery_actions),
        }
        if self.run_id:
            payload["run_id"] = self.run_id
        if self.provider_status_code is not None:
            payload["provider_status_code"] = self.provider_status_code
        for key in ("reset_at", "retry_after_seconds", "blocked_until", "scope"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


def provider_failure_from_info(
    info: ProviderErrorInfo,
    *,
    provider_id: str,
    model_id: str,
    run_id: Optional[str] = None,
) -> ProviderFailure:
    safe_messages = {
        "usage_limit_reached": "This provider account has reached its configured usage limit.",
        "authentication_failed": "The provider rejected the configured credentials or permissions.",
        "quota_exceeded": "This provider account has no available quota for the request.",
        "billing_required": "This provider account needs billing attention before it can run requests.",
        "rate_limited": "The provider is rate-limiting requests right now.",
        "safety_rejected": "The provider rejected this request for safety reasons.",
        "invalid_input": "The provider rejected the submitted input.",
        "provider_unavailable": "The provider is temporarily unavailable.",
        "connectivity_failed": "The app could not connect to the provider.",
        "provider_failed": "The provider could not complete this request.",
    }
    actions = ["switch_provider"]
    if info.retryable:
        actions.insert(0, "retry")
    elif info.reset_at or info.retry_after_seconds is not None:
        actions.insert(0, "retry_after_reset")
    actions.append("open_settings")
    return ProviderFailure(
        code=info.code,
        user_message=safe_messages.get(info.code, "The provider could not complete this request."),
        provider_id=str(provider_id or "unknown"),
        model_id=str(model_id or "unknown"),
        retryable=bool(info.retryable),
        provider_status_code=info.status_code,
        run_id=run_id,
        recovery_actions=actions,
        reset_at=info.reset_at,
        retry_after_seconds=info.retry_after_seconds,
    )


def _failed_turns(session: Any) -> list[Dict[str, Any]]:
    records = getattr(session, "failed_turns", None)
    if not isinstance(records, list):
        records = []
        setattr(session, "failed_turns", records)
    return records


def record_failed_turn(
    session: Any,
    *,
    failure: Dict[str, Any],
    user_message: str,
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    run_id = str(failure.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("A failed turn requires a run id")
    records = _failed_turns(session)
    previous = next(
        (item for item in records if str(item.get("run_id") or "") == run_id),
        None,
    )
    records[:] = [item for item in records if str(item.get("run_id") or "") != run_id]
    record = {
        "run_id": run_id,
        "user_message": str(user_message or ""),
        "failure": dict(failure),
        "event_meta": dict(event_meta or {}),
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "retry_consumed": bool(previous and previous.get("retry_consumed")),
    }
    if previous and previous.get("retried_at"):
        record["retried_at"] = previous.get("retried_at")
    records.append(record)
    if len(records) > FAILED_TURN_REPLAY_LIMIT:
        del records[:-FAILED_TURN_REPLAY_LIMIT]
    return record


def get_failed_turn(session: Any, run_id: str) -> Optional[Dict[str, Any]]:
    target = str(run_id or "").strip()
    for record in reversed(_failed_turns(session)):
        if str(record.get("run_id") or "").strip() == target:
            return record
    return None


def consume_failed_turn_retry(session: Any, run_id: str) -> Dict[str, Any]:
    record = get_failed_turn(session, run_id)
    if not record:
        raise ValueError("The failed turn is no longer available to retry.")
    if bool(record.get("retry_consumed")):
        raise ValueError("This failed turn has already been retried.")
    record["retry_consumed"] = True
    record["retried_at"] = datetime.now(timezone.utc).isoformat()
    return record


def prune_failed_turns(session: Any, live_run_ids: Iterable[str]) -> None:
    allowed = {str(value or "").strip() for value in live_run_ids}
    records = _failed_turns(session)
    records[:] = [record for record in records if str(record.get("run_id") or "").strip() in allowed]
