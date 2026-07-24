from types import SimpleNamespace

import pytest

from app_backend.automation_sessions import (
    resolve_existing_automation_session,
    resolve_new_automation_session,
)


IDENTITIES = [
    {
        "identity_id": "manager-1",
        "display_name": "Desktop Manager",
        "role": "manager",
        "status": "active",
        "enabled_tool_packs": ["manager_core"],
        "metadata": {},
    },
    {
        "identity_id": "worker-1",
        "display_name": "Default Worker",
        "role": "worker",
        "worker_id": "worker-record-1",
        "status": "active",
        "enabled_tool_packs": ["workspace_read", "workspace_write"],
        "metadata": {},
    },
]


class FakeBridge:
    def __init__(self):
        self.sessions = {
            "manager-chat": SimpleNamespace(
                id="manager-chat",
                company_id="company-a",
                fleet_identity_id="manager-1",
                model="existing-model",
                variant="medium",
            ),
            "worker-chat": SimpleNamespace(
                id="worker-chat",
                company_id="company-a",
                fleet_identity_id="worker-1",
                model="worker-model",
                variant="high",
            ),
        }
        self.created = []
        self.updated = []

    def get_session(self, session_id):
        if session_id not in self.sessions:
            raise KeyError(session_id)
        return self.sessions[session_id]

    def create_session(self, name, **kwargs):
        session = SimpleNamespace(
            id="automation-chat",
            fleet_identity_id=kwargs.get("fleet_identity_id"),
            model=kwargs.get("model"),
            variant=kwargs.get("variant"),
            company_id=kwargs.get("company_id"),
        )
        self.sessions[session.id] = session
        self.created.append((name, kwargs))
        return session

    def update_session_model_config(self, session_id, **kwargs):
        session = self.get_session(session_id)
        session.model = kwargs["model"]
        if kwargs.get("variant"):
            session.variant = kwargs["variant"]
        self.updated.append((session_id, kwargs))
        return session


def test_existing_chat_must_belong_to_selected_entity():
    bridge = FakeBridge()
    selected = resolve_existing_automation_session(
        bridge=bridge,
        identities=IDENTITIES,
        session_id="worker-chat",
        identity_id="worker-1",
    )
    assert selected.session.id == "worker-chat"
    assert selected.chat_target == "existing"

    with pytest.raises(ValueError, match="different entity"):
        resolve_existing_automation_session(
            bridge=bridge,
            identities=IDENTITIES,
            session_id="worker-chat",
            identity_id="manager-1",
        )


def test_new_chat_uses_selected_entity_and_model_without_activation():
    bridge = FakeBridge()
    selected = resolve_new_automation_session(
        bridge=bridge,
        identities=IDENTITIES,
        active_identity_id="manager-1",
        automation_name="Morning brief",
        identity_id="worker-1",
        model="openai/gpt-5.6",
        variant="high",
        permission_mode="standard",
    )

    assert selected.created is True
    assert selected.identity_id == "worker-1"
    assert selected.session.model == "openai/gpt-5.6"
    _, create_kwargs = bridge.created[0]
    assert create_kwargs["activate"] is False
    assert create_kwargs["fleet_identity_role"] == "worker"
    assert create_kwargs["fleet_worker_id"] == "worker-record-1"
    assert create_kwargs["company_id"] is None


def test_editing_new_chat_reuses_it_and_updates_only_its_model_config():
    bridge = FakeBridge()
    selected = resolve_new_automation_session(
        bridge=bridge,
        identities=IDENTITIES,
        active_identity_id="manager-1",
        automation_name="Worker monitor",
        identity_id="worker-1",
        model="openai/gpt-5.6",
        variant="xhigh",
        permission_mode="standard",
        reusable_session_id="worker-chat",
    )

    assert selected.created is False
    assert selected.session.id == "worker-chat"
    assert bridge.created == []
    assert bridge.updated == [("worker-chat", {"model": "openai/gpt-5.6", "variant": "xhigh"})]


def test_automation_chat_cannot_cross_company_boundary():
    bridge = FakeBridge()

    with pytest.raises(ValueError, match="different company"):
        resolve_existing_automation_session(
            bridge=bridge,
            identities=IDENTITIES,
            session_id="worker-chat",
            identity_id="worker-1",
            company_id="company-b",
        )

    selected = resolve_new_automation_session(
        bridge=bridge,
        identities=IDENTITIES,
        active_identity_id="manager-1",
        automation_name="Company B monitor",
        identity_id="worker-1",
        model="openai/gpt-5.6",
        variant="high",
        permission_mode="standard",
        company_id="company-b",
        reusable_session_id="worker-chat",
    )

    assert selected.created is True
    assert selected.session.company_id == "company-b"
