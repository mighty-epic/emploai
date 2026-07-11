from __future__ import annotations

import re
from dataclasses import dataclass
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "error_type": self.error_type,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "safe_alternate_allowed": self.safe_alternate_allowed,
            "code": self.code,
        }


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
