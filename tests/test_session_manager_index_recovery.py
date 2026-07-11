import json
from pathlib import Path

from cli.session_manager import SessionManager


def _index_payload(base_path: Path) -> dict:
    index_path = base_path / "sessions" / "index.json"
    return json.loads(index_path.read_text(encoding="utf-8"))


def test_list_sessions_recovers_sessions_missing_from_index(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    first = manager.create_session(name="First", workspace=tmp_path, model="gpt-5.4")
    second = manager.create_session(name="Second", workspace=tmp_path, model="gpt-5.4")
    third = manager.create_session(name="Third", workspace=tmp_path, model="gpt-5.4")

    index_path = tmp_path / "sessions" / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "sessions": [first.to_summary().to_dict()],
                "current_session_id": first.id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    recovered = manager.list_sessions()

    assert {summary.id for summary in recovered} == {first.id, second.id, third.id}
    repaired_payload = _index_payload(tmp_path)
    assert {item["id"] for item in repaired_payload["sessions"]} == {first.id, second.id, third.id}


def test_get_current_session_id_recovers_invalid_current_pointer(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    older = manager.create_session(name="Older", workspace=tmp_path, model="gpt-5.4")
    newer = manager.create_session(name="Newer", workspace=tmp_path, model="gpt-5.4")

    index_path = tmp_path / "sessions" / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "sessions": [older.to_summary().to_dict(), newer.to_summary().to_dict()],
                "current_session_id": "missing-session",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    assert manager.get_current_session_id() == newer.id
    assert _index_payload(tmp_path)["current_session_id"] == newer.id


def test_load_session_recovers_last_durable_copy_after_corruption(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Recoverable", workspace=tmp_path, model="gpt-5.4")
    session.chat_history.append({"role": "user", "content": "durable message"})
    manager.save_session(session)

    session_path = tmp_path / "sessions" / f"{session.id}.json"
    session_path.write_text('{"chat_history":', encoding="utf-8")

    recovered = manager.load_session(session.id, set_current=False)

    assert recovered.name == "Recoverable"
    assert recovered.chat_history[-1]["content"] == "durable message"
    assert json.loads(session_path.read_text(encoding="utf-8"))["id"] == session.id


def test_nonactivating_load_does_not_replace_in_memory_current_session(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    first = manager.create_session(name="First", workspace=tmp_path, model="gpt-5.4")
    second = manager.create_session(name="Second", workspace=tmp_path, model="gpt-5.4")
    manager.load_session(first.id)

    loaded = manager.load_session(second.id, set_current=False)

    assert loaded.id == second.id
    assert manager.current_session is not None
    assert manager.current_session.id == first.id
