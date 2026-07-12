from __future__ import annotations

import json
import time
from types import SimpleNamespace

from cli.agent_tools.loop import run_tool_loop
from shared import provider_availability
from shared.provider_availability import (
    active_provider_block,
    applicable_provider_availability_snapshot,
    mark_provider_success,
    merge_provider_availability,
    provider_availability_snapshot,
    provider_availability_sync_targets,
    record_provider_failure,
)


FINGERPRINT = "a" * 64


def _configure_store(monkeypatch, tmp_path, *, fingerprint: str | None = FINGERPRINT):
    monkeypatch.setenv("EMPLOAI_PROVIDER_AVAILABILITY_PATH", str(tmp_path / "provider-availability.json"))
    monkeypatch.setattr(
        provider_availability,
        "provider_identity_fingerprint",
        lambda provider_id: fingerprint if provider_id == "openai-codex" else None,
    )


def test_usage_limit_persists_reset_and_blocks_without_provider_traffic(monkeypatch, tmp_path):
    _configure_store(monkeypatch, tmp_path)
    now = time.time()
    record = record_provider_failure(
        {
            "provider_id": "openai-codex",
            "model_id": "gpt-5.5",
            "code": "usage_limit_reached",
            "user_message": "raw payload must not survive",
            "retryable": False,
            "reset_at": "2030-01-01T00:00:00Z",
        },
        now=now,
    )

    assert record is not None
    assert record["scope"] == "provider"
    assert record["user_message"] == "This provider account has reached its configured usage limit."
    assert record["identity_fingerprint"] == FINGERPRINT
    assert active_provider_block("openai-codex", "gpt-5.4", now=now + 1)["code"] == "usage_limit_reached"

    class ProviderMustNotRun:
        @property
        def responses(self):
            raise AssertionError("blocked provider received traffic")

    result = run_tool_loop(
        provider="openai-codex",
        model_id="gpt-5.5",
        client=ProviderMustNotRun(),
        messages=[{"role": "user", "content": "do work"}],
        tool_executor=SimpleNamespace(check_interruption=None),
        callbacks={},
        api_type="responses",
    )

    assert result.failure["code"] == "usage_limit_reached"
    assert result.failure["preflight_blocked"] is True
    assert result.failure["blocked_until"]


def test_expired_block_clears_and_success_removes_matching_scope(monkeypatch, tmp_path):
    _configure_store(monkeypatch, tmp_path)
    record_provider_failure(
        {
            "provider_id": "openai-codex",
            "model_id": "gpt-5.5",
            "code": "rate_limited",
            "retryable": True,
            "retry_after_seconds": 30,
        },
        now=1_000,
    )
    assert active_provider_block("openai-codex", "gpt-5.5", now=1_010)
    assert active_provider_block("openai-codex", "gpt-5.5", now=1_031) is None

    record_provider_failure(
        {
            "provider_id": "openai-codex",
            "model_id": "gpt-5.5",
            "code": "usage_limit_reached",
            "retryable": False,
        },
        now=2_000,
    )
    assert mark_provider_success("openai-codex", "gpt-5.5") is True
    assert applicable_provider_availability_snapshot(now=2_001) == []


def test_repeated_rate_limits_use_bounded_exponential_backoff(monkeypatch, tmp_path):
    _configure_store(monkeypatch, tmp_path, fingerprint=None)
    first = record_provider_failure(
        {"provider_id": "openai", "model_id": "gpt-5.5", "code": "rate_limited", "retryable": True},
        now=10_000,
    )
    second = record_provider_failure(
        {"provider_id": "openai", "model_id": "gpt-5.5", "code": "rate_limited", "retryable": True},
        now=10_010,
    )
    assert first["retry_after_seconds"] == 30
    assert second["retry_after_seconds"] == 60
    assert second["consecutive_failures"] == 2


def test_yggdrasil_merge_requires_fingerprint_and_is_identity_scoped(monkeypatch, tmp_path):
    _configure_store(monkeypatch, tmp_path)
    assert merge_provider_availability(
        [{"provider_id": "openai-codex", "code": "usage_limit_reached", "blocked_until": "2030-01-01T00:00:00Z"}],
        now=1_700_000_000,
    ) is False

    foreign = "b" * 64
    assert merge_provider_availability(
        [{
            "provider_id": "openai-codex",
            "model_id": "gpt-5.5",
            "code": "usage_limit_reached",
            "identity_fingerprint": foreign,
            "blocked_until": "2030-01-01T00:00:00Z",
        }],
        now=1_700_000_000,
    ) is True
    assert active_provider_block("openai-codex", "gpt-5.5", now=1_700_000_001) is None
    assert len(provider_availability_snapshot(public_only=True, now=1_700_000_001)) == 1
    assert applicable_provider_availability_snapshot(now=1_700_000_001) == []

    persisted = json.loads(provider_availability.provider_availability_path().read_text(encoding="utf-8"))
    serialized = json.dumps(persisted)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized


def test_yggdrasil_sync_targets_origin_only_when_it_needs_aggregate_and_peers_on_change():
    record = {"provider_id": "openai-codex", "identity_fingerprint": FINGERPRINT, "code": "usage_limit_reached"}
    other = {**record, "blocked_until": "2030-01-01T00:00:00Z"}

    assert provider_availability_sync_targets(
        origin_desktop_id="desktop-a",
        connected_desktop_ids=["desktop-a", "desktop-b"],
        incoming_records=[record],
        aggregate_records=[record],
        aggregate_changed=True,
    ) == ["desktop-b"]
    assert provider_availability_sync_targets(
        origin_desktop_id="desktop-a",
        connected_desktop_ids=["desktop-a", "desktop-b"],
        incoming_records=[record],
        aggregate_records=[other],
        aggregate_changed=False,
    ) == ["desktop-a"]
