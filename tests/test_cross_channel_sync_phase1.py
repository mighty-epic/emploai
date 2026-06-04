from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mobile_app.backend import app_server
from mobile_app.backend import runtime as app_runtime
from mobile_app.backend.models import SessionDetailView
from shared import channel_runtime
from shared.task_intent import is_screen_observation_message, is_task_like_message
from telegram_bot.telegram_session_state import TelegramSession


class _CaptureHub:
    def __init__(self) -> None:
        self.events: list[tuple[int, dict]] = []

    def publish(self, *, user_id: int, event: dict) -> None:
        self.events.append((user_id, event))


def test_begin_chat_turn_publishes_user_message_with_channel_metadata(monkeypatch):
    hub = _CaptureHub()
    monkeypatch.setattr(channel_runtime, "get_channel_sync_hub", lambda: hub)

    runtime = SimpleNamespace(
        lock=asyncio.Lock(),
        is_processing=False,
        current_task_id=0,
        should_interrupt=False,
        chat_history=[],
        last_user_message=None,
        current_model="gpt-5.2",
        context_manager=None,
        user_id=77,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-1"),
        start_browser_task=lambda *_args, **_kwargs: None,
        refresh_system_info=lambda: None,
        save_session=lambda: None,
    )

    reservation = asyncio.run(
        channel_runtime.begin_chat_turn(
            runtime,
            user_message="hello from telegram",
            user_message_payload={
                "channel": "telegram",
                "source_format": "telegram_text",
                "display_label": "Telegram",
            },
        )
    )

    assert reservation.event_meta["channel"] == "telegram"
    assert hub.events == [
        (
            77,
            {
                "type": "user_message",
                "session_id": "sess-1",
                "origin_channel": "telegram",
                "source_client_id": None,
                "payload": {
                    "message": {
                        "role": "user",
                        "content": "hello from telegram",
                        "timestamp": runtime.chat_history[0]["timestamp"],
                        "channel": "telegram",
                        "source_format": "telegram_text",
                        "display_label": "Telegram",
                    },
                    "text": "hello from telegram",
                },
            },
        )
    ]


def test_run_reserved_chat_turn_publishes_live_events(monkeypatch):
    hub = _CaptureHub()
    monkeypatch.setattr(channel_runtime, "get_channel_sync_hub", lambda: hub)

    def fake_run_tool_loop(**kwargs):
        callbacks = kwargs["callbacks"]
        callbacks["append_stream"]("Hel")
        callbacks["append_stream"]("lo")
        return SimpleNamespace(content="Hello", input_tokens=12, output_tokens=7, total_tokens=19)

    monkeypatch.setattr(channel_runtime, "run_tool_loop", fake_run_tool_loop)

    saved_sessions: list[list[dict]] = []

    runtime = SimpleNamespace(
        lock=asyncio.Lock(),
        user_id=42,
        current_task_id=1,
        is_processing=True,
        current_model="gpt-5.2",
        current_variant="standard",
        chat_history=[{"role": "user", "content": "ping"}],
        pending_files=[],
        skill_registry=None,
        active_skills=[],
        session_context=None,
        memory_manager=None,
        config_manager=SimpleNamespace(get_api_key=lambda _provider: None),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-2"),
        get_client_for_model=lambda: (object(), "openai"),
        single_agent=object(),
        tool_executor=None,
        save_session=lambda: saved_sessions.append(list(runtime.chat_history)),
        last_user_message="ping",
        hook_manager=None,
        analytics_tracker=None,
        auto_rename_session=lambda: None,
    )

    reservation = channel_runtime.TurnReservation(
        busy=False,
        task_id=1,
        session_id="sess-2",
        event_meta={
            "channel": "app",
            "display_label": "App",
            "source_format": "app_text",
            "source_client_id": "client-1",
        },
    )

    result = asyncio.run(
        channel_runtime.run_reserved_chat_turn(
            runtime,
            reservation,
            prompt_builder=lambda *_args, **_kwargs: "system prompt",
            assistant_message_payload={
                "channel": "app",
                "display_label": "App",
                "source_format": "app_response",
                "source_client_id": "client-1",
            },
        )
    )

    assert result.assistant_text == "Hello"
    assert [event["type"] for _, event in hub.events] == [
        "status",
        "assistant_delta",
        "assistant_delta",
        "assistant_final",
        "status",
    ]
    assert hub.events[-2][1]["payload"]["message"]["channel"] == "app"
    assert hub.events[-2][1]["source_client_id"] == "client-1"
    assert hub.events[-1][1]["payload"]["run_state"] == "idle"


def test_sync_event_to_realtime_event_filters_same_client():
    sync_event = {
        "type": "assistant_final",
        "session_id": "sess-3",
        "source_client_id": "client-a",
        "payload": {"text": "done"},
    }

    assert app_server._sync_event_to_realtime_event(
        sync_event,
        active_session_id="sess-3",
        client_id="client-a",
        verbose_mode=True,
    ) is None

    translated = app_server._sync_event_to_realtime_event(
        sync_event,
        active_session_id="sess-3",
        client_id="client-b",
        verbose_mode=True,
    )

    assert translated is not None
    assert translated.type == "assistant_final"
    assert translated.payload["text"] == "done"


def test_sync_event_to_realtime_event_translates_task_board():
    sync_event = {
        "type": "task_board",
        "session_id": "sess-board",
        "payload": {
            "summary": "Completed sub-goal: Open Spotify.",
            "board": {
                "task_id": "task_123",
                "main_goal": "Play a song on Spotify",
                "progress_summary": "1/3 sub-goals complete",
            },
            "completed_task_boards": [
                {
                    "task_id": "task_old",
                    "main_goal": "Open Chrome",
                    "display_mode": "completed_collapsed",
                }
            ],
        },
    }

    translated = app_server._sync_event_to_realtime_event(
        sync_event,
        active_session_id="sess-board",
        client_id="client-b",
        verbose_mode=True,
    )

    assert translated is not None
    assert translated.type == "task_board"
    assert translated.payload == sync_event["payload"]


def test_sync_event_to_realtime_event_translates_current_session_changed():
    sync_event = {
        "type": "current_session_changed",
        "session_id": "sess-board",
        "payload": {"current_session_id": "sess-board", "reason": "session_activated"},
    }

    translated = app_server._sync_event_to_realtime_event(
        sync_event,
        active_session_id="sess-board",
        client_id="client-b",
        verbose_mode=True,
    )

    assert translated is not None
    assert translated.type == "current_session_changed"
    assert translated.payload["current_session_id"] == "sess-board"


def test_sync_event_to_realtime_event_translates_session_deleted_to_previous_active_session():
    sync_event = {
        "type": "current_session_changed",
        "session_id": None,
        "payload": {
            "current_session_id": None,
            "previous_session_id": "sess-deleted",
            "reason": "session_deleted",
        },
    }

    translated = app_server._sync_event_to_realtime_event(
        sync_event,
        active_session_id="sess-deleted",
        client_id="client-b",
        verbose_mode=True,
    )

    assert translated is not None
    assert translated.type == "current_session_changed"
    assert translated.session_id == "sess-deleted"
    assert translated.payload["current_session_id"] is None


def test_resolve_external_current_session_id_switches_when_bridge_current_matches_event():
    bridge = SimpleNamespace(get_current_session=lambda: SimpleNamespace(id="sess-new"))
    event = {
        "type": "user_message",
        "session_id": "sess-new",
        "payload": {"text": "hello"},
    }

    switched = app_server._resolve_external_current_session_id(
        bridge,
        active_session_id="sess-old",
        event=event,
    )

    assert switched == "sess-new"


def test_resolve_external_current_session_id_ignores_noncurrent_event_session():
    bridge = SimpleNamespace(get_current_session=lambda: SimpleNamespace(id="sess-other"))
    event = {
        "type": "user_message",
        "session_id": "sess-new",
        "payload": {"text": "hello"},
    }

    switched = app_server._resolve_external_current_session_id(
        bridge,
        active_session_id="sess-old",
        event=event,
    )

    assert switched is None


def test_app_steering_publishes_cross_channel_user_message(monkeypatch):
    hub = _CaptureHub()
    monkeypatch.setattr(app_runtime, "get_channel_sync_hub", lambda: hub)
    monkeypatch.setattr(app_runtime, "_steering_beta_enabled", lambda _session: True)

    saved_history: list[list[dict]] = []

    runtime = SimpleNamespace(
        lock=asyncio.Lock(),
        is_processing=True,
        user_id=123,
        chat_history=[],
        last_user_message=None,
        should_interrupt=False,
        interrupt_message=None,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-steer"),
        save_session=lambda: saved_history.append(list(runtime.chat_history)),
        queue_interrupt=lambda message, deferred=False: saved_history.append(
            [{"queued": message, "deferred": deferred}]
        ),
    )

    result = asyncio.run(
        app_runtime._request_app_steering(
            runtime,
            user_message="switch to docs tab",
            source_format="app_text",
            interrupt_policy="steer_now",
            source_client_id="client-7",
        )
    )

    assert result is not None
    assert result["steering"] is True
    assert hub.events == [
        (
            123,
            {
                "type": "user_message",
                "session_id": "sess-steer",
                "origin_channel": "app",
                "source_client_id": "client-7",
                "payload": {
                    "message": runtime.chat_history[0],
                    "text": "switch to docs tab",
                },
            },
        )
    ]
    assert runtime.chat_history[0]["display_label"] == "App Steering"
    assert runtime.chat_history[0]["source_client_id"] == "client-7"


def test_session_detail_view_accepts_historic_telegram_response_source_format():
    detail = SessionDetailView(
        id="sess-legacy",
        name="Legacy Session",
        created_at="2026-04-23T00:00:00",
        updated_at="2026-04-23T00:00:00",
        model="gpt-5.2",
        variant="standard",
        agent_mode="auto",
        workspace="C:\\workspace",
        messages=[
            {
                "role": "assistant",
                "content": "done",
                "channel": "telegram",
                "source_format": "telegram_response",
                "display_label": "Telegram",
                "raw": {},
            }
        ],
    )

    assert detail.messages[0].source_format == "telegram_response"


def test_task_intent_classifier_keeps_hello_conversational():
    assert is_task_like_message("hello") is False
    assert is_task_like_message("thanks") is False
    assert is_task_like_message("describe what is on the screen") is True
    assert is_task_like_message("can you open chrome?") is True


def test_screen_observation_classifier_prefers_live_vision_over_filesystem():
    assert is_screen_observation_message("what do you see right now?") is True
    assert is_screen_observation_message("look again") is True
    assert is_screen_observation_message("tell me the directory contents and the path") is False


def test_telegram_session_mirrors_non_telegram_events():
    sent_messages: list[str] = []
    chat_actions: list[str] = []

    class DummyBot:
        async def send_message(self, *, chat_id: int, text: str, parse_mode=None):
            assert chat_id == 99
            sent_messages.append(text)

        async def send_chat_action(self, *, chat_id: int, action: str):
            assert chat_id == 99
            chat_actions.append(action)

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 99
    runtime._app = SimpleNamespace(bot=DummyBot())
    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: "sess-9")

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "user_message",
                "session_id": "sess-9",
                "origin_channel": "app",
                "payload": {
                    "message": {
                        "content": "hello from app",
                        "display_label": "App",
                    }
                },
            }
        )
    )
    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "assistant_final",
                "session_id": "sess-9",
                "origin_channel": "app",
                "payload": {"text": "assistant reply"},
            }
        )
    )
    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "assistant_final",
                "session_id": "sess-9",
                "origin_channel": "telegram",
                "payload": {"text": "should be ignored"},
            }
        )
    )

    assert chat_actions == ["typing"]
    assert sent_messages == [
        "📲 *App Chat · App*\n\nhello from app",
        "*App Chat*\n\nassistant reply",
    ]


def test_app_runtime_user_zero_does_not_send_telegram_mirror():
    class DummyBot:
        async def send_message(self, **_kwargs):
            raise AssertionError("desktop app user 0 must not send Telegram messages")

        async def send_chat_action(self, **_kwargs):
            raise AssertionError("desktop app user 0 must not send Telegram chat actions")

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 0
    runtime._app = SimpleNamespace(bot=DummyBot())
    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: "sess-9")

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "user_message",
                "session_id": "sess-9",
                "origin_channel": "app",
                "payload": {
                    "message": {
                        "content": "desktop-only message",
                        "display_label": "App",
                    }
                },
            }
        )
    )


def test_telegram_session_refreshes_same_shared_session_before_mirroring_app_event():
    sent_messages: list[str] = []
    refreshed_session_ids: list[str] = []

    class DummyBot:
        async def send_message(self, *, chat_id: int, text: str, parse_mode=None):
            assert chat_id == 99
            sent_messages.append(text)

        async def send_chat_action(self, *, chat_id: int, action: str):
            assert chat_id == 99

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 99
    runtime._app = SimpleNamespace(bot=DummyBot())
    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: "sess-9")
    runtime.shared_current_session_id = "sess-9"
    runtime.is_processing = False
    runtime.load_session_by_id = lambda session_id: refreshed_session_ids.append(session_id)

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "user_message",
                "session_id": "sess-9",
                "origin_channel": "app",
                "payload": {
                    "message": {
                        "content": "hello from app",
                        "display_label": "App",
                    }
                },
            }
        )
    )

    assert refreshed_session_ids == ["sess-9"]
    assert sent_messages == ["📲 *App Chat · App*\n\nhello from app"]


def test_telegram_session_follows_explicit_current_session_change():
    switched_to: list[str] = []

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 99
    runtime._app = SimpleNamespace(bot=SimpleNamespace())
    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: "sess-old")
    runtime.load_session_by_id = lambda session_id: switched_to.append(session_id)

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "current_session_changed",
                "session_id": "sess-new",
                "origin_channel": "app",
                "payload": {"current_session_id": "sess-new"},
            }
        )
    )

    assert switched_to == ["sess-new"]


def test_telegram_session_follows_app_message_session_before_mirroring():
    sent_messages: list[str] = []
    switched_to: list[str] = []
    current_session_id = "sess-old"

    class DummyBot:
        async def send_message(self, *, chat_id: int, text: str, parse_mode=None):
            assert chat_id == 99
            sent_messages.append(text)

        async def send_chat_action(self, *, chat_id: int, action: str):
            return None

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 99
    runtime._app = SimpleNamespace(bot=DummyBot())

    def load_session_by_id(session_id: str) -> None:
        nonlocal current_session_id
        switched_to.append(session_id)
        current_session_id = session_id

    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: current_session_id)
    runtime.load_session_by_id = load_session_by_id

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "user_message",
                "session_id": "sess-new",
                "origin_channel": "app",
                "payload": {
                    "message": {
                        "content": "hello from desktop",
                        "display_label": "App",
                    }
                },
            }
        )
    )

    assert switched_to == ["sess-new"]
    assert sent_messages == ["📲 *App Chat · App*\n\nhello from desktop"]


def test_telegram_session_mirrors_verbose_tool_events():
    sent_messages: list[str] = []

    class DummyBot:
        async def send_message(self, *, chat_id: int, text: str, parse_mode=None):
            assert chat_id == 99
            sent_messages.append(text)

        async def send_chat_action(self, *, chat_id: int, action: str):
            return None

    runtime = object.__new__(TelegramSession)
    runtime.user_id = 99
    runtime._app = SimpleNamespace(bot=DummyBot())
    runtime.session_manager = SimpleNamespace(get_current_session_id=lambda: "sess-9")
    runtime.verbose_mode = True

    asyncio.run(
        runtime._handle_channel_sync_event(
            {
                "type": "tool_use",
                "session_id": "sess-9",
                "origin_channel": "app",
                "payload": {
                    "tool_name": "describe_screen",
                    "tool_args": {"question": "what changed"},
                    "tool_result": {"description": "Codex is open"},
                    "duration_ms": 128.0,
                },
            }
        )
    )

    assert len(sent_messages) == 1
    assert "Command" in sent_messages[0]
    assert "describe_screen" in sent_messages[0]
    assert "Command Result" in sent_messages[0]
