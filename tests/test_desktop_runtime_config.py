import json
import os
from pathlib import Path

import desktop_runtime.config as desktop_config
from desktop_runtime.config import (
    PACKAGED_RUNTIME_HOME_NAME,
    RUNTIME_DATA_SCHEMA_STATE_KEY,
    RUNTIME_DATA_SCHEMA_VERSION,
    build_setup_state,
    configure_ssl_certificate_environment,
    configure_process_environment,
    current_release_version,
    default_release_config,
    ensure_runtime_files,
    save_setup_values,
    merge_env,
    needs_versioned_setup,
    needs_first_run_setup,
    load_release_state,
    render_env,
    run_first_run_setup,
    runtime_home,
    update_voice_pack_preferences,
    validate_setup_values,
)


def test_packaged_runtime_home_defaults_to_isolated_beta_home(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EMPLOAI_HOME", raising=False)
    monkeypatch.delenv("EMPLOAI_RUNTIME_HOME_NAME", raising=False)
    monkeypatch.delenv("EMPLOAI_PACKAGED_RUNTIME_HOME_NAME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(desktop_config.sys, "frozen", True, raising=False)

    assert runtime_home() == (tmp_path / PACKAGED_RUNTIME_HOME_NAME).resolve()


def test_ensure_runtime_files_creates_runtime_layout(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    bundled_context_dir = source_root / "runtime_context"
    bundled_context_dir.mkdir(parents=True)
    (bundled_context_dir / "AGENTS.md").write_text("# Runtime Agents\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    ensure_runtime_files(runtime_home, source_root)

    assert (runtime_home / "logs").is_dir()
    assert (runtime_home / "memory").is_dir()
    assert (runtime_home / "MEMORY.md").exists()
    assert (runtime_home / "agent_data" / "AGENTS.md").exists()
    assert (runtime_home / ".env.example").exists()

    config = (runtime_home / "config.json").read_text(encoding="utf-8")
    assert '"enabled": true' in config
    assert '"desktop"' in config
    assert '"default_model": "auto"' in config
    assert '"default_planner_model": "auto"' in config
    assert '"final_quality_guard": "planner"' in config
    assert '"final_quality_max_auto_continues": 2' in config
    assert "# MEMORY.md - Long-Term Memory" in (runtime_home / "MEMORY.md").read_text(encoding="utf-8")
    assert (runtime_home / "agent_data" / "AGENTS.md").read_text(encoding="utf-8") == "# Runtime Agents\n"
    assert load_release_state(runtime_home)[RUNTIME_DATA_SCHEMA_STATE_KEY] == RUNTIME_DATA_SCHEMA_VERSION


def test_ensure_runtime_files_keeps_legacy_telegram_agent_data_fallback(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    bundled_context_dir = source_root / "telegram_bot" / "agent_data"
    bundled_context_dir.mkdir(parents=True)
    (bundled_context_dir / "AGENTS.md").write_text("# Legacy Runtime Agents\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    ensure_runtime_files(runtime_home, source_root)

    assert (runtime_home / "agent_data" / "AGENTS.md").read_text(encoding="utf-8") == "# Legacy Runtime Agents\n"


def test_ensure_runtime_files_resets_stale_runtime_home_on_schema_mismatch(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "desktop-sidebar-state.json").write_text('{"stale":true}', encoding="utf-8")
    (runtime_home / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    (runtime_home / "config.json").write_text('{"voice":{"default_engine":"english_local"}}', encoding="utf-8")
    (runtime_home / "release_state.json").write_text(
        json.dumps(
            {
                RUNTIME_DATA_SCHEMA_STATE_KEY: RUNTIME_DATA_SCHEMA_VERSION - 1,
                "last_onboarded_version": "0.1.0-beta.1",
            }
        ),
        encoding="utf-8",
    )

    ensure_runtime_files(runtime_home, source_root)

    state = load_release_state(runtime_home)
    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert state[RUNTIME_DATA_SCHEMA_STATE_KEY] == RUNTIME_DATA_SCHEMA_VERSION
    assert "last_onboarded_version" not in state
    assert not (runtime_home / "desktop-sidebar-state.json").exists()
    assert config["voice"]["default_engine"] == "none"
    assert (runtime_home / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-test\n"


def test_ensure_runtime_files_migrates_legacy_runtime_config(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "config.json").write_text(
        """
        {
          "channels": {
            "telegram": { "enabled": true },
            "app": { "enabled": false, "port": 8787 }
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    ensure_runtime_files(runtime_home, source_root)

    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert config["channels"]["app"]["enabled"] is True
    assert config["channels"]["desktop"]["enabled"] is True
    assert config["channels"]["desktop"]["auto_start"] is False
    assert config["channels"]["desktop"]["keep_runtime_on_app_close"] is False


def test_ensure_runtime_files_preserves_existing_extension_payload(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    extension_src = source_root / "browser_extension"
    extension_src.mkdir()
    (extension_src / "background.js").write_text("source-background", encoding="utf-8")
    (extension_src / "popup.js").write_text("source-popup", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "release_state.json").write_text(
        json.dumps({RUNTIME_DATA_SCHEMA_STATE_KEY: RUNTIME_DATA_SCHEMA_VERSION}),
        encoding="utf-8",
    )
    extension_dst = runtime_home / "browser_extension"
    extension_dst.mkdir()
    (extension_dst / "popup.js").write_text("existing-popup", encoding="utf-8")

    ensure_runtime_files(runtime_home, source_root)

    assert (extension_dst / "popup.js").read_text(encoding="utf-8") == "existing-popup"
    assert (extension_dst / "background.js").read_text(encoding="utf-8") == "source-background"


def test_merge_env_overrides_known_values_and_keeps_existing():
    existing = {
        "TELEGRAM_BOT_TOKEN": "old",
        "ALLOWED_USER_IDS": "1",
        "EXTRA_FLAG": "keep",
    }
    merged = merge_env(existing, {"TELEGRAM_BOT_TOKEN": "new", "DEFAULT_WORKSPACE": "C:/Work"})

    assert merged["TELEGRAM_BOT_TOKEN"] == "new"
    assert merged["ALLOWED_USER_IDS"] == "1"
    assert merged["DEFAULT_WORKSPACE"] == "C:/Work"
    assert merged["EXTRA_FLAG"] == "keep"


def test_render_env_keeps_release_fields_first():
    rendered = render_env(
        {
            "DEFAULT_WORKSPACE": "C:/Users/Test/Documents",
            "OPENAI_API_KEY": "sk-test",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "ALLOWED_USER_IDS": "42",
            "ZZZ": "tail",
        }
    )

    lines = rendered.strip().splitlines()
    assert lines[:4] == [
        "TELEGRAM_BOT_TOKEN=123:abc",
        "ALLOWED_USER_IDS=42",
        "OPENAI_API_KEY=sk-test",
        "DEFAULT_WORKSPACE=C:/Users/Test/Documents",
    ]
    assert lines[-1] == "ZZZ=tail"


def test_validate_setup_values_allows_account_token_remote_configuration():
    issues = validate_setup_values(
        {
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "EMPLOAI_REMOTE_CONTROL_BASE_URL": "https://example.com",
        }
    )

    assert not any("Remote control requires service URL, email, and password together." in issue for issue in issues)


def test_build_setup_state_marks_remote_control_configuration(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    env_file = tmp_path / ".env"
    state = build_setup_state(
        home=tmp_path,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "EMPLOAI_REMOTE_CONTROL_BASE_URL": "https://example.com",
            "EMPLOAI_REMOTE_CONTROL_EMAIL": "user@example.com",
            "EMPLOAI_REMOTE_CONTROL_PASSWORD": "correct horse battery staple",
        },
    )

    assert state["remoteControlConfigured"] is True
    assert state["remoteControlPartiallyConfigured"] is False


def test_build_setup_state_marks_remote_account_session_configured(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    env_file = tmp_path / ".env"
    (tmp_path / "remote-account-session.json").write_text(
        json.dumps({"apiBaseUrl": "https://api.kraitos.app", "sessionToken": "session-token"}),
        encoding="utf-8",
    )

    state = build_setup_state(
        home=tmp_path,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
    )

    assert state["remoteControlConfigured"] is True
    assert state["remoteControlPartiallyConfigured"] is False


def test_build_setup_state_marks_plain_json_fallback_remote_session_configured(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    env_file = tmp_path / ".env"
    (tmp_path / "remote-account-session.json").write_text(
        json.dumps(
            {
                "version": 2,
                "storage": "plain_json_fallback",
                "payload": {
                    "apiBaseUrl": "https://api.kraitos.app",
                    "sessionToken": "session-token",
                    "user": {"user_id": 77},
                },
            }
        ),
        encoding="utf-8",
    )

    state = build_setup_state(
        home=tmp_path,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
    )

    assert state["remoteControlConfigured"] is True
    assert state["remoteControlPartiallyConfigured"] is False
    assert desktop_config.remote_account_session_payload(tmp_path)["user"]["user_id"] == 77


def test_build_setup_state_does_not_treat_encrypted_remote_session_as_plaintext(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    env_file = tmp_path / ".env"
    (tmp_path / "remote-account-session.json").write_text(
        json.dumps({"version": 2, "storage": "electron_safe_storage", "ciphertext": "opaque"}),
        encoding="utf-8",
    )

    state = build_setup_state(
        home=tmp_path,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
    )

    assert state["remoteControlConfigured"] is False
    assert state["remoteControlPartiallyConfigured"] is False


def test_build_setup_state_marks_env_remote_account_session_configured(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    env_file = tmp_path / ".env"
    (tmp_path / "remote-account-session.json").write_text(
        json.dumps({"version": 2, "storage": "electron_safe_storage", "ciphertext": "opaque"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_BASE_URL", "https://api.kraitos.app")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN", "session-token")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_USER_ID", "77")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_DESKTOP_ID", "desktop-abc")

    state = build_setup_state(
        home=tmp_path,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
    )
    session = desktop_config.remote_account_session_payload(tmp_path)

    assert state["remoteControlConfigured"] is True
    assert state["remoteControlPartiallyConfigured"] is False
    assert session["user"]["user_id"] == "77"
    assert session["desktop"]["desktop_id"] == "desktop-abc"


def test_needs_first_run_setup_requires_workspace_and_provider_key():
    assert needs_first_run_setup({})
    assert needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work"})
    assert not needs_first_run_setup({"OPENAI_API_KEY": "sk-test"})
    assert not needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work", "NVIDIA_API_KEY": "nvapi-test"})
    assert needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work", "TELEGRAM_BOT_TOKEN": "123:abc"})
    assert not needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work", "OPENAI_API_KEY": "sk-test"})


def test_default_release_config_enables_local_desktop_channels_only_by_default():
    config = default_release_config()
    assert config["channels"]["telegram"]["enabled"] is False
    assert config["channels"]["app"]["enabled"] is True
    assert config["channels"]["desktop"]["enabled"] is True
    assert config["channels"]["desktop"]["auto_start"] is False
    assert config["channels"]["desktop"]["keep_runtime_on_app_close"] is False
    assert config["voice"]["default_engine"] == "none"
    assert config["voice"]["packs"]["english_local"]["requested"] is False
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is False


def test_tracked_root_config_matches_local_first_defaults():
    root_config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))

    assert root_config["channels"]["telegram"]["enabled"] is False
    assert root_config["channels"]["app"]["enabled"] is True
    assert root_config["channels"]["desktop"]["enabled"] is True
    assert root_config["channels"]["desktop"]["host"] == "127.0.0.1"
    assert root_config["voice"]["default_engine"] == "none"
    assert root_config["voice"]["packs"]["english_local"]["requested"] is False
    assert root_config["voice"]["packs"]["hebrew_local"]["requested"] is False


def test_ensure_runtime_files_ignores_legacy_installer_voice_preferences(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    monkeypatch.setattr(
        "desktop_runtime.config._read_installer_voice_pack_preferences",
        lambda: {
            "schema_version": 1,
            "english_requested": False,
            "hebrew_requested": True,
        },
    )

    ensure_runtime_files(runtime_home, source_root)

    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert config["voice"]["default_engine"] == "none"
    assert config["voice"]["selection_source"] == "default"
    assert config["voice"]["packs"]["english_local"]["requested"] is False
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is False


def test_needs_versioned_setup_triggers_on_new_release(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "release_state.json").write_text(
        '{"last_onboarded_version":"0.1.0-beta.1"}',
        encoding="utf-8",
    )

    values = {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "ALLOWED_USER_IDS": "42",
    }
    assert current_release_version(source_root) == "0.1.0-beta.2"
    assert needs_versioned_setup(values, home=runtime_home, source_root=source_root)


def test_run_first_run_setup_saves_all_provider_keys_and_onboarded_version(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"

    answers = iter([
        "123:abc",
        "42",
        "C:/Work",
        "https://remote.emplo.ai",
        "user@example.com",
        "",
        "",
        "sk-openai",
        "sk-ant",
        "google-key",
        "xai-key",
        "deepseek-key",
        "nvidia-key",
        "openrouter-key",
        "",
        "",
    ])

    merged = run_first_run_setup(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={},
        input_fn=lambda _prompt: next(answers),
    )

    assert merged["OPENAI_API_KEY"] == "sk-openai"
    assert merged["ANTHROPIC_API_KEY"] == "sk-ant"
    assert merged["GOOGLE_API_KEY"] == "google-key"
    assert merged["GEMINI_API_KEY"] == "google-key"
    assert merged["XAI_API_KEY"] == "xai-key"
    assert merged["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert merged["NVIDIA_API_KEY"] == "nvidia-key"
    assert merged["OPENROUTER_API_KEY"] == "openrouter-key"
    assert merged["EMPLOAI_REMOTE_CONTROL_BASE_URL"] == "https://remote.emplo.ai"
    assert merged["EMPLOAI_REMOTE_CONTROL_EMAIL"] == "user@example.com"
    assert merged["EMPLOAI_REMOTE_CONTROL_PASSWORD"] == ""
    assert merged["EMPLOAI_REMOTE_DESKTOP_NAME"] == "EmploAI Desktop"
    assert merged["EMPLOAI_REMOTE_DESKTOP_KEY"] == "desktop-default"
    assert load_release_state(runtime_home)["last_onboarded_version"] == "0.1.0-beta.2"


def test_build_setup_state_marks_versioned_setup_and_provider_labels(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"

    state = build_setup_state(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "PLANNER_MODEL": "gpt-5.4-mini",
        },
    )

    assert state["required"] is False
    assert state["versioned"] is True
    assert state["telegramRebindRequired"] is True
    assert state["configuredProviders"] == ["OpenAI"]
    assert state["modelGroups"]
    assert any(group["provider"] == "openai" for group in state["modelGroups"])
    assert state["plannerModels"]
    assert state["plannerModels"][0] == "gpt-5.4-mini"
    assert "gpt-5.4-mini" in state["plannerModels"]
    assert state["validationIssues"][0].startswith("Review Telegram bot access")
    assert "voiceAvailable" in state
    assert "voiceStatus" in state
    assert state["values"]["PLANNER_MODEL"] == "gpt-5.4-mini"
    assert state["values"]["TELEGRAM_BOT_TOKEN"] == ""
    assert state["values"]["ALLOWED_USER_IDS"] == ""
    assert state["values"]["VOICE_DEFAULT_ENGINE"] == "none"
    assert state["voicePacks"]["defaultEngine"] == "none"
    assert state["voicePacks"]["packs"][0]["id"] == "english_local"


def test_build_setup_state_exposes_nvidia_models_when_nvidia_key_is_configured(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"

    state = build_setup_state(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "NVIDIA_API_KEY": "nvapi-test",
        },
    )

    nvidia_group = next(group for group in state["modelGroups"] if group["provider"] == "nvidia")
    assert state["configuredProviders"] == ["NVIDIA NIM"]
    assert nvidia_group["models"] == [
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
    ]
    assert "deepseek-ai/deepseek-v4-pro" not in nvidia_group["models"]
    assert "nvidia/llama-3.3-nemotron-super-49b-v1" not in nvidia_group["models"]
    assert "openai/gpt-oss-120b" not in nvidia_group["models"]
    assert "openai/gpt-oss-20b" not in nvidia_group["models"]
    assert state["plannerModels"][0] == "mistralai/ministral-14b-instruct-2512"


def test_build_setup_state_accepts_local_codex_auth_without_api_key(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    auth_dir = runtime_home / "data"
    auth_dir.mkdir(parents=True)
    (auth_dir / "openai-codex-auth.json").write_text(
        '{"tokens":{"access_token":"access","refresh_token":"refresh","expires_at":4102444800}}',
        encoding="utf-8",
    )

    state = build_setup_state(
        home=runtime_home,
        env_file=runtime_home / ".env",
        source_root=source_root,
        existing={"DEFAULT_WORKSPACE": "C:/Work"},
    )

    assert state["required"] is False
    assert "OpenAI Codex (ChatGPT)" in state["configuredProviders"]
    assert any(group["provider"] == "openai-codex" for group in state["modelGroups"])
    assert "chatgpt/gpt-5.4-mini" in state["plannerModels"]


def test_save_setup_values_clears_telegram_rebind_flag(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    (runtime_home / "config.json").write_text(json.dumps(default_release_config(), indent=2), encoding="utf-8")
    (runtime_home / "release_state.json").write_text(
        json.dumps(
            {
                "last_onboarded_version": "0.1.0-beta.1",
                "telegram_rebind_required": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    save_setup_values(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "TELEGRAM_BOT_TOKEN": "old-token",
            "ALLOWED_USER_IDS": "42",
        },
        updates={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "TELEGRAM_BOT_TOKEN": "",
            "ALLOWED_USER_IDS": "",
        },
    )

    state = load_release_state(runtime_home)
    assert state["last_onboarded_version"] == "0.1.0-beta.2"
    assert state["telegram_rebind_required"] is False


def test_save_setup_values_persists_voice_pack_scaffold_in_config_only(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    (runtime_home / "config.json").write_text(json.dumps(default_release_config(), indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "desktop_runtime.config._read_installer_voice_pack_preferences",
        lambda: {"schema_version": 0, "english_requested": None, "hebrew_requested": None},
    )

    save_setup_values(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
        updates={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "VOICE_DEFAULT_ENGINE": "none",
            "VOICE_ENGLISH_REQUESTED": "0",
            "VOICE_HEBREW_REQUESTED": "1",
        },
    )

    rendered_env = env_file.read_text(encoding="utf-8")
    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))

    assert "VOICE_DEFAULT_ENGINE" not in rendered_env
    assert "VOICE_ENGLISH_REQUESTED" not in rendered_env
    assert "VOICE_HEBREW_REQUESTED" not in rendered_env
    assert config["voice"]["default_engine"] == "none"
    assert config["voice"]["selection_source"] == "settings"
    assert config["voice"]["packs"]["english_local"]["requested"] is False
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is True


def test_save_setup_values_persists_planner_model_in_env(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    (runtime_home / "config.json").write_text(json.dumps(default_release_config(), indent=2), encoding="utf-8")

    merged = save_setup_values(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
        updates={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "PLANNER_MODEL": "gpt-5.4-mini",
        },
    )

    assert merged["PLANNER_MODEL"] == "gpt-5.4-mini"
    assert "PLANNER_MODEL=gpt-5.4-mini" in env_file.read_text(encoding="utf-8")


def test_save_setup_values_keeps_cloud_secrets_out_of_env(tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    (runtime_home / "config.json").write_text(json.dumps(default_release_config(), indent=2), encoding="utf-8")

    merged = save_setup_values(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
        },
        updates={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-cloud-only",
            "TELEGRAM_BOT_TOKEN": "123456:cloud-only",
            "ALLOWED_USER_IDS": "42",
            "EMPLOAI_REMOTE_CONTROL_PASSWORD": "remote-password",
            "GMAIL_LOGIN_PASSWORD": "gmail-password",
            "PLANNER_MODEL": "gpt-5.4-mini",
        },
    )

    rendered = env_file.read_text(encoding="utf-8")
    assert merged["OPENAI_API_KEY"] == "sk-cloud-only"
    assert "PLANNER_MODEL=gpt-5.4-mini" in rendered
    assert "OPENAI_API_KEY" not in rendered
    assert "TELEGRAM_BOT_TOKEN" not in rendered
    assert "EMPLOAI_REMOTE_CONTROL_PASSWORD" not in rendered
    assert "GMAIL_LOGIN_PASSWORD" not in rendered


def test_save_setup_values_allows_hebrew_default_engine_when_requested(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    deploy_dir = source_root / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    (runtime_home / "config.json").write_text(json.dumps(default_release_config(), indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "desktop_runtime.config._read_installer_voice_pack_preferences",
        lambda: {"schema_version": 0, "english_requested": None, "hebrew_requested": None},
    )

    save_setup_values(
        home=runtime_home,
        env_file=env_file,
        source_root=source_root,
        existing={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
        },
        updates={
            "DEFAULT_WORKSPACE": "C:/Work",
            "OPENAI_API_KEY": "sk-test",
            "VOICE_DEFAULT_ENGINE": "hebrew_local",
            "VOICE_ENGLISH_REQUESTED": "1",
            "VOICE_HEBREW_REQUESTED": "1",
        },
    )

    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert config["voice"]["default_engine"] == "hebrew_local"
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is True


def test_update_voice_pack_preferences_falls_back_when_active_pack_is_removed(tmp_path: Path):
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "config.json").write_text(
        json.dumps(
            {
                "voice": {
                    "default_engine": "hebrew_local",
                    "selection_source": "settings",
                    "packs": {
                        "english_local": {"requested": True},
                        "hebrew_local": {"requested": True},
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    update_voice_pack_preferences(
        home=runtime_home,
        pack_id="hebrew_local",
        requested=False,
        default_engine="english_local",
    )

    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is False
    assert config["voice"]["default_engine"] == "english_local"


def test_configure_ssl_certificate_environment_repairs_missing_cert_env(monkeypatch, tmp_path: Path):
    missing_cert = tmp_path / "missing-cacert.pem"
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.setenv(key, str(missing_cert))

    cert_path = configure_ssl_certificate_environment()

    assert cert_path is not None
    assert Path(cert_path).exists()
    assert Path(cert_path) != missing_cert
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        assert Path(os.environ[key]).exists()


def test_configure_process_environment_prunes_older_regex_metadata(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    env_file.write_text("", encoding="utf-8")
    bundle = tmp_path / "bundle"
    internal = bundle / "_internal"
    internal.mkdir(parents=True)
    older = internal / "regex-2024.11.6.dist-info"
    newer = internal / "regex-2026.4.4.dist-info"
    older.mkdir()
    newer.mkdir()

    monkeypatch.setattr("desktop_runtime.config.bundle_root", lambda: bundle)

    configure_process_environment(runtime_home, env_file)

    assert not older.exists()
    assert newer.exists()


def test_configure_process_environment_scrubs_existing_local_secrets(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEFAULT_WORKSPACE=C:/Work",
                "OPENAI_API_KEY=sk-stale-local",
                "TELEGRAM_BOT_TOKEN=123456:stale-local",
                "EMPLOAI_REMOTE_CONTROL_PASSWORD=stale-password",
                "PLANNER_MODEL=gpt-5.4-mini",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "host-value")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "host-telegram")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_PASSWORD", "host-password")

    values = configure_process_environment(runtime_home, env_file)
    rendered = env_file.read_text(encoding="utf-8")

    assert values == {
        "DEFAULT_WORKSPACE": "C:/Work",
        "PLANNER_MODEL": "gpt-5.4-mini",
    }
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("TELEGRAM_BOT_TOKEN") is None
    assert os.environ.get("EMPLOAI_REMOTE_CONTROL_PASSWORD") is None
    assert "OPENAI_API_KEY" not in rendered
    assert "TELEGRAM_BOT_TOKEN" not in rendered
    assert "EMPLOAI_REMOTE_CONTROL_PASSWORD" not in rendered


def test_configure_process_environment_prunes_duplicates_when_bundle_root_is_internal(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    env_file = runtime_home / ".env"
    env_file.write_text("", encoding="utf-8")
    internal = tmp_path / "bundle" / "_internal"
    internal.mkdir(parents=True)
    older = internal / "regex-2024.11.6.dist-info"
    newer = internal / "regex-2026.4.4.dist-info"
    older.mkdir()
    newer.mkdir()

    monkeypatch.setattr("desktop_runtime.config.bundle_root", lambda: internal)

    configure_process_environment(runtime_home, env_file)

    assert not older.exists()
    assert newer.exists()
