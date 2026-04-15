from pathlib import Path

from deploy.windows.release_runtime import (
    current_release_version,
    default_release_config,
    ensure_runtime_files,
    merge_env,
    needs_versioned_setup,
    needs_first_run_setup,
    load_release_state,
    render_env,
    run_first_run_setup,
)


def test_ensure_runtime_files_creates_runtime_layout(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    ensure_runtime_files(runtime_home, source_root)

    assert (runtime_home / "logs").is_dir()
    assert (runtime_home / "memory").is_dir()
    assert (runtime_home / ".env.example").exists()

    config = (runtime_home / "config.json").read_text(encoding="utf-8")
    assert '"enabled": false' in config
    assert '"default_model": "gpt-4o-mini"' in config


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


def test_needs_first_run_setup_requires_token_and_user_ids():
    assert needs_first_run_setup({})
    assert needs_first_run_setup({"TELEGRAM_BOT_TOKEN": "abc"})
    assert not needs_first_run_setup(
        {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "ALLOWED_USER_IDS": "42",
        }
    )


def test_default_release_config_disables_app_channel():
    config = default_release_config()
    assert config["channels"]["telegram"]["enabled"] is True
    assert config["channels"]["app"]["enabled"] is False


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
    assert merged["XAI_API_KEY"] == "xai-key"
    assert merged["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert merged["OPENROUTER_API_KEY"] == "openrouter-key"
    assert load_release_state(runtime_home)["last_onboarded_version"] == "0.1.0-beta.2"
