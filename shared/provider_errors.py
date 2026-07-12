from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

from shared.security_policy import redact_text


PROVIDER_SAFETY_REJECTION = "provider_safety_rejection"
PROVIDER_INPUT_REJECTED = "provider_input_rejected"
PROVIDER_TRANSIENT_ERROR = "provider_transient_error"
PROVIDER_AUTH_OR_QUOTA_ERROR = "provider_auth_or_quota_error"
PROVIDER_ERROR = "provider_error"

PROVIDER_FAILURE_USAGE_LIMIT = "usage_limit_reached"
PROVIDER_FAILURE_AUTHENTICATION = "authentication_failed"
PROVIDER_FAILURE_QUOTA = "quota_exceeded"
PROVIDER_FAILURE_BILLING = "billing_required"
PROVIDER_FAILURE_RATE_LIMIT = "rate_limited"
PROVIDER_FAILURE_SAFETY = "safety_rejected"
PROVIDER_FAILURE_INVALID_INPUT = "invalid_input"
PROVIDER_FAILURE_TRANSIENT = "provider_unavailable"
PROVIDER_FAILURE_CONNECTIVITY = "connectivity_failed"
PROVIDER_FAILURE_UNKNOWN = "provider_failed"


@dataclass(frozen=True)
class ProviderErrorInfo:
    error_type: str
    message: str
    status_code: Optional[int] = None
    retryable: bool = False
    safe_alternate_allowed: bool = False
    code: str = PROVIDER_FAILURE_UNKNOWN
    reset_at: Optional[str] = None
    retry_after_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "error_type": self.error_type,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "safe_alternate_allowed": self.safe_alternate_allowed,
            "code": self.code,
            "reset_at": self.reset_at,
            "retry_after_seconds": self.retry_after_seconds,
        }


def _duration_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return max(0, int(float(text)))
    except ValueError:
        pass
    match = re.fullmatch(r"([0-9.]+)\s*(ms|s|m|h)", text)
    if match:
        multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[match.group(2)]
        return max(0, int(float(match.group(1)) * multiplier))
    try:
        return max(0, int(parsedate_to_datetime(text).timestamp() - time.time()))
    except (TypeError, ValueError, OverflowError):
        return None


def _provider_reset_metadata(exc: BaseException) -> tuple[Optional[str], Optional[int]]:
    text = str(exc or "")
    headers: Dict[str, Any] = {}
    for source in (getattr(exc, "headers", None), getattr(getattr(exc, "response", None), "headers", None)):
        try:
            headers.update({str(key).lower(): value for key, value in dict(source or {}).items()})
        except Exception:
            continue

    retry_after: Optional[int] = None
    for key in ("retry-after", "x-ratelimit-reset-seconds", "x-ratelimit-reset-requests"):
        value = headers.get(key)
        retry_after = _duration_seconds(value)
        if retry_after is not None:
            break
    if retry_after is None:
        match = re.search(r'["\'](?:resets_in_seconds|reset_in_seconds|retry_after_seconds)["\']\s*:\s*([0-9.]+)', text, re.I)
        if match:
            try:
                retry_after = max(0, int(float(match.group(1))))
            except (TypeError, ValueError):
                retry_after = None

    reset_timestamp: Optional[float] = None
    match = re.search(r'["\'](?:resets_at|reset_at)["\']\s*:\s*["\']?([0-9.]+)', text, re.I)
    if match:
        try:
            reset_timestamp = float(match.group(1))
        except (TypeError, ValueError):
            reset_timestamp = None
    if reset_timestamp is None and retry_after is not None:
        reset_timestamp = time.time() + retry_after
    reset_at = (
        datetime.fromtimestamp(reset_timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
        if reset_timestamp and reset_timestamp > 0
        else None
    )
    return reset_at, retry_after


def _status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        try:
            if value is not None and str(value).isdigit():
                return int(str(value))
        except Exception:
            pass
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return int(value) if isinstance(value, int) else None


def _error_code_text(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    for attr in ("code", "type", "param"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    body = getattr(exc, "body", None)
    if body:
        parts.append(str(body))
    return " ".join(parts).lower()


def normalize_provider_error(exc: BaseException, *, payload_kind: str = "text") -> ProviderErrorInfo:
    status = _status_code(exc)
    text = _error_code_text(exc)
    reset_at, retry_after_seconds = _provider_reset_metadata(exc)
    clean_message = redact_text(str(exc))
    if len(clean_message) > 600:
        clean_message = clean_message[:597] + "..."

    safety_markers = (
        "content_filter",
        "content filter",
        "safety",
        "safe prompt",
        "blocked by",
        "policy violation",
        "violates",
        "unsafe",
        "harmful",
        "sexual",
        "explicit",
        "disallowed",
        "responsible ai",
        "sensitive content",
    )
    if any(marker in text for marker in safety_markers):
        return ProviderErrorInfo(
            PROVIDER_SAFETY_REJECTION,
            (
                "The provider rejected this input for safety reasons. "
                "The raw rejected content was not retained."
            ),
            status,
            retryable=False,
            safe_alternate_allowed=payload_kind in {"image", "screenshot", "vision"},
            code=PROVIDER_FAILURE_SAFETY,
        )

    input_markers = (
        "invalid image",
        "unsupported image",
        "image too large",
        "invalid_request",
        "bad request",
        "unsupported content",
        "input validation",
        "context length",
        "maximum context",
        "too many tokens",
        "payload too large",
    )
    if status == 400 or any(marker in text for marker in input_markers):
        return ProviderErrorInfo(
            PROVIDER_INPUT_REJECTED,
            f"The provider rejected the submitted {payload_kind} input. {clean_message}",
            status,
            retryable=False,
            safe_alternate_allowed=payload_kind in {"image", "screenshot", "vision"},
            code=PROVIDER_FAILURE_INVALID_INPUT,
        )

    usage_limit_markers = (
        "usage_limit_reached",
        "usage limit reached",
        "monthly usage limit",
        "spending limit reached",
    )
    if any(marker in text for marker in usage_limit_markers):
        return ProviderErrorInfo(
            PROVIDER_AUTH_OR_QUOTA_ERROR,
            "This provider account has reached its configured usage limit.",
            status,
            retryable=False,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_USAGE_LIMIT,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    billing_markers = (
        "billing",
        "payment required",
        "credit balance",
        "insufficient credits",
    )
    if status == 402 or any(marker in text for marker in billing_markers):
        return ProviderErrorInfo(
            PROVIDER_AUTH_OR_QUOTA_ERROR,
            "This provider account needs billing attention before it can run requests.",
            status,
            retryable=False,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_BILLING,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    quota_markers = (
        "quota",
        "insufficient_quota",
        "quota_exceeded",
    )
    if any(marker in text for marker in quota_markers):
        return ProviderErrorInfo(
            PROVIDER_AUTH_OR_QUOTA_ERROR,
            "This provider account has no available quota for the request.",
            status,
            retryable=False,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_QUOTA,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    rate_limit_markers = (
        "rate limit",
        "rate_limit",
        "too many requests",
    )
    if status == 429 or any(marker in text for marker in rate_limit_markers):
        return ProviderErrorInfo(
            PROVIDER_AUTH_OR_QUOTA_ERROR,
            f"Provider authentication, quota, or permission error. {clean_message}",
            status,
            retryable=True,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_RATE_LIMIT,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    auth_markers = (
        "authentication",
        "api key",
        "unauthorized",
        "forbidden",
        "permission",
    )
    if status in {401, 403} or any(marker in text for marker in auth_markers):
        return ProviderErrorInfo(
            PROVIDER_AUTH_OR_QUOTA_ERROR,
            f"Provider authentication, quota, or permission error. {clean_message}",
            status,
            retryable=status == 429,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_AUTHENTICATION,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    connectivity_markers = (
        "connection",
        "dns",
        "network is unreachable",
        "connection reset",
        "connection refused",
        "name resolution",
    )
    if any(marker in text for marker in connectivity_markers):
        return ProviderErrorInfo(
            PROVIDER_TRANSIENT_ERROR,
            "The app could not connect to the provider.",
            status,
            retryable=True,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_CONNECTIVITY,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    transient_markers = (
        "timeout",
        "timed out",
        "temporarily unavailable",
        "server error",
        "overloaded",
        "service unavailable",
    )
    if status in {408, 409, 500, 502, 503, 504} or any(marker in text for marker in transient_markers):
        return ProviderErrorInfo(
            PROVIDER_TRANSIENT_ERROR,
            f"Temporary provider error. {clean_message}",
            status,
            retryable=True,
            safe_alternate_allowed=False,
            code=PROVIDER_FAILURE_TRANSIENT,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
        )

    return ProviderErrorInfo(
        PROVIDER_ERROR,
        f"Provider error. {clean_message}",
        status,
        retryable=False,
        safe_alternate_allowed=False,
        code=PROVIDER_FAILURE_UNKNOWN,
    )


def provider_blocker_message(info: ProviderErrorInfo) -> str:
    if info.error_type == PROVIDER_SAFETY_REJECTION:
        return (
            "The AI provider rejected part of this request for safety reasons. "
            "I stopped this turn rather than retrying the same blocked content."
        )
    if info.error_type == PROVIDER_INPUT_REJECTED:
        return (
            "The AI provider rejected the submitted input. "
            "I stopped this turn because no safe alternate input path was available."
        )
    return info.message


def is_provider_rejection(value: Any) -> bool:
    if isinstance(value, ProviderErrorInfo):
        return value.error_type in {PROVIDER_SAFETY_REJECTION, PROVIDER_INPUT_REJECTED}
    if isinstance(value, dict):
        return str(value.get("error_type") or "") in {PROVIDER_SAFETY_REJECTION, PROVIDER_INPUT_REJECTED}
    text = str(value or "")
    return bool(re.search(r"provider_(?:safety_rejection|input_rejected)", text))
