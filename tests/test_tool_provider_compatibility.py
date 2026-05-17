from types import SimpleNamespace

from cli.agent_tools.adapters import build_tools_for_provider, get_tool_names, get_tools_for_provider
from cli.agent_tools.loop import run_tool_loop
from shared.unified_agent import UnifiedToolRegistry


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

    assert names.count("str_replace_based_edit_tool") == 1
    assert "read_file" not in names
    assert "write_file" not in names
    assert "edit_file" not in names
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


def test_base_provider_tool_lists_match_provider_contracts():
    openai_names = _openai_tool_names(get_tools_for_provider("openai"))
    anthropic_names = get_tool_names(get_tools_for_provider("anthropic"))

    assert "str_replace_based_edit_tool" not in openai_names
    assert "write_file" in openai_names
    assert "edit_file" in openai_names
    assert "str_replace_based_edit_tool" in anthropic_names
    assert "write_file" not in anthropic_names
    assert "edit_file" not in anthropic_names


def test_legacy_unified_registry_uses_provider_specific_formats():
    registry = UnifiedToolRegistry()

    openai_tools = registry.get_tools_for_provider("openai")
    anthropic_tools = registry.get_tools_for_provider("anthropic")
    google_tools = registry.get_tools_for_provider("google")

    assert all(tool.get("type") == "function" and "function" in tool for tool in openai_tools)
    assert not any("function" in tool for tool in anthropic_tools)
    assert google_tools
    assert not any(isinstance(tool, dict) and tool.get("type") == "function" for tool in google_tools)
