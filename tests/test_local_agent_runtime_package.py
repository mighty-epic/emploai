import importlib


def test_local_agent_runtime_imports_from_preferred_package_name():
    agent_module = importlib.import_module("local_agent_runtime.agent")
    tool_manifest = importlib.import_module("local_agent_runtime.tool_manifest")

    assert callable(agent_module.SingleAgent)
    assert isinstance(tool_manifest.AGENT_TOOLS, list)


def test_legacy_single_agent_import_path_is_compatible():
    legacy_agent = importlib.import_module("single_agent.agent")
    legacy_tools = importlib.import_module("single_agent.tool_manifest")

    assert callable(legacy_agent.SingleAgent)
    assert isinstance(legacy_tools.AGENT_TOOLS, list)
    assert "local_agent_runtime" in str(legacy_agent.__file__)
