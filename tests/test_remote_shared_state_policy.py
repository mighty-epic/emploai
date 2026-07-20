from __future__ import annotations

from app_backend.remote_shared_state_policy import (
    empty_fleet_state,
    empty_sidebar_state,
    fleet_selection_for_desktop,
    normalize_fleet_state,
    project_groups_from_sessions,
    store_fleet_selection_for_desktop,
)


def test_normalize_fleet_state_preserves_known_fields_and_sanitizes_selection_map():
    state = normalize_fleet_state(
        {
            "schema_version": 99,
            "active_identity_id": "manager-1",
            "selected_chat_by_identity": {
                "manager-1": " sess-1 ",
                "": "ignored",
                "worker-1": "",
                "worker-2": None,
            },
            "active_identity_version": "7",
            "active_identity_updated_at": 123.4,
            "extra": "ignored",
        }
    )

    assert state == {
        "schema_version": 99,
        "active_identity_id": "manager-1",
        "selected_chat_by_identity": {
            "manager-1": "sess-1",
            "worker-1": None,
            "worker-2": None,
        },
        "active_identity_version": 7,
        "active_identity_updated_at": 123.4,
        "selection_by_desktop": {},
    }


def test_normalize_fleet_state_defaults_invalid_values():
    state = normalize_fleet_state({"selected_chat_by_identity": [], "active_identity_version": "bad"})

    assert state["selected_chat_by_identity"] == {}
    assert state["active_identity_version"] == 0
    assert state["active_identity_id"] is None


def test_fleet_identity_selection_is_scoped_per_desktop():
    state = empty_fleet_state()
    state = store_fleet_selection_for_desktop(
        state,
        "desktop-a",
        {"active_identity_id": "manager-a", "active_identity_version": 3},
    )
    state = store_fleet_selection_for_desktop(
        state,
        "desktop-b",
        {"active_identity_id": "worker-b", "active_identity_version": 8},
    )

    assert fleet_selection_for_desktop(state, "desktop-a")["active_identity_id"] == "manager-a"
    assert fleet_selection_for_desktop(state, "desktop-a")["active_identity_version"] == 3
    assert fleet_selection_for_desktop(state, "desktop-b")["active_identity_id"] == "worker-b"
    assert fleet_selection_for_desktop(state, "desktop-b")["active_identity_version"] == 8


def test_empty_state_helpers_return_independent_mutable_defaults():
    first_fleet = empty_fleet_state()
    second_fleet = empty_fleet_state()
    first_fleet["selected_chat_by_identity"]["manager"] = "chat"

    first_sidebar = empty_sidebar_state()
    second_sidebar = empty_sidebar_state()
    first_sidebar["projectOrder"].append("C:/Project")

    assert second_fleet["selected_chat_by_identity"] == {}
    assert second_sidebar["projectOrder"] == []


def test_project_groups_from_sessions_groups_and_orders_by_project_label():
    groups = project_groups_from_sessions(
        [
            {"id": "sess-b", "workspace": "C:/Work/Beta"},
            {"id": "sess-default", "workspace": ""},
            {"id": "sess-a1", "workspace": "C:/Work/Alpha"},
            {"id": "sess-a2", "workspace": "C:/Work/Alpha"},
            {"id": "", "workspace": "C:/Work/Alpha"},
        ]
    )

    assert [group["label"] for group in groups] == ["Alpha", "Beta", "default"]
    assert groups[0]["path"] == "C:/Work/Alpha"
    assert groups[0]["session_ids"] == ["sess-a1", "sess-a2"]
    assert groups[1]["session_ids"] == ["sess-b"]
    assert groups[2]["session_ids"] == ["sess-default"]
