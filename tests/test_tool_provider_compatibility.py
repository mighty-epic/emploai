import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import cli.agent_tools.loop as loop_module
from cli.agent_tools.adapters import (
    build_tools_for_provider,
    get_tool_names,
    get_tools_for_provider,
    validate_provider_tool_names,
)
from cli.agent_tools.definitions import CLI_AGENT_TOOLS
import cli.agent_tools.executor as executor_module
from cli.agent_tools.executor import ToolExecutor
from cli.agent_tools.loop import run_tool_loop
from shared.openai_api import create_openai_completion
from shared.unified_agent import UnifiedToolRegistry
from shared.tool_packs import filter_tools_by_enabled_packs, tools_for_enabled_packs
from local_agent_runtime.extension_tool import create_extension_tool
from local_agent_runtime.tool_manifest import AGENT_TOOLS


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


class DummyGoogleCompletionsWithTool:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            tool_delta = SimpleNamespace(
                index=0,
                id="gemini-call-1",
                function=SimpleNamespace(
                    name="read_file",
                    arguments='{"path":"README.md"}',
                ),
            )
            chunk = SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[tool_delta])
                    )
                ]
            )
            return iter([chunk])

        final_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Gemini used the tool.", reasoning_content=None, tool_calls=None)
                )
            ]
        )
        return iter([final_chunk])


class DummyGoogleOpenAIClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=DummyGoogleCompletionsWithTool())


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


class OpenAICodexClient:
    def __init__(self):
        self.responses = DummyResponseOnce()
        self.chat = SimpleNamespace(completions=DummyCompletions())


def _openai_tool_names(tools):
    return [tool["function"]["name"] for tool in tools]


def test_openai_compatible_models_get_openai_tools_only():
    for provider in ["openai", "xai", "deepseek", "openrouter", "nvidia"]:
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


def test_run_tool_loop_sends_nvidia_tools_without_openai_stream_options():
    client = DummyClient()

    result = run_tool_loop(
        provider="nvidia",
        model_id="mistralai/ministral-14b-instruct-2512",
        client=client,
        messages=[{"role": "user", "content": "hello"}],
        tool_executor=DummyExecutor(),
        callbacks={},
        extra_tools=[ANTHROPIC_NATIVE_EDITOR, EXTRA_OPENAI_TOOL],
    )

    sent_kwargs = client.chat.completions.last_kwargs
    names = _openai_tool_names(sent_kwargs["tools"])
    assert result.content == "ready"
    assert sent_kwargs["model"] == "mistralai/ministral-14b-instruct-2512"
    assert sent_kwargs["stream"] is True
    assert sent_kwargs["tool_choice"] == "auto"
    assert "stream_options" not in sent_kwargs
    assert "str_replace_based_edit_tool" not in names
    assert "write_file" in names
    assert "edit_file" in names
    assert "desktop_status_probe" in names


def test_run_tool_loop_forces_explicitly_named_nvidia_tool():
    client = DummyClient()

    result = run_tool_loop(
        provider="nvidia",
        model_id="mistralai/ministral-14b-instruct-2512",
        client=client,
        messages=[{"role": "user", "content": "Use the describe screen tool and the write file tool."}],
        tool_executor=DummyExecutor(),
        callbacks={},
        extra_tools=AGENT_TOOLS,
    )

    sent_kwargs = client.chat.completions.last_kwargs
    assert result.content == "ready"
    assert sent_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "describe_screen"},
    }


def test_run_tool_loop_uses_openai_compatible_transport_for_gemini_tools():
    class ExecutorWithReadFile:
        check_interruption = None

        def execute(self, name, args):
            assert name == "read_file"
            assert args == {"path": "README.md"}
            return {"content": "hello from README", "path": args["path"]}

    client = DummyGoogleOpenAIClient()

    result = run_tool_loop(
        provider="google",
        model_id="gemini-3.5-flash",
        client=client,
        messages=[{"role": "user", "content": "Read README.md and summarize it."}],
        tool_executor=ExecutorWithReadFile(),
        callbacks={},
    )

    first_call = client.chat.completions.calls[0]
    second_call = client.chat.completions.calls[1]
    assert result.content == "Gemini used the tool."
    assert "stream_options" not in first_call
    assert all(tool.get("type") == "function" and "function" in tool for tool in first_call["tools"])
    assert "read_file" in _openai_tool_names(first_call["tools"])
    assert any(message.get("role") == "tool" and message.get("tool_call_id") == "gemini-call-1" for message in second_call["messages"])


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
        extra_tools=AGENT_TOOLS,
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


def test_run_tool_loop_auto_continues_empty_post_tool_final():
    class EmptyThenFinalCompletions:
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
                        arguments='{"question":"What is visible on screen?"}',
                    ),
                )
                return iter([
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[tool_delta]))]
                    )
                ])
            if len(self.calls) == 2:
                return iter([
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=None))]
                    )
                ])
            return iter([
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="I can see the desktop app.", reasoning_content=None, tool_calls=None))]
                )
            ])

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=EmptyThenFinalCompletions())

    class Executor:
        check_interruption = None

        def execute(self, name, args):
            assert name == "describe_screen"
            return {
                "image_captured": True,
                "description": "The desktop app is visible with a chat open.",
                "question": args.get("question"),
            }

    client = Client()
    result = run_tool_loop(
        provider="nvidia",
        model_id="nvidia-test",
        client=client,
        messages=[{"role": "user", "content": "what do you see?"}],
        tool_executor=Executor(),
        callbacks={},
        extra_tools=AGENT_TOOLS,
    )

    assert result.content == "I can see the desktop app."
    assert len(client.chat.completions.calls) == 3
    retry_messages = client.chat.completions.calls[2]["messages"]
    assert any(
        "previous turn ended with no user-visible assistant reply after tool use" in str(message.get("content") or "")
        for message in retry_messages
        if isinstance(message, dict)
    )
    assert not any(
        message.get("role") == "assistant" and message.get("content") is None and not message.get("tool_calls")
        for message in retry_messages
    )


def test_run_tool_loop_falls_back_if_empty_post_tool_retry_stays_empty():
    class AlwaysEmptyAfterToolCompletions:
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
                        arguments='{"question":"What is visible on screen?"}',
                    ),
                )
                return iter([
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[tool_delta]))]
                    )
                ])
            return iter([
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=None))]
                )
            ])

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=AlwaysEmptyAfterToolCompletions())

    class Executor:
        check_interruption = None

        def execute(self, name, _args):
            assert name == "describe_screen"
            return {
                "image_captured": True,
                "description": "Visible state: the EmploAI chat is open.",
            }

    result = run_tool_loop(
        provider="nvidia",
        model_id="nvidia-test",
        client=Client(),
        messages=[{"role": "user", "content": "what do you see?"}],
        tool_executor=Executor(),
        callbacks={},
        extra_tools=AGENT_TOOLS,
    )

    assert result.content.startswith("I looked at the screen.")
    assert "EmploAI chat is open" in result.content


def test_process_control_guard_blocks_broad_process_name_cleanup(tmp_path):
    executor = ToolExecutor(workspace_path=tmp_path)

    taskkill_error = executor._unsafe_process_scope_error("taskkill /IM electron.exe /F")
    assert taskkill_error is not None
    assert taskkill_error["error_type"] == "unsafe_process_scope"
    assert "kill_command" in taskkill_error["error"]

    powershell_error = executor._unsafe_process_scope_error("Get-Process electron | Stop-Process -Force")
    assert powershell_error is not None
    assert powershell_error["error_type"] == "unsafe_process_scope"

    assert executor._unsafe_process_scope_error("taskkill /PID 12345 /T /F") is None
    assert executor._unsafe_process_scope_error("Stop-Process -Id 12345 -Force") is None


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
    assert "store" not in client.responses.last_kwargs
    assert all(tool.get("type") == "function" and "name" in tool for tool in sent_tools)
    assert any(tool.get("name") == "desktop_status_probe" for tool in sent_tools)


def test_create_openai_completion_disables_store_for_chatgpt_models():
    client = DummyResponseOnceClient()

    response = create_openai_completion(
        client,
        model_name="chatgpt/gpt-5.4-mini",
        model_id="gpt-5.4-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=50,
    )

    assert response.choices[0].message.content == "ready"
    assert client.responses.last_kwargs["store"] is False


def test_create_openai_completion_disables_store_for_codex_client_even_with_plain_model_name():
    client = OpenAICodexClient()

    response = create_openai_completion(
        client,
        model_name="gpt-5.4-mini",
        model_id="gpt-5.4-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=50,
    )

    assert response.choices[0].message.content == "ready"
    assert client.responses.last_kwargs["store"] is False


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


def test_default_tool_packs_expose_canonical_tool_names_without_legacy_aliases():
    names = tools_for_enabled_packs(
        ["interactive_desktop", "browser_isolated", "workspace_write", "workspace_read"]
    )

    assert "browser_navigate" in names
    assert "browser_snapshot" in names
    assert "run_command" in names
    assert "run_background_command" in names
    assert "list_dir" in names
    assert "find_files" in names

    assert "open_app" not in names
    assert "open_browser" not in names
    assert "observe_browser" not in names
    assert "switch_tab" not in names
    assert "close_tab" not in names
    assert "go_back" not in names
    assert "go_forward" not in names
    assert "execute_command" not in names
    assert "change_directory" not in names
    assert "list_files" not in names
    assert "find_file" not in names


def test_run_command_tools_include_shell_parameter():
    by_name = {tool["name"]: tool for tool in CLI_AGENT_TOOLS}

    assert "change_directory" not in by_name
    for name in ["run_command", "run_background_command"]:
        properties = by_name[name]["parameters"]["properties"]
        shell_schema = properties["shell"]
        visible_terminal_schema = properties["visible_terminal"]
        assert shell_schema["enum"] == ["auto", "cmd", "powershell", "pwsh", "bash"]
        assert visible_terminal_schema["type"] == "boolean"
        assert visible_terminal_schema["default"] is False


def test_command_creationflags_default_to_hidden_on_windows(tmp_path):
    executor = ToolExecutor(tmp_path)

    hidden_flags = executor._command_creationflags(visible_terminal=False)
    visible_flags = executor._command_creationflags(visible_terminal=True)

    if os.name == "nt":
        assert hidden_flags == subprocess.CREATE_NO_WINDOW
        assert visible_flags == subprocess.CREATE_NEW_CONSOLE
    else:
        assert hidden_flags == 0
        assert visible_flags == 0


def test_visible_background_command_input_reports_visible_terminal_boundary(tmp_path):
    class DummyProcess:
        returncode = None

        def poll(self):
            return None

    executor = ToolExecutor(tmp_path)
    executor._background_commands["abc123"] = {
        "process": DummyProcess(),
        "command": "npm run dev",
        "visible_terminal": True,
    }

    result = executor.tool_send_input("abc123", "q")

    assert result["error_type"] == "visible_terminal_input"
    assert "visible terminal" in result["error"]


def test_visible_background_command_records_visible_terminal_metadata(monkeypatch, tmp_path):
    class DummyProcess:
        pid = 12345
        stdout = None

        def poll(self):
            return None

    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append({"args": args, "kwargs": kwargs})
        return DummyProcess()

    executor = ToolExecutor(tmp_path)
    monkeypatch.setattr(executor_module.os, "name", "nt")
    monkeypatch.setattr(executor_module.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    monkeypatch.setattr(executor_module.subprocess, "Popen", fake_popen)

    result = executor.tool_run_background_command("echo hi", visible_terminal=True)

    assert result["visible_terminal"] is True
    assert result["output_capture"] == "visible_terminal"
    assert result["message"].endswith("check process state.")
    assert result["command_id"] in executor._background_commands
    assert executor._background_commands[result["command_id"]]["visible_terminal"] is True
    assert popen_calls[-1]["kwargs"]["creationflags"] == 16
    assert "stdout" not in popen_calls[-1]["kwargs"]
    assert "stdin" not in popen_calls[-1]["kwargs"]


def test_kill_all_background_commands_terminates_running_entries(tmp_path, monkeypatch):
    executor = ToolExecutor(tmp_path)
    terminated = []

    class FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return self.returncode

    process = FakeProcess()
    executor._background_commands["cmd-1"] = {
        "process": process,
        "command": "long-running",
        "output_lines": [],
        "visible_terminal": True,
    }

    def fake_terminate(proc):
        terminated.append(proc.pid)
        proc.returncode = -9

    monkeypatch.setattr(executor, "_terminate_process_tree", fake_terminate)

    result = executor.kill_all_background_commands()

    assert terminated == [12345]
    assert result["killed_count"] == 1
    assert result["killed"][0]["command_id"] == "cmd-1"
    assert result["killed"][0]["exit_code"] == -9


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell required")
def test_run_command_executes_powershell_syntax(tmp_path):
    executor = ToolExecutor(tmp_path)

    result = executor.execute("run_command", {"command": "Get-Location", "shell": "powershell"})

    assert result["exit_code"] == 0
    assert result["shell"] == "powershell"
    assert str(tmp_path) in result["stdout"]


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
