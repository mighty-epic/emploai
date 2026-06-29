from __future__ import annotations

import os
from pathlib import Path

from shared.agent_eval_harness import (
    AgentEvalHarness,
    ArtifactCheck,
    EvalCase,
    EvalConfig,
    EvalExpectations,
    ToolContentCheck,
    ToolOrderCheck,
    _artifact_check_results,
    _ordered_tool_trace,
    analyze_turn,
    compute_stream_metrics,
    evaluate_expectations,
    stable_eval_user_id,
)


def test_stable_eval_user_id_is_deterministic() -> None:
    assert stable_eval_user_id("smoke") == stable_eval_user_id("smoke")
    assert stable_eval_user_id("smoke") != stable_eval_user_id("other")


def test_eval_config_parses_planner_final_quality_guard(tmp_path: Path) -> None:
    config = EvalConfig.from_dict(
        {
            "name": "planner-smoke",
            "workspace": ".",
            "model": "gpt-5.4-mini",
            "planner_model": "gpt-5.4-mini",
            "final_quality_guard": "planner",
            "final_quality_max_auto_continues": 2,
            "cases": [{"name": "case", "prompt": "Create and verify a file."}],
        },
        repo_root=tmp_path,
    )

    assert config.final_quality_guard == "planner"
    assert config.final_quality_max_auto_continues == 2


def test_eval_harness_applies_planner_final_quality_guard_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EMPLOAI_FINAL_QUALITY_GUARD", raising=False)
    monkeypatch.delenv("EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES", raising=False)
    config = EvalConfig(
        name="planner-smoke",
        workspace=tmp_path,
        model="gpt-5.4-mini",
        planner_model="gpt-5.4-mini",
        final_quality_guard="planner",
        final_quality_max_auto_continues=2,
        cases=[EvalCase(name="case", prompt="Create and verify a file.")],
    )
    harness = AgentEvalHarness(
        repo_root=tmp_path,
        config=config,
        runtime_home=tmp_path / "runtime",
        output_root=tmp_path / "runs",
    )

    harness.prepare_environment()

    assert os.environ["EMPLOAI_FINAL_QUALITY_GUARD"] == "planner"
    assert os.environ["EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES"] == "2"


def test_normalize_phrase_handles_smart_quotes() -> None:
    from shared.agent_eval_harness import normalize_phrase

    assert normalize_phrase("I can’t inspect “workspace”") == normalize_phrase("i can't inspect \"workspace\"")


def test_compute_stream_metrics_tracks_reasoning_and_tool_timing() -> None:
    metrics = compute_stream_metrics(
        [
            {"type": "status", "ts_ms": 10.0},
            {"type": "reasoning_delta", "ts_ms": 50.0, "delta": "Thinking..."},
            {"type": "assistant_delta", "ts_ms": 110.0, "delta": "Hel"},
            {"type": "assistant_delta", "ts_ms": 310.0, "delta": "lo"},
            {"type": "tool_use", "ts_ms": 450.0, "tool_name": "list_dir", "duration_ms": 12.0},
            {"type": "assistant_delta", "ts_ms": 980.0, "delta": "!"},
        ],
        total_duration_ms=1400.0,
        assistant_text="Hello!",
    )

    assert metrics["time_to_first_delta_ms"] == 110.0
    assert metrics["time_to_first_tool_ms"] == 450.0
    assert metrics["longest_delta_gap_ms"] == 670.0
    assert metrics["tool_names"] == ["list_dir"]
    assert metrics["assistant_chars_streamed"] == 6
    assert metrics["reasoning_chars_streamed"] == len("Thinking...")


def test_ordered_tool_trace_marks_unsupported_attempts() -> None:
    trace = _ordered_tool_trace(
        [
            {
                "type": "tool_use",
                "ts_ms": 100.0,
                "tool_name": "ghost_tool",
                "tool_args": {"foo": "bar"},
                "tool_result": {"error_type": "unknown_tool", "error": "Unknown tool"},
                "result_error_type": "unknown_tool",
                "duration_ms": 1.5,
            }
        ]
    )

    assert trace[0]["tool_name"] == "ghost_tool"
    assert trace[0]["unsupported_attempt"] is True


def test_artifact_checks_fail_on_missing_or_forbidden_content(tmp_path: Path) -> None:
    artifact = tmp_path / "result.txt"
    artifact.write_text("example.com\nexample.net\nexample.org\nlocalhost\n", encoding="utf-8")

    results = _artifact_check_results(
        tmp_path,
        [
            ArtifactCheck(
                path="result.txt",
                contains_all=["example.com", "example.net", "example.org"],
                not_contains=["localhost"],
            )
        ],
    )

    assert results[0]["passed"] is False
    assert any("forbidden content" in failure.lower() for failure in results[0]["failures"])


def test_evaluate_expectations_flags_fatal_answer_and_artifact_failure(tmp_path: Path) -> None:
    artifact = tmp_path / "result.txt"
    artifact.write_text("example.com\nlocalhost\n", encoding="utf-8")
    artifact_results = _artifact_check_results(
        tmp_path,
        [ArtifactCheck(path="result.txt", contains_all=["example.com"], not_contains=["localhost"])],
    )
    metrics = {
        "tool_names": ["write_file"],
        "total_duration_ms": 1500.0,
        "time_to_first_delta_ms": 250.0,
        "time_to_first_tool_ms": 700.0,
        "longest_delta_gap_ms": 500.0,
    }
    expectations = EvalExpectations(
        final_answer_forbidden_phrases=["task completed successfully"],
    )
    result = evaluate_expectations(
        assistant_text="Task completed successfully. Your input exceeds the context window.",
        metrics=metrics,
        events=[],
        expectations=expectations,
        artifact_results=artifact_results,
        runtime_result={"ok": True},
    )
    assert result["passed"] is False
    assert result["failure_classification"] == "infra"
    assert any("context window" in failure.lower() for failure in result["failures"])


def test_evaluate_expectations_does_not_treat_normal_bridge_mentions_as_fatal() -> None:
    metrics = {
        "tool_names": [],
        "total_duration_ms": 900.0,
        "time_to_first_delta_ms": 150.0,
        "time_to_first_tool_ms": None,
        "longest_delta_gap_ms": 120.0,
    }
    result = evaluate_expectations(
        assistant_text="The live Chrome / extension bridge is unavailable right now, so I would use the isolated browser instead.",
        metrics=metrics,
        events=[],
        expectations=EvalExpectations(required_phrases=["isolated browser"]),
        artifact_results=[],
        runtime_result={"ok": True},
    )

    assert result["passed"] is True
    assert result["fatal_error"] is None
    assert result["failure_classification"] == "none"


def test_evaluate_expectations_accepts_required_phrase_variants() -> None:
    metrics = {
        "tool_names": [],
        "total_duration_ms": 900.0,
        "time_to_first_delta_ms": 150.0,
        "time_to_first_tool_ms": None,
        "longest_delta_gap_ms": 120.0,
    }
    result = evaluate_expectations(
        assistant_text="I can't directly inspect the workspace because the file-listing tool is unavailable.",
        metrics=metrics,
        events=[],
        expectations=EvalExpectations(required_phrases_any=["unavailable", "cannot directly inspect", "can't directly inspect"]),
        artifact_results=[],
        runtime_result={},
    )

    assert result["passed"] is True
    assert result["issues"] == []


def test_evaluate_expectations_accepts_equivalent_tool_names_and_blocks_unsupported_attempts() -> None:
    metrics = {
        "tool_names": ["open_browser"],
        "total_duration_ms": 1500.0,
        "time_to_first_delta_ms": 250.0,
        "time_to_first_tool_ms": 700.0,
        "longest_delta_gap_ms": 500.0,
    }
    events = [
        {
            "type": "tool_use",
            "ts_ms": 50.0,
            "tool_name": "ghost_tool",
            "duration_ms": 1.0,
            "tool_result": {"error_type": "unknown_tool"},
            "result_error_type": "unknown_tool",
        }
    ]
    expectations = EvalExpectations(
        required_tools_any=["browser_navigate"],
        accepted_tool_names_any=["open_browser"],
        max_unsupported_tool_attempts=0,
    )
    result = evaluate_expectations(
        assistant_text="Opened the browser.",
        metrics=metrics,
        events=events,
        expectations=expectations,
        artifact_results=[],
        runtime_result={},
    )

    assert result["passed"] is False
    assert result["unsupported_tool_attempts"] == 1
    assert any("Unsupported tool attempts" in failure for failure in result["failures"])


def test_evaluate_expectations_reports_structured_decision_tool_and_reasoning_issues() -> None:
    events = [
        {
            "type": "reasoning_delta",
            "ts_ms": 10.0,
            "delta": "I will guess and write first.",
        },
        {
            "type": "tool_use",
            "ts_ms": 50.0,
            "tool_name": "write_file",
            "duration_ms": 8.0,
            "tool_args": {"path": "wrong.txt", "content": "Example Domain"},
            "tool_result": {"ok": True},
        },
        {
            "type": "tool_use",
            "ts_ms": 100.0,
            "tool_name": "browser_navigate",
            "duration_ms": 12.0,
            "tool_args": {"url": "https://example.com"},
            "tool_result": {"ok": True},
        },
        {
            "type": "tool_use",
            "ts_ms": 150.0,
            "tool_name": "ghost_tool",
            "duration_ms": 1.0,
            "tool_result": {"error_type": "unknown_tool"},
            "result_error_type": "unknown_tool",
        },
    ]
    metrics = compute_stream_metrics(events, total_duration_ms=300.0, assistant_text="Done.")
    metrics["total_duration_ms"] = 300.0
    expectations = EvalExpectations(
        forbidden_reasoning_phrases=["guess"],
        required_tool_sequence=[["browser_navigate", "open_browser"], ["browser_snapshot", "observe_browser"], ["write_file"]],
        required_tool_order=[ToolOrderCheck(before="browser_navigate", after="write_file")],
        tool_arg_checks=[ToolContentCheck(tool_name="write_file", contains_all=["expected.txt"])],
        max_unsupported_tool_attempts=0,
        min_tool_calls=4,
    )

    result = evaluate_expectations(
        assistant_text="Done.",
        metrics=metrics,
        events=events,
        expectations=expectations,
        artifact_results=[],
        runtime_result={},
    )

    assert result["passed"] is False
    assert {"decision", "reasoning", "tool-use"}.issubset(set(result["failure_categories"]))
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert "forbidden_reasoning_phrase" in issue_codes
    assert "missing_required_tool_sequence" in issue_codes
    assert "wrong_tool_order" in issue_codes
    assert "tool_args_mismatch" in issue_codes
    assert "unsupported_tool_attempt_limit_exceeded" in issue_codes
    assert "too_few_tool_calls" in issue_codes


def test_evaluate_expectations_accepts_sequence_alternatives_and_tool_content_checks() -> None:
    events = [
        {
            "type": "tool_use",
            "ts_ms": 50.0,
            "tool_name": "open_browser",
            "duration_ms": 8.0,
            "tool_args": {"url": "https://example.com"},
            "tool_result": {"title": "Example Domain"},
        },
        {
            "type": "tool_use",
            "ts_ms": 100.0,
            "tool_name": "observe_browser",
            "duration_ms": 12.0,
            "tool_result": {"heading": "Example Domain"},
        },
        {
            "type": "tool_use",
            "ts_ms": 150.0,
            "tool_name": "write_file",
            "duration_ms": 10.0,
            "tool_args": {"path": "expected.txt", "content": "Example Domain"},
            "tool_result": {"ok": True, "path": "expected.txt"},
        },
        {
            "type": "tool_use",
            "ts_ms": 190.0,
            "tool_name": "read_file",
            "duration_ms": 5.0,
            "tool_args": {"path": "expected.txt"},
            "tool_result": {"content": "Example Domain"},
        },
    ]
    metrics = compute_stream_metrics(events, total_duration_ms=250.0, assistant_text="Verified Example Domain.")
    metrics["total_duration_ms"] = 250.0
    expectations = EvalExpectations(
        required_tool_sequence=[["browser_navigate", "open_browser"], ["browser_snapshot", "observe_browser"], "write_file", "read_file"],
        required_tool_order=[ToolOrderCheck(before="write_file", after="read_file")],
        tool_arg_checks=[ToolContentCheck(tool_name="write_file", contains_all=["expected.txt", "Example Domain"])],
        tool_result_checks=[ToolContentCheck(tool_name="read_file", contains_all=["Example Domain"])],
        max_tool_errors=0,
        min_tool_calls=4,
        max_tool_calls=4,
    )

    result = evaluate_expectations(
        assistant_text="Verified Example Domain.",
        metrics=metrics,
        events=events,
        expectations=expectations,
        artifact_results=[],
        runtime_result={},
    )

    assert result["passed"] is True
    assert result["issues"] == []
    assert result["failure_classification"] == "none"


def test_evaluate_expectations_flags_repeated_launch_tools_as_verification_issue() -> None:
    events = [
        {
            "type": "tool_use",
            "ts_ms": 10.0,
            "tool_name": "run_background_command",
            "duration_ms": 1.0,
            "tool_args": {"command": "npm start"},
            "tool_result": {"status": "running"},
        },
        {
            "type": "tool_use",
            "ts_ms": 20.0,
            "tool_name": "run_background_command",
            "duration_ms": 1.0,
            "tool_args": {"command": "npm start"},
            "tool_result": {"status": "running"},
        },
        {
            "type": "tool_use",
            "ts_ms": 30.0,
            "tool_name": "run_background_command",
            "duration_ms": 1.0,
            "tool_args": {"command": "npm start -- --disable-gpu"},
            "tool_result": {"status": "running"},
        },
    ]
    metrics = compute_stream_metrics(events, total_duration_ms=100.0, assistant_text="Running.")
    metrics["total_duration_ms"] = 100.0
    result = evaluate_expectations(
        assistant_text="Running.",
        metrics=metrics,
        events=events,
        expectations=EvalExpectations(max_tool_calls_by_name={"run_background_command": 2}),
        artifact_results=[],
        runtime_result={},
    )

    assert result["passed"] is False
    assert result["failure_classification"] == "verification"
    assert result["issues"][0]["code"] == "tool_call_limit_exceeded"


def test_eval_config_from_dict_parses_diagnostic_expectation_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = EvalConfig.from_dict(
        {
            "name": "diagnostic-demo",
            "workspace": str(workspace),
            "model": "gpt-5.4-mini",
            "cases": [
                {
                    "name": "browser-write-verify",
                    "prompt": "Open a page and save the heading.",
                    "expectations": {
                        "required_tool_sequence": [["browser_navigate", "open_browser"], "write_file", "read_file"],
                        "required_tool_order": [{"before": "write_file", "after": "read_file"}],
                        "tool_arg_checks": [{"tool": "write_file", "contains_all": ["heading.txt"]}],
                        "tool_result_checks": [{"tool_name": "read_file", "contains_any": ["Example Domain"]}],
                        "required_reasoning_phrases": ["verify"],
                        "max_tool_errors": 0,
                        "min_tool_calls": 3,
                        "max_tool_calls": 5,
                        "max_tool_calls_by_name": {"run_background_command": 2},
                    },
                }
            ],
        },
        repo_root=tmp_path,
    )

    expectations = config.cases[0].expectations
    assert expectations.required_tool_sequence == [["browser_navigate", "open_browser"], ["write_file"], ["read_file"]]
    assert expectations.required_tool_order[0].before == "write_file"
    assert expectations.tool_arg_checks[0].tool_name == "write_file"
    assert expectations.tool_result_checks[0].contains_any == ["Example Domain"]
    assert expectations.required_reasoning_phrases == ["verify"]
    assert expectations.max_tool_errors == 0
    assert expectations.min_tool_calls == 3
    assert expectations.max_tool_calls == 5
    assert expectations.max_tool_calls_by_name == {"run_background_command": 2}


def test_analyze_turn_reports_streaming_stall() -> None:
    notes = analyze_turn(
        {
            "time_to_first_delta_ms": 4200.0,
            "longest_delta_gap_ms": 2300.0,
            "final_delay_after_last_delta_ms": 5100.0,
            "delta_count": 2,
            "assistant_chars_final": 80,
            "tool_call_count": 0,
        }
    )
    assert any("late" in note.lower() for note in notes)
    assert any("stalled" in note.lower() for note in notes)


def test_eval_config_from_dict_resolves_workspace(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "workspace").mkdir()
    payload = {
        "name": "demo",
        "workspace": "workspace",
        "model": "gpt-5.4-mini",
        "cases": [{"name": "hello", "prompt": "hey"}],
    }
    config = EvalConfig.from_dict(payload, repo_root=repo_root)
    assert config.workspace == (repo_root / "workspace").resolve()
    assert config.cases[0].name == "hello"


def test_prepare_environment_defaults_eval_browser_to_headed(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    workspace = repo_root / "workspace"
    runtime_home = tmp_path / "runtime"
    output_root = tmp_path / "out"
    workspace.mkdir(parents=True)
    config = EvalConfig.from_dict(
        {
            "name": "demo",
            "workspace": str(workspace),
            "model": "gpt-5.4-mini",
            "cases": [{"name": "hello", "prompt": "hey"}],
        },
        repo_root=repo_root,
    )
    harness = AgentEvalHarness(
        repo_root=repo_root,
        config=config,
        runtime_home=runtime_home,
        output_root=output_root,
    )

    harness.prepare_environment()

    assert runtime_home.exists()
    assert output_root.exists()
    assert config.workspace == workspace.resolve()
    assert os.environ["HEADLESS"] == "false"
