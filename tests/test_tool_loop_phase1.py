from types import SimpleNamespace

from cli.agent_tools.loop import run_tool_loop


class DummyExecutor:
    check_interruption = None

    def execute(self, _name, _args):
        raise AssertionError("Tool execution should not run in this test")


class DummyCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="ready", reasoning_content=None, tool_calls=None)
                )
            ]
        )
        return iter([chunk])


class DummyClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=DummyCompletions())


def test_responses_api_models_do_not_send_reasoning_effort_through_chat_completions():
    client = DummyClient()

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-5.4-2026-03-05",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        variant="high",
        api_type="responses",
    )

    assert result.content == "ready"
    assert "reasoning_effort" not in client.chat.completions.last_kwargs
