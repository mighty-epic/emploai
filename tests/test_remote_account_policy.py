from __future__ import annotations

import pytest

from app_backend.remote_account_policy import (
    MAX_SECRET_VALUE_CHARS,
    normalize_email,
    redact_secret_value,
    safe_secret_metadata,
    sanitize_user_profile,
    strong_password_errors,
    validate_secret_location,
    validate_secret_namespace,
)


def test_strong_password_errors_reject_common_contextual_passwords():
    assert "Password is too common." in strong_password_errors("password123!")
    assert "Password cannot include the email name." in strong_password_errors(
        "ProfileName!2026",
        email="profile@example.com",
    )
    assert "Password cannot include the display name." in strong_password_errors(
        "CorrectHorseProfile!2026",
        display_name="Profile",
    )


def test_strong_password_errors_reports_missing_character_classes():
    errors = strong_password_errors("lowercaseonly")

    assert "Password must include an uppercase letter." in errors
    assert "Password must include a number." in errors
    assert "Password must include a symbol." in errors
    assert "Password must include a lowercase letter." not in errors


def test_strong_password_errors_accepts_valid_password_and_normalizes_email():
    assert normalize_email("  User@Example.COM ") == "user@example.com"
    assert strong_password_errors("CorrectHorse!2026", email="user@example.com", display_name="Profile") == []


def test_sanitize_user_profile_drops_secret_like_values_and_normalizes_telegram_ids():
    profile = sanitize_user_profile(
        {
            "preferences": {
                "verbose_mode": True,
                "cloud_chat_backup_enabled": False,
                "interrupt_policy_default": "surprise",
                "planner_model": "gpt-5",
                "custom_system_prompt_append": "Prefer short answers.",
                "max_turns": "120",
                "sleep_mode_enabled": True,
                "memory_controls": {
                    "prompt_context_enabled": False,
                    "search_enabled": True,
                    "write_enabled": False,
                },
            },
            "setup": {
                "desktop": {"theme": "dark", "api_key": "strip-me"},
                "mobile": {"compact": True, "token": "strip-me"},
            },
            "integrations": {
                "telegram": {
                    "enabled": True,
                    "allowedUserIds": ["12345", "+67890", "not-a-number", "12345"],
                    "bots": [
                        {
                            "id": "main",
                            "label": "Main",
                            "bot_token": "secret",
                            "credential_ref": "telegram/main",
                        }
                    ],
                }
            },
            "metadata": {"api_key": "secret", "theme": "calm"},
        }
    )

    assert profile["preferences"]["verbose_mode"] is True
    assert profile["preferences"]["cloud_chat_backup_enabled"] is False
    assert profile["preferences"]["interrupt_policy_default"] == "none"
    assert profile["preferences"]["planner_model"] == "gpt-5"
    assert profile["preferences"]["custom_system_prompt_append"] == "Prefer short answers."
    assert profile["preferences"]["max_turns"] == 120
    assert profile["preferences"]["sleep_mode_enabled"] is True
    assert profile["preferences"]["memory_controls"] == {
        "prompt_context_enabled": False,
        "search_enabled": True,
        "write_enabled": False,
    }
    assert profile["setup"]["desktop"] == {"theme": "dark"}
    assert profile["setup"]["mobile"] == {"compact": True}
    assert profile["integrations"]["telegram"]["allowed_user_ids"] == ["12345", "67890"]
    assert profile["integrations"]["telegram"]["bots"][0] == {
        "bot_config_id": "main",
        "label": "Main",
        "is_default": False,
        "credential_ref": "telegram/main",
    }
    assert profile["metadata"] == {"theme": "calm"}


def test_secret_policy_validates_namespaces_locations_and_metadata():
    assert validate_secret_namespace(" Telegram_Bots ") == "telegram_bots"
    assert validate_secret_location("setup", "OPENAI_API_KEY") == ("setup", "OPENAI_API_KEY")
    assert validate_secret_location("login_credentials", "GMAIL_PASSWORD") == ("login_credentials", "GMAIL_PASSWORD")
    assert safe_secret_metadata({"label": "Key", "api_key": "strip-me"}) == {"label": "Key"}
    assert redact_secret_value("1234567890") == "1234...7890"
    assert len("x" * MAX_SECRET_VALUE_CHARS) == MAX_SECRET_VALUE_CHARS


def test_secret_policy_rejects_invalid_locations():
    with pytest.raises(ValueError, match="Secret namespace is invalid"):
        validate_secret_namespace("bad namespace")
    with pytest.raises(ValueError, match="Secret name is invalid"):
        validate_secret_location("setup", "x")
    with pytest.raises(ValueError, match="Unsupported setup secret"):
        validate_secret_location("setup", "GMAIL_PASSWORD")
