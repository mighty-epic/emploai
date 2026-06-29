from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.artifact_store import ChatArtifactStore


FATAL_ERROR_PATTERNS = {
    "quota": [
        "insufficient_quota",
        "rate limit",
        "rate-limit",
        "quota",
        "out of codex messages",
        "add credits",
    ],
    "infra": [
        "error in model generation",
        "context window",
        "provider error",
        "api error",
        "api key",
        "timed out",
        "timeout",
        "connection refused",
        "failed to connect",
        "overloaded",
        "internal server error",
    ],
}
UNSUPPORTED_TOOL_ERROR_TYPES = {"policy", "unsupported_tool", "unknown_tool", "provider_tool_validation"}


def stable_eval_user_id(profile: str) -> int:
    digest = hashlib.sha1(profile.encode("utf-8")).hexdigest()
    return 900_000_000 + (int(digest[:8], 16) % 99_999_999)


def normalize_phrase(value: str) -> str:
    normalized = (
        str(value or "")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    collapsed = " ".join(normalized.strip().lower().split())
    return collapsed


def truncate_jsonable(value: Any, *, limit: int = 240) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[: limit - 3] + "..."
    if isinstance(value, dict):
        return {str(key): truncate_jsonable(val, limit=limit) for key, val in list(value.items())[:8]}
    if isinstance(value, (list, tuple)):
        return [truncate_jsonable(item, limit=limit) for item in list(value)[:12]]
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _string_list(value: Any) -> List[str]:
    return [str(item) for item in value or []]


def _tool_step_options(step: Any) -> List[str]:
    if isinstance(step, (list, tuple, set)):
        return [str(item) for item in step if str(item).strip()]
    text = str(step or "").strip()
    return [text] if text else []


def _coerce_tool_sequence(value: Any) -> List[List[str]]:
    return [options for options in (_tool_step_options(step) for step in value or []) if options]


@dataclass
class ArtifactCheck:
    path: str
    must_exist: bool = True
    contains_all: List[str] = field(default_factory=list)
    contains_any: List[str] = field(default_factory=list)
    not_contains: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ArtifactCheck":
        payload = dict(data or {})
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError("artifact_checks entries require a non-empty 'path'.")
        return cls(
            path=path,
            must_exist=bool(payload.get("must_exist", True)),
            contains_all=[str(item) for item in payload.get("contains_all", []) or []],
            contains_any=[str(item) for item in payload.get("contains_any", []) or []],
            not_contains=[str(item) for item in payload.get("not_contains", []) or []],
        )


@dataclass
class ToolOrderCheck:
    before: str
    after: str

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ToolOrderCheck":
        payload = dict(data or {})
        before = str(payload.get("before") or "").strip()
        after = str(payload.get("after") or "").strip()
        if not before or not after:
            raise ValueError("tool order checks require non-empty 'before' and 'after' fields.")
        return cls(before=before, after=after)


@dataclass
class ToolContentCheck:
    tool_name: str
    contains_all: List[str] = field(default_factory=list)
    contains_any: List[str] = field(default_factory=list)
    not_contains: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ToolContentCheck":
        payload = dict(data or {})
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "").strip()
        if not tool_name:
            raise ValueError("tool content checks require a non-empty 'tool' or 'tool_name' field.")
        return cls(
            tool_name=tool_name,
            contains_all=_string_list(payload.get("contains_all")),
            contains_any=_string_list(payload.get("contains_any")),
            not_contains=_string_list(payload.get("not_contains")),
        )


@dataclass
class EvalExpectations:
    required_phrases: List[str] = field(default_factory=list)
    required_phrases_any: List[str] = field(default_factory=list)
    forbidden_phrases: List[str] = field(default_factory=list)
    required_reasoning_phrases: List[str] = field(default_factory=list)
    forbidden_reasoning_phrases: List[str] = field(default_factory=list)
    required_tools_any: List[str] = field(default_factory=list)
    required_tools_all: List[str] = field(default_factory=list)
    required_tool_sequence: List[List[str]] = field(default_factory=list)
    required_tool_order: List[ToolOrderCheck] = field(default_factory=list)
    accepted_tool_names_any: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    tool_arg_checks: List[ToolContentCheck] = field(default_factory=list)
    tool_result_checks: List[ToolContentCheck] = field(default_factory=list)
    final_answer_forbidden_phrases: List[str] = field(default_factory=list)
    artifact_checks: List[ArtifactCheck] = field(default_factory=list)
    max_unsupported_tool_attempts: Optional[int] = None
    max_tool_errors: Optional[int] = None
    min_tool_calls: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_tool_calls_by_name: Dict[str, int] = field(default_factory=dict)
    max_total_duration_ms: Optional[float] = None
    max_time_to_first_delta_ms: Optional[float] = None
    max_time_to_first_tool_ms: Optional[float] = None
    max_longest_delta_gap_ms: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EvalExpectations":
        payload = dict(data or {})
        return cls(
            required_phrases=_string_list(payload.get("required_phrases")),
            required_phrases_any=_string_list(payload.get("required_phrases_any")),
            forbidden_phrases=_string_list(payload.get("forbidden_phrases")),
            required_reasoning_phrases=_string_list(payload.get("required_reasoning_phrases")),
            forbidden_reasoning_phrases=_string_list(payload.get("forbidden_reasoning_phrases")),
            required_tools_any=_string_list(payload.get("required_tools_any")),
            required_tools_all=_string_list(payload.get("required_tools_all")),
            required_tool_sequence=_coerce_tool_sequence(payload.get("required_tool_sequence")),
            required_tool_order=[ToolOrderCheck.from_dict(item) for item in payload.get("required_tool_order", []) or []],
            accepted_tool_names_any=_string_list(payload.get("accepted_tool_names_any")),
            forbidden_tools=_string_list(payload.get("forbidden_tools")),
            tool_arg_checks=[ToolContentCheck.from_dict(item) for item in payload.get("tool_arg_checks", []) or []],
            tool_result_checks=[ToolContentCheck.from_dict(item) for item in payload.get("tool_result_checks", []) or []],
            final_answer_forbidden_phrases=_string_list(payload.get("final_answer_forbidden_phrases")),
            artifact_checks=[ArtifactCheck.from_dict(item) for item in payload.get("artifact_checks", []) or []],
            max_unsupported_tool_attempts=_coerce_optional_int(payload.get("max_unsupported_tool_attempts")),
            max_tool_errors=_coerce_optional_int(payload.get("max_tool_errors")),
            min_tool_calls=_coerce_optional_int(payload.get("min_tool_calls")),
            max_tool_calls=_coerce_optional_int(payload.get("max_tool_calls")),
            max_tool_calls_by_name={
                str(key): int(value)
                for key, value in dict(payload.get("max_tool_calls_by_name") or {}).items()
                if str(key).strip()
            },
            max_total_duration_ms=_coerce_optional_float(payload.get("max_total_duration_ms")),
            max_time_to_first_delta_ms=_coerce_optional_float(payload.get("max_time_to_first_delta_ms")),
            max_time_to_first_tool_ms=_coerce_optional_float(payload.get("max_time_to_first_tool_ms")),
            max_longest_delta_gap_ms=_coerce_optional_float(payload.get("max_longest_delta_gap_ms")),
        )


@dataclass
class EvalCase:
    name: str
    prompt: str
    setup_messages: List[str] = field(default_factory=list)
    workspace: Optional[str] = None
    model: Optional[str] = None
    variant: Optional[str] = None
    planner_model: Optional[str] = None
    enabled_tool_packs: Optional[List[str]] = None
    task_board_armed_next_turn: Optional[bool] = None
    fresh_session: Optional[bool] = None
    expectations: EvalExpectations = field(default_factory=EvalExpectations)
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalCase":
        payload = dict(data or {})
        name = str(payload.get("name") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not name:
            raise ValueError("Every eval case needs a non-empty 'name'.")
        if not prompt:
            raise ValueError(f"Eval case '{name}' needs a non-empty 'prompt'.")
        enabled_tool_packs = payload.get("enabled_tool_packs")
        return cls(
            name=name,
            prompt=prompt,
            setup_messages=[str(item) for item in payload.get("setup_messages", []) or []],
            workspace=str(payload.get("workspace")).strip() if payload.get("workspace") is not None else None,
            model=str(payload.get("model")).strip() if payload.get("model") is not None else None,
            variant=str(payload.get("variant")).strip() if payload.get("variant") is not None else None,
            planner_model=str(payload.get("planner_model")).strip() if payload.get("planner_model") is not None else None,
            enabled_tool_packs=[str(item) for item in enabled_tool_packs] if enabled_tool_packs is not None else None,
            task_board_armed_next_turn=bool(payload["task_board_armed_next_turn"]) if "task_board_armed_next_turn" in payload else None,
            fresh_session=bool(payload["fresh_session"]) if "fresh_session" in payload else None,
            expectations=EvalExpectations.from_dict(payload.get("expectations")),
            notes=str(payload.get("notes")).strip() if payload.get("notes") is not None else None,
        )


@dataclass
class EvalConfig:
    name: str
    workspace: Path
    model: str
    variant: str = "standard"
    planner_model: Optional[str] = None
    final_quality_guard: Optional[str] = None
    final_quality_max_auto_continues: Optional[int] = None
    enabled_tool_packs: Optional[List[str]] = None
    repeat: int = 1
    fresh_runtime: bool = False
    fresh_session_per_case: bool = True
    capture_prompt_snapshot: bool = True
    task_board_armed_next_turn: bool = False
    cases: List[EvalCase] = field(default_factory=list)
    profile: str = "default"
    user_id: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, repo_root: Path) -> "EvalConfig":
        payload = dict(data or {})
        name = str(payload.get("name") or "agent-eval").strip() or "agent-eval"
        workspace_raw = str(payload.get("workspace") or ".").strip() or "."
        workspace = (repo_root / workspace_raw).resolve() if not Path(workspace_raw).is_absolute() else Path(workspace_raw).resolve()
        model = str(payload.get("model") or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
        cases = [EvalCase.from_dict(item) for item in payload.get("cases", []) or []]
        if not cases:
            raise ValueError("Eval config needs at least one case.")
        enabled_tool_packs = payload.get("enabled_tool_packs")
        user_id_value = payload.get("user_id")
        return cls(
            name=name,
            workspace=workspace,
            model=model,
            variant=str(payload.get("variant") or "standard").strip() or "standard",
            planner_model=str(payload.get("planner_model")).strip() if payload.get("planner_model") is not None else None,
            final_quality_guard=_normalize_final_quality_guard(payload.get("final_quality_guard")),
            final_quality_max_auto_continues=_coerce_optional_int(payload.get("final_quality_max_auto_continues")),
            enabled_tool_packs=[str(item) for item in enabled_tool_packs] if enabled_tool_packs is not None else None,
            repeat=max(1, int(payload.get("repeat", 1) or 1)),
            fresh_runtime=bool(payload.get("fresh_runtime", False)),
            fresh_session_per_case=bool(payload.get("fresh_session_per_case", True)),
            capture_prompt_snapshot=bool(payload.get("capture_prompt_snapshot", True)),
            task_board_armed_next_turn=bool(payload.get("task_board_armed_next_turn", False)),
            cases=cases,
            profile=str(payload.get("profile") or name).strip() or name,
            user_id=int(user_id_value) if user_id_value is not None else None,
        )


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _normalize_final_quality_guard(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"", "off", "none", "false", "disabled", "disable"}:
        return ""
    if raw in {"planner", "nli"}:
        return raw
    raise ValueError("final_quality_guard must be one of: planner, nli, off")


class EventRecorder:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.events: List[Dict[str, Any]] = []

    async def sink(self, event: Dict[str, Any]) -> None:
        self.events.append(
            {
                "ts_ms": round((time.perf_counter() - self.started) * 1000.0, 3),
                **self._sanitize_event(event),
            }
        )

    def _sanitize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(event or {})
        event_type = str(payload.get("type") or "unknown")
        if event_type == "assistant_delta":
            return {"type": event_type, "delta": str(payload.get("delta") or "")}
        if event_type == "reasoning_delta":
            return {"type": event_type, "delta": str(payload.get("delta") or "")}
        if event_type == "tool_use":
            result = payload.get("tool_result")
            result_preview = truncate_jsonable(result, limit=360)
            error_type = result.get("error_type") if isinstance(result, dict) else None
            return {
                "type": event_type,
                "tool_name": str(payload.get("tool_name") or ""),
                "tool_args": truncate_jsonable(payload.get("tool_args"), limit=200),
                "tool_result": result_preview,
                "result_error_type": str(error_type) if error_type else None,
                "duration_ms": float(payload.get("duration_ms") or 0.0),
            }
        if event_type == "status":
            return {"type": event_type, "message": str(payload.get("message") or "")}
        if event_type == "log":
            return {"type": event_type, "message": str(payload.get("message") or "")}
        if event_type == "auto_continue":
            return {
                "type": event_type,
                "reason": str(payload.get("reason") or ""),
                "action": str(payload.get("action") or ""),
                "scores": truncate_jsonable(payload.get("scores"), limit=400),
                "auto_continue_count": payload.get("auto_continue_count"),
                "auto_continue_limit": payload.get("auto_continue_limit"),
                "failed_obligation": truncate_jsonable(payload.get("failed_obligation"), limit=1000),
                "evidence_gap": truncate_jsonable(payload.get("evidence_gap"), limit=1500),
                "retry_instruction": truncate_jsonable(payload.get("retry_instruction"), limit=2000),
                "continuation_instruction": truncate_jsonable(payload.get("continuation_instruction"), limit=2000),
                "candidate_final_preview": truncate_jsonable(payload.get("candidate_final_preview"), limit=2000),
                "must_use_tool": payload.get("must_use_tool"),
            }
        if event_type == "task_board":
            return {
                "type": event_type,
                "summary": str(payload.get("summary") or ""),
                "board": truncate_jsonable(payload.get("board")),
            }
        if event_type == "model_context":
            return {
                "type": event_type,
                "kind": str(payload.get("kind") or ""),
                "content": truncate_jsonable(payload.get("content"), limit=3000),
            }
        return truncate_jsonable(payload)


def compute_stream_metrics(
    events: List[Dict[str, Any]],
    *,
    total_duration_ms: float,
    assistant_text: str,
) -> Dict[str, Any]:
    delta_events = [event for event in events if event.get("type") == "assistant_delta"]
    delta_times = [float(event["ts_ms"]) for event in delta_events]
    delta_text = "".join(str(event.get("delta") or "") for event in delta_events)
    reasoning_events = [event for event in events if event.get("type") == "reasoning_delta"]
    reasoning_text = "".join(str(event.get("delta") or "") for event in reasoning_events)
    tool_events = [event for event in events if event.get("type") == "tool_use"]
    tool_times = [float(event["ts_ms"]) for event in tool_events]

    gap_values = [
        round(delta_times[index] - delta_times[index - 1], 3)
        for index in range(1, len(delta_times))
    ]
    first_delta_ms = delta_times[0] if delta_times else None
    last_delta_ms = delta_times[-1] if delta_times else None
    first_tool_ms = tool_times[0] if tool_times else None

    return {
        "assistant_chars_final": len(assistant_text or ""),
        "assistant_chars_streamed": len(delta_text),
        "streamed_text": delta_text,
        "delta_count": len(delta_events),
        "reasoning_chars_streamed": len(reasoning_text),
        "reasoning_excerpt": reasoning_text[:1200],
        "time_to_first_delta_ms": first_delta_ms,
        "time_to_first_tool_ms": first_tool_ms,
        "longest_delta_gap_ms": max(gap_values) if gap_values else None,
        "avg_delta_gap_ms": round(statistics.mean(gap_values), 3) if gap_values else None,
        "stall_count_gt_750ms": sum(1 for gap in gap_values if gap > 750.0),
        "stall_count_gt_1500ms": sum(1 for gap in gap_values if gap > 1500.0),
        "final_delay_after_last_delta_ms": round(total_duration_ms - last_delta_ms, 3) if last_delta_ms is not None else None,
        "tool_call_count": len(tool_events),
        "tool_names": [str(event.get("tool_name") or "") for event in tool_events],
        "tool_calls": [
            {
                "tool_name": str(event.get("tool_name") or ""),
                "ts_ms": float(event.get("ts_ms") or 0.0),
                "duration_ms": float(event.get("duration_ms") or 0.0),
            }
            for event in tool_events
        ],
        "total_tool_runtime_ms": round(sum(float(event.get("duration_ms") or 0.0) for event in tool_events), 3),
    }


def analyze_turn(metrics: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    first_delta = metrics.get("time_to_first_delta_ms")
    longest_gap = metrics.get("longest_delta_gap_ms")
    final_delay = metrics.get("final_delay_after_last_delta_ms")
    delta_count = int(metrics.get("delta_count") or 0)
    tool_count = int(metrics.get("tool_call_count") or 0)

    if first_delta is None:
        notes.append("No streamed assistant deltas were observed before completion.")
    elif first_delta > 3000:
        notes.append(f"First streamed token arrived late ({first_delta:.0f}ms).")

    if longest_gap is not None and longest_gap > 1500:
        notes.append(f"Streaming stalled between chunks (worst gap {longest_gap:.0f}ms).")

    if final_delay is not None and final_delay > 4000:
        notes.append(f"Most text likely arrived early and completion lagged afterward ({final_delay:.0f}ms after last delta).")

    if delta_count <= 2 and metrics.get("assistant_chars_final"):
        notes.append("Response streamed in very few chunks, which often feels bursty instead of live.")

    if tool_count == 0:
        notes.append("No tool calls were made during the measured turn.")

    return notes


def _artifact_check_results(workspace: Path, checks: List[ArtifactCheck]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in checks:
        path = Path(check.path)
        resolved = (workspace / path).resolve() if not path.is_absolute() else path.resolve()
        result: Dict[str, Any] = {
            "path": check.path,
            "resolved_path": str(resolved),
            "must_exist": check.must_exist,
            "passed": True,
            "failures": [],
            "exists": resolved.exists(),
            "content_preview": None,
        }
        if check.must_exist and not resolved.exists():
            result["passed"] = False
            result["failures"].append("Artifact missing.")
            results.append(result)
            continue

        content = ""
        if resolved.exists() and resolved.is_file():
            try:
                content = resolved.read_text(encoding="utf-8")
            except Exception as exc:
                result["passed"] = False
                result["failures"].append(f"Unable to read artifact: {exc}")
                results.append(result)
                continue
            result["content_preview"] = truncate_jsonable(content, limit=320)

        normalized_content = normalize_phrase(content)
        for phrase in check.contains_all:
            if normalize_phrase(phrase) not in normalized_content:
                result["passed"] = False
                result["failures"].append(f"Missing artifact content: {phrase}")
        if check.contains_any:
            if not any(normalize_phrase(phrase) in normalized_content for phrase in check.contains_any):
                result["passed"] = False
                result["failures"].append(
                    "Artifact missing all accepted content variants: " + ", ".join(check.contains_any)
                )
        for phrase in check.not_contains:
            if normalize_phrase(phrase) in normalized_content:
                result["passed"] = False
                result["failures"].append(f"Artifact contains forbidden content: {phrase}")
        results.append(result)
    return results


def _session_artifact_records(*, user_id: int, session_id: str) -> List[Dict[str, Any]]:
    store = ChatArtifactStore(user_id=user_id, session_id=session_id)
    return [store.build_summary_view(record) for record in store.list_records(descending=True)[:20]]


def _ordered_tool_trace(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trace: List[Dict[str, Any]] = []
    for event in events:
        if event.get("type") != "tool_use":
            continue
        tool_result = event.get("tool_result")
        unsupported = str(event.get("result_error_type") or "") in UNSUPPORTED_TOOL_ERROR_TYPES
        trace.append(
            {
                "ts_ms": float(event.get("ts_ms") or 0.0),
                "tool_name": str(event.get("tool_name") or ""),
                "duration_ms": float(event.get("duration_ms") or 0.0),
                "tool_args": truncate_jsonable(event.get("tool_args"), limit=180),
                "result_preview": truncate_jsonable(tool_result, limit=240),
                "error_type": event.get("result_error_type"),
                "unsupported_attempt": unsupported,
            }
        )
    return trace


def _detect_fatal_error(assistant_text: str, runtime_result: Dict[str, Any]) -> Optional[Dict[str, str]]:
    combined = " ".join(
        [
            str(assistant_text or ""),
            json.dumps(runtime_result or {}, ensure_ascii=False, default=str),
        ]
    ).lower()
    for classification, patterns in FATAL_ERROR_PATTERNS.items():
        for pattern in patterns:
            if pattern in combined:
                return {
                    "classification": classification,
                    "message": f"Detected fatal {classification} signal: {pattern}",
                }
    return None


def _diagnostic_issue(
    *,
    code: str,
    category: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    evidence: Any = None,
    severity: str = "error",
) -> Dict[str, Any]:
    issue: Dict[str, Any] = {
        "code": code,
        "category": category,
        "severity": severity,
        "message": message,
    }
    if expected is not None:
        issue["expected"] = truncate_jsonable(expected, limit=320)
    if actual is not None:
        issue["actual"] = truncate_jsonable(actual, limit=320)
    if evidence is not None:
        issue["evidence"] = truncate_jsonable(evidence, limit=420)
    return issue


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _sequence_label(sequence: List[List[str]]) -> str:
    return " -> ".join("/".join(options) for options in sequence)


def _match_tool_sequence(tool_names: List[str], sequence: List[List[str]]) -> Optional[List[int]]:
    positions: List[int] = []
    cursor = 0
    for options in sequence:
        matched_index = None
        option_set = set(options)
        for index in range(cursor, len(tool_names)):
            if tool_names[index] in option_set:
                matched_index = index
                break
        if matched_index is None:
            return None
        positions.append(matched_index)
        cursor = matched_index + 1
    return positions


def _tool_content_failures(value: Any, check: ToolContentCheck) -> List[str]:
    normalized = normalize_phrase(_json_text(value))
    failures: List[str] = []
    for phrase in check.contains_all:
        if normalize_phrase(phrase) not in normalized:
            failures.append(f"missing '{phrase}'")
    if check.contains_any and not any(normalize_phrase(phrase) in normalized for phrase in check.contains_any):
        failures.append("missing one of " + ", ".join(repr(phrase) for phrase in check.contains_any))
    for phrase in check.not_contains:
        if normalize_phrase(phrase) in normalized:
            failures.append(f"contains forbidden '{phrase}'")
    return failures


def _content_check_issue(
    *,
    check: ToolContentCheck,
    trace: List[Dict[str, Any]],
    source_key: str,
    code: str,
    label: str,
) -> Optional[Dict[str, Any]]:
    candidates = [item for item in trace if item.get("tool_name") == check.tool_name]
    if not candidates:
        return _diagnostic_issue(
            code=f"{code}_tool_missing",
            category="tool-use",
            message=f"No `{check.tool_name}` call was available for {label} validation.",
            expected={"tool_name": check.tool_name},
            actual=[item.get("tool_name") for item in trace],
        )
    failures_by_call: List[Dict[str, Any]] = []
    for item in candidates:
        failures = _tool_content_failures(item.get(source_key), check)
        if not failures:
            return None
        failures_by_call.append(
            {
                "tool_name": item.get("tool_name"),
                "ts_ms": item.get("ts_ms"),
                "failures": failures,
                "value": item.get(source_key),
            }
        )
    return _diagnostic_issue(
        code=code,
        category="tool-use",
        message=f"`{check.tool_name}` {label} did not match the expected content.",
        expected={
            "contains_all": check.contains_all,
            "contains_any": check.contains_any,
            "not_contains": check.not_contains,
        },
        evidence=failures_by_call,
    )


def _failure_classification(issues: List[Dict[str, Any]]) -> str:
    categories = [str(issue.get("category") or "") for issue in issues]
    for category in [
        "quota",
        "infra",
        "artifact",
        "prompt-contract",
        "verification",
        "reasoning",
        "decision",
        "tool-use",
        "tooling",
        "efficiency",
        "timing",
    ]:
        if category in categories:
            return category
    return "behavior" if issues else "none"


def evaluate_expectations(
    *,
    assistant_text: str,
    metrics: Dict[str, Any],
    events: List[Dict[str, Any]],
    expectations: EvalExpectations,
    artifact_results: Optional[List[Dict[str, Any]]] = None,
    runtime_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    text_normalized = normalize_phrase(assistant_text)
    reasoning_text = "".join(str(event.get("delta") or "") for event in events if event.get("type") == "reasoning_delta")
    reasoning_normalized = normalize_phrase(reasoning_text)
    tool_names = list(metrics.get("tool_names") or [])
    tool_name_set = set(tool_names)
    accepted_any = set(str(name) for name in expectations.accepted_tool_names_any or [])
    any_tool_candidates = set(expectations.required_tools_any) | accepted_any
    ordered_trace = _ordered_tool_trace(events)
    unsupported_tool_attempts = sum(1 for item in ordered_trace if item.get("unsupported_attempt"))
    tool_error_count = sum(1 for item in ordered_trace if item.get("error_type"))
    artifact_results = list(artifact_results or [])

    fatal_error = _detect_fatal_error(assistant_text, runtime_result or {})
    if fatal_error:
        issues.append(
            _diagnostic_issue(
                code=f"fatal_{fatal_error['classification']}",
                category=fatal_error["classification"],
                severity="fatal",
                message=fatal_error["message"],
                evidence={"assistant_text": assistant_text, "runtime_result": runtime_result or {}},
            )
        )

    for phrase in expectations.required_phrases:
        if normalize_phrase(phrase) not in text_normalized:
            issues.append(
                _diagnostic_issue(
                    code="missing_required_phrase",
                    category="prompt-contract",
                    message=f"Missing required phrase: {phrase}",
                    expected=phrase,
                    actual=assistant_text,
                )
            )

    if expectations.required_phrases_any and not any(
        normalize_phrase(phrase) in text_normalized for phrase in expectations.required_phrases_any
    ):
        issues.append(
            _diagnostic_issue(
                code="missing_required_phrase_choice",
                category="prompt-contract",
                message="Missing all accepted phrase variants: " + ", ".join(expectations.required_phrases_any),
                expected=expectations.required_phrases_any,
                actual=assistant_text,
            )
        )

    for phrase in expectations.forbidden_phrases:
        if normalize_phrase(phrase) in text_normalized:
            issues.append(
                _diagnostic_issue(
                    code="forbidden_phrase",
                    category="prompt-contract",
                    message=f"Found forbidden phrase: {phrase}",
                    expected=f"Do not include: {phrase}",
                    actual=assistant_text,
                )
            )

    for phrase in expectations.final_answer_forbidden_phrases:
        if normalize_phrase(phrase) in text_normalized:
            issues.append(
                _diagnostic_issue(
                    code="final_answer_forbidden_phrase",
                    category="prompt-contract",
                    message=f"Final answer contains forbidden phrase: {phrase}",
                    expected=f"Do not include: {phrase}",
                    actual=assistant_text,
                )
            )

    for phrase in expectations.required_reasoning_phrases:
        if normalize_phrase(phrase) not in reasoning_normalized:
            issues.append(
                _diagnostic_issue(
                    code="missing_required_reasoning_phrase",
                    category="reasoning",
                    message=f"Missing required reasoning phrase: {phrase}",
                    expected=phrase,
                    actual=reasoning_text,
                )
            )

    for phrase in expectations.forbidden_reasoning_phrases:
        if normalize_phrase(phrase) in reasoning_normalized:
            issues.append(
                _diagnostic_issue(
                    code="forbidden_reasoning_phrase",
                    category="reasoning",
                    message=f"Reasoning contains forbidden phrase: {phrase}",
                    expected=f"Do not include: {phrase}",
                    actual=reasoning_text,
                )
            )

    for tool_name in expectations.required_tools_all:
        if tool_name not in tool_name_set:
            issues.append(
                _diagnostic_issue(
                    code="missing_required_tool",
                    category="decision",
                    message=f"Required tool was not used: {tool_name}",
                    expected=tool_name,
                    actual=tool_names,
                )
            )

    if any_tool_candidates and not any(tool_name in tool_name_set for tool_name in any_tool_candidates):
        issues.append(
            _diagnostic_issue(
                code="missing_required_tool_choice",
                category="decision",
                message=f"Expected at least one of these tools: {', '.join(sorted(any_tool_candidates))}",
                expected=sorted(any_tool_candidates),
                actual=tool_names,
            )
        )

    for tool_name in expectations.forbidden_tools:
        if tool_name in tool_name_set:
            issues.append(
                _diagnostic_issue(
                    code="forbidden_tool_used",
                    category="decision",
                    message=f"Forbidden tool was used: {tool_name}",
                    expected=f"Do not use: {tool_name}",
                    actual=tool_names,
                    evidence=[item for item in ordered_trace if item.get("tool_name") == tool_name],
                )
            )

    expected_tool_sequence = _coerce_tool_sequence(expectations.required_tool_sequence)
    if expected_tool_sequence:
        sequence_positions = _match_tool_sequence(tool_names, expected_tool_sequence)
        if sequence_positions is None:
            issues.append(
                _diagnostic_issue(
                    code="missing_required_tool_sequence",
                    category="decision",
                    message=f"Required tool sequence was not observed: {_sequence_label(expected_tool_sequence)}",
                    expected=expected_tool_sequence,
                    actual=tool_names,
                    evidence=ordered_trace,
                )
            )

    for order_check in expectations.required_tool_order:
        before_positions = [index for index, name in enumerate(tool_names) if name == order_check.before]
        after_positions = [index for index, name in enumerate(tool_names) if name == order_check.after]
        if not before_positions or not after_positions:
            issues.append(
                _diagnostic_issue(
                    code="tool_order_missing_tool",
                    category="decision",
                    message=f"Could not verify tool order `{order_check.before}` before `{order_check.after}` because one tool was missing.",
                    expected={"before": order_check.before, "after": order_check.after},
                    actual=tool_names,
                )
            )
        elif min(before_positions) > max(after_positions):
            issues.append(
                _diagnostic_issue(
                    code="wrong_tool_order",
                    category="decision",
                    message=f"Tool order was wrong: `{order_check.before}` should occur before `{order_check.after}`.",
                    expected={"before": order_check.before, "after": order_check.after},
                    actual=tool_names,
                    evidence=ordered_trace,
                )
            )

    for check in expectations.tool_arg_checks:
        issue = _content_check_issue(
            check=check,
            trace=ordered_trace,
            source_key="tool_args",
            code="tool_args_mismatch",
            label="arguments",
        )
        if issue:
            issues.append(issue)

    for check in expectations.tool_result_checks:
        issue = _content_check_issue(
            check=check,
            trace=ordered_trace,
            source_key="result_preview",
            code="tool_result_mismatch",
            label="result",
        )
        if issue:
            issues.append(issue)

    if expectations.max_unsupported_tool_attempts is not None and unsupported_tool_attempts > expectations.max_unsupported_tool_attempts:
        issues.append(
            _diagnostic_issue(
                code="unsupported_tool_attempt_limit_exceeded",
                category="decision",
                message=f"Unsupported tool attempts {unsupported_tool_attempts} exceeded limit {expectations.max_unsupported_tool_attempts}",
                expected=expectations.max_unsupported_tool_attempts,
                actual=unsupported_tool_attempts,
                evidence=[item for item in ordered_trace if item.get("unsupported_attempt")],
            )
        )

    if expectations.max_tool_errors is not None and tool_error_count > expectations.max_tool_errors:
        issues.append(
            _diagnostic_issue(
                code="tool_error_limit_exceeded",
                category="tooling",
                message=f"Tool errors {tool_error_count} exceeded limit {expectations.max_tool_errors}",
                expected=expectations.max_tool_errors,
                actual=tool_error_count,
                evidence=[item for item in ordered_trace if item.get("error_type")],
            )
        )

    tool_call_count = int(metrics.get("tool_call_count") or len(tool_names))
    if expectations.min_tool_calls is not None and tool_call_count < expectations.min_tool_calls:
        issues.append(
            _diagnostic_issue(
                code="too_few_tool_calls",
                category="decision",
                message=f"Tool call count {tool_call_count} was below minimum {expectations.min_tool_calls}",
                expected=expectations.min_tool_calls,
                actual=tool_call_count,
                evidence=tool_names,
            )
        )
    if expectations.max_tool_calls is not None and tool_call_count > expectations.max_tool_calls:
        issues.append(
            _diagnostic_issue(
                code="too_many_tool_calls",
                category="efficiency",
                message=f"Tool call count {tool_call_count} exceeded maximum {expectations.max_tool_calls}",
                expected=expectations.max_tool_calls,
                actual=tool_call_count,
                evidence=tool_names,
            )
        )

    for tool_name, limit in expectations.max_tool_calls_by_name.items():
        count = sum(1 for name in tool_names if name == tool_name)
        if count > int(limit):
            issues.append(
                _diagnostic_issue(
                    code="tool_call_limit_exceeded",
                    category="verification",
                    message=f"`{tool_name}` was called {count} times, exceeding limit {int(limit)}",
                    expected={tool_name: int(limit)},
                    actual={tool_name: count},
                    evidence=[item for item in ordered_trace if item.get("tool_name") == tool_name],
                )
            )

    total_duration_ms = float(metrics.get("total_duration_ms") or 0.0)
    first_delta = metrics.get("time_to_first_delta_ms")
    first_tool = metrics.get("time_to_first_tool_ms")
    longest_gap = metrics.get("longest_delta_gap_ms")

    if expectations.max_total_duration_ms is not None and total_duration_ms > expectations.max_total_duration_ms:
        issues.append(
            _diagnostic_issue(
                code="total_duration_limit_exceeded",
                category="timing",
                message=f"Total duration {total_duration_ms:.0f}ms exceeded limit {expectations.max_total_duration_ms:.0f}ms",
                expected=expectations.max_total_duration_ms,
                actual=total_duration_ms,
            )
        )
    if expectations.max_time_to_first_delta_ms is not None:
        if first_delta is None or first_delta > expectations.max_time_to_first_delta_ms:
            issues.append(
                _diagnostic_issue(
                    code="first_delta_limit_exceeded",
                    category="timing",
                    message=f"Time to first delta {first_delta if first_delta is not None else 'none'} exceeded limit {expectations.max_time_to_first_delta_ms:.0f}ms",
                    expected=expectations.max_time_to_first_delta_ms,
                    actual=first_delta,
                )
            )
    if expectations.max_time_to_first_tool_ms is not None:
        if first_tool is None or first_tool > expectations.max_time_to_first_tool_ms:
            issues.append(
                _diagnostic_issue(
                    code="first_tool_limit_exceeded",
                    category="timing",
                    message=f"Time to first tool {first_tool if first_tool is not None else 'none'} exceeded limit {expectations.max_time_to_first_tool_ms:.0f}ms",
                    expected=expectations.max_time_to_first_tool_ms,
                    actual=first_tool,
                )
            )
    if expectations.max_longest_delta_gap_ms is not None:
        if longest_gap is None or longest_gap > expectations.max_longest_delta_gap_ms:
            issues.append(
                _diagnostic_issue(
                    code="delta_gap_limit_exceeded",
                    category="timing",
                    message=f"Longest delta gap {longest_gap if longest_gap is not None else 'none'} exceeded limit {expectations.max_longest_delta_gap_ms:.0f}ms",
                    expected=expectations.max_longest_delta_gap_ms,
                    actual=longest_gap,
                )
            )

    artifact_failures: List[str] = []
    for artifact in artifact_results:
        if artifact.get("passed", True):
            continue
        for failure in artifact.get("failures", []):
            message = f"{artifact.get('path')}: {failure}"
            artifact_failures.append(message)
            issues.append(
                _diagnostic_issue(
                    code="artifact_check_failed",
                    category="artifact",
                    message=message,
                    expected=artifact.get("path"),
                    actual=artifact,
                )
            )

    failures = [str(issue.get("message") or "") for issue in issues]
    classification = _failure_classification(issues)
    failure_categories = sorted({str(issue.get("category") or "") for issue in issues if issue.get("category")})

    return {
        "passed": not failures,
        "failures": failures,
        "issues": issues,
        "failure_classification": classification,
        "failure_categories": failure_categories,
        "unsupported_tool_attempts": unsupported_tool_attempts,
        "tool_error_count": tool_error_count,
        "fatal_error": fatal_error,
    }


def summarize_case_runs(case_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics_list = [run.get("metrics", {}) for run in case_runs]
    numeric_fields = [
        "total_duration_ms",
        "time_to_first_delta_ms",
        "time_to_first_tool_ms",
        "longest_delta_gap_ms",
        "avg_delta_gap_ms",
        "final_delay_after_last_delta_ms",
    ]
    summary: Dict[str, Any] = {
        "repeat_count": len(case_runs),
        "pass_count": sum(1 for run in case_runs if run.get("expectation_result", {}).get("passed")),
        "fail_count": sum(1 for run in case_runs if not run.get("expectation_result", {}).get("passed", True)),
        "failure_classifications": sorted(
            {
                str(run.get("expectation_result", {}).get("failure_classification") or "")
                for run in case_runs
                if run.get("expectation_result", {}).get("failure_classification") not in {None, "", "none"}
            }
        ),
        "failure_categories": sorted(
            {
                str(category)
                for run in case_runs
                for category in run.get("expectation_result", {}).get("failure_categories", []) or []
                if str(category).strip()
            }
        ),
        "issue_codes": sorted(
            {
                str(issue.get("code") or "")
                for run in case_runs
                for issue in run.get("expectation_result", {}).get("issues", []) or []
                if str(issue.get("code") or "").strip()
            }
        ),
    }
    for field_name in numeric_fields:
        values = [
            float(metrics[field_name])
            for metrics in metrics_list
            if metrics.get(field_name) is not None
        ]
        if values:
            summary[f"avg_{field_name}"] = round(statistics.mean(values), 3)
            summary[f"max_{field_name}"] = round(max(values), 3)
    summary["tool_names_union"] = sorted(
        {
            tool_name
            for metrics in metrics_list
            for tool_name in metrics.get("tool_names", []) or []
        }
    )
    return summary


def build_markdown_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Agent Eval Report: {report['config']['name']}")
    lines.append("")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append(f"- Profile: `{report['config']['profile']}`")
    lines.append(f"- Runtime home: `{report['runtime_home']}`")
    lines.append(f"- Workspace: `{report['config']['workspace']}`")
    lines.append(f"- Model default: `{report['config']['model']}` / `{report['config']['variant']}`")
    lines.append(f"- Planner default: `{report['config'].get('planner_model') or 'automatic'}`")
    lines.append(
        "- Final quality guard: `{mode}` / max auto-continues `{limit}`".format(
            mode=report["config"].get("effective_final_quality_guard") or "off",
            limit=report["config"].get("effective_final_quality_max_auto_continues") or "default",
        )
    )
    lines.append(f"- Repeat count: `{report['config']['repeat']}`")
    lines.append("")
    lines.append("## Case Summary")
    lines.append("")
    lines.append("| Case | Pass | Avg total (ms) | Avg first delta (ms) | Avg first tool (ms) | Worst gap (ms) | Tools used | Failures |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for case_report in report["cases"]:
        summary = case_report["summary"]
        lines.append(
            "| {name} | {pass_count}/{repeat_count} | {total} | {first_delta} | {first_tool} | {gap} | {tools} | {failures} |".format(
                name=case_report["name"],
                pass_count=summary["pass_count"],
                repeat_count=summary["repeat_count"],
                total=_format_optional_metric(summary.get("avg_total_duration_ms")),
                first_delta=_format_optional_metric(summary.get("avg_time_to_first_delta_ms")),
                first_tool=_format_optional_metric(summary.get("avg_time_to_first_tool_ms")),
                gap=_format_optional_metric(summary.get("max_longest_delta_gap_ms")),
                tools=", ".join(summary.get("tool_names_union", [])) or "none",
                failures=", ".join(summary.get("failure_classifications", [])) or "none",
            )
        )
    lines.append("")
    for case_report in report["cases"]:
        lines.append(f"## {case_report['name']}")
        lines.append("")
        if case_report.get("notes"):
            lines.append(case_report["notes"])
            lines.append("")
        for run in case_report["runs"]:
            metrics = run["metrics"]
            expectation_result = run["expectation_result"]
            lines.append(f"### Repeat {run['repeat_index'] + 1}")
            lines.append("")
            lines.append(f"- Prompt: `{run['prompt']}`")
            lines.append(f"- Passed expectations: `{'yes' if expectation_result['passed'] else 'no'}`")
            lines.append(f"- Failure classification: `{expectation_result.get('failure_classification', 'none')}`")
            if expectation_result.get("failure_categories"):
                lines.append(f"- Failure categories: `{', '.join(expectation_result.get('failure_categories', []))}`")
            lines.append(f"- Total duration: `{_format_metric_with_unit(metrics.get('total_duration_ms'), 'ms')}`")
            lines.append(f"- Time to first delta: `{_format_metric_with_unit(metrics.get('time_to_first_delta_ms'), 'ms')}`")
            lines.append(f"- Time to first tool: `{_format_metric_with_unit(metrics.get('time_to_first_tool_ms'), 'ms')}`")
            lines.append(f"- Longest delta gap: `{_format_metric_with_unit(metrics.get('longest_delta_gap_ms'), 'ms')}`")
            lines.append(f"- Tool sequence: `{', '.join(metrics.get('tool_names', [])) or 'none'}`")
            prompt_snapshot = run.get("prompt_snapshot") or {}
            if prompt_snapshot:
                lines.append(f"- Active tool packs: `{', '.join(prompt_snapshot.get('active_tool_packs', []) or []) or 'none'}`")
                lines.append(f"- Allowed tools: `{', '.join(prompt_snapshot.get('allowed_tool_names', []) or []) or 'none'}`")
            if run.get("reasoning_excerpt"):
                lines.append("- Reasoning excerpt:")
                lines.append("")
                lines.append("```text")
                lines.append(str(run["reasoning_excerpt"]))
                lines.append("```")
            if run.get("ordered_tool_trace"):
                lines.append("- Ordered tool trace:")
                for item in run["ordered_tool_trace"]:
                    lines.append(
                        f"  - `{item['tool_name']}` at {item['ts_ms']:.1f}ms "
                        f"({item['duration_ms']:.1f}ms) -> {item.get('result_preview')!r}"
                    )
            if run.get("artifact_results"):
                lines.append("- Artifact verification:")
                for artifact in run["artifact_results"]:
                    status = "pass" if artifact.get("passed") else "fail"
                    lines.append(f"  - `{artifact['path']}`: {status}")
                    for failure in artifact.get("failures", []):
                        lines.append(f"    - {failure}")
            if run.get("artifact_records"):
                lines.append("- Saved chat artifacts:")
                for artifact in run["artifact_records"]:
                    lines.append(
                        f"  - `{artifact['artifact_id']}` · {artifact['artifact_kind']} · {artifact['title']}"
                    )
            if run.get("analysis_notes"):
                lines.append("- Analysis:")
                for note in run["analysis_notes"]:
                    lines.append(f"  - {note}")
            if expectation_result["failures"]:
                lines.append("- Expectation failures:")
                for failure in expectation_result["failures"]:
                    lines.append(f"  - {failure}")
            if expectation_result.get("issues"):
                lines.append("- Diagnostic issues:")
                for issue in expectation_result["issues"]:
                    lines.append(
                        "  - `{code}` · `{category}` · {message}".format(
                            code=issue.get("code", "unknown"),
                            category=issue.get("category", "behavior"),
                            message=issue.get("message", ""),
                        )
                    )
                    if issue.get("expected") is not None:
                        lines.append(f"    - expected: `{issue.get('expected')}`")
                    if issue.get("actual") is not None:
                        lines.append(f"    - actual: `{issue.get('actual')}`")
                    if issue.get("evidence") is not None:
                        lines.append(f"    - evidence: `{issue.get('evidence')}`")
            lines.append("- Final assistant answer:")
            lines.append("")
            lines.append("```text")
            lines.append(str(run.get("assistant_text") or ""))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _format_optional_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1f}"


def _format_metric_with_unit(value: Any, unit: str) -> str:
    formatted = _format_optional_metric(value)
    if formatted == "n/a":
        return formatted
    return f"{formatted}{unit}"


class AgentEvalHarness:
    def __init__(
        self,
        *,
        repo_root: Path,
        config: EvalConfig,
        runtime_home: Path,
        output_root: Path,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.config = config
        self.runtime_home = runtime_home.resolve()
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.user_id = int(config.user_id or stable_eval_user_id(config.profile))
        self._shared_session_id: Optional[str] = None
        self._mods: Dict[str, Any] = {}

    def prepare_environment(self) -> None:
        if self.config.fresh_runtime and self.runtime_home.exists():
            shutil.rmtree(self.runtime_home)
        self.runtime_home.mkdir(parents=True, exist_ok=True)
        os.environ["EMPLOAI_HOME"] = str(self.runtime_home)
        os.environ["DEFAULT_WORKSPACE"] = str(self.config.workspace)
        os.environ["HEADLESS"] = "false"
        try:
            from dotenv import load_dotenv

            load_dotenv(self.repo_root / ".env", override=False)
        except Exception:
            pass
        self._configure_final_quality_guard_env()
        self._configure_isolated_scheduler()

    def _configure_final_quality_guard_env(self) -> None:
        if self.config.final_quality_guard is not None:
            if self.config.final_quality_guard:
                os.environ["EMPLOAI_FINAL_QUALITY_GUARD"] = self.config.final_quality_guard
            else:
                os.environ.pop("EMPLOAI_FINAL_QUALITY_GUARD", None)
        if self.config.final_quality_max_auto_continues is not None:
            os.environ["EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES"] = str(
                max(0, int(self.config.final_quality_max_auto_continues))
            )

    def _configure_isolated_scheduler(self) -> None:
        try:
            from single_agent import cron_scheduler

            cron_scheduler._global_scheduler = cron_scheduler.create_scheduler(
                job_store=str((self.runtime_home / "jobs.json").resolve())
            )
        except Exception:
            pass

    def _load_modules(self) -> None:
        if self._mods:
            return
        from mobile_app.backend.runtime import (
            _conversational_turn_guard,
            _kickstart_prelude,
            _screen_observation_contract,
            _task_execution_contract,
            run_app_chat_turn,
        )
        from mobile_app.backend.session_bridge import AppSessionBridge
        from shared.channel_runtime import _memory_context
        from shared.multi_chat_orchestrator import _ORCHESTRATORS
        from shared.task_intent import (
            is_screen_observation_message,
            is_task_like_message,
            request_requires_tool_evidence,
        )
        from shared.tool_packs import (
            default_enabled_tool_packs,
            normalize_enabled_tool_packs,
            tools_for_enabled_packs,
        )
        from telegram_bot import telegram_session_state as tg_state
        from telegram_bot.telegram_unified_agent import build_unified_system_prompt

        self._mods = {
            "AppSessionBridge": AppSessionBridge,
            "build_unified_system_prompt": build_unified_system_prompt,
            "default_enabled_tool_packs": default_enabled_tool_packs,
            "normalize_enabled_tool_packs": normalize_enabled_tool_packs,
            "tools_for_enabled_packs": tools_for_enabled_packs,
            "is_screen_observation_message": is_screen_observation_message,
            "is_task_like_message": is_task_like_message,
            "request_requires_tool_evidence": request_requires_tool_evidence,
            "_memory_context": _memory_context,
            "_kickstart_prelude": _kickstart_prelude,
            "_task_execution_contract": _task_execution_contract,
            "_conversational_turn_guard": _conversational_turn_guard,
            "_screen_observation_contract": _screen_observation_contract,
            "run_app_chat_turn": run_app_chat_turn,
            "tg_state": tg_state,
            "_ORCHESTRATORS": _ORCHESTRATORS,
        }

    def _clear_runtime_caches(self) -> None:
        self._load_modules()
        tg_state = self._mods["tg_state"]
        tg_state.user_sessions.pop(self.user_id, None)
        self._mods["_ORCHESTRATORS"].pop(self.user_id, None)
        self._shared_session_id = None

    def _generated_workspace_root(self) -> Path:
        return (self.repo_root / "test_outputs" / "agent_eval" / "workspaces").resolve()

    def _is_generated_eval_workspace(self, workspace: Path) -> bool:
        try:
            workspace.resolve().relative_to(self._generated_workspace_root())
            return True
        except Exception:
            return False

    def _clean_generated_workspace(self, workspace: Path) -> None:
        """Remove prior case artifacts from generated eval workspaces only."""
        workspace = workspace.resolve()
        if not self._is_generated_eval_workspace(workspace):
            return
        self._cleanup_workspace_processes(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        for child in list(workspace.iterdir()):
            for attempt in range(5):
                try:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    self._cleanup_workspace_processes(workspace)
                    time.sleep(0.5)

    def _kill_process_tree(self, pid: int) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            else:
                os.kill(int(pid), 15)
        except Exception:
            pass

    def _cleanup_background_commands(self, runtime: Any) -> None:
        session = getattr(runtime, "session", None)
        executor = getattr(session, "tool_executor", None) or getattr(runtime, "tool_executor", None)
        commands = dict(getattr(executor, "_background_commands", {}) or {})
        for entry in commands.values():
            proc = entry.get("process") if isinstance(entry, dict) else None
            pid = getattr(proc, "pid", None)
            if pid:
                self._kill_process_tree(int(pid))
            elif proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        if executor is not None and hasattr(executor, "_background_commands"):
            try:
                executor._background_commands.clear()
            except Exception:
                pass

    def _cleanup_workspace_processes(self, workspace: Path) -> None:
        if os.name != "nt":
            return
        workspace_text = str(workspace.resolve())
        script = (
            "$workspace = @'\n"
            f"{workspace_text}\n"
            "'@\n"
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($workspace) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\n"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            time.sleep(0.5)
        except Exception:
            pass

    def _clear_eval_clipboard(self) -> bool:
        if os.name != "nt":
            return False
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ''"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return True
        except Exception:
            return False

    def _eval_desktop_cleanup_action(self, title: str) -> Optional[str]:
        normalized = " ".join(str(title or "").split())
        lowered = normalized.lower()
        if not lowered:
            return None
        if lowered == "shut down windows":
            return "escape"
        if lowered in {"open", "run", "spotify", "calculator"}:
            return "close"
        if "notepad" in lowered and "untitled" in lowered:
            return "close"
        return None

    def _cleanup_eval_desktop_surface(self) -> List[str]:
        """Close or dismiss known scratch windows left by eval GUI tasks."""
        if os.name != "nt":
            return []
        actions: List[str] = []
        if self._clear_eval_clipboard():
            actions.append("clear:clipboard")
        try:
            from pywinauto import Desktop
        except Exception:
            return actions

        try:
            desktop = Desktop(backend="uia")
        except Exception:
            return actions

        for _ in range(3):
            changed = False
            try:
                windows = list(desktop.windows())
            except Exception:
                break
            for win in windows:
                try:
                    title = str(win.window_text() or "").strip()
                except Exception:
                    continue
                action = self._eval_desktop_cleanup_action(title)
                if not action:
                    continue
                try:
                    win.set_focus()
                    time.sleep(0.1)
                    if action == "escape":
                        win.type_keys("{ESC}")
                        actions.append(f"escape:{title}")
                    else:
                        win.close()
                        actions.append(f"close:{title}")
                    changed = True
                    time.sleep(0.2)
                except Exception:
                    continue
            if not changed:
                break
        return actions

    def _cleanup_runtime_surface(self, runtime: Any) -> None:
        if runtime is None:
            return
        self._cleanup_background_commands(runtime)
        session = getattr(runtime, "session", None)
        for owner in (runtime, session):
            if owner is None:
                continue
            for attr in ("browser_tool", "extension_tool"):
                tool = getattr(owner, attr, None)
                stop = getattr(tool, "stop", None) or getattr(tool, "shutdown", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        pass
                if hasattr(owner, attr):
                    try:
                        setattr(owner, attr, None)
                    except Exception:
                        pass

    def _normalize_enabled_tool_packs(self, value: Optional[List[str]]) -> List[str]:
        self._load_modules()
        packs = self._mods["normalize_enabled_tool_packs"](value or [])
        if not packs:
            packs = self._mods["default_enabled_tool_packs"]()
        return list(packs)

    def _resolve_workspace(self, case: EvalCase) -> Path:
        raw = case.workspace or str(self.config.workspace)
        candidate = Path(raw)
        resolved = (self.repo_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(f"Workspace does not exist: {resolved}")
        return resolved

    def _bridge_for_workspace(self, workspace: Path):
        self._load_modules()
        bridge_cls = self._mods["AppSessionBridge"]
        return bridge_cls(user_id=self.user_id, workspace=workspace)

    def _session_defaults_for_case(self, case: EvalCase) -> Dict[str, Any]:
        return {
            "model": case.model or self.config.model,
            "variant": case.variant or self.config.variant,
            "planner_model": case.planner_model if case.planner_model is not None else self.config.planner_model,
            "enabled_tool_packs": self._normalize_enabled_tool_packs(
                case.enabled_tool_packs if case.enabled_tool_packs is not None else self.config.enabled_tool_packs
            ),
            "task_board_armed_next_turn": (
                case.task_board_armed_next_turn
                if case.task_board_armed_next_turn is not None
                else self.config.task_board_armed_next_turn
            ),
        }

    def _configure_runtime_session(self, runtime: Any, *, workspace: Path, case: EvalCase) -> None:
        defaults = self._session_defaults_for_case(case)
        runtime.set_workspace(workspace)
        runtime.current_model = defaults["model"]
        runtime.current_variant = defaults["variant"]
        runtime.planner_model = defaults["planner_model"]
        runtime.enabled_tool_packs = list(defaults["enabled_tool_packs"])
        runtime.task_board_armed_next_turn = bool(defaults["task_board_armed_next_turn"])
        if getattr(runtime, "session", None) is not None:
            runtime.session.workspace = str(workspace)
            runtime.session.model = runtime.current_model
            runtime.session.variant = runtime.current_variant
            runtime.session.planner_model = runtime.planner_model
            runtime.session.enabled_tool_packs = list(runtime.enabled_tool_packs)
            runtime.session.task_board_armed_next_turn = bool(runtime.task_board_armed_next_turn)

        async def _noop_send(_text: str) -> None:
            return None

        runtime.bind_telegram_runtime = lambda _app, loop=None: None
        runtime._resolved_telegram_bot = lambda: None
        runtime._safe_send_bot_message = _noop_send
        runtime._app = None
        runtime._loop = None
        runtime.save_session()

    def _build_prompt_snapshot(self, runtime: Any, *, user_message: str, active_tool_packs: List[str]) -> Dict[str, Any]:
        if not self.config.capture_prompt_snapshot:
            return {}
        screen_observation_turn = self._mods["is_screen_observation_message"](user_message)
        task_like_turn = screen_observation_turn or self._mods["is_task_like_message"](user_message)
        tool_evidence_turn = self._mods["request_requires_tool_evidence"](user_message)
        prelude_messages: List[Dict[str, Any]] = []
        if tool_evidence_turn and len(getattr(runtime, "chat_history", []) or []) <= 3:
            prelude_messages.extend(self._mods["_kickstart_prelude"](active_tool_packs))
        system_messages: List[Dict[str, Any]] = []
        if screen_observation_turn:
            system_messages.append(self._mods["_screen_observation_contract"](active_tool_packs))
        if tool_evidence_turn:
            system_messages.append(self._mods["_task_execution_contract"](runtime, active_tool_packs))
        if not tool_evidence_turn or not task_like_turn:
            system_messages.append(self._mods["_conversational_turn_guard"]())
        skills_index = ""
        active_skills_context = ""
        if getattr(runtime, "skill_registry", None):
            skills_index = f"\n\n{runtime.skill_registry.get_skills_index()}"
            if getattr(runtime, "active_skills", None):
                active_skills_context = (
                    "\n\n# LOADED SPECIALIZED SKILLS\n"
                    f"{runtime.skill_registry.get_active_skills_context(runtime.active_skills)}"
                )
        memory_context = self._mods["_memory_context"](runtime)
        custom_system_prompt = self._mods["build_unified_system_prompt"](
            runtime,
            memory_context=memory_context,
            skills_index=skills_index,
            active_skills_context=active_skills_context,
        )
        allowed_tool_names = sorted(self._mods["tools_for_enabled_packs"](active_tool_packs))
        return {
            "task_like_turn": bool(task_like_turn),
            "screen_observation_turn": bool(screen_observation_turn),
            "tool_evidence_turn": bool(tool_evidence_turn),
            "active_tool_packs": list(active_tool_packs),
            "allowed_tool_names": allowed_tool_names,
            "system_messages": system_messages,
            "prelude_messages": prelude_messages,
            "system_prompt": custom_system_prompt,
        }

    async def _run_one_turn(
        self,
        *,
        bridge: Any,
        runtime: Any,
        text: str,
        measure: bool,
    ) -> Dict[str, Any]:
        self._load_modules()
        session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip()
        if not session_id:
            raise RuntimeError("Runtime session is missing an active session id.")
        lease = await bridge.orchestrator.prepare_turn(session_id, origin_channel="app")
        if lease.busy:
            raise RuntimeError(lease.error or "Session is already busy.")
        runtime._active_tool_packs_for_current_run = list(lease.active_tool_packs)
        recorder = EventRecorder()
        prompt_snapshot = self._build_prompt_snapshot(runtime, user_message=text, active_tool_packs=list(lease.active_tool_packs))
        started = time.perf_counter()
        try:
            result = await self._mods["run_app_chat_turn"](
                runtime,
                user_message=text,
                source_format="app_text",
                interrupt_policy="none",
                log_callback=recorder.sink if measure else None,
            )
        finally:
            await bridge.orchestrator.complete_turn(lease)
            runtime._active_tool_packs_for_current_run = []
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        assistant_text = str(result.get("assistant_text") or "")
        metrics = compute_stream_metrics(
            recorder.events if measure else [],
            total_duration_ms=elapsed_ms,
            assistant_text=assistant_text,
        )
        metrics["total_duration_ms"] = elapsed_ms
        return {
            "result": result,
            "assistant_text": assistant_text,
            "events": recorder.events if measure else [],
            "metrics": metrics,
            "prompt_snapshot": prompt_snapshot,
        }

    async def _run_case_repeat(self, case: EvalCase, *, repeat_index: int) -> Dict[str, Any]:
        workspace = self._resolve_workspace(case)
        pre_case_desktop_cleanup = self._cleanup_eval_desktop_surface()
        self._clean_generated_workspace(workspace)
        bridge = self._bridge_for_workspace(workspace)
        use_fresh_session = case.fresh_session if case.fresh_session is not None else self.config.fresh_session_per_case
        if use_fresh_session or not self._shared_session_id:
            session = bridge.create_session(
                name=f"Eval {case.name} #{repeat_index + 1}",
                workspace=workspace,
                enabled_tool_packs=self._session_defaults_for_case(case)["enabled_tool_packs"],
            )
            session_id = str(session.id)
            if not use_fresh_session:
                self._shared_session_id = session_id
        else:
            session_id = str(self._shared_session_id)
            bridge.activate_session(session_id)
        runtime = bridge.load_runtime_session(session_id)
        try:
            self._configure_runtime_session(runtime, workspace=workspace, case=case)

            for warmup in case.setup_messages:
                await self._run_one_turn(bridge=bridge, runtime=runtime, text=warmup, measure=False)

            turn_report = await self._run_one_turn(bridge=bridge, runtime=runtime, text=case.prompt, measure=True)
            metrics = turn_report["metrics"]
            artifact_results = _artifact_check_results(workspace, case.expectations.artifact_checks)
            expectation_result = evaluate_expectations(
                assistant_text=turn_report["assistant_text"],
                metrics=metrics,
                events=turn_report["events"],
                expectations=case.expectations,
                artifact_results=artifact_results,
                runtime_result={
                    key: truncate_jsonable(value, limit=400)
                    for key, value in dict(turn_report["result"]).items()
                    if key not in {"assistant_text", "raw_response"}
                },
            )
            ordered_trace = _ordered_tool_trace(turn_report["events"])
            artifact_records = _session_artifact_records(user_id=self.user_id, session_id=session_id)
            return {
                "repeat_index": repeat_index,
                "session_id": session_id,
                "workspace": str(workspace),
                "prompt": case.prompt,
                "setup_messages": list(case.setup_messages),
                "pre_case_desktop_cleanup": list(pre_case_desktop_cleanup),
                "assistant_text": turn_report["assistant_text"],
                "metrics": metrics,
                "events": turn_report["events"],
                "prompt_snapshot": turn_report["prompt_snapshot"],
                "analysis_notes": analyze_turn(metrics),
                "reasoning_excerpt": metrics.get("reasoning_excerpt") or "",
                "ordered_tool_trace": ordered_trace,
                "artifact_results": artifact_results,
                "artifact_records": artifact_records,
                "expectation_result": expectation_result,
                "runtime_result": {
                    key: truncate_jsonable(value, limit=400)
                    for key, value in dict(turn_report["result"]).items()
                    if key not in {"assistant_text", "raw_response"}
                },
            }
        finally:
            self._cleanup_runtime_surface(runtime)
            self._cleanup_workspace_processes(workspace)
            self._cleanup_eval_desktop_surface()

    async def run(self) -> Dict[str, Any]:
        self.prepare_environment()
        self._load_modules()
        self._clear_runtime_caches()

        run_dir = self.output_root / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{self.config.profile}"
        run_dir.mkdir(parents=True, exist_ok=True)
        report: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_home": str(self.runtime_home),
            "output_dir": str(run_dir),
            "config": {
                "name": self.config.name,
                "profile": self.config.profile,
                "workspace": str(self.config.workspace),
                "model": self.config.model,
                "variant": self.config.variant,
                "planner_model": self.config.planner_model,
                "final_quality_guard": self.config.final_quality_guard,
                "final_quality_max_auto_continues": self.config.final_quality_max_auto_continues,
                "effective_final_quality_guard": os.getenv("EMPLOAI_FINAL_QUALITY_GUARD", "").strip(),
                "effective_final_quality_max_auto_continues": os.getenv(
                    "EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES", ""
                ).strip(),
                "enabled_tool_packs": list(self._normalize_enabled_tool_packs(self.config.enabled_tool_packs)),
                "repeat": self.config.repeat,
                "fresh_runtime": self.config.fresh_runtime,
                "fresh_session_per_case": self.config.fresh_session_per_case,
                "capture_prompt_snapshot": self.config.capture_prompt_snapshot,
                "task_board_armed_next_turn": bool(self.config.task_board_armed_next_turn),
                "user_id": self.user_id,
            },
            "cases": [],
        }

        for case in self.config.cases:
            case_runs: List[Dict[str, Any]] = []
            for repeat_index in range(self.config.repeat):
                case_run = await self._run_case_repeat(case, repeat_index=repeat_index)
                case_runs.append(case_run)
            case_report = {
                "name": case.name,
                "notes": case.notes,
                "summary": summarize_case_runs(case_runs),
                "runs": case_runs,
            }
            report["cases"].append(case_report)

        report_path = run_dir / "report.json"
        markdown_path = run_dir / "report.md"
        report["report_path"] = str(report_path)
        report["markdown_path"] = str(markdown_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(build_markdown_report(report), encoding="utf-8")
        return report


def sample_config_payload() -> Dict[str, Any]:
    return {
        "name": "agent-smoke-suite",
        "profile": "smoke",
        "workspace": ".",
        "model": "gpt-5.4-mini",
        "variant": "standard",
        "planner_model": "gpt-5.4-mini",
        "final_quality_guard": "planner",
        "final_quality_max_auto_continues": 2,
        "enabled_tool_packs": [
            "interactive_desktop",
            "browser_isolated",
            "workspace_write",
            "workspace_read",
            "web_research",
            "scheduler",
            "app_runtime",
        ],
        "repeat": 1,
        "fresh_runtime": True,
        "fresh_session_per_case": True,
        "capture_prompt_snapshot": True,
        "task_board_armed_next_turn": False,
        "cases": [
            {
                "name": "greeting",
                "prompt": "hey",
                "expectations": {
                    "max_tool_calls": 0,
                    "final_answer_forbidden_phrases": ["error in model generation", "context window"],
                },
            },
            {
                "name": "workspace-list-current-dir",
                "prompt": "Inspect the current workspace and list the top-level files and folders. Do not change anything.",
                "expectations": {
                    "required_tools_any": ["list_dir", "find_files"],
                    "forbidden_tools": [
                        "web_search",
                        "fetch_url",
                        "browser_navigate",
                        "describe_screen",
                        "observe_desktop",
                        "write_file",
                        "edit_file",
                        "append_file",
                        "run_command",
                    ],
                    "max_unsupported_tool_attempts": 0,
                    "max_tool_errors": 0,
                    "min_tool_calls": 1,
                },
            },
            {
                "name": "screen-observation-current-window",
                "prompt": "Tell me the main app or window currently visible on screen.",
                "expectations": {
                    "required_tools_any": ["describe_screen", "observe_desktop", "ocr_screen"],
                    "forbidden_tools": [
                        "read_file",
                        "list_dir",
                        "write_file",
                        "web_search",
                        "fetch_url",
                        "browser_navigate",
                    ],
                    "max_unsupported_tool_attempts": 0,
                },
            },
            {
                "name": "browser-heading-to-file",
                "prompt": "Open https://example.com, capture the main heading, write it to example_heading.txt, then verify the saved file.",
                "expectations": {
                    "required_tool_sequence": [
                        ["browser_navigate"],
                        ["browser_snapshot", "browser_read_text"],
                        "write_file",
                        "read_file",
                    ],
                    "required_tool_order": [{"before": "write_file", "after": "read_file"}],
                    "tool_arg_checks": [
                        {
                            "tool": "write_file",
                            "contains_all": ["example_heading.txt", "Example Domain"],
                        }
                    ],
                    "tool_result_checks": [
                        {
                            "tool": "read_file",
                            "contains_all": ["Example Domain"],
                        }
                    ],
                    "artifact_checks": [
                        {
                            "path": "example_heading.txt",
                            "must_exist": True,
                            "contains_all": ["Example Domain"],
                        }
                    ],
                    "max_unsupported_tool_attempts": 0,
                    "max_tool_errors": 0,
                    "min_tool_calls": 4,
                },
            },
        ],
    }
