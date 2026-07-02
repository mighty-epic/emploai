from __future__ import annotations

from app_backend.jarvis_voice_policy import (
    jarvis_barge_in_is_self_echo,
    jarvis_barge_in_text_is_meaningful,
    jarvis_barge_in_words,
    jarvis_confirmation_intent,
    jarvis_confirmation_prompt,
    jarvis_start_task_message,
)


def test_jarvis_start_task_message_selects_domain_specific_phrase():
    assert jarvis_start_task_message("open Gmail") == "Opening that now."
    assert jarvis_start_task_message("search for the deployment notes") == "I am checking that now."
    assert jarvis_start_task_message("send a Telegram reply") == "I will prepare that now."
    assert jarvis_start_task_message("write a short summary") == "I am working on that now."
    assert jarvis_start_task_message("please help with this") == "I am on it. I will start working on that now."


def test_jarvis_barge_in_helpers_detect_meaningful_non_echo_text():
    assert not jarvis_barge_in_text_is_meaningful("ok")
    assert jarvis_barge_in_text_is_meaningful("wait stop")
    assert jarvis_barge_in_words("Wait, stop that please!") == ["wait", "stop", "that", "please"]
    assert jarvis_barge_in_is_self_echo("checking that now", "I am checking that now.") is True
    assert jarvis_barge_in_is_self_echo("wait stop", "I am checking that now.") is False


def test_jarvis_confirmation_intent_accepts_short_clear_answers_only():
    assert jarvis_confirmation_intent("yes, proceed") is True
    assert jarvis_confirmation_intent("no cancel that") is False
    assert jarvis_confirmation_intent("yes no") is None
    assert jarvis_confirmation_intent("I was asking a different question with many words") is None


def test_jarvis_confirmation_prompt_formats_tool_confirmation():
    prompt = jarvis_confirmation_prompt(
        "fleet_stop_all",
        {
            "confirmation_required": True,
            "action": "stop all workers",
            "summary": "This stops every active worker task.",
            "risk": "bulk_stop",
            "confirmation_id": "confirm-123",
        },
    )

    assert prompt is not None
    assert prompt["confirmation_id"] == "confirm-123"
    assert prompt["tool_name"] == "fleet_stop_all"
    assert "stop all workers" in prompt["spoken_prompt"]
    assert "bulk_stop" in prompt["spoken_prompt"]


def test_jarvis_confirmation_prompt_accepts_security_confirmation_results():
    prompt = jarvis_confirmation_prompt(
        "shell_command",
        {
            "error_type": "security_confirmation_required",
            "tool_name": "shell command",
            "error": "Command requires approval.",
        },
    )

    assert prompt is not None
    assert prompt["action"] == "shell command"
    assert prompt["confirmation_id"].startswith("voice_confirm_")
    assert jarvis_confirmation_prompt("noop", {"ok": True}) is None
