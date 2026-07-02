import importlib


def test_legacy_agent_orchestration_imports_from_preferred_package_name():
    unified = importlib.import_module("legacy_agent_orchestration.unified_agent")
    dual = importlib.import_module("legacy_agent_orchestration.dual_agent")

    assert callable(unified.UnifiedAgent)
    assert callable(dual.DualAgentCoordinator)


def test_legacy_agent_package_name_is_compatible():
    legacy_unified = importlib.import_module("agent.unified_agent")
    legacy_dual = importlib.import_module("agent.dual_agent")

    assert callable(legacy_unified.UnifiedAgent)
    assert callable(legacy_dual.DualAgentCoordinator)
    assert "legacy_agent_orchestration" in str(legacy_unified.__file__)
