from pathlib import Path

from cli.tui_constants import (
    MODEL_CONFIGS,
    MODEL_VARIANTS,
    NVIDIA_EXCLUDED_MODEL_IDS,
    NVIDIA_MODEL_IDS,
    is_supported_nvidia_chat_or_code_model_id,
)
from shared.unified_agent import create_unified_agent
from shared.model_defaults import default_model_pair_for_enabled_providers


def test_gpt_5_4_is_available_in_primary_model_registry():
    assert MODEL_CONFIGS["gpt-5.4"]["provider"] == "openai"
    assert MODEL_CONFIGS["gpt-5.4"]["id"] == "gpt-5.4-2026-03-05"
    assert MODEL_CONFIGS["gpt-5.4"]["api"] == "responses"
    assert MODEL_VARIANTS["gpt-5.4"]["variants"] == ["standard"]


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
    assert agent.model_config.api_type == "responses"


def test_codex_subscription_models_use_separate_provider():
    assert MODEL_CONFIGS["gpt-5.5"]["provider"] == "openai"
    assert MODEL_CONFIGS["chatgpt/gpt-5.5"]["provider"] == "openai-codex"
    assert MODEL_CONFIGS["chatgpt/gpt-5.5"]["id"] == "gpt-5.5"
    assert MODEL_CONFIGS["chatgpt/gpt-5.4"]["provider"] == "openai-codex"
    assert MODEL_CONFIGS["chatgpt/gpt-5.4-mini"]["provider"] == "openai-codex"

    defaults = default_model_pair_for_enabled_providers({"openai-codex"})
    assert defaults.model == "chatgpt/gpt-5.5"
    assert defaults.planner_model == "chatgpt/gpt-5.4-mini"

    agent = create_unified_agent(
        model_name="chatgpt/gpt-5.5",
        client=object(),
        tool_executor=lambda _name, _args: None,
        workspace=Path.cwd(),
        logger_func=lambda _text: None,
        system_prompt="test",
    )

    assert agent.model_config.provider == "openai-codex"
    assert agent.model_config.model_id == "gpt-5.5"
    assert agent.model_config.api_type == "responses"


def test_current_gemini_models_are_registered_without_shutdown_ids():
    expected = {
        "gemini-3.5-flash",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    }

    for model in expected:
        assert MODEL_CONFIGS[model]["provider"] == "google"
        assert MODEL_VARIANTS[model]["variants"][0] == "standard"

    assert "gemini-2.0-flash" not in MODEL_CONFIGS
    assert "gemini-1.5-pro" not in MODEL_CONFIGS
    assert "gemini-3-pro" not in MODEL_CONFIGS


def test_gemini_only_provider_defaults_to_gemini_models():
    defaults = default_model_pair_for_enabled_providers({"google"})

    assert defaults.model == "gemini-3.5-flash"
    assert defaults.planner_model == "gemini-3.1-flash-lite"


def test_current_nvidia_models_are_registered_for_nim_provider():
    expected = {
        "google/diffusiongemma-26b-a4b-it",
        "google/gemma-3n-e2b-it",
        "meta/llama-3.2-11b-vision-instruct",
        "meta/llama-4-maverick-17b-128e-instruct",
        "minimaxai/minimax-m3",
        "mistralai/ministral-14b-instruct-2512",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-medium-3.5-128b",
        "mistralai/mistral-small-4-119b-2603",
        "nvidia/nemotron-nano-12b-v2-vl",
    }

    assert set(NVIDIA_MODEL_IDS) == expected
    for model in expected:
        assert MODEL_CONFIGS[model]["provider"] == "nvidia"
        assert MODEL_CONFIGS[model]["id"] == model
        assert MODEL_VARIANTS[model]["variants"] == ["standard"]


def test_nvidia_registry_excludes_non_chat_utility_endpoints():
    excluded_fragments = {
        "embed",
        "retriever",
        "rerank",
        "reward",
        "safety",
        "guard",
        "parse",
        "detector",
        "translate",
        "bge",
        "nvclip",
        "gliner",
        "omni",
        "video",
    }

    for model in NVIDIA_MODEL_IDS:
        lowered = model.lower()
        assert not any(fragment in lowered for fragment in excluded_fragments)
        assert model not in NVIDIA_EXCLUDED_MODEL_IDS
        assert is_supported_nvidia_chat_or_code_model_id(model)


def test_nvidia_registry_filters_known_unsupported_and_special_purpose_models():
    excluded = {
        "microsoft/phi-4-multimodal-instruct",
        "minimaxai/minimax-m2.7",
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
        "meta/llama-3.2-90b-vision-instruct",
        "moonshotai/kimi-k2.6",
        "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "nvidia/nemotron-mini-4b-instruct",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-next-80b-a3b-instruct",
        "qwen/qwen3.5-122b-a10b",
        "stepfun-ai/step-3.7-flash",
    }

    for model in excluded:
        assert model not in NVIDIA_MODEL_IDS
        assert model not in MODEL_CONFIGS
        assert not is_supported_nvidia_chat_or_code_model_id(model)


def test_nvidia_only_provider_defaults_to_verified_image_input_model():
    defaults = default_model_pair_for_enabled_providers({"nvidia"})

    assert defaults.model == "mistralai/ministral-14b-instruct-2512"
    assert defaults.planner_model == "mistralai/ministral-14b-instruct-2512"
