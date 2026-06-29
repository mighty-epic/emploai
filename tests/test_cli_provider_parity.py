from types import SimpleNamespace

from cli import config_manager as config_manager_module
from cli import core_commands
from cli.chat_processor_core import refresh_llm_clients
from cli.config_manager import ConfigManager
from cli.tui_constants import MODEL_CONFIGS


PROVIDER_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
]


class _Result:
    def __init__(self, success, message, **kwargs):
        self.success = success
        self.message = message
        self.kwargs = kwargs


class _FakeConfigManager:
    def __init__(self, keys):
        self.keys = keys

    def get_api_key(self, provider):
        return self.keys.get(provider)

    def get_enabled_providers(self):
        return [provider for provider, key in self.keys.items() if key]


class _FakeOpenAI:
    created = []

    def __init__(self, *, api_key, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.created.append((api_key, base_url))


class _FakeAnthropic:
    def __init__(self, *, api_key):
        self.api_key = api_key


def test_refresh_llm_clients_builds_nvidia_client_without_restart(monkeypatch):
    for env_var in PROVIDER_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr("cli.chat_processor_core.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("cli.chat_processor_core.Anthropic", _FakeAnthropic)
    monkeypatch.setattr("cli.chat_processor_core.create_gemini_openai_client", lambda key: ("gemini", key))

    processor = SimpleNamespace(
        config_manager=_FakeConfigManager(
            {
                "openai": "sk-openai",
                "anthropic": "sk-ant",
                "google": "google-key",
                "xai": "xai-key",
                "deepseek": "deepseek-key",
                "nvidia": "nvidia-key",
                "openrouter": "openrouter-key",
            }
        )
    )

    refresh_llm_clients(processor)

    assert processor.client.api_key == "sk-openai"
    assert processor.anthropic.api_key == "sk-ant"
    assert processor.gemini_openai_client == ("gemini", "google-key")
    assert processor.xai_client.base_url == "https://api.x.ai/v1"
    assert processor.deepseek_client.base_url == "https://api.deepseek.com"
    assert processor.nvidia_client.base_url == "https://integrate.api.nvidia.com/v1"
    assert processor.openrouter_client.base_url == "https://openrouter.ai/api/v1"


def test_refresh_llm_clients_clears_removed_nvidia_key(monkeypatch):
    for env_var in PROVIDER_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr("cli.chat_processor_core.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("cli.chat_processor_core.Anthropic", _FakeAnthropic)
    monkeypatch.setattr("cli.chat_processor_core.create_gemini_openai_client", lambda key: ("gemini", key))

    processor = SimpleNamespace(
        config_manager=_FakeConfigManager({}),
        nvidia_client=object(),
        openrouter_client=object(),
        xai_client=object(),
        deepseek_client=object(),
        gemini_openai_client=object(),
    )

    refresh_llm_clients(processor)

    assert processor.nvidia_client is None
    assert processor.openrouter_client is None
    assert processor.xai_client is None
    assert processor.deepseek_client is None
    assert processor.gemini_openai_client is None


def test_model_command_rejects_nvidia_model_without_nvidia_key():
    context = SimpleNamespace(
        config_manager=_FakeConfigManager({"openai": "sk-openai"}),
        current_variant="standard",
        _get_available_variants=lambda _model: ["standard"],
        _get_default_variant=lambda _model: "standard",
        update_status=lambda: None,
    )

    result = core_commands.model(context, ["mistralai/ministral-14b-instruct-2512"], _Result)

    assert not result.success
    assert "nvidia API key is not configured" in result.message


def test_model_command_accepts_nvidia_model_with_nvidia_key():
    context = SimpleNamespace(
        config_manager=_FakeConfigManager({"nvidia": "nvidia-key"}),
        current_variant="standard",
        _get_available_variants=lambda _model: ["standard"],
        _get_default_variant=lambda _model: "standard",
        update_status=lambda: None,
    )

    model_name = "mistralai/ministral-14b-instruct-2512"
    result = core_commands.model(context, [model_name], _Result)

    assert result.success
    assert context.current_model == model_name
    assert context.max_tokens == MODEL_CONFIGS[model_name]["context"]


def test_config_manager_requires_actual_key_for_enabled_provider(monkeypatch, tmp_path):
    for env_var in PROVIDER_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(config_manager_module, "KEYRING_AVAILABLE", False)

    manager = ConfigManager(base_path=tmp_path)
    manager.config_file.write_text(
        '{"providers":{"nvidia":{"enabled":true}}}',
        encoding="utf-8",
    )

    assert manager.is_provider_enabled("nvidia") is False
    assert "nvidia" not in manager.get_enabled_providers()

    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-key")

    assert manager.is_provider_enabled("nvidia") is True
    assert "nvidia" in manager.get_enabled_providers()
