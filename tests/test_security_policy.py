from __future__ import annotations

from shared.provider_errors import PROVIDER_INPUT_REJECTED, PROVIDER_SAFETY_REJECTION, normalize_provider_error
from shared.security_policy import (
    ACTION_CONFIRM,
    ACTION_DENY,
    FULL_PERMISSION,
    LOW_PERMISSION,
    SecurityContext,
    evaluate_tool_call,
    filter_tool_result,
    redact_json,
    redact_text,
)


def test_security_policy_blocks_protected_secret_paths():
    decision = evaluate_tool_call(
        "read_file",
        {"path": "C:/Users/example/.ssh/id_rsa"},
        context=SecurityContext(),
    )

    assert decision.action == ACTION_DENY
    assert decision.risk == "secret_access"


def test_security_policy_blocks_explicit_browser_destination():
    decision = evaluate_tool_call(
        "browser_navigate",
        {"url": "https://example-porn-site.test"},
        context=SecurityContext(permission_mode=FULL_PERMISSION),
    )

    assert decision.action == ACTION_DENY
    assert decision.risk == "explicit_or_illegal_destination"


def test_security_policy_requires_low_mode_confirmation_for_active_control():
    decision = evaluate_tool_call(
        "browser_navigate",
        {"url": "https://example.com"},
        context=SecurityContext(permission_mode=LOW_PERMISSION),
    )

    assert decision.action == ACTION_CONFIRM
    assert decision.risk == "browser_control"


def test_security_policy_full_mode_confirms_destructive_legitimate_command():
    decision = evaluate_tool_call(
        "run_command",
        {"command": "Remove-Item C:/Temp/example -Recurse -Force"},
        context=SecurityContext(permission_mode=FULL_PERMISSION),
    )

    assert decision.action == ACTION_CONFIRM
    assert decision.risk == "destructive_command"


def test_security_policy_blocks_workspace_write_when_binding_missing(tmp_path):
    missing_workspace = tmp_path / "missing"
    decision = evaluate_tool_call(
        "write_file",
        {"path": "report.md", "content": "hello"},
        context=SecurityContext(workspace_path=str(missing_workspace)),
    )

    assert decision.action == ACTION_DENY
    assert decision.risk == "workspace_write_blocked"

    readonly = evaluate_tool_call(
        "write_file",
        {"path": "report.md", "content": "hello"},
        context=SecurityContext(workspace_path=str(tmp_path), workspace_binding_status="read_only"),
    )

    assert readonly.action == ACTION_DENY
    assert readonly.risk == "workspace_write_blocked"


def test_redaction_removes_secrets_from_text_and_json():
    secret_like_value = "sk-" + "live-secret1234567890"
    assert secret_like_value[:14] not in redact_text(f"key={secret_like_value}")
    payload = redact_json({"password": "secret", "nested": {"token": "abc"}, "safe": "hello", "session_id": "sess-1"})

    assert payload["password"] == "[REDACTED_SECRET]"
    assert payload["nested"]["token"] == "[REDACTED_SECRET]"
    assert payload["safe"] == "hello"
    assert payload["session_id"] == "sess-1"


def test_observation_filter_blocks_explicit_content():
    result = filter_tool_result(
        "describe_screen",
        {},
        {"description": "A browser is open to xvideos.example with search results."},
    )

    assert result["error_type"] == "security_policy"
    assert result["risk"] == "explicit_or_illegal_content"


def test_provider_error_normalization_classifies_safety_and_input_rejections():
    safety = normalize_provider_error(RuntimeError("content_filter blocked by safety policy"), payload_kind="image")
    input_error = normalize_provider_error(RuntimeError("400 invalid image payload"), payload_kind="image")

    assert safety.error_type == PROVIDER_SAFETY_REJECTION
    assert safety.safe_alternate_allowed is True
    assert input_error.error_type == PROVIDER_INPUT_REJECTED
    assert input_error.safe_alternate_allowed is True
