from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared.provider_errors import normalize_provider_error
from shared.provider_failures import (
    consume_failed_turn_retry,
    provider_failure_from_info,
    record_failed_turn,
)


class ProviderException(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@pytest.mark.parametrize(
    ("error", "expected_code", "retryable"),
    [
        (ProviderException("usage_limit_reached"), "usage_limit_reached", False),
        (ProviderException("invalid API key sk-secret", status_code=401), "authentication_failed", False),
        (ProviderException("insufficient_quota"), "quota_exceeded", False),
        (ProviderException("payment required", status_code=402), "billing_required", False),
        (ProviderException("too many requests", status_code=429), "rate_limited", True),
        (ProviderException("content_filter blocked"), "safety_rejected", False),
        (ProviderException("maximum context exceeded", status_code=400), "invalid_input", False),
        (ProviderException("service unavailable", status_code=503), "provider_unavailable", True),
        (ProviderException("DNS connection failed"), "connectivity_failed", True),
    ],
)
def test_provider_failures_are_structured_and_sanitized(error, expected_code, retryable):
    info = normalize_provider_error(error)
    failure = provider_failure_from_info(
        info,
        provider_id="provider-a",
        model_id="model-a",
        run_id="run-a",
    ).to_dict()

    assert failure["code"] == expected_code
    assert failure["retryable"] is retryable
    assert failure["run_id"] == "run-a"
    assert "sk-secret" not in failure["user_message"]
    assert "body" not in failure


def test_failed_turn_retry_is_preserved_and_consumed_exactly_once():
    session = SimpleNamespace(failed_turns=[])
    failure = {
        "run_id": "run-123",
        "code": "quota_exceeded",
        "user_message": "Quota is unavailable.",
    }
    record_failed_turn(session, failure=failure, user_message="Do the saved task")

    replay = consume_failed_turn_retry(session, "run-123")
    assert replay["user_message"] == "Do the saved task"
    assert replay["retry_consumed"] is True

    with pytest.raises(ValueError, match="already been retried"):
        consume_failed_turn_retry(session, "run-123")


def test_usage_limit_reset_metadata_is_extracted_without_exposing_raw_payload():
    error = ProviderException(
        'Provider error: {"error":{"type":"usage_limit_reached","resets_at":1893456000,"resets_in_seconds":120}}'
    )
    info = normalize_provider_error(error)
    failure = provider_failure_from_info(
        info,
        provider_id="openai-codex",
        model_id="gpt-5.5",
    ).to_dict()

    assert failure["code"] == "usage_limit_reached"
    assert failure["retry_after_seconds"] == 120
    assert failure["reset_at"] == "2030-01-01T00:00:00Z"
    assert "resets_in_seconds" not in failure["user_message"]
