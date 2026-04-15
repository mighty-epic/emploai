from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PROVIDER_ORDER = [
    "anthropic",
    "openai",
    "google",
    "xai",
    "deepseek",
    "openrouter",
    "unknown",
]

PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def enabled_providers_from_env(values: Mapping[str, str]) -> set[str]:
    enabled: set[str] = set()
    for provider, env_var in PROVIDER_ENV_VARS.items():
        if str(values.get(env_var, "")).strip():
            enabled.add(provider)
    return enabled


def enabled_providers_from_clients(
    *,
    openai_client: Any = None,
    anthropic_client: Any = None,
    google_client: Any = None,
    xai_client: Any = None,
    deepseek_client: Any = None,
    openrouter_client: Any = None,
) -> set[str]:
    enabled: set[str] = set()
    if openai_client is not None:
        enabled.add("openai")
    if anthropic_client is not None:
        enabled.add("anthropic")
    if google_client is not None:
        enabled.add("google")
    if xai_client is not None:
        enabled.add("xai")
    if deepseek_client is not None:
        enabled.add("deepseek")
    if openrouter_client is not None:
        enabled.add("openrouter")
    return enabled


def filter_models_by_provider_access(
    models: Sequence[str],
    model_configs: Mapping[str, Mapping[str, Any]],
    enabled_providers: set[str],
) -> list[str]:
    filtered: list[str] = []
    for model in models:
        provider = str(model_configs.get(model, {}).get("provider", "unknown"))
        if provider == "unknown" or provider in enabled_providers:
            filtered.append(model)
    return filtered


def group_models_by_provider(
    models: Sequence[str],
    model_configs: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    providers: dict[str, list[str]] = {}
    for model in models:
        provider = str(model_configs.get(model, {}).get("provider", "unknown"))
        providers.setdefault(provider, []).append(model)

    ordered_groups: list[dict[str, Any]] = []
    seen: set[str] = set()

    for provider in PROVIDER_ORDER:
        grouped_models = sorted(providers.get(provider, []))
        if grouped_models:
            ordered_groups.append({"provider": provider, "models": grouped_models})
            seen.add(provider)

    for provider in sorted(providers):
        if provider in seen:
            continue
        ordered_groups.append({"provider": provider, "models": sorted(providers[provider])})

    return ordered_groups


def first_available_model(models: Sequence[str], current_model: str | None = None) -> str | None:
    if current_model and current_model in models:
        return current_model
    for model in models:
        return model
    return None
