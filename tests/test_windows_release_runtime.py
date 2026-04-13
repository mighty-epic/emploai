from pathlib import Path

from deploy.windows.release_runtime import (
    default_release_config,
    ensure_runtime_files,
    merge_env,
    needs_first_run_setup,
    render_env,
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
