import asyncio
import os

from telegram_bot import telegram_commands_utility as utility_module
from telegram_bot.restart_runtime import build_restart_exec_args, exec_current_process
from telegram_bot.telegram_commands_utility import build_utility_command_handlers


def test_build_restart_exec_args_preserves_module_invocation():
    args = build_restart_exec_args(
        executable="/venv/python",
        orig_argv=["python", "-m", "telegram_bot.telegram_agent"],
        argv=["telegram_bot/telegram_agent.py"],
    )

    assert args == ["/venv/python", "-m", "telegram_bot.telegram_agent"]


def test_build_restart_exec_args_uses_fallback_script_path_when_needed():
    script_path = os.path.abspath("C:/repo/telegram_bot/telegram_agent.py")
    args = build_restart_exec_args(
        executable="/venv/python",
        orig_argv=[],
        argv=[],
        script_path_fallback=script_path,
    )

    assert args == ["/venv/python", script_path]


def test_exec_current_process_calls_execve_with_expected_args():
    captured = {}

    def fake_execve(executable, args, env):
        captured["executable"] = executable
        captured["args"] = args
        captured["env"] = env

    exec_current_process(
        executable="/venv/python",
        orig_argv=[],
        argv=[],
        env={"EMPLOAI": "1"},
        execve_func=fake_execve,
        script_path_fallback="telegram_bot/telegram_agent.py",
    )

    assert captured["executable"] == "/venv/python"
    assert captured["args"] == ["/venv/python", os.path.abspath("telegram_bot/telegram_agent.py")]
    assert captured["env"] == {"EMPLOAI": "1"}


def test_restart_command_acknowledges_and_reexecs_process():
    class DummyLock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class DummyStopper:
        def __init__(self):
            self.stopped = 0

        def stop(self):
            self.stopped += 1

    class DummySession:
        def __init__(self):
            self.lock = DummyLock()
            self.should_interrupt = False
            self.is_processing = True
            self.single_agent = DummyStopper()
            self.refined_agent = DummyStopper()
            self.unified_agent = DummyStopper()
            self.heartbeat_manager = DummyStopper()
            self.saved = 0

        def save_session(self):
            self.saved += 1

    class DummySecurityManager:
        def is_user_authorized(self, _user_id):
            return True

    class DummyUser:
        id = 42

    class DummyUpdate:
        effective_user = DummyUser()

    class DummyApplication:
        def __init__(self):
            self.tasks = []

        def create_task(self, coro):
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task

    class DummyContext:
        def __init__(self):
            self.args = []
            self.application = DummyApplication()

    replies = []
    restart_calls = []
    session = DummySession()

    async def safe_reply(_update, text, **_kwargs):
        replies.append(text)

    def get_session(_user_id):
        return session

    def track_command_usage(_session, _command):
        return None

    def rate_limited(_security_manager):
        def decorator(func):
            return func

        return decorator

    def restart_process():
        restart_calls.append("restart")

    handlers = build_utility_command_handlers(
        security_manager=DummySecurityManager(),
        rate_limited=rate_limited,
        get_session=get_session,
        track_command_usage=track_command_usage,
        safe_reply=safe_reply,
        InlineKeyboardHelper=None,
        restart_process=restart_process,
    )
    restart_command = handlers["restart_command"]

    async def fast_sleep(_seconds):
        return None

    async def run_test():
        original_sleep = utility_module.asyncio.sleep
        utility_module.asyncio.sleep = fast_sleep
        try:
            context = DummyContext()
            await restart_command(DummyUpdate(), context)
            await asyncio.gather(*context.application.tasks)
        finally:
            utility_module.asyncio.sleep = original_sleep

    asyncio.run(run_test())

    assert replies == ["♻️ Restarting the bot process now..."]
    assert restart_calls == ["restart"]
    assert session.should_interrupt is True
    assert session.is_processing is False
    assert session.saved == 1
    assert session.single_agent.stopped == 1
    assert session.refined_agent.stopped == 1
    assert session.unified_agent.stopped == 1
    assert session.heartbeat_manager.stopped == 1
