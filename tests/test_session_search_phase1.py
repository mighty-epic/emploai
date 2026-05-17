from pathlib import Path

from cli.session_manager import SessionManager
from mobile_app.backend import app_server


def _create_session_with_messages(
    manager: SessionManager,
    *,
    name: str,
    workspace: Path,
    messages: list[dict],
):
    session = manager.create_session(name=name, workspace=workspace, model="gpt-5.4")
    session.chat_history = messages
    manager.save_session(session)
    return session


def test_session_search_ranks_projects_then_sessions_then_messages(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    project = tmp_path / "5070 ti lab"
    project.mkdir()
    _create_session_with_messages(
        manager,
        name="5070 Ti Notes",
        workspace=project,
        messages=[
            {
                "role": "user",
                "content": "Best 5070 TI for running local models on Windows.",
                "timestamp": "2026-05-16T10:00:00",
            }
        ],
    )

    results = app_server._search_sessions_in_manager(
        user_id=9101,
        session_manager=manager,
        query="5070 ti",
        limit=10,
    )

    assert [item["kind"] for item in results[:3]] == ["project", "session", "message"]
    assert results[0]["project_name"] == "5070 ti lab"
    assert results[1]["session_name"] == "5070 Ti Notes"
    assert "5070 TI" in results[2]["snippet"]


def test_session_search_is_case_insensitive_and_prefers_newer_phrase_matches(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    project = tmp_path / "hardware"
    project.mkdir()
    session = _create_session_with_messages(
        manager,
        name="GPU Research",
        workspace=project,
        messages=[
            {
                "role": "assistant",
                "content": "Older note about the 5070 ti for running local inference.",
                "timestamp": "2026-05-16T09:00:00",
            },
            {
                "role": "assistant",
                "content": "Newer note about the 5070 TI for RUNNING local inference.",
                "timestamp": "2026-05-16T11:00:00",
            },
        ],
    )

    results = app_server._search_sessions_in_manager(
        user_id=9102,
        session_manager=manager,
        query="5070 ti for runNING",
        limit=10,
    )

    message_hits = [item for item in results if item["kind"] == "message" and item["session_id"] == session.id]
    assert [item["message_index"] for item in message_hits[:2]] == [1, 0]


def test_session_search_reloads_changed_session_files(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    project = tmp_path / "workspace"
    project.mkdir()
    session = _create_session_with_messages(
        manager,
        name="Hardware Notes",
        workspace=project,
        messages=[
            {
                "role": "user",
                "content": "Initial note with no relevant search term.",
                "timestamp": "2026-05-16T08:00:00",
            }
        ],
    )

    first_results = app_server._search_sessions_in_manager(
        user_id=9103,
        session_manager=manager,
        query="5070 ti for running",
        limit=10,
    )
    assert all(item["session_id"] != session.id for item in first_results if item["kind"] == "message")

    loaded = manager.load_session(session.id, set_current=False)
    loaded.chat_history.append(
        {
            "role": "assistant",
            "content": "Updated note covering the 5070 ti for running local models.",
            "timestamp": "2026-05-16T12:30:00",
        }
    )
    manager.save_session(loaded)

    second_results = app_server._search_sessions_in_manager(
        user_id=9103,
        session_manager=manager,
        query="5070 ti for running",
        limit=10,
    )

    message_hits = [item for item in second_results if item["kind"] == "message" and item["session_id"] == session.id]
    assert len(message_hits) == 1
    assert message_hits[0]["message_index"] == 1
