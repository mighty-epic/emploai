import json
import os
from pathlib import Path

from deploy.windows.release_runtime import (
    build_setup_state,
    configure_ssl_certificate_environment,
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
    update_voice_pack_preferences,
)


def test_ensure_runtime_files_creates_runtime_layout(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    bundled_context_dir = source_root / "telegram_bot" / "agent_data"
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
    assert '"default_model": "gpt-4o-mini"' in config
    assert "# MEMORY.md - Long-Term Memory" in (runtime_home / "MEMORY.md").read_text(encoding="utf-8")
    assert (runtime_home / "agent_data" / "AGENTS.md").read_text(encoding="utf-8") == "# Runtime Agents\n"


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


def test_needs_first_run_setup_requires_workspace_and_provider_key():
    assert needs_first_run_setup({})
    assert needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work"})
    assert not needs_first_run_setup({"OPENAI_API_KEY": "sk-test"})
    assert needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work", "TELEGRAM_BOT_TOKEN": "123:abc"})
    assert not needs_first_run_setup({"DEFAULT_WORKSPACE": "C:/Work", "OPENAI_API_KEY": "sk-test"})


def test_default_release_config_enables_desktop_and_app_channels():
    config = default_release_config()
    assert config["channels"]["telegram"]["enabled"] is True
    assert config["channels"]["app"]["enabled"] is True
    assert config["channels"]["desktop"]["enabled"] is True
    assert config["channels"]["desktop"]["auto_start"] is False
    assert config["channels"]["desktop"]["keep_runtime_on_app_close"] is False
    assert config["voice"]["default_engine"] == "english_local"
    assert config["voice"]["packs"]["english_local"]["requested"] is True
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is False


def test_ensure_runtime_files_seeds_voice_packs_from_installer_preferences(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    monkeypatch.setattr(
        "deploy.windows.release_runtime._read_installer_voice_pack_preferences",
        lambda: {
            "schema_version": 1,
            "english_requested": False,
            "hebrew_requested": True,
        },
    )

    ensure_runtime_files(runtime_home, source_root)

    config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
    assert config["voice"]["default_engine"] == "hebrew_local"
    assert config["voice"]["selection_source"] == "installer"
    assert config["voice"]["packs"]["english_local"]["requested"] is False
    assert config["voice"]["packs"]["hebrew_local"]["requested"] is True


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
        "sk-openai",
        "sk-ant",
        "google-key",
        "xai-key",
        "deepseek-key",
        "openrouter-key",
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
    assert merged["OPENROUTER_API_KEY"] == "openrouter-key"
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
    assert state["configuredProviders"] == ["OpenAI"]
    assert "voiceAvailable" in state
    assert "voiceStatus" in state
    assert state["values"]["PLANNER_MODEL"] == "gpt-5.4-mini"
    assert state["values"]["VOICE_DEFAULT_ENGINE"] == "english_local"
    assert state["voicePacks"]["defaultEngine"] == "english_local"
    assert state["voicePacks"]["packs"][0]["id"] == "english_local"


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
        "deploy.windows.release_runtime._read_installer_voice_pack_preferences",
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
        "deploy.windows.release_runtime._read_installer_voice_pack_preferences",
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
