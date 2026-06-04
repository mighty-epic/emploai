from types import SimpleNamespace

from cli.agent_tools.loop import run_tool_loop
from cli.agent_tools.final_quality_guard import FinalQualityVerdict


class DummyExecutor:
    check_interruption = None

    def execute(self, _name, _args):
        raise AssertionError("Tool execution should not run in this test")


class DummyCompletions:
    def __init__(self):
        self.last_kwargs = None
        self.responses = ["ready"]
        self.calls = []

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        captured = dict(kwargs)
        if "messages" in captured:
            captured["messages"] = [dict(message) for message in captured["messages"]]
        self.calls.append(captured)
        text = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=text, reasoning_content=None, tool_calls=None)
                )
            ]
        )
        return iter([chunk])


class DummyResponses:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            output=[],
            output_text="ready",
        )
        return iter(
            [
                SimpleNamespace(type="response.output_text.delta", delta="ready"),
                SimpleNamespace(type="response.completed", response=response),
            ]
        )


class DummyClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=DummyCompletions())
        self.responses = DummyResponses()


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
    assert client.chat.completions.last_kwargs is None
    assert "reasoning_effort" not in client.responses.last_kwargs


def test_final_quality_guard_silently_continues_before_returning(monkeypatch):
    client = DummyClient()
    client.chat.completions.responses = [
        "I could try another safe route if you want.",
        "Done and verified.",
    ]
    events = []
    stream_deltas = []
    stream_markers = []

    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_enabled", lambda: True)
    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_mode", lambda: "nli")
    monkeypatch.setattr("cli.agent_tools.loop.max_auto_continues", lambda: 1)

    def fake_judge(**_kwargs):
        return FinalQualityVerdict(
            action="continue",
            reason="test_incomplete",
            scores={"task_incomplete": 0.99},
            continuation_instruction="Continue hidden.",
        )

    monkeypatch.setattr("cli.agent_tools.loop.judge_final_quality_with_nli", fake_judge)

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-test",
        client=client,
        messages=[{"role": "user", "content": "open the file"}],
        tool_executor=DummyExecutor(),
        callbacks={
            "on_auto_continue": events.append,
            "begin_stream": lambda: stream_markers.append("begin"),
            "append_stream": stream_deltas.append,
            "finish_stream": lambda: stream_markers.append("finish"),
        },
    )

    assert result.content == "Done and verified."
    assert stream_deltas == ["Done and verified."]
    assert stream_markers == ["begin", "finish"]
    assert len(client.chat.completions.calls) == 2
    assert events == [
        {
            "reason": "test_incomplete",
            "action": "continue",
            "scores": {"task_incomplete": 0.99},
            "auto_continue_count": 1,
            "auto_continue_limit": 1,
            "candidate_final_preview": "I could try another safe route if you want.",
        }
    ]
    second_messages = client.chat.completions.calls[1]["messages"]
    assert second_messages[-1] == {"role": "user", "content": "Continue hidden."}


def test_final_quality_guard_uses_planner_callback_and_requires_tool(monkeypatch):
    client = DummyClient()
    client.chat.completions.responses = [
        "The file is not visible yet.",
        "Still no tool.",
        "Done and verified.",
    ]
    events = []
    stream_deltas = []
    planner_calls = []

    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_enabled", lambda: True)
    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_mode", lambda: "planner")
    monkeypatch.setattr("cli.agent_tools.loop.max_auto_continues", lambda: 2)

    def fake_planner(payload):
        planner_calls.append(payload)
        return {
            "action": "retry",
            "reason": "file_visible_missing",
            "continuation_instruction": "Use a tool to open and verify the file.",
        }

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-test",
        client=client,
        messages=[{"role": "user", "content": "open the file"}],
        tool_executor=DummyExecutor(),
        callbacks={
            "judge_final_candidate": fake_planner,
            "on_auto_continue": events.append,
            "append_stream": stream_deltas.append,
        },
    )

    assert result.content == "Done and verified."
    assert stream_deltas == ["Done and verified."]
    assert len(client.chat.completions.calls) == 3
    assert len(planner_calls) == 1
    assert events[0]["reason"] == "file_visible_missing"
    assert events[1]["reason"] == "retry_requires_tool"
    second_messages = client.chat.completions.calls[1]["messages"]
    assert second_messages[-1] == {"role": "user", "content": "Use a tool to open and verify the file."}
    third_messages = client.chat.completions.calls[2]["messages"]
    assert "Call an appropriate tool now" in third_messages[-1]["content"]
