from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app_backend import context_inspection
from cli.models.session import Session
from cli.session_manager import SessionManager


def _session() -> Session:
    now = datetime.now()
    return Session(
        id="manager-chat",
        name="Manager",
        created_at=now.isoformat(),
        account_user_id=7,
        fleet_identity_id="manager-1",
        fleet_identity_role="manager",
        chat_history=[
            {
                "role": "user",
                "content": "old private history",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            }
        ],
    )


def test_context_index_only_captures_enabled_period_and_retains_disabled_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(context_inspection, "user_state_root", lambda user_id: tmp_path / f"user_{user_id}")
    manager = SessionManager(base_path=tmp_path / "sessions")
    session = _session()

    context_inspection.set_context_inspection_enabled(7, True, computer_id="pc-1", computer_name="PC")
    session.chat_history.append(
        {
            "role": "assistant",
            "content": "Build finished with artifact release.zip",
            "timestamp": datetime.now().isoformat(),
        }
    )
    manager.save_session(session)

    found = context_inspection.search_context_index(7, "release", limit=10)
    assert len(found["results"]) == 1
    assert found["results"][0]["computer_id"] == "pc-1"
    assert found["results"][0]["message_id"]
    assert "old private history" not in str(found)

    context_inspection.set_context_inspection_enabled(7, False)
    session.chat_history.append(
        {"role": "user", "content": "disabled period marker", "timestamp": datetime.now().isoformat()}
    )
    manager.save_session(session)
    with pytest.raises(PermissionError):
        context_inspection.search_context_index(7, "release")

    context_inspection.set_context_inspection_enabled(7, True)
    manager.save_session(session)
    assert context_inspection.search_context_index(7, "disabled")["results"] == []
    assert len(context_inspection.search_context_index(7, "release")["results"]) == 1


def test_context_window_is_redacted_and_paged(tmp_path, monkeypatch):
    monkeypatch.setattr(context_inspection, "user_state_root", lambda user_id: tmp_path / f"user_{user_id}")
    manager = SessionManager(base_path=tmp_path / "sessions")
    session = _session()
    context_inspection.set_context_inspection_enabled(7, True)
    for index in range(14):
        session.chat_history.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"message {index} token=super-secret-value",
                "timestamp": (datetime.now() + timedelta(milliseconds=index)).isoformat(),
            }
        )
    manager.save_session(session)
    match = context_inspection.search_context_index(7, "message", limit=20)["results"][7]
    window = context_inspection.context_window(7, match["message_id"])

    assert len(window["items"]) <= 11
    assert all("super-secret-value" not in item["content"] for item in window["items"])
    assert window["previous_cursor"] or window["next_cursor"]
