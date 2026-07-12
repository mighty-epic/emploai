from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import shared_state_root


PROVIDER_AVAILABILITY_FILENAME = "provider-availability.json"
MAX_SHARED_BLOCK_SECONDS = 7 * 24 * 60 * 60
DEFAULT_USAGE_RECHECK_SECONDS = 15 * 60

_PERSISTENT_CODES = {
    "usage_limit_reached",
    "authentication_failed",
    "quota_exceeded",
    "billing_required",
    "rate_limited",
    "provider_unavailable",
    "connectivity_failed",
    "provider_failed",
}
_PROVIDER_SCOPE_CODES = {
    "usage_limit_reached",
    "authentication_failed",
    "quota_exceeded",
    "billing_required",
}
_SAFE_MESSAGES = {
    "usage_limit_reached": "This provider account has reached its configured usage limit.",
    "authentication_failed": "The provider rejected the configured credentials or permissions.",
    "quota_exceeded": "This provider account has no available quota for the request.",
    "billing_required": "This provider account needs billing attention before it can run requests.",
    "rate_limited": "The provider is rate-limiting requests right now.",
    "provider_unavailable": "The provider is temporarily unavailable.",
    "connectivity_failed": "The app could not connect to the provider.",
    "provider_failed": "The provider could not complete this request.",
}
_LOCK = threading.RLock()


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        if number > 0:
            return number
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return None
    return None


def provider_availability_path() -> Path:
    configured = os.getenv("EMPLOAI_PROVIDER_AVAILABILITY_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (shared_state_root() / PROVIDER_AVAILABILITY_FILENAME).resolve()


def _read_state() -> dict[str, Any]:
    path = provider_availability_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "records": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return {"version": 1, "records": []}
    return {"version": 1, "records": [dict(item) for item in payload["records"] if isinstance(item, dict)]}


def _write_state(state: Mapping[str, Any]) -> None:
    atomic_write_json(
        provider_availability_path(),
        {"version": 1, "records": list(state.get("records") or [])},
        sort_keys=True,
    )


def _provider_id(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized in {"chatgpt", "openai_codex", "codex"}:
        return "openai-codex"
    return normalized or "unknown"


def provider_identity_fingerprint(provider_id: str) -> Optional[str]:
    provider = _provider_id(provider_id)
    if provider != "openai-codex":
        return None
    try:
        from shared.openai_codex_auth import codex_auth_status

        account_id = str(codex_auth_status(include_path=False).get("accountId") or "").strip()
    except Exception:
        account_id = ""
    if not account_id:
        return None
    return hashlib.sha256(f"{provider}\0{account_id}".encode("utf-8")).hexdigest()


def _record_key(record: Mapping[str, Any]) -> str:
    provider = _provider_id(record.get("provider_id"))
    fingerprint = str(record.get("identity_fingerprint") or "local").strip().lower() or "local"
    scope = str(record.get("scope") or "model").strip().lower()
    model = "*" if scope == "provider" else str(record.get("model_id") or "unknown").strip().lower()
    return hashlib.sha256(f"{provider}|{fingerprint}|{scope}|{model}".encode("utf-8")).hexdigest()


def _default_backoff(code: str, consecutive_failures: int) -> float:
    attempt = max(1, int(consecutive_failures or 1))
    if code in _PROVIDER_SCOPE_CODES:
        return float(DEFAULT_USAGE_RECHECK_SECONDS)
    if code == "rate_limited":
        return float(min(15 * 60, 30 * (2 ** min(attempt - 1, 5))))
    if code == "provider_unavailable":
        return float(min(5 * 60, 10 * (2 ** min(attempt - 1, 5))))
    if code == "connectivity_failed":
        return float(min(2 * 60, 5 * (2 ** min(attempt - 1, 5))))
    return float(min(60, 5 * attempt))


def _sanitize_record(record: Mapping[str, Any], *, source: str, now: float) -> Optional[dict[str, Any]]:
    code = str(record.get("code") or "provider_failed").strip().lower()
    if code not in _PERSISTENT_CODES:
        return None
    provider = _provider_id(record.get("provider_id"))
    model = str(record.get("model_id") or "unknown").strip()[:160] or "unknown"
    scope = "provider" if code in _PROVIDER_SCOPE_CODES else str(record.get("scope") or "model").strip().lower()
    if scope not in {"provider", "model"}:
        scope = "model"
    fingerprint = str(record.get("identity_fingerprint") or "").strip().lower()
    if fingerprint and (len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint)):
        return None
    observed_at = _timestamp(record.get("observed_at")) or now
    reset_at = _timestamp(record.get("reset_at"))
    blocked_until = _timestamp(record.get("blocked_until"))
    retry_after = record.get("retry_after_seconds")
    try:
        retry_after_seconds = max(0.0, float(retry_after)) if retry_after is not None else None
    except (TypeError, ValueError):
        retry_after_seconds = None
    consecutive = max(1, min(20, int(record.get("consecutive_failures") or 1)))
    if blocked_until is None:
        if reset_at and reset_at > now:
            blocked_until = reset_at + 2.0
        elif retry_after_seconds is not None:
            blocked_until = now + retry_after_seconds
        else:
            blocked_until = now + _default_backoff(code, consecutive)
    blocked_until = min(max(now, blocked_until), now + MAX_SHARED_BLOCK_SECONDS)
    return {
        "provider_id": provider,
        "model_id": model,
        "scope": scope,
        "code": code,
        "user_message": _SAFE_MESSAGES.get(code, _SAFE_MESSAGES["provider_failed"]),
        "retryable": bool(record.get("retryable", code in {"rate_limited", "provider_unavailable", "connectivity_failed", "provider_failed"})),
        "provider_status_code": int(record["provider_status_code"]) if str(record.get("provider_status_code") or "").isdigit() else None,
        "identity_fingerprint": fingerprint or None,
        "observed_at": _utc_iso(observed_at),
        "reset_at": _utc_iso(reset_at) if reset_at else None,
        "retry_after_seconds": max(0, int(blocked_until - now)),
        "blocked_until": _utc_iso(blocked_until),
        "consecutive_failures": consecutive,
        "source": str(source or record.get("source") or "local").strip()[:40] or "local",
    }


def record_provider_failure(failure: Mapping[str, Any], *, source: str = "local", now: Optional[float] = None) -> Optional[dict[str, Any]]:
    current_time = float(now if now is not None else time.time())
    provider = _provider_id(failure.get("provider_id"))
    enriched = dict(failure)
    enriched["provider_id"] = provider
    enriched.setdefault("identity_fingerprint", provider_identity_fingerprint(provider))
    with _LOCK:
        state = _read_state()
        provisional = _sanitize_record(enriched, source=source, now=current_time)
        if provisional is None:
            return None
        key = _record_key(provisional)
        previous = next((item for item in state["records"] if _record_key(item) == key), None)
        if previous:
            previous_seen = _timestamp(previous.get("observed_at")) or 0
            if current_time - previous_seen <= 60 * 60:
                enriched["consecutive_failures"] = int(previous.get("consecutive_failures") or 1) + 1
                provisional = _sanitize_record(enriched, source=source, now=current_time) or provisional
        provisional["record_id"] = key
        state["records"] = [item for item in state["records"] if _record_key(item) != key]
        state["records"].append(provisional)
        _write_state(state)
        return dict(provisional)


def active_provider_block(provider_id: str, model_id: str, *, now: Optional[float] = None) -> Optional[dict[str, Any]]:
    current_time = float(now if now is not None else time.time())
    provider = _provider_id(provider_id)
    model = str(model_id or "unknown").strip().lower()
    local_fingerprint = provider_identity_fingerprint(provider)
    with _LOCK:
        state = _read_state()
        kept: list[dict[str, Any]] = []
        matches: list[dict[str, Any]] = []
        changed = False
        for item in state["records"]:
            blocked_until = _timestamp(item.get("blocked_until")) or 0
            if blocked_until <= current_time:
                changed = True
                continue
            kept.append(item)
            if _provider_id(item.get("provider_id")) != provider:
                continue
            fingerprint = str(item.get("identity_fingerprint") or "").strip().lower()
            if fingerprint and fingerprint != str(local_fingerprint or "").lower():
                continue
            scope = str(item.get("scope") or "model").lower()
            if scope == "provider" or str(item.get("model_id") or "").strip().lower() == model:
                matches.append(item)
        if changed:
            state["records"] = kept
            _write_state(state)
        if not matches:
            return None
        matches.sort(key=lambda item: _timestamp(item.get("blocked_until")) or 0, reverse=True)
        return dict(matches[0])


def mark_provider_success(provider_id: str, model_id: str) -> bool:
    provider = _provider_id(provider_id)
    model = str(model_id or "unknown").strip().lower()
    local_fingerprint = provider_identity_fingerprint(provider)
    with _LOCK:
        state = _read_state()
        kept: list[dict[str, Any]] = []
        changed = False
        for item in state["records"]:
            fingerprint = str(item.get("identity_fingerprint") or "").strip().lower()
            applies_to_identity = not fingerprint or fingerprint == str(local_fingerprint or "").lower()
            applies_to_model = str(item.get("scope") or "model") == "provider" or str(item.get("model_id") or "").strip().lower() == model
            if _provider_id(item.get("provider_id")) == provider and applies_to_identity and applies_to_model:
                changed = True
                continue
            kept.append(item)
        if changed:
            state["records"] = kept
            _write_state(state)
        return changed


def clear_provider_availability(provider_id: str) -> bool:
    provider = _provider_id(provider_id)
    local_fingerprint = provider_identity_fingerprint(provider)
    with _LOCK:
        state = _read_state()
        kept: list[dict[str, Any]] = []
        changed = False
        for item in state["records"]:
            fingerprint = str(item.get("identity_fingerprint") or "").strip().lower()
            applies_to_identity = not fingerprint or fingerprint == str(local_fingerprint or "").lower()
            if _provider_id(item.get("provider_id")) == provider and applies_to_identity:
                changed = True
                continue
            kept.append(item)
        if changed:
            state["records"] = kept
            _write_state(state)
        return changed


def provider_availability_snapshot(*, public_only: bool = False, now: Optional[float] = None) -> list[dict[str, Any]]:
    current_time = float(now if now is not None else time.time())
    with _LOCK:
        state = _read_state()
        active = [dict(item) for item in state["records"] if (_timestamp(item.get("blocked_until")) or 0) > current_time]
        if len(active) != len(state["records"]):
            state["records"] = active
            _write_state(state)
    if public_only:
        active = [item for item in active if str(item.get("identity_fingerprint") or "").strip()]
    active.sort(key=lambda item: (_provider_id(item.get("provider_id")), str(item.get("model_id") or "")))
    return active


def applicable_provider_availability_snapshot(*, now: Optional[float] = None) -> list[dict[str, Any]]:
    records = provider_availability_snapshot(now=now)
    applicable: list[dict[str, Any]] = []
    for item in records:
        fingerprint = str(item.get("identity_fingerprint") or "").strip().lower()
        local_fingerprint = provider_identity_fingerprint(str(item.get("provider_id") or ""))
        if fingerprint and fingerprint != str(local_fingerprint or "").lower():
            continue
        applicable.append(item)
    return applicable


def merge_provider_availability(records: list[Mapping[str, Any]], *, source: str = "yggdrasil", now: Optional[float] = None) -> bool:
    current_time = float(now if now is not None else time.time())
    changed = False
    with _LOCK:
        state = _read_state()
        by_key = {_record_key(item): dict(item) for item in state["records"]}
        for raw in list(records or [])[:100]:
            if not isinstance(raw, Mapping) or not str(raw.get("identity_fingerprint") or "").strip():
                continue
            item = _sanitize_record(raw, source=source, now=current_time)
            if item is None or (_timestamp(item.get("blocked_until")) or 0) <= current_time:
                continue
            key = _record_key(item)
            item["record_id"] = key
            previous = by_key.get(key)
            if previous and (_timestamp(previous.get("blocked_until")) or 0) >= (_timestamp(item.get("blocked_until")) or 0):
                continue
            by_key[key] = item
            changed = True
        if changed:
            state["records"] = list(by_key.values())
            _write_state(state)
    return changed


def provider_failure_from_block(block: Mapping[str, Any], *, run_id: Optional[str] = None) -> dict[str, Any]:
    payload = {
        key: block.get(key)
        for key in (
            "code",
            "user_message",
            "provider_id",
            "model_id",
            "retryable",
            "provider_status_code",
            "scope",
            "reset_at",
            "retry_after_seconds",
            "blocked_until",
        )
        if block.get(key) is not None
    }
    payload["recovery_actions"] = ["retry_after_reset", "switch_provider", "open_settings"]
    if run_id:
        payload["run_id"] = str(run_id)
    payload["preflight_blocked"] = True
    return payload


def provider_availability_sync_targets(
    *,
    origin_desktop_id: str,
    connected_desktop_ids: list[str],
    incoming_records: list[Mapping[str, Any]],
    aggregate_records: list[Mapping[str, Any]],
    aggregate_changed: bool,
) -> list[str]:
    origin = str(origin_desktop_id or "").strip()
    targets: set[str] = set()
    if aggregate_changed:
        targets.update(str(item or "").strip() for item in connected_desktop_ids)
        targets.discard(origin)
    incoming_signature = json.dumps(list(incoming_records or []), sort_keys=True, ensure_ascii=True)
    aggregate_signature = json.dumps(list(aggregate_records or []), sort_keys=True, ensure_ascii=True)
    if origin and incoming_signature != aggregate_signature:
        targets.add(origin)
    return sorted(item for item in targets if item)
