from types import SimpleNamespace

from shared.chat_modes import (
    apply_goal_status_update,
    extract_proposed_plan,
    is_safe_plan_command,
    normalize_plan_question,
    plan_tool_denial,
    start_goal,
)


def test_plan_mode_blocks_mutating_tools():
    assert plan_tool_denial("write_file", {"path": "x", "content": "y"})
    assert plan_tool_denial("run_background_command", {"command": "npm run dev"})
    assert plan_tool_denial("run_command", {"command": "Set-Content file.txt value"})


def test_plan_mode_allows_safe_validation_commands():
    assert plan_tool_denial("read_file", {"path": "README.md"}) is None
    assert plan_tool_denial("run_command", {"command": "npm run typecheck"}) is None
    assert is_safe_plan_command("git status --short")


def test_extract_proposed_plan_block():
    content = "Intro\n<proposed_plan>\n# Plan\nDo the thing.\n</proposed_plan>\nTail"
    assert extract_proposed_plan(content) == "# Plan\nDo the thing."


def test_normalize_plan_question_falls_back_to_options():
    question = normalize_plan_question({"question": "Which path?", "options": [{"label": "Only one"}]})
    assert question["question"] == "Which path?"
    assert len(question["options"]) == 2
    assert question["question_id"].startswith("plan_q_")


def test_goal_status_requires_summary_and_evidence():
    session = SimpleNamespace(active_goal=None)
    start_goal(session, "Ship the feature")
    missing = apply_goal_status_update(session, {"status": "complete", "summary": "Done"})
    assert missing["ok"] is False

    result = apply_goal_status_update(
        session,
        {"status": "complete", "summary": "Done", "evidence": "Typecheck passed"},
    )
    assert result["ok"] is True
    assert session.active_goal["status"] == "complete"
