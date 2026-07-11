import json
from types import SimpleNamespace

from cli.agent_tools.loop import (
    _drop_prior_ephemeral_runtime_context,
    _max_auto_continues_for_request,
    _quality_guard_objective_from_messages,
    run_tool_loop,
)
from cli.agent_tools.final_quality_guard import FinalQualityVerdict, final_quality_guard_mode, max_auto_continues


class DummyExecutor:
    check_interruption = None

    def execute(self, _name, _args):
        raise AssertionError("Tool execution should not run in this test")


def test_runtime_ephemeral_context_is_replaced_between_model_turns():
    messages = [
        {"role": "system", "content": "Base system prompt"},
        {"role": "user", "content": "Open the file"},
        {"role": "system", "content": "CURRENT TASK CONTRACT (fresh before this model turn):\nold contract"},
        {"role": "system", "content": "LIVE DESKTOP WINDOW SNAPSHOT (fresh before this model turn):\nold snapshot"},
        {"role": "assistant", "content": "working"},
        {"role": "system", "content": "CHAT ARTIFACT INDEX (current chat only):\nold artifacts"},
    ]

    _drop_prior_ephemeral_runtime_context(messages)

    assert messages == [
        {"role": "system", "content": "Base system prompt"},
        {"role": "user", "content": "Open the file"},
        {"role": "assistant", "content": "working"},
    ]


def test_final_quality_guard_reads_live_config_when_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("EMPLOAI_FINAL_QUALITY_GUARD", raising=False)
    monkeypatch.delenv("EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES", raising=False)
    monkeypatch.setenv("DEFAULT_WORKSPACE", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "agent": {
                    "final_quality_guard": "planner",
                    "final_quality_max_auto_continues": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    assert final_quality_guard_mode() == "planner"
    assert max_auto_continues() == 2


def test_coding_tasks_get_higher_auto_continue_budget(monkeypatch):
    monkeypatch.setattr("cli.agent_tools.loop.max_auto_continues", lambda: 2)
    messages = [
        {"role": "user", "content": "Build and run an Electron calculator app"},
        {"role": "assistant", "content": "Node is missing."},
        {"role": "user", "content": "continue"},
    ]

    assert _max_auto_continues_for_request("Build and run an Electron calculator app") >= 5
    assert _max_auto_continues_for_request(_quality_guard_objective_from_messages(messages)) >= 5
    assert _max_auto_continues_for_request("Summarize these notes") == 2


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


class OpenAICodexClient(DummyClient):
    pass


class DummyAnthropicStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, _exc_type, _exc, _tb):
        return False


class DummyAnthropicMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return DummyAnthropicStream(self.responses[index])


class DummyAnthropicClient:
    def __init__(self, responses):
        self.messages = DummyAnthropicMessages(responses)


def _anthropic_text_event(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _anthropic_thinking_start_event():
    return SimpleNamespace(
        type="content_block_start",
        index=0,
        content_block=SimpleNamespace(type="thinking"),
    )


def _anthropic_thinking_delta_event(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="thinking_delta", thinking=text),
    )


def _anthropic_signature_delta_event(signature):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="signature_delta", signature=signature),
    )


def _anthropic_tool_start_event(name, tool_id="toolu_1"):
    return SimpleNamespace(
        type="content_block_start",
        index=0,
        content_block=SimpleNamespace(type="tool_use", id=tool_id, name=name),
    )


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
    assert client.responses.last_kwargs["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in client.responses.last_kwargs


def test_openai_codex_responses_models_receive_reasoning_payload():
    client = DummyClient()

    result = run_tool_loop(
        provider="openai-codex",
        model_id="gpt-5.2-codex",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        variant="xhigh",
        api_type="responses",
    )

    assert result.content == "ready"
    assert client.chat.completions.last_kwargs is None
    assert client.responses.last_kwargs["reasoning"] == {"effort": "xhigh"}
    assert client.responses.last_kwargs["store"] is False


def test_responses_loop_disables_store_for_codex_client_even_with_plain_provider():
    client = OpenAICodexClient()

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-5.4-mini",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        variant="high",
        api_type="responses",
    )

    assert result.content == "ready"
    assert client.responses.last_kwargs["store"] is False


def test_anthropic_receives_joined_system_prompt():
    client = DummyAnthropicClient([[_anthropic_text_event("ready")]])

    result = run_tool_loop(
        provider="anthropic",
        model_id="claude-test",
        client=client,
        messages=[
            {"role": "system", "content": "Base unified prompt"},
            {"role": "system", "content": "Runtime task contract"},
            {"role": "user", "content": "hello"},
        ],
        tool_executor=DummyExecutor(),
        callbacks={},
        custom_system_prompt="Base unified prompt",
    )

    assert result.content == "ready"
    assert client.messages.calls[0]["system"] == "Base unified prompt\n\nRuntime task contract"


def test_anthropic_thinking_variant_sends_payload_and_preserves_thinking_blocks():
    client = DummyAnthropicClient(
        [
            [
                _anthropic_thinking_start_event(),
                _anthropic_thinking_delta_event("Inspecting tool plan."),
                _anthropic_signature_delta_event("sig_123"),
                _anthropic_tool_start_event("screenshot"),
            ],
            [_anthropic_text_event("Recovered.")],
        ]
    )

    result = run_tool_loop(
        provider="anthropic",
        model_id="claude-sonnet-4-5",
        client=client,
        messages=[{"role": "user", "content": "Inspect the screen."}],
        tool_executor=DummyExecutor(),
        callbacks={},
        variant="thinking",
    )

    assert result.content == "Recovered."
    assert client.messages.calls[0]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    second_messages = client.messages.calls[1]["messages"]
    assistant_messages = [
        message
        for message in second_messages
        if message.get("role") == "assistant" and isinstance(message.get("content"), list)
    ]
    assert assistant_messages
    assert assistant_messages[-1]["content"][0] == {
        "type": "thinking",
        "thinking": "Inspecting tool plan.",
        "signature": "sig_123",
    }


def test_undeclared_provider_tool_call_is_blocked_before_executor():
    client = DummyAnthropicClient(
        [
            [_anthropic_tool_start_event("screenshot")],
            [_anthropic_text_event("Recovered.")],
        ]
    )
    tool_events = []

    result = run_tool_loop(
        provider="anthropic",
        model_id="claude-test",
        client=client,
        messages=[{"role": "user", "content": "Inspect the screen."}],
        tool_executor=DummyExecutor(),
        callbacks={"on_tool_use": lambda name, args, output, duration: tool_events.append((name, args, output, duration))},
    )

    assert result.content == "Recovered."
    assert len(client.messages.calls) == 2
    assert tool_events
    assert tool_events[0][0] == "screenshot"
    assert tool_events[0][2]["error_type"] == "invalid_provider_tool_call"

    second_messages = client.messages.calls[1]["messages"]
    tool_result_messages = [
        message
        for message in second_messages
        if message.get("role") == "user"
        and isinstance(message.get("content"), list)
        and any(part.get("type") == "tool_result" for part in message["content"] if isinstance(part, dict))
    ]
    assert tool_result_messages
    assert "invalid_provider_tool_call" in str(tool_result_messages[-1]["content"])


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


def test_planner_final_quality_guard_skips_answer_only_chat(monkeypatch):
    client = DummyClient()
    client.chat.completions.responses = ["Sleep mode closes the desktop UI but keeps Telegram control available."]
    planner_calls = []

    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_enabled", lambda: True)
    monkeypatch.setattr("cli.agent_tools.loop.final_quality_guard_mode", lambda: "planner")
    monkeypatch.setattr("cli.agent_tools.loop.max_auto_continues", lambda: 2)

    def fake_planner(payload):
        planner_calls.append(payload)
        return {
            "action": "retry",
            "reason": "should_not_run_for_chat",
            "continuation_instruction": "Use a tool.",
        }

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-test",
        client=client,
        messages=[{"role": "user", "content": "Can you explain how sleep mode works in one sentence?"}],
        tool_executor=DummyExecutor(),
        callbacks={"judge_final_candidate": fake_planner},
    )

    assert result.content == "Sleep mode closes the desktop UI but keeps Telegram control available."
    assert planner_calls == []
    assert len(client.chat.completions.calls) == 1


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
