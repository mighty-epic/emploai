from types import SimpleNamespace

import cli.agent_tools.loop as loop_module
from cli.agent_tools.adapters import (
    build_tools_for_provider,
    get_tool_names,
    get_tools_for_provider,
    validate_provider_tool_names,
)
from cli.agent_tools.definitions import CLI_AGENT_TOOLS
from cli.agent_tools.executor import ToolExecutor
from cli.agent_tools.loop import run_tool_loop
from shared.openai_api import create_openai_completion
from shared.unified_agent import UnifiedToolRegistry
from shared.tool_packs import filter_tools_by_enabled_packs
from single_agent.extension_tool import create_extension_tool


ANTHROPIC_NATIVE_EDITOR = {
    "type": "text_editor_20250728",
    "name": "str_replace_based_edit_tool",
}

EXTRA_OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "desktop_status_probe",
        "description": "Probe desktop status.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_windows": {
                    "type": "boolean",
                    "description": "Whether to include window titles.",
                    "default": True,
                }
            },
        },
    },
}


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


class DummyResponses:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        response = SimpleNamespace(
            output=[],
            output_text="ready",
            usage=SimpleNamespace(input_tokens=12, output_tokens=3),
        )
        return iter(
            [
                SimpleNamespace(type="response.output_text.delta", delta="ready"),
                SimpleNamespace(type="response.completed", response=response),
            ]
        )


class DummyResponsesClient:
    def __init__(self):
        self.responses = DummyResponses()
        self.chat = SimpleNamespace(completions=DummyCompletions())


class DummyResponseOnce:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            output=[],
            output_text="ready",
            usage=SimpleNamespace(input_tokens=12, output_tokens=3),
        )


class DummyResponseOnceClient:
    def __init__(self):
        self.responses = DummyResponseOnce()
        self.chat = SimpleNamespace(completions=DummyCompletions())


def _openai_tool_names(tools):
    return [tool["function"]["name"] for tool in tools]


def test_openai_compatible_models_get_openai_tools_only():
    for provider in ["openai", "xai", "deepseek", "openrouter"]:
        tools = build_tools_for_provider(provider, [ANTHROPIC_NATIVE_EDITOR, EXTRA_OPENAI_TOOL])
        names = _openai_tool_names(tools)

        assert "str_replace_based_edit_tool" not in names
        assert "read_file" in names
        assert "write_file" in names
        assert "edit_file" in names
        assert "append_file" in names
        assert "desktop_status_probe" in names
        assert all(tool.get("type") == "function" and "function" in tool for tool in tools)


def test_anthropic_models_get_native_editor_and_not_duplicate_file_edit_tools():
    tools = build_tools_for_provider("anthropic", [ANTHROPIC_NATIVE_EDITOR, EXTRA_OPENAI_TOOL])
    names = get_tool_names(tools)

    assert "str_replace_based_edit_tool" not in names
    assert "read_file" in names
    assert "write_file" in names
    assert "edit_file" in names
    assert "append_file" in names
    assert "desktop_status_probe" in names


def test_google_models_get_google_tool_objects_and_sanitized_names():
    tools = build_tools_for_provider("google", [ANTHROPIC_NATIVE_EDITOR, EXTRA_OPENAI_TOOL])
    names = get_tool_names(tools)

    assert tools
    assert "str_replace_based_edit_tool" not in names
    assert "read_file" in names
    assert "write_file" in names
    assert "edit_file" in names
    assert "append_file" in names
    assert "desktop_status_probe" in names
    assert not any(isinstance(tool, dict) and tool.get("type") == "function" for tool in tools)


def test_run_tool_loop_sends_openai_compatible_tool_set_for_openai_model():
    client = DummyClient()

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-test",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        extra_tools=[ANTHROPIC_NATIVE_EDITOR, EXTRA_OPENAI_TOOL],
    )

    sent_tools = client.chat.completions.last_kwargs["tools"]
    names = _openai_tool_names(sent_tools)
    assert result.content == "ready"
    assert "str_replace_based_edit_tool" not in names
    assert "write_file" in names
    assert "edit_file" in names
    assert "desktop_status_probe" in names


def test_run_tool_loop_uses_responses_api_for_responses_models():
    client = DummyResponsesClient()

    result = run_tool_loop(
        provider="openai",
        model_id="gpt-5.4-mini",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        extra_tools=[EXTRA_OPENAI_TOOL],
        api_type="responses",
    )

    sent_tools = client.responses.last_kwargs["tools"]
    assert result.content == "ready"
    assert client.responses.last_kwargs["stream"] is True
    assert all(tool.get("type") == "function" and "name" in tool for tool in sent_tools)
    assert any(tool.get("name") == "desktop_status_probe" for tool in sent_tools)


def test_run_tool_loop_uses_sidecar_summary_instead_of_reinjecting_raw_image(monkeypatch):
    monkeypatch.setattr(
        loop_module,
        "_analyze_image_sidecar",
        lambda **_kwargs: "Visible state: Notepad is open and the requested file content is visible.",
    )

    class StreamingCompletionsWithTool:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                tool_delta = SimpleNamespace(
                    index=0,
                    id="call-1",
                    function=SimpleNamespace(
                        name="describe_screen",
                        arguments='{"question":"Did the requested file open in Notepad?"}',
                    ),
                )
                chunk = SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[tool_delta]))]
                )
                return iter([chunk])

            final_chunk = SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Verified.", reasoning_content=None, tool_calls=None))]
            )
            usage_chunk = SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
            )
            return iter([final_chunk, usage_chunk])

    class StreamingClientWithTool:
        def __init__(self):
            self.chat = SimpleNamespace(completions=StreamingCompletionsWithTool())

    class ExecutorWithScreenTool:
        check_interruption = None

        def execute(self, name, args):
            assert name == "describe_screen"
            assert "requested file open" in str(args.get("question", "")).lower()
            return {
                "image_captured": True,
                "image_base64": "ZmFrZV9pbWFnZQ==",
                "description": "Screenshot captured successfully. Looking at the screen now.",
                "question": args.get("question"),
            }

    client = StreamingClientWithTool()
    result = run_tool_loop(
        provider="openai",
        model_id="gpt-test",
        client=client,
        messages=[{"role": "user", "content": "Open the file in Notepad and verify it."}],
        tool_executor=ExecutorWithScreenTool(),
        callbacks={},
    )

    assert result.content == "Verified."
    assert len(client.chat.completions.calls) == 2
    second_messages = client.chat.completions.calls[1]["messages"]
    assert not any(
        isinstance(message.get("content"), list)
        and any(isinstance(part, dict) and part.get("type") == "image_url" for part in message["content"])
        for message in second_messages
        if isinstance(message, dict)
    )
    tool_messages = [message for message in second_messages if message.get("role") == "tool"]
    assert tool_messages
    assert "vision_summary" in str(tool_messages[-1]["content"])
    assert "Notepad is open" in str(tool_messages[-1]["content"])


def test_create_openai_completion_uses_responses_api_for_responses_models():
    client = DummyResponseOnceClient()

    response = create_openai_completion(
        client,
        model_name="gpt-5.4-mini",
        model_id="gpt-5.4-mini",
        messages=[{"role": "user", "content": "hello"}],
        tools=[EXTRA_OPENAI_TOOL],
        tool_choice="auto",
        max_tokens=50,
    )

    sent_tools = client.responses.last_kwargs["tools"]
    assert response.choices[0].message.content == "ready"
    assert client.responses.last_kwargs["max_output_tokens"] == 50
    assert all(tool.get("type") == "function" and "name" in tool for tool in sent_tools)
    assert any(tool.get("name") == "desktop_status_probe" for tool in sent_tools)


def test_build_tools_for_provider_respects_filtered_base_tool_set():
    filtered_base_tools = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, ["workspace_read"])

    tools = build_tools_for_provider(
        "openai",
        [EXTRA_OPENAI_TOOL],
        base_tools=filtered_base_tools,
    )
    names = _openai_tool_names(tools)

    assert "read_file" in names
    assert "list_dir" in names
    assert "find_files" in names
    assert "write_file" not in names
    assert "append_file" not in names
    assert "run_command" not in names
    assert "desktop_status_probe" in names


def test_open_file_is_interactive_desktop_only():
    workspace_tools = build_tools_for_provider(
        "openai",
        [],
        base_tools=filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, ["workspace_read"]),
    )
    desktop_tools = build_tools_for_provider(
        "openai",
        [],
        base_tools=filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, ["interactive_desktop"]),
    )

    assert "open_file" not in _openai_tool_names(workspace_tools)
    assert "open_file" in _openai_tool_names(desktop_tools)


def test_tool_executor_blocks_disabled_tool_when_allowed_tool_policy_is_set(tmp_path):
    executor = ToolExecutor(tmp_path)
    executor.allowed_tool_names_provider = lambda: {"read_file"}

    result = executor.execute("write_file", {"path": "hello.py", "content": 'print("hi")'})

    assert result["error_type"] == "policy"


def test_tool_executor_open_file_reports_missing_path_without_launching(tmp_path):
    executor = ToolExecutor(tmp_path)

    result = executor.execute("open_file", {"path": "missing.txt"})

    assert result["error_type"] == "not_found"
    assert "missing.txt" in result["path"]
    assert "Not a file" in result["error"]


def test_tool_executor_blocks_redundant_prompt_context_file_reads(tmp_path):
    executor = ToolExecutor(tmp_path)

    result = executor.execute("read_file", {"path": "AGENTS.md"})

    assert result["error_type"] == "redundant_context_lookup"
    assert "already injected into the runtime prompt context" in result["error"]


def test_tool_executor_blocks_redundant_prompt_context_file_searches(tmp_path):
    executor = ToolExecutor(tmp_path)

    result = executor.execute("find_files", {"pattern": "MEMORY.md"})

    assert result["error_type"] == "redundant_context_lookup"
    assert "already injected into the runtime prompt context" in result["error"]


def test_base_provider_tool_lists_match_provider_contracts():
    openai_names = _openai_tool_names(get_tools_for_provider("openai"))
    anthropic_names = get_tool_names(get_tools_for_provider("anthropic"))

    assert "str_replace_based_edit_tool" not in openai_names
    assert "write_file" in openai_names
    assert "edit_file" in openai_names
    assert "str_replace_based_edit_tool" not in anthropic_names
    assert "write_file" in anthropic_names
    assert "edit_file" in anthropic_names


def test_legacy_unified_registry_uses_provider_specific_formats():
    registry = UnifiedToolRegistry()

    openai_tools = registry.get_tools_for_provider("openai")
    anthropic_tools = registry.get_tools_for_provider("anthropic")
    google_tools = registry.get_tools_for_provider("google")

    assert all(tool.get("type") == "function" and "function" in tool for tool in openai_tools)
    assert not any("function" in tool for tool in anthropic_tools)
    assert google_tools
    assert not any(isinstance(tool, dict) and tool.get("type") == "function" for tool in google_tools)


def test_validate_provider_tool_names_flags_ghost_tools():
    provider_tools = [
        {
            "name": "read_file",
            "description": "Read a file.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "ghost_tool",
            "description": "Should not be here.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]

    error = validate_provider_tool_names(provider_tools, allowed_names={"read_file", "write_file"})

    assert error is not None
    assert "ghost_tool" in error


def test_extension_tool_factory_reuses_singleton_for_same_host_and_port():
    first = create_extension_tool()
    second = create_extension_tool()
    other_port = create_extension_tool(port=9001)

    assert first is second
    assert other_port is not first


def test_extension_tool_start_is_suppressed_during_port_conflict_cooldown():
    tool = create_extension_tool(port=9002)
    tool.shutdown_server()
    tool.is_running = False
    tool.server_thread = None
    tool._port_conflict_until = 10**12

    tool.start_server()

    assert tool.server_thread is None
