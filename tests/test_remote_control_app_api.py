from fastapi.testclient import TestClient

from mobile_app.backend import app_server
from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.remote_control_store import RemoteControlPlaneStore


def test_remote_mobile_token_can_read_app_profile_and_sessions(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store

    user = store.register_user(email="remote@example.com", password="correct horse", display_name="Remote User")
    desktop_login = store.login(
        email="remote@example.com",
        password="correct horse",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-key",
    )
    mobile_login = store.login(
        email="remote@example.com",
        password="correct horse",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="phone-key",
    )
    pairing = store.create_pairing(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
    )
    store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={
            "desktop_id": desktop_login["desktop"]["desktop_id"],
            "desktop_name": "Desk",
            "current_session_id": "sess-1",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [
                {
                    "id": "sess-1",
                    "name": "Synced chat",
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
                    "name": "Synced chat",
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

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    me = client.get("/api/app/me", headers=headers)
    sessions = client.get("/api/app/sessions", headers=headers)
    detail = client.get("/api/app/sessions/sess-1", headers=headers)

    assert me.status_code == 200
    assert me.json()["current_session_id"] == "sess-1"
    assert sessions.status_code == 200
    assert sessions.json()[0]["id"] == "sess-1"
    assert detail.status_code == 200
    assert detail.json()["name"] == "Synced chat"
