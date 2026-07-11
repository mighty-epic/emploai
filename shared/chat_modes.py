from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


RUN_MODE_NORMAL = "normal"
RUN_MODE_PLAN = "plan"
RUN_MODE_GOAL = "goal"
VALID_RUN_MODES = {RUN_MODE_NORMAL, RUN_MODE_PLAN, RUN_MODE_GOAL}

PLAN_ACTION_APPROVE = "approve"
PLAN_ACTION_DISMISS = "dismiss"
PLAN_ACTION_ANSWER_QUESTION = "answer_question"
PLAN_ACTION_EXIT = "exit"
VALID_PLAN_ACTIONS = {
    PLAN_ACTION_APPROVE,
    PLAN_ACTION_DISMISS,
    PLAN_ACTION_ANSWER_QUESTION,
    PLAN_ACTION_EXIT,
}

GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_COMPLETE = "complete"
GOAL_STATUS_BLOCKED = "blocked"
VALID_GOAL_STATUSES = {GOAL_STATUS_ACTIVE, GOAL_STATUS_COMPLETE, GOAL_STATUS_BLOCKED}

PLAN_SAFE_TOOL_NAMES = {
    "read_file",
    "list_dir",
    "find_files",
    "grep_search",
    "run_command",
    "command_status",
    "describe_screen",
    "ocr_screen",
    "observe_desktop",
    "browser_snapshot",
    "browser_read_text",
    "browser_screenshot",
    "observe_browser",
    "web_search",
    "fetch_url",
    "pull_skill",
    "request_user_input",
}

PLAN_MUTATING_TOOL_NAMES = {
    "write_file",
    "append_file",
    "edit_file",
    "delete_file",
    "move_file",
    "copy_file",
    "run_background_command",
    "send_input",
    "kill_command",
    "start_visual_monitor",
    "stop_visual_monitor",
    "update_memory",
    "send_email",
    "gmail_send",
    "telegram_send",
    "whatsapp_send",
    "post_message",
    "fleet_send_worker_message",
    "fleet_send_group_message",
    "fleet_delegate_task",
    "fleet_assign_task",
}

REQUEST_USER_INPUT_TOOL: Dict[str, Any] = {
    "name": "request_user_input",
    "description": (
        "Plan Mode only. Ask the user one concise structured clarification question "
        "with two or three options and an optional freeform answer path."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The direct question to ask before finalizing the plan.",
            },
            "header": {
                "type": "string",
                "description": "A short card header, 12 characters or fewer when possible.",
            },
            "options": {
                "type": "array",
                "description": "Two or three mutually exclusive options.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["label", "description"],
                },
            },
        },
        "required": ["question", "options"],
    },
}

UPDATE_GOAL_STATUS_TOOL: Dict[str, Any] = {
    "name": "update_goal_status",
    "description": (
        "Goal Mode only. Mark the active session goal complete or blocked when the "
        "definition of done is truly satisfied or genuinely blocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["complete", "blocked"],
                "description": "New goal status.",
            },
            "summary": {
                "type": "string",
                "description": "Concise outcome summary. Required for complete and blocked.",
            },
            "evidence": {
                "type": "string",
                "description": "Concrete verification evidence or the repeated blocker details.",
            },
            "blocker_key": {
                "type": "string",
                "description": "Stable identifier for a repeated blocker when status is blocked.",
            },
            "user_dependent": {
                "type": "boolean",
                "description": "True only for credentials, 2FA, account choice, or required user input blockers.",
                "default": False,
            },
        },
        "required": ["status", "summary", "evidence"],
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_run_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_RUN_MODES else RUN_MODE_NORMAL


def normalize_plan_action(value: Any) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_PLAN_ACTIONS else None


def clone_mode_state(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return dict(value)
    return None


def active_plan_mode(session: Any) -> Optional[Dict[str, Any]]:
    state = clone_mode_state(getattr(session, "plan_mode", None))
    if not state:
        return None
    status = str(state.get("status") or "").strip().lower()
    if status in {"active", "awaiting_user_input", "awaiting_approval"}:
        return state
    return None


def active_goal(session: Any) -> Optional[Dict[str, Any]]:
    state = clone_mode_state(getattr(session, "active_goal", None))
    if not state:
        return None
    return state if str(state.get("status") or "").strip().lower() == GOAL_STATUS_ACTIVE else None


def ensure_plan_mode(session: Any) -> Dict[str, Any]:
    timestamp = now_iso()
    current = active_plan_mode(session) or {}
    if not current:
        current = {
            "status": "active",
            "started_at": timestamp,
            "updated_at": timestamp,
            "pending_question": None,
            "last_plan": None,
        }
    else:
        current["status"] = "active"
        current["updated_at"] = timestamp
        current.setdefault("started_at", timestamp)
        current.setdefault("pending_question", None)
        current.setdefault("last_plan", None)
    session.plan_mode = current
    return current


def exit_plan_mode(session: Any, *, reason: str = "exited") -> None:
    current = clone_mode_state(getattr(session, "plan_mode", None)) or {}
    if current:
        current["status"] = "exited"
        current["updated_at"] = now_iso()
        current["exit_reason"] = reason
        session.plan_mode = None
    else:
        session.plan_mode = None


def create_goal_state(objective: str, *, token_budget: Optional[int] = None) -> Dict[str, Any]:
    timestamp = now_iso()
    goal: Dict[str, Any] = {
        "goal_id": f"goal_{uuid.uuid4().hex[:12]}",
        "objective": str(objective or "").strip(),
        "status": GOAL_STATUS_ACTIVE,
        "tokens_used": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    if token_budget is not None and token_budget > 0:
        goal["token_budget"] = int(token_budget)
    return goal


def start_goal(session: Any, objective: str) -> Dict[str, Any]:
    current = active_goal(session)
    if current:
        return current
    goal = create_goal_state(objective)
    session.active_goal = goal
    return goal


def plan_mode_system_message(session: Any) -> str:
    state = active_plan_mode(session) or {}
    pending = state.get("pending_question") if isinstance(state.get("pending_question"), Mapping) else None
    lines = [
        "# PLAN MODE",
        "You are in Plan Mode for this session. Treat every user message as planning work until Plan Mode is approved, dismissed, or exited.",
        "Allowed: inspect the repo/environment, search/read files, reason about configs, run safe non-mutating validation commands, and ask structured clarification questions.",
        "Forbidden: file edits, formatter writes, migrations, app/desktop input, scheduler changes, memory writes, external sends, background commands, visual monitors, fleet delegation, and any other mutating action.",
        "Discover repo facts before asking questions that local inspection can answer.",
        "If product intent or implementation choice is ambiguous, call request_user_input with one concise multiple-choice question.",
        "When the plan is decision-complete, output exactly one official handoff block wrapped in <proposed_plan>...</proposed_plan>.",
        "The proposed plan must cover summary, affected areas, interfaces, edge cases, test plan, and assumptions.",
    ]
    if pending:
        lines.append(f"Current pending question id: {pending.get('question_id')}. The user may answer it before you finalize the plan.")
    return "\n".join(lines)


def goal_mode_system_message(session: Any) -> str:
    goal = active_goal(session)
    if not goal:
        return ""
    lines = [
        "# GOAL MODE",
        f"Active goal id: {goal.get('goal_id')}",
        f"Objective: {goal.get('objective')}",
        f"Tokens used so far: {goal.get('tokens_used', 0)}",
        "Keep pursuing this objective across turns. Do not shrink it into only the latest message.",
        "Normal tools and permissions remain available. Goal Mode is a persistence and definition-of-done contract, not a Plan Mode mutation ban.",
        "Only call update_goal_status(status='complete') when the objective is actually satisfied and you can provide summary and concrete evidence.",
        "Only call update_goal_status(status='blocked') for a repeated same blocker, unless the blocker clearly needs user credentials, 2FA, account choice, or required user input.",
    ]
    budget = goal.get("token_budget")
    if budget:
        lines.append(f"Token budget: {budget}")
    return "\n".join(lines)


def _tool_name(tool: Mapping[str, Any]) -> str:
    return str(tool.get("name") or tool.get("function", {}).get("name") or "").strip()


def filter_plan_tools(tools: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for tool in tools or []:
        name = _tool_name(tool)
        if not name or name in seen:
            continue
        if name in PLAN_SAFE_TOOL_NAMES:
            filtered.append(tool)
            seen.add(name)
    return filtered


def is_plan_tool_allowed(tool_name: str) -> bool:
    name = str(tool_name or "").strip()
    if name == "run_command":
        return True
    return name in PLAN_SAFE_TOOL_NAMES and name not in PLAN_MUTATING_TOOL_NAMES


def is_safe_plan_command(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    lower = text.lower()
    mutating_markers = (
        ">",
        ">>",
        "| set-content",
        "| add-content",
        "apply_patch",
        "cat >",
        "copy ",
        "cp ",
        "del ",
        "erase ",
        "format ",
        "git checkout",
        "git commit",
        "git reset",
        "git push",
        "mkdir",
        "move ",
        "mv ",
        "new-item",
        "npm install",
        "pnpm install",
        "pip install",
        "poetry add",
        "remove-item",
        "ren ",
        "rename-item",
        "rm ",
        "rmdir",
        "set-content",
        "start-process",
        "stop-process",
        "touch ",
        "write-output",
    )
    if any(marker in lower for marker in mutating_markers):
        return False
    safe_prefixes = (
        "dir",
        "echo ",
        "git diff",
        "git log",
        "git show",
        "git status",
        "get-childitem",
        "get-content",
        "npm run typecheck",
        "npm test",
        "pnpm test",
        "pytest",
        "python -m compileall",
        "python -m pytest",
        "rg ",
        "select-string",
        "type ",
        "where ",
        "where.exe",
    )
    return any(lower == prefix.strip() or lower.startswith(prefix) for prefix in safe_prefixes)


def plan_tool_denial(tool_name: str, args: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    name = str(tool_name or "").strip()
    if name == "run_command":
        if is_safe_plan_command(str((args or {}).get("command") or "")):
            return None
        return "Plan Mode allows only clearly non-mutating inspection or validation commands."
    if is_plan_tool_allowed(name):
        return None
    return f"Plan Mode blocks mutating or side-effectful tool '{name}'."


def normalize_plan_question(payload: Mapping[str, Any]) -> Dict[str, Any]:
    timestamp = now_iso()
    question_id = str(payload.get("question_id") or f"plan_q_{uuid.uuid4().hex[:10]}")
    raw_options = payload.get("options") if isinstance(payload.get("options"), list) else []
    options: List[Dict[str, str]] = []
    for index, option in enumerate(raw_options[:3]):
        if not isinstance(option, Mapping):
            continue
        label = str(option.get("label") or "").strip()
        if not label:
            continue
        options.append(
            {
                "id": str(option.get("id") or f"option_{index + 1}"),
                "label": label[:80],
                "description": str(option.get("description") or "").strip()[:240],
            }
        )
    if len(options) < 2:
        options = [
            {"id": "recommended", "label": "Recommended", "description": "Use the most direct repo-first plan."},
            {"id": "minimal", "label": "Minimal", "description": "Keep the plan as narrow as possible."},
        ]
    return {
        "question_id": question_id,
        "header": str(payload.get("header") or "Plan").strip()[:24] or "Plan",
        "question": str(payload.get("question") or "Which direction should the implementation plan take?").strip(),
        "options": options,
        "created_at": timestamp,
    }


def extract_proposed_plan(text: str) -> Optional[str]:
    match = re.search(r"<proposed_plan>\s*(.*?)\s*</proposed_plan>", str(text or ""), re.I | re.S)
    if not match:
        return None
    content = match.group(1).strip()
    return content or None


def record_proposed_plan(session: Any, text: str) -> Optional[Dict[str, Any]]:
    content = extract_proposed_plan(text)
    if not content:
        return None
    state = ensure_plan_mode(session)
    plan = {
        "plan_id": f"plan_{uuid.uuid4().hex[:10]}",
        "content": content,
        "created_at": now_iso(),
    }
    state["status"] = "awaiting_approval"
    state["updated_at"] = plan["created_at"]
    state["pending_question"] = None
    state["last_plan"] = plan
    session.plan_mode = state
    return plan


def apply_goal_status_update(session: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
    goal = active_goal(session)
    if not goal:
        return {"ok": False, "error": "No active goal exists for this session."}

    status = str(payload.get("status") or "").strip().lower()
    if status not in {GOAL_STATUS_COMPLETE, GOAL_STATUS_BLOCKED}:
        return {"ok": False, "error": "Goal status must be complete or blocked."}

    summary = str(payload.get("summary") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()
    if not summary or not evidence:
        return {"ok": False, "error": "Goal completion/blocking requires both summary and evidence."}

    timestamp = now_iso()
    goal = dict(goal)
    goal["status"] = status
    goal["summary"] = summary
    goal["evidence"] = evidence
    goal["updated_at"] = timestamp
    if status == GOAL_STATUS_COMPLETE:
        goal["completed_at"] = timestamp
    else:
        goal["blocked_at"] = timestamp
        if payload.get("blocker_key"):
            goal["blocker_key"] = str(payload.get("blocker_key"))
        goal["user_dependent"] = bool(payload.get("user_dependent"))
    session.active_goal = goal
    return {"ok": True, "goal": goal}


def add_goal_token_usage(session: Any, input_tokens: Any = None, output_tokens: Any = None) -> None:
    goal = active_goal(session)
    if not goal:
        return
    try:
        used = int(goal.get("tokens_used") or 0)
        used += max(0, int(input_tokens or 0))
        used += max(0, int(output_tokens or 0))
    except Exception:
        return
    goal["tokens_used"] = used
    goal["updated_at"] = now_iso()
    session.active_goal = goal
