import asyncio
from types import SimpleNamespace

from mobile_app.backend import cron_runtime
from telegram_bot import cron_runner


class DummyToolExecutor:
    def __init__(self):
        self.custom_tool_handlers = None


class DummyMemoryManager:
    def __init__(self):
        self.prompt_kwargs = None
        self.daily_log_calls = []

    def build_prompt_context(self, **kwargs):
        self.prompt_kwargs = kwargs
        return "PROMPT_MEMORY"

    def append_to_daily_log(self, content, source, session_id=None):
        self.daily_log_calls.append((content, source, session_id))


class DummySession:
    def __init__(self):
        self.tool_executor = DummyToolExecutor()
        self.skill_registry = None
        self.active_skills = []
        self.memory_manager = DummyMemoryManager()
        self.current_model = "gpt-5.4"
        self.current_variant = "standard"
        self.chat_history = []
        self.session_manager = SimpleNamespace(
            get_current_session_id=lambda: "session-42",
            current_session=SimpleNamespace(id="session-42"),
        )

    def get_client_for_model(self):
        return object(), "openai"

    def save_session(self):
        return None


def test_run_cron_job_uses_shared_memory_prompt_context(monkeypatch):
    session = DummySession()
    captured = {}

    class DummyLoopResult:
        def __init__(self, content):
            self.content = content

    monkeypatch.setattr(cron_runner, "get_auto_mode_tool_handlers", lambda _session: {"x": "y"})
    monkeypatch.setattr(cron_runner, "_get_provider_tools", lambda _provider: [])
    monkeypatch.setattr(
        cron_runner,
        "build_unified_system_prompt",
        lambda _session, **kwargs: captured.setdefault("prompt_kwargs", kwargs) or "SYSTEM_PROMPT",
    )
    monkeypatch.setattr(
        cron_runner,
        "run_tool_loop",
        lambda **kwargs: DummyLoopResult("cron complete"),
    )

    result = asyncio.run(cron_runner.run_cron_job_via_unified_flow(session, "Check status"))

    assert result == "cron complete"
    assert session.tool_executor.custom_tool_handlers == {"x": "y"}
    assert session.memory_manager.prompt_kwargs == {
        "session_id": "session-42",
        "recent_days": 7,
        "recent_chars": 3000,
        "long_term_chars": 4000,
    }
    assert captured["prompt_kwargs"]["memory_context"] == "PROMPT_MEMORY"
    assert session.chat_history[-1]["scheduled_job"] is True
    assert session.memory_manager.daily_log_calls[-1][1] == "cron"


def test_cron_spawn_callback_runs_against_owner_session(monkeypatch):
    owner_session = SimpleNamespace(chat_history=[], save_session=lambda: None)
    calls = []

    class FakeScheduler:
        @staticmethod
        def get_job(job_id):
            assert job_id == "job-1"
            return SimpleNamespace(owner_user_id=77, name="Nightly Check")

    async def fake_run(session, prompt, scheduled_job_id=None):
        calls.append((session, prompt, scheduled_job_id))
        return "owner result"

    def fake_get_session(user_id=0):
        calls.append(("get_session", user_id))
        assert user_id == 77
        return owner_session

    monkeypatch.setattr(cron_runtime, "get_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(cron_runtime, "get_cron_runtime_session", fake_get_session)
    monkeypatch.setattr(cron_runtime, "run_cron_job_via_unified_flow", fake_run)

    asyncio.run(cron_runtime.cron_spawn_callback("job-1", "Run the nightly check"))

    assert calls[0] == ("get_session", 77)
    assert calls[1] == (owner_session, "Run the nightly check", "job-1")
    assert owner_session.chat_history[0]["content"] == "Scheduled job running: Nightly Check"
    assert owner_session.chat_history[1]["content"] == "owner result"
    assert all(item["scheduled_job_id"] == "job-1" for item in owner_session.chat_history)
