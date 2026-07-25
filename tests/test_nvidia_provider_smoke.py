import os

import pytest

from cli.tui_constants import NVIDIA_MODEL_IDS
from scripts import verify_nvidia_provider
from shared.model_defaults import NVIDIA_DEFAULT_MODEL


def test_registry_missing_from_catalog_reports_only_registered_drift():
    live_catalog = [model for model in NVIDIA_MODEL_IDS if model != "google/diffusiongemma-26b-a4b-it"]

    assert verify_nvidia_provider.registry_missing_from_catalog(live_catalog) == ["google/diffusiongemma-26b-a4b-it"]


def test_verify_nvidia_provider_accepts_catalog_only_without_key(monkeypatch):
    monkeypatch.setattr(verify_nvidia_provider, "fetch_live_model_ids", lambda timeout=30.0: list(NVIDIA_MODEL_IDS))
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    assert verify_nvidia_provider.main(["--skip-chat"]) == 0


def test_verify_nvidia_provider_requires_key_when_requested(monkeypatch):
    monkeypatch.setattr(verify_nvidia_provider, "fetch_live_model_ids", lambda timeout=30.0: list(NVIDIA_MODEL_IDS))
    monkeypatch.setattr(verify_nvidia_provider, "_load_dotenv", lambda: None)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    assert verify_nvidia_provider.main(["--require-key"]) == 2


def test_verify_nvidia_provider_rejects_unregistered_model(monkeypatch):
    monkeypatch.setattr(verify_nvidia_provider, "fetch_live_model_ids", lambda timeout=30.0: list(NVIDIA_MODEL_IDS))

    assert verify_nvidia_provider.main(["--skip-chat", "--model", "nvidia/not-in-menu"]) == 1


@pytest.mark.skipif(
    os.getenv("EMPLOAI_RUN_LIVE_NVIDIA_SMOKE") != "1"
    or not os.getenv("NVIDIA_API_KEY"),
    reason=(
        "Set EMPLOAI_RUN_LIVE_NVIDIA_SMOKE=1 with NVIDIA_API_KEY "
        "to run the live NVIDIA smoke"
    ),
)
def test_live_nvidia_chat_smoke_with_configured_key():
    assert verify_nvidia_provider.main(["--require-key", "--model", NVIDIA_DEFAULT_MODEL]) == 0
