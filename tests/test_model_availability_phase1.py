from shared.model_availability import (
    enabled_providers_from_env,
    filter_models_by_provider_access,
    first_available_model,
    group_models_by_provider,
)


MODEL_CONFIGS = {
    "gpt-5.4": {"provider": "openai"},
    "gpt-4o-mini": {"provider": "openai"},
    "claude-haiku-4.5": {"provider": "anthropic"},
    "gemini-2.5-pro": {"provider": "google"},
    "grok-4-0709": {"provider": "xai"},
    "mistralai/ministral-14b-instruct-2512": {"provider": "nvidia"},
}


def test_enabled_providers_from_env_detects_configured_keys():
    enabled = enabled_providers_from_env(
        {
            "OPENAI_API_KEY": "sk-openai",
            "GOOGLE_API_KEY": "google-key",
            "NVIDIA_API_KEY": "nvapi-key",
            "ANTHROPIC_API_KEY": "",
        }
    )

    assert enabled == {"openai", "google", "nvidia"}


def test_filter_models_by_provider_access_keeps_only_configured_providers():
    models = list(MODEL_CONFIGS.keys())
    filtered = filter_models_by_provider_access(models, MODEL_CONFIGS, {"openai"})

    assert filtered == ["gpt-5.4", "gpt-4o-mini"]


def test_group_models_by_provider_returns_ordered_filtered_groups():
    models = ["gemini-2.5-pro", "gpt-5.4", "claude-haiku-4.5", "mistralai/ministral-14b-instruct-2512"]
    groups = group_models_by_provider(models, MODEL_CONFIGS)

    assert groups == [
        {"provider": "anthropic", "models": ["claude-haiku-4.5"]},
        {"provider": "openai", "models": ["gpt-5.4"]},
        {"provider": "google", "models": ["gemini-2.5-pro"]},
        {"provider": "nvidia", "models": ["mistralai/ministral-14b-instruct-2512"]},
    ]


def test_first_available_model_prefers_current_when_still_valid():
    assert first_available_model(["gpt-5.4", "gpt-4o-mini"], "gpt-4o-mini") == "gpt-4o-mini"
    assert first_available_model(["claude-haiku-4.5"], "gpt-5.4") == "claude-haiku-4.5"
