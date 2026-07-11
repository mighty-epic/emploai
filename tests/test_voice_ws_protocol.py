from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app_backend import app_server


class _Draft:
    state = "idle"

    def reset(self):
        self.state = "idle"


class _TranscriptDraft(_Draft):
    cancel_empty_pending_before_final = True

    async def wait_for_pending(self, timeout=None):
        return None

    def transcript(self):
        return "wait stop"

    def cancel_pending(self):
        return None

    async def final_transcript(self, fast=False):
        return "wait stop"


def _next_event(websocket, event_type: str) -> dict:
    for _ in range(8):
        event = websocket.receive_json()
        if event.get("type") == event_type:
            return event
    raise AssertionError(f"Did not receive {event_type!r}")


def test_voice_socket_rejects_malformed_cross_session_and_stale_events(monkeypatch):
    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 7})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: object())
    monkeypatch.setattr(app_server, "_new_voice_draft_state", _Draft)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        "/ws/app/voice?token=test-token&session_id=session-a&surface_mode=jarvis"
    ) as websocket:
        connected = _next_event(websocket, "voice_state")
        assert connected["payload"]["state"] == "connected"

        websocket.send_text("not-json")
        malformed = _next_event(websocket, "error")
        assert malformed["payload"] == {"message": "Voice event is malformed or unsupported"}
        assert "detail" not in malformed["payload"]

        websocket.send_json(
            {
                "type": "voice_start",
                "session_id": "session-b",
                "utterance_id": "wrong-session-turn",
            }
        )
        wrong_session = _next_event(websocket, "error")
        assert wrong_session["session_id"] == "session-a"
        assert "does not match" in wrong_session["payload"]["message"]

        websocket.send_json(
            {
                "type": "voice_commit",
                "session_id": "session-a",
                "utterance_id": "never-started",
            }
        )
        missing_start = _next_event(websocket, "warning")
        assert "no utterance is active" in missing_start["payload"]["message"]

        websocket.send_json(
            {
                "type": "voice_start",
                "session_id": "session-a",
                "utterance_id": "active-turn",
            }
        )
        listening = _next_event(websocket, "voice_state")
        assert listening["payload"]["state"] == "listening"
        assert listening["payload"]["turn_id"] == "active-turn"

        websocket.send_json(
            {
                "type": "voice_pause",
                "session_id": "session-a",
                "utterance_id": "stale-turn",
            }
        )
        stale = _next_event(websocket, "warning")
        assert stale["payload"]["message"] == "Stale voice event ignored"

        websocket.send_json(
            {
                "type": "voice_cancel",
                "session_id": "session-a",
                "utterance_id": "active-turn",
            }
        )
        cancelled = _next_event(websocket, "voice_state")
        assert cancelled["payload"]["state"] == "cancelled"
        assert cancelled["payload"]["turn_id"] == "active-turn"


def test_jarvis_barge_in_is_ignored_without_transcription_or_provider_work(monkeypatch):
    calls: list[dict] = []
    runtime = SimpleNamespace(
        session=SimpleNamespace(account_user_id=None),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "session-a"),
        verbose_mode=False,
    )
    bridge = SimpleNamespace(load_runtime_session=lambda _session_id: runtime)

    async def fake_run(_runtime, **kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "busy": False,
            "steering": True,
            "steering_status": "armed",
            "session_id": "session-a",
            "assistant_text": "",
        }

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 7})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: bridge)
    monkeypatch.setattr(app_server, "_new_voice_draft_state", _TranscriptDraft)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", fake_run)
    monkeypatch.setattr(app_server, "_synthesize_assistant_audio_sync", lambda _text: None)
    monkeypatch.setattr(app_server, "_jarvis_voice_turn_is_task_like", lambda _text: False)
    monkeypatch.setattr(app_server, "_mirror_session_snapshot", lambda **_kwargs: None)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        "/ws/app/voice?token=test-token&session_id=session-a&surface_mode=jarvis"
    ) as websocket:
        _next_event(websocket, "voice_state")
        websocket.send_json(
            {
                "type": "voice_start",
                "session_id": "session-a",
                "surface_mode": "jarvis",
                "capture_mode": "always_on",
                "wake_phrase": "Jarvis",
                "utterance_id": "barge-turn",
            }
        )
        _next_event(websocket, "voice_state")
        websocket.send_json(
            {
                "type": "voice_commit",
                "session_id": "session-a",
                "surface_mode": "jarvis",
                "capture_mode": "always_on",
                "wake_phrase": "Jarvis",
                "utterance_id": "barge-turn",
                "auto_send": True,
                "interrupt_policy": "none",
                "barge_in_candidate": True,
                "barge_in_reference_text": "I am checking that now.",
            }
        )

        ignored = _next_event(websocket, "voice_state")
        assert ignored["payload"]["ignored"] == "barge_in_disabled"

    assert calls == []


def test_locally_verified_jarvis_wake_runs_command_only_transcript_once(monkeypatch):
    calls: list[dict] = []
    runtime = SimpleNamespace(
        session=SimpleNamespace(account_user_id=None),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "session-a"),
        verbose_mode=False,
    )
    bridge = SimpleNamespace(load_runtime_session=lambda _session_id: runtime)

    async def fake_run(_runtime, **kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "busy": False,
            "steering": False,
            "session_id": "session-a",
            "assistant_text": "Done.",
        }

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 7})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: bridge)
    monkeypatch.setattr(app_server, "_new_voice_draft_state", _TranscriptDraft)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", fake_run)
    monkeypatch.setattr(app_server, "_synthesize_assistant_audio_sync", lambda _text: None)
    monkeypatch.setattr(app_server, "_jarvis_voice_turn_is_task_like", lambda _text: False)
    monkeypatch.setattr(app_server, "_mirror_session_snapshot", lambda **_kwargs: None)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        "/ws/app/voice?token=test-token&session_id=session-a&surface_mode=jarvis"
    ) as websocket:
        _next_event(websocket, "voice_state")
        websocket.send_json(
            {
                "type": "voice_start",
                "session_id": "session-a",
                "surface_mode": "jarvis",
                "capture_mode": "always_on",
                "wake_phrase": "Jarvis",
                "wake_verified_locally": True,
                "utterance_id": "local-wake-turn",
            }
        )
        _next_event(websocket, "voice_state")
        websocket.send_json(
            {
                "type": "voice_commit",
                "session_id": "session-a",
                "surface_mode": "jarvis",
                "capture_mode": "always_on",
                "wake_phrase": "Jarvis",
                "wake_verified_locally": True,
                "utterance_id": "local-wake-turn",
                "auto_send": True,
            }
        )
        final_event = _next_event(websocket, "voice_final")
        assert final_event["payload"]["text"] == "wait stop"

    assert len(calls) == 1
    assert calls[0]["user_message"] == "wait stop"
    assert calls[0]["interrupt_policy"] == "none"
