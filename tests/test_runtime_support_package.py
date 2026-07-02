import importlib


def test_runtime_support_imports_from_preferred_package_name():
    ui_helpers = importlib.import_module("runtime_support.ui_helpers")
    hooks = importlib.import_module("runtime_support.hooks")

    assert callable(ui_helpers.ThinkingModeVisualizer.extract_thinking_content)
    assert hooks.HookType.MESSAGE_RECEIVED.value == "message_received"


def test_legacy_bot_core_import_path_is_compatible():
    legacy_ui = importlib.import_module("bot_core.ui_helpers")
    legacy_hooks = importlib.import_module("bot_core.hooks")

    assert callable(legacy_ui.ThinkingModeVisualizer.extract_thinking_content)
    assert legacy_hooks.HookType.MESSAGE_RECEIVED.value == "message_received"
    assert "runtime_support" in str(legacy_ui.__file__)
