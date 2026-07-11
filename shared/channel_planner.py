from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

from anthropic import Anthropic

from cli.tui_constants import MODEL_CONFIGS
from shared.openai_api import create_openai_completion
from shared.proactive_planner_contract import (
    normalize_planner_contract_response,
    planner_contract_prompt_payload,
    planner_contract_system_prompt,
    record_planner_contract,
)
from shared.task_intent import (
    is_screen_observation_message,
    request_requires_tool_evidence,
)

def _collapse_for_verifier(value: Any, *, limit: int = 1800) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _desktop_window_context_message(session: Any) -> Optional[Dict[str, str]]:
    allowed_tools = set(getattr(session, "current_turn_allowed_tool_names", None) or [])
    enabled_packs = set(getattr(session, "enabled_tool_packs", None) or [])
    if "observe_desktop" not in allowed_tools and "interactive_desktop" not in enabled_packs:
        return None
    try:
        from runtime_support.system_info import format_active_windows_snapshot

        snapshot = format_active_windows_snapshot(limit=30)
    except Exception:
        snapshot = "Unavailable"
    if not str(snapshot or "").strip() or str(snapshot).strip() == "Unavailable":
        return None
    return {
        "role": "system",
        "content": (
            "LIVE DESKTOP WINDOW SNAPSHOT (fresh before this model turn):\n"
            f"{snapshot}\n"
            "- Use exact visible window titles from this snapshot with focus_window when a target is already open.\n"
            "- Before typing, clicking, or sending a hotkey, make sure the intended target window is active or explicitly focus it.\n"
            "- If the active window is a system power/shutdown, lock, sign-out, or unrelated user window, do not continue the task through that window; first dismiss or avoid it safely and re-observe.\n"
            "- Do not use broad close shortcuts such as Alt+F4 for ambiguous cleanup. Prefer close_window with an exact target title, Escape/Cancel for a visible modal, or another targeted route."
        ),
    }


def _task_contract_context_message(session: Any) -> Optional[Dict[str, str]]:
    user_request = _collapse_for_verifier(getattr(session, "last_user_message", ""), limit=900)
    if not user_request:
        return None
    if not request_requires_tool_evidence(user_request):
        return None

    allowed_tools = set(getattr(session, "current_turn_allowed_tool_names", None) or [])
    enabled_packs = set(getattr(session, "enabled_tool_packs", None) or [])
    if not allowed_tools and not enabled_packs:
        return None

    return {
        "role": "system",
        "content": (
            "CURRENT TASK CONTRACT (fresh before this model turn):\n"
            f"User request: {user_request}\n"
            "- Treat the request above as the active completion contract for this turn.\n"
            "- Finish only when the requested observable end state is true and verified in the relevant surface. "
            "Artifacts, intentions, typed paths, file reads, or host-app launches are not enough for visible UI/open/send tasks.\n"
            "- For local file open/show tasks, prefer open_file or a direct OS/app file-open command with the exact resolved path; "
            "use GUI Open dialogs only as a fallback and abandon them if they do not change visible state.\n"
            "- If the last route failed or produced no useful state change, re-observe or inspect state, classify what failed, "
            "then switch method family/tool surface unless new evidence makes retrying materially different.\n"
            "- Match proof to the surface: browser tools prove browser/DOM state, while native apps, desktop windows, local file-open state, "
            "and physical UI focus require desktop/window/file evidence such as describe_screen, observe_desktop, OCR, open_file, or exact OS command output.\n"
            "- Match command syntax to the platform and shell. On Windows, use shell='powershell' for PowerShell cmdlets and shell='cmd' for cmd.exe built-ins; "
            "on macOS/Linux use their native shell equivalents instead of Windows syntax.\n"
            "- Cleanup and retries must be scoped to this task: prefer kill_command for agent-started background commands, exact PIDs, exact windows, or visible cancel/escape paths. "
            "Do not terminate broad process names as a convenience.\n"
            "- User-directed work in communication/account apps is allowed, including WhatsApp, Gmail, Microsoft apps, email, messaging, "
            "calendar, and collaboration platforms. Proceed after verifying recipient/account/target identity and intended content/action; "
            "personal-account or communication context by itself is not a blocker."
        ),
    }


def _planner_verifier_system_prompt() -> str:
    return (
        "You are a final-answer verifier for an autonomous desktop agent. "
        "Your job is to decide whether the assistant's candidate final answer can be shown to the user. "
        "Infer the task-specific success obligations from the original user request. "
        "Only force continuation for requests that require observable external/tool evidence. "
        "For normal chat, explanation, opinion, brainstorming, or Q&A where the answer can be produced from context without using tools, choose allow. "
        "Use tool evidence as proof; do not treat the assistant final answer as proof by itself. "
        "Judge the latest verified state, not the messiness of intermediate attempts: an earlier failed tool call, draft artifact, "
        "or partial write is not a failure if later evidence shows the requested final state was corrected and verified. "
        "If an obligation required visible UI state, message sending, file opening, browser navigation, or a running app, "
        "require concrete tool evidence for that state. "
        "Match evidence source to obligation: browser_snapshot, browser_read_text, browser_wait_for, and browser_screenshot prove browser context only; "
        "native desktop apps, local file-open state, active windows, Electron/native app UI, and physical focus require desktop/window/file evidence such as "
        "describe_screen, observe_desktop, OCR, open_file, or exact OS command output. "
        "Do not accept isolated browser evidence as proof that a native desktop app is open, and do not require desktop evidence for a browser-only task when browser evidence is sufficient. "
        "Broad process cleanup by app/process name is not valid progress when a safer exact command id, PID, window, or cancel route is available. "
        "If safe useful tool actions remain, choose retry. "
        "For coding, build, install, run, app-creation, website, desktop-app, server, test, or launch tasks, be much stricter: "
        "choose retry unless tool evidence shows the requested files/artifacts exist and the requested run/open/usable/tested state was verified. "
        "Do not accept a final that says a dependency is missing, an installer failed, PATH is missing, a command could not launch, or asks whether to keep going "
        "when safe installation, portable download, alternate package manager, direct executable, or other workaround routes remain. "
        "For these coding/runtime tasks, environment setup problems are retry conditions, not true blockers, when the user has granted permission to install or use alternatives. "
        "Choose true_blocker only when the evidence shows the task cannot safely proceed without user action, login, identity choice, "
        "missing app/account state, or external state not available to the agent. "
        "Do not classify a user-directed task inside the user's personal apps/accounts as blocked solely because the app/account is personal. "
        "This includes WhatsApp, Gmail, Microsoft apps, email, messaging, calendar, and collaboration platforms. "
        "The safety obligation is verified recipient/account/target identity and intended content/action. "
        "Return only strict JSON with keys: action, reason, failed_obligation, evidence_gap, retry_instruction, must_use_tool. "
        "action must be one of allow, retry, true_blocker. must_use_tool must be boolean."
    )


def _planner_verifier_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    trace = []
    for item in list(payload.get("tool_trace") or [])[-28:]:
        if not isinstance(item, dict):
            continue
        trace.append(
            {
                "tool": _collapse_for_verifier(item.get("tool"), limit=80),
                "args": _collapse_for_verifier(item.get("args"), limit=450),
                "result": _collapse_for_verifier(item.get("result"), limit=1200),
            }
        )
    return {
        "original_user_request": _collapse_for_verifier(payload.get("user_request"), limit=1600),
        "candidate_final_answer": _collapse_for_verifier(payload.get("assistant_final"), limit=1800),
        "tool_trace": trace,
        "planner_contract": payload.get("planner_contract") or {},
        "decision_instructions": {
            "allow": "All material obligations are supported by evidence, or a true blocker is explicitly classified separately.",
            "retry": "A material obligation that requires tool evidence lacks that evidence and at least one safe useful tool action remains.",
            "true_blocker": "The evidence shows the agent cannot proceed safely without user/external action.",
        },
    }


_CODING_TASK_RE = re.compile(
    r"\b("
    r"code|coding|program|script|app|application|electron|website|web\s*app|server|api|backend|frontend|"
    r"build|compile|run|launch|start|install|npm|node|package|test|tests|pytest|calculator|"
    r"create|write|implement|fix|debug"
    r")\b",
    re.IGNORECASE,
)
_CONTINUATION_TEXT_RE = re.compile(
    r"^\s*(continue|keep going|go on|proceed|resume|yes|ok|okay|do it|try again|"
    r"you have permission.*|.*complete the task.*)\s*[.!?]*\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PREMATURE_FINAL_RE = re.compile(
    r"("
    r"if you want|i can keep going|i can take the next step|could not launch|couldn't launch|"
    r"could not run|couldn't run|cannot run|can't run|not runnable|not usable|"
    r"node(?:\.js)?(?:/npm)? (?:is )?(?:missing|not installed|not on path)|npm (?:is )?(?:missing|not installed|not on path)|"
    r"installer failed|msi .*failed|exit code\s+1619|no working .*install|blocked/broken|"
    r"remaining blocker|cannot honestly claim|could not honestly claim"
    r")",
    re.IGNORECASE,
)
_SUCCESS_EVIDENCE_RE = re.compile(
    r"("
    r"exit_code\]\s*0|\"exit_code\"\s*:\s*0|window|windows|started|running|listening|localhost|"
    r"visible|opened|launched|served|server|test.*pass|passed|success"
    r")",
    re.IGNORECASE,
)


def _coding_task_requires_strict_retry(user_request: Any, assistant_final: Any, tool_trace: List[Dict[str, Any]]) -> bool:
    request_text = str(user_request or "")
    final_text = str(assistant_final or "")
    if not request_text or not _CODING_TASK_RE.search(request_text):
        return False
    if not _PREMATURE_FINAL_RE.search(final_text):
        return False
    if re.search(r"\b(could not|couldn't|cannot|can't|did not|not)\b.{0,80}\b(run|launch|start|open|install)\b", final_text, re.IGNORECASE):
        return True
    trace_text = json.dumps(tool_trace[-12:], ensure_ascii=False, default=str)
    return not _SUCCESS_EVIDENCE_RE.search(trace_text)


def _preserved_task_objective(session: Any, fallback: str) -> str:
    fallback_text = str(fallback or "").strip()
    if fallback_text and not _CONTINUATION_TEXT_RE.match(fallback_text):
        return fallback_text
    history = list(getattr(session, "chat_history", []) or [])
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content and not _CONTINUATION_TEXT_RE.match(content) and request_requires_tool_evidence(content):
            return content
    return fallback_text


def _planner_model_for_final_verifier(session: Any) -> str:
    configured = str(getattr(session, "planner_model", "") or "").strip()
    default = str(getattr(session, "default_planner_model", "") or "").strip()
    current = str(getattr(session, "current_model", "") or "").strip()
    return configured or current or default


def _planner_final_completion(session: Any, *, prompt_payload: Dict[str, Any]) -> Optional[str]:
    model_name = _planner_model_for_final_verifier(session)
    if not model_name:
        return None
    try:
        client, provider = session.get_client_for_specific_model(model_name)
    except Exception:
        return None
    if client is None:
        return None

    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)
    system_prompt = _planner_verifier_system_prompt()
    user_prompt = json.dumps(prompt_payload, ensure_ascii=True, indent=2)

    try:
        if provider in {"openai", "openai-codex", "xai", "deepseek", "openrouter", "nvidia", "google"}:
            response = create_openai_completion(
                client,
                model_name=model_name,
                model_id=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=700,
            )
            return str(response.choices[0].message.content or "") if response.choices else None

        if provider == "anthropic":
            response = client.messages.create(
                model=model_id,
                max_tokens=700,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parts = getattr(response, "content", None) or []
            text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
            return "\n".join(text_parts).strip() or None
    except Exception:
        return None
    return None


def _planner_contract_completion(session: Any, *, user_message: str) -> Optional[str]:
    model_name = _planner_model_for_final_verifier(session)
    if not model_name:
        return None
    try:
        client, provider = session.get_client_for_specific_model(model_name)
    except Exception:
        return None
    if client is None:
        return None

    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)
    system_prompt = planner_contract_system_prompt()
    user_prompt = json.dumps(planner_contract_prompt_payload(user_message), ensure_ascii=True, indent=2)

    try:
        if provider in {"openai", "openai-codex", "xai", "deepseek", "openrouter", "nvidia", "google"}:
            response = create_openai_completion(
                client,
                model_name=model_name,
                model_id=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=900,
            )
            return str(response.choices[0].message.content or "") if response.choices else None

        if provider == "anthropic":
            response = client.messages.create(
                model=model_id,
                max_tokens=900,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parts = getattr(response, "content", None) or []
            text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
            return "\n".join(text_parts).strip() or None
    except Exception:
        return None
    return None


async def _run_parallel_planner_contract(
    session: Any,
    *,
    user_message: str,
    session_id: Optional[str],
    turn_id: str,
    schedule_emit: Callable[[Dict[str, Any]], None],
) -> None:
    user_id = int(getattr(session, "sync_user_id", None) or getattr(session, "user_id", 0) or 0)
    pending_contract = getattr(session, "proactive_planner_contract", None)
    if not isinstance(pending_contract, dict) or pending_contract.get("action") != "pending":
        return
    record_planner_contract(
        {
            "user_id": user_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "pending",
            "action": "pending",
            "contract": pending_contract,
        }
    )
    loop = asyncio.get_running_loop()
    try:
        raw = await loop.run_in_executor(
            None,
            lambda: _planner_contract_completion(session, user_message=user_message),
        )
        contract = normalize_planner_contract_response(raw or "", user_message=user_message)
        contract["source"] = "planner_model" if raw else "fallback_no_planner_response"
        status = "complete" if contract.get("action") in {"inject", "no_op"} else "fallback"
    except Exception as exc:
        contract = dict(pending_contract.get("fallback_contract") or {})
        contract["source"] = "fallback_planner_error"
        contract["planner_error"] = str(exc)[:400]
        status = "fallback"

    setattr(session, "proactive_planner_contract", contract if contract.get("action") == "inject" else None)
    setattr(session, "proactive_planner_contract_injected", False if contract.get("action") == "inject" else True)
    setattr(session, "proactive_planner_contract_version", int(getattr(session, "proactive_planner_contract_version", 0) or 0) + 1)
    record_planner_contract(
        {
            "user_id": user_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "status": status,
            "action": contract.get("action"),
            "contract": contract,
        }
    )
    schedule_emit(
        {
            "type": "planner_contract",
            "status": status,
            "action": contract.get("action"),
            "contract": contract,
        }
    )


def _planner_final_verdict(session: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    objective = _preserved_task_objective(session, str(payload.get("user_request") or ""))
    if objective:
        payload = dict(payload)
        payload["user_request"] = objective
    if not request_requires_tool_evidence(objective):
        return {
            "action": "allow",
            "reason": "planner_skipped_answer_only_turn",
            "failed_obligation": "",
            "evidence_gap": "",
            "retry_instruction": "",
            "continuation_instruction": "",
            "must_use_tool": False,
        }
    prompt_payload = _planner_verifier_payload(payload)
    raw = _planner_final_completion(session, prompt_payload=prompt_payload)
    parsed = _extract_json_object(raw or "") or {}
    action = str(parsed.get("action") or "allow").strip().lower()
    if action not in {"allow", "retry", "true_blocker"}:
        action = "allow"

    failed_obligation = _collapse_for_verifier(parsed.get("failed_obligation"), limit=240)
    evidence_gap = _collapse_for_verifier(parsed.get("evidence_gap"), limit=400)
    reason = _collapse_for_verifier(parsed.get("reason") or failed_obligation or "planner_final_verifier", limit=400)
    retry_instruction = _collapse_for_verifier(parsed.get("retry_instruction"), limit=900)
    must_use_tool = bool(parsed.get("must_use_tool", action == "retry"))
    tool_trace = list(payload.get("tool_trace") or [])
    if action != "retry" and _coding_task_requires_strict_retry(objective, payload.get("assistant_final"), tool_trace):
        action = "retry"
        failed_obligation = failed_obligation or "Coding/runtime task was not verified as run and usable."
        evidence_gap = evidence_gap or "The candidate final describes an unfinished dependency/install/launch state while safe coding-task routes may remain."
        reason = "coding_task_premature_final"
        retry_instruction = retry_instruction or (
            "Continue using a different safe route: inspect the failing install/download, try a portable or alternate Node/Electron route if needed, "
            "then launch and verify the app window or running state."
        )
        must_use_tool = True

    if action == "retry":
        original_request = _collapse_for_verifier(prompt_payload.get("original_user_request"), limit=900)
        instruction_parts = [
            "[Hidden runtime continuation: your previous answer was not shown to the user.]",
            "A planner verifier found the user's task is not sufficiently evidenced yet.",
        ]
        if original_request:
            instruction_parts.append(f"Original user request still active: {original_request}")
        if failed_obligation:
            instruction_parts.append(f"Failed obligation: {failed_obligation}.")
        if evidence_gap:
            instruction_parts.append(f"Evidence gap: {evidence_gap}.")
        if retry_instruction:
            instruction_parts.append(f"Next action: {retry_instruction}")
        instruction_parts.append(
            "Continue the original task from the current state. Do not ask whether to continue. "
            "Use a safe, materially useful tool action before final-answering, then verify the result. "
            "Treat the user's requested observable end state as the success criterion. "
            "Do not repeat the same failed method loop; switch method family/tool surface unless new evidence makes the retry materially different."
        )
        continuation_instruction = " ".join(instruction_parts)
    else:
        continuation_instruction = ""

    return {
        "action": "continue" if action == "retry" else "allow",
        "reason": f"planner_{action}:{reason}",
        "failed_obligation": failed_obligation,
        "evidence_gap": evidence_gap,
        "retry_instruction": continuation_instruction,
        "continuation_instruction": continuation_instruction,
        "must_use_tool": must_use_tool,
    }
