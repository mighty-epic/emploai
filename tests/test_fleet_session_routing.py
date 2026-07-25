from __future__ import annotations

from types import SimpleNamespace

from app_backend.fleet_session_routing import (
    reconcile_local_identity_session_profiles,
    reconcile_local_manager_chat_selection,
    session_belongs_to_fleet_identity,
    session_id_for_fleet_identity,
)
from app_backend.fleet_identity_profiles import DEFAULT_WORKER_TOOL_PACKS, MANAGER_TOOL_PACKS
from shared.tool_packs import PACK_MANAGER_CORE, PACK_WEB_RESEARCH


MANAGER = {
    "identity_id": "manager-current",
    "role": "manager",
    "desktop_id": "desktop-local",
}


def test_replacement_manager_keeps_manager_sessions_but_never_worker_sessions():
    old_manager_session = SimpleNamespace(
        id="manager-chat",
        fleet_identity_id="manager-retired",
        fleet_identity_role="manager",
        fleet_worker_id=None,
    )
    worker_session = SimpleNamespace(
        id="worker-chat",
        fleet_identity_id="worker-identity",
        fleet_identity_role="worker",
        fleet_worker_id="worker-1",
    )

    assert session_belongs_to_fleet_identity(old_manager_session, MANAGER) is True
    assert session_belongs_to_fleet_identity(worker_session, MANAGER) is False
    assert session_id_for_fleet_identity(
        [worker_session, old_manager_session],
        MANAGER,
        "worker-chat",
    ) == "manager-chat"


def test_manager_session_from_another_company_is_never_reused():
    identity = {
        **MANAGER,
        "metadata": {"company_id": "company-b"},
    }
    other_company_session = SimpleNamespace(
        id="company-a-manager-chat",
        company_id="company-a",
        fleet_identity_id="manager-company-a",
        fleet_identity_role="manager",
        fleet_worker_id=None,
    )

    assert session_belongs_to_fleet_identity(other_company_session, identity) is False
    assert session_id_for_fleet_identity([other_company_session], identity) is None


class _Store:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.selections = []

    def set_active_chat_for_fleet_identity(self, **kwargs):
        self.selections.append(kwargs)
        selected = dict(self.snapshot["selected_chat_by_identity"])
        if kwargs["chat_id"]:
            selected[kwargs["identity_id"]] = kwargs["chat_id"]
        else:
            selected.pop(kwargs["identity_id"], None)
        self.snapshot = {**self.snapshot, "selected_chat_by_identity": selected}

    def get_fleet_snapshot(self, **_kwargs):
        return self.snapshot


def test_reconciliation_replaces_cross_identity_manager_selection():
    snapshot = {
        "identities": [MANAGER],
        "selected_chat_by_identity": {"manager-current": "worker-chat"},
    }
    store = _Store(snapshot)
    sessions = [
        {"id": "worker-chat", "fleet_identity_role": "worker", "fleet_worker_id": "worker-1"},
        {"id": "manager-chat", "fleet_identity_role": "manager", "fleet_identity_id": "manager-retired"},
    ]

    reconciled = reconcile_local_manager_chat_selection(
        store=store,
        user_id=7,
        desktop_id="desktop-local",
        snapshot=snapshot,
        sessions=sessions,
    )

    assert reconciled["selected_chat_by_identity"]["manager-current"] == "manager-chat"
    assert store.selections == [
        {
            "user_id": 7,
            "identity_id": "manager-current",
            "chat_id": "manager-chat",
            "source": "local_session_reconciliation",
            "desktop_id": "desktop-local",
        }
    ]


def test_reconciliation_clears_invalid_manager_selection_without_local_manager_chat():
    snapshot = {
        "identities": [MANAGER],
        "selected_chat_by_identity": {"manager-current": "worker-chat"},
    }
    store = _Store(snapshot)

    reconciled = reconcile_local_manager_chat_selection(
        store=store,
        user_id=7,
        desktop_id="desktop-local",
        snapshot=snapshot,
        sessions=[{"id": "worker-chat", "fleet_identity_role": "worker", "fleet_worker_id": "worker-1"}],
    )

    assert "manager-current" not in reconciled["selected_chat_by_identity"]
    assert store.selections[0]["chat_id"] is None


def test_reconciliation_does_not_touch_a_manager_for_another_desktop():
    remote_manager = {**MANAGER, "desktop_id": "desktop-remote"}
    snapshot = {
        "identities": [remote_manager],
        "selected_chat_by_identity": {"manager-current": "worker-chat"},
    }
    store = _Store(snapshot)

    reconciled = reconcile_local_manager_chat_selection(
        store=store,
        user_id=7,
        desktop_id="desktop-local",
        snapshot=snapshot,
        sessions=[],
    )

    assert reconciled == snapshot
    assert store.selections == []


class _SessionManager:
    def __init__(self):
        self.saved = []

    def save_session(self, session):
        self.saved.append(session.id)


class _Bridge:
    def __init__(self, sessions):
        self.sessions = sessions
        self.session_manager = _SessionManager()

    def list_sessions(self):
        return self.sessions


def test_legacy_local_sessions_are_migrated_to_role_locked_profiles_idempotently():
    manager_session = SimpleNamespace(
        id="manager-chat",
        fleet_identity_id=None,
        fleet_identity_role=None,
        fleet_worker_id=None,
        fleet_task_mode=None,
        enabled_tool_packs=[PACK_WEB_RESEARCH],
    )
    worker_session = SimpleNamespace(
        id="worker-chat",
        fleet_identity_id="worker-identity",
        fleet_identity_role="worker",
        fleet_worker_id="worker-1",
        fleet_task_mode=None,
        enabled_tool_packs=[PACK_MANAGER_CORE],
    )
    snapshot = {
        "identities": [
            {**MANAGER, "metadata": {"enabled_tool_packs": [PACK_WEB_RESEARCH]}},
            {
                "identity_id": "worker-identity",
                "role": "worker",
                "worker_id": "worker-1",
                "desktop_id": "desktop-local",
                "metadata": {"enabled_tool_packs": list(DEFAULT_WORKER_TOOL_PACKS)},
            },
        ]
    }
    bridge = _Bridge([manager_session, worker_session])

    assert reconcile_local_identity_session_profiles(bridge=bridge, snapshot=snapshot) == 2
    assert manager_session.fleet_identity_id == "manager-current"
    assert manager_session.enabled_tool_packs == [*MANAGER_TOOL_PACKS, PACK_WEB_RESEARCH]
    assert worker_session.enabled_tool_packs == DEFAULT_WORKER_TOOL_PACKS
    assert worker_session.fleet_task_mode == "direct"
    assert bridge.session_manager.saved == ["manager-chat", "worker-chat"]

    assert reconcile_local_identity_session_profiles(bridge=bridge, snapshot=snapshot) == 0
    assert bridge.session_manager.saved == ["manager-chat", "worker-chat"]


def test_reconciliation_does_not_promote_a_session_bound_to_another_desktop():
    foreign_worker_session = SimpleNamespace(
        id="foreign-worker-chat",
        fleet_identity_id="foreign-worker-identity",
        fleet_identity_role="worker",
        fleet_worker_id="foreign-worker",
        fleet_task_mode="direct",
        enabled_tool_packs=[PACK_WEB_RESEARCH],
    )
    bridge = _Bridge([foreign_worker_session])

    assert reconcile_local_identity_session_profiles(
        bridge=bridge,
        snapshot={"identities": [MANAGER]},
    ) == 0
    assert foreign_worker_session.fleet_identity_id == "foreign-worker-identity"
    assert foreign_worker_session.enabled_tool_packs == [PACK_WEB_RESEARCH]
    assert bridge.session_manager.saved == []
