from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from cli.tui_constants import MODEL_CONFIGS


OPENAI_DEFAULT_MODEL = "gpt-5.4-mini"
OPENAI_DEFAULT_PLANNER_MODEL = "gpt-5.4-mini"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4.5"
ANTHROPIC_DEFAULT_PLANNER_MODEL = "claude-haiku-4.5"
GOOGLE_DEFAULT_MODEL = "gemini-3.5-flash"
GOOGLE_DEFAULT_PLANNER_MODEL = "gemini-3.1-flash-lite"
NVIDIA_DEFAULT_MODEL = "mistralai/ministral-14b-instruct-2512"
NVIDIA_DEFAULT_PLANNER_MODEL = "mistralai/ministral-14b-instruct-2512"
AUTO_MODEL_SETTING_VALUES = {"", "auto", "automatic", "provider_auto", "provider-auto"}


@dataclass(frozen=True)
class DefaultModelPair:
    model: str
    planner_model: str


def is_auto_model_setting(value: Any) -> bool:
    return str(value or "").strip().lower() in AUTO_MODEL_SETTING_VALUES


def provider_for_model(
    model_name: str,
    model_configs: Mapping[str, Mapping[str, Any]] = MODEL_CONFIGS,
) -> str:
    return str(model_configs.get(str(model_name or "").strip(), {}).get("provider", "") or "").strip()


def default_model_pair_for_enabled_providers(enabled_providers: set[str]) -> DefaultModelPair:
    if "openai" in enabled_providers:
        return DefaultModelPair(OPENAI_DEFAULT_MODEL, OPENAI_DEFAULT_PLANNER_MODEL)
    if "anthropic" in enabled_providers:
        return DefaultModelPair(ANTHROPIC_DEFAULT_MODEL, ANTHROPIC_DEFAULT_PLANNER_MODEL)
    if "google" in enabled_providers:
        return DefaultModelPair(GOOGLE_DEFAULT_MODEL, GOOGLE_DEFAULT_PLANNER_MODEL)
    if "nvidia" in enabled_providers:
        return DefaultModelPair(NVIDIA_DEFAULT_MODEL, NVIDIA_DEFAULT_PLANNER_MODEL)
    return DefaultModelPair(OPENAI_DEFAULT_MODEL, OPENAI_DEFAULT_PLANNER_MODEL)


def default_planner_for_model(
    model_name: str,
    *,
    enabled_providers: set[str],
    model_configs: Mapping[str, Mapping[str, Any]] = MODEL_CONFIGS,
) -> str:
    provider = provider_for_model(model_name, model_configs)
    if provider == "openai":
        return OPENAI_DEFAULT_PLANNER_MODEL
    if provider == "anthropic":
        return ANTHROPIC_DEFAULT_PLANNER_MODEL
    if provider == "google":
        return GOOGLE_DEFAULT_PLANNER_MODEL
    if provider and provider in enabled_providers:
        return str(model_name or "").strip()
    return default_model_pair_for_enabled_providers(enabled_providers).planner_model
