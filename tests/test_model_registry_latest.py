from pathlib import Path

from cli.tui_constants import MODEL_CONFIGS, MODEL_VARIANTS
from shared.unified_agent import create_unified_agent


def test_gpt_5_4_is_available_in_primary_model_registry():
    assert MODEL_CONFIGS["gpt-5.4"]["provider"] == "openai"
    assert MODEL_CONFIGS["gpt-5.4"]["id"] == "gpt-5.4-2026-03-05"
    assert MODEL_VARIANTS["gpt-5.4"]["variants"] == ["low", "medium", "high", "xhigh"]


def test_shared_unified_agent_maps_gpt_5_4_to_openai_snapshot():
    agent = create_unified_agent(
        model_name="gpt-5.4",
        client=object(),
        tool_executor=lambda _name, _args: None,
        workspace=Path.cwd(),
        logger_func=lambda _text: None,
        system_prompt="test",
    )

    assert agent.model_config.name == "gpt-5.4"
    assert agent.model_config.provider == "openai"
    assert agent.model_config.model_id == "gpt-5.4-2026-03-05"
