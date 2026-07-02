from __future__ import annotations

import pytest
from fastapi import HTTPException

from app_backend.app_confirmation_workflow import (
    consume_approved_confirmation,
    publish_confirmation_delta,
)


class _FakeSyncHub:
    def __init__(self):
        self.published = []

    def publish(self, *, user_id, event):
        self.published.append({"user_id": user_id, "event": event})


class _FakeConfirmationStore:
    def __init__(self, confirmation):
        self.confirmation = confirmation
        self.executed = []

    def get_confirmation(self, *, user_id, confirmation_id):
        if confirmation_id != self.confirmation.get("confirmation_id"):
            raise KeyError("missing")
        return dict(self.confirmation)

    def record_confirmation_executed(self, *, user_id, confirmation_id, executed_by_surface, metadata=None):
        executed = {
            **self.confirmation,
            "status": "executed",
            "executed_by_surface": executed_by_surface,
            "metadata": dict(metadata or {}),
        }
        self.executed.append(executed)
        return executed


def test_publish_confirmation_delta_emits_sync_event_shape():
    hub = _FakeSyncHub()
    confirmation = {"confirmation_id": "conf_1", "origin_chat_id": "chat_1"}

    publish_confirmation_delta(
        sync_hub=hub,
        user_id=7,
        confirmation=confirmation,
        origin_channel="desktop",
    )

    assert hub.published == [
        {
            "user_id": 7,
            "event": {
                "type": "confirmation_changed",
                "session_id": "chat_1",
                "origin_channel": "desktop",
                "payload": {"confirmation": confirmation},
            },
        }
    ]


def test_consume_approved_confirmation_requires_confirmation_id():
    with pytest.raises(HTTPException) as exc_info:
        consume_approved_confirmation(
            store=_FakeConfirmationStore({}),
            publish_confirmation_delta=lambda **_: None,
            user_id=7,
            confirmation_id=None,
            action_kind="fleet_worker_reset",
            executed_by_surface="desktop",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_type"] == "confirmation_required"


def test_consume_approved_confirmation_executes_and_publishes():
    published = []
    store = _FakeConfirmationStore(
        {
            "confirmation_id": "conf_1",
            "action_kind": "fleet_worker_reset",
            "status": "approved",
            "origin_chat_id": "chat_1",
        }
    )

    result = consume_approved_confirmation(
        store=store,
        publish_confirmation_delta=lambda **kwargs: published.append(kwargs),
        user_id=7,
        confirmation_id=" conf_1 ",
        action_kind="fleet_worker_reset",
        executed_by_surface="desktop",
        metadata={"worker_id": "worker_1"},
    )

    assert result["status"] == "executed"
    assert result["metadata"] == {"worker_id": "worker_1"}
    assert published == [
        {
            "user_id": 7,
            "confirmation": result,
            "origin_channel": "desktop",
        }
    ]


def test_consume_approved_confirmation_rejects_wrong_action_or_status():
    store = _FakeConfirmationStore(
        {
            "confirmation_id": "conf_1",
            "action_kind": "remote_secret_delete",
            "status": "pending",
        }
    )

    with pytest.raises(HTTPException, match="does not match"):
        consume_approved_confirmation(
            store=store,
            publish_confirmation_delta=lambda **_: None,
            user_id=7,
            confirmation_id="conf_1",
            action_kind="fleet_worker_reset",
            executed_by_surface="desktop",
        )

    store.confirmation["action_kind"] = "fleet_worker_reset"
    with pytest.raises(HTTPException, match="pending"):
        consume_approved_confirmation(
            store=store,
            publish_confirmation_delta=lambda **_: None,
            user_id=7,
            confirmation_id="conf_1",
            action_kind="fleet_worker_reset",
            executed_by_surface="desktop",
        )
