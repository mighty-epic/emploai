from mobile_app.backend.remote_control_store import RemoteControlPlaneStore


def test_remote_control_store_registers_login_and_pairs_mobile_to_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    user = store.register_user(email="user@example.com", password="correct horse", display_name="User")
    assert user["email"] == "user@example.com"

    desktop_login = store.login(
        email="user@example.com",
        password="correct horse",
        actor_kind="desktop",
        device_name="Workstation",
        device_platform="desktop-electron",
        device_key="desktop-key",
    )
    mobile_login = store.login(
        email="user@example.com",
        password="correct horse",
        actor_kind="mobile",
        device_name="Pixel",
        device_platform="android",
        device_key="phone-key",
    )

    desktop_payload = store.resolve_session_token(desktop_login["session_token"])
    mobile_payload = store.resolve_session_token(mobile_login["session_token"])

    assert desktop_payload is not None
    assert mobile_payload is not None
    assert desktop_payload["actor_kind"] == "desktop"
    assert mobile_payload["actor_kind"] == "mobile"

    pairing = store.create_pairing(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
    )
    paired = store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )

    assert paired["desktop"]["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert paired["mobile"]["paired_desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert store.paired_desktop_id_for_payload(mobile_payload) == desktop_login["desktop"]["desktop_id"]


def test_remote_control_store_updates_shared_snapshot_and_groups_sessions(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="sync@example.com", password="correct horse", display_name="Sync")
    desktop_login = store.login(
        email="sync@example.com",
        password="correct horse",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-key",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]

    state = store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        snapshot={
            "desktop_id": desktop_id,
            "desktop_name": "Desk",
            "current_session_id": "sess-1",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [
                {
                    "id": "sess-1",
                    "name": "Alpha",
                    "created_at": "2026-05-31T00:00:00Z",
                    "updated_at": "2026-05-31T00:00:00Z",
                    "model": "gpt-5",
                    "message_count": 1,
                    "workspace": "C:/Users/example/Documents/ProjectA",
                    "origin_channels": ["app"],
                    "is_running": False,
                    "run_state": "idle",
                    "enabled_tool_packs": [],
                    "available_tool_packs": [],
                    "lock_status": {},
                    "headless_eligible": False,
                    "artifact_count": 0,
                }
            ],
            "session_details": {
                "sess-1": {
                    "id": "sess-1",
                    "name": "Alpha",
                    "created_at": "2026-05-31T00:00:00Z",
                    "updated_at": "2026-05-31T00:00:00Z",
                    "model": "gpt-5",
                    "variant": "standard",
                    "agent_mode": "auto",
                    "workspace": "C:/Users/example/Documents/ProjectA",
                    "messages": [],
                    "timeline_events": [],
                    "completed_task_boards": [],
                    "task_board_armed_next_turn": False,
                    "is_running": False,
                    "run_state": "idle",
                    "enabled_tool_packs": [],
                    "available_tool_packs": [],
                    "lock_status": {},
                    "headless_eligible": False,
                    "artifact_count": 0,
                }
            },
            "jobs": [],
        },
    )

    assert state["current_session_id"] == "sess-1"
    assert state["current_model"] == "gpt-5"
    assert state["sync_version"] >= 1
    assert state["project_groups"][0]["label"] == "ProjectA"
    assert state["desktop_connection"]["status"] == "connected"
