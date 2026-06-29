from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

from shared.task_intent import request_requires_tool_evidence


_SIMPLE_CHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|yes|no|what'?s up|how are you|who are you)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_TASK_HINT_RE = re.compile(
    r"\b(open|launch|start|create|write|edit|fix|debug|run|install|send|message|email|"
    r"search|find|research|summarize|download|upload|build|test|deploy|compare|check|"
    r"worker|fleet|automation|schedule|remind)\b",
    re.IGNORECASE,
)

_PLANNER_CONTRACT_STORE_CALLBACK: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None


def set_planner_contract_store_callback(callback: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]]) -> None:
    global _PLANNER_CONTRACT_STORE_CALLBACK
    _PLANNER_CONTRACT_STORE_CALLBACK = callback


def record_planner_contract(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    callback = _PLANNER_CONTRACT_STORE_CALLBACK
    if callable(callback):
        try:
            return callback(dict(payload or {}))
        except Exception:
            return None
    return None


def should_create_planner_contract(user_message: str) -> bool:
    text = str(user_message or "").strip()
    if not text or _SIMPLE_CHAT_RE.match(text):
        return False
    words = re.findall(r"[A-Za-z0-9]+", text)
    if len(words) <= 5 and not _TASK_HINT_RE.search(text):
        return False
    return bool(request_requires_tool_evidence(text) or _TASK_HINT_RE.search(text))


def build_planner_contract(user_message: str) -> Dict[str, Any]:
    text = str(user_message or "").strip()
    if not should_create_planner_contract(text):
        return {"action": "no_op"}
    tool_or_state_task = bool(request_requires_tool_evidence(text))
    return {
        "action": "inject",
        "requirements": [
            "Preserve the user's exact objective and do not narrow it mid-run.",
            "Use available tools or delegated workers when the task requires external state, files, apps, browser state, or computer control.",
            "If a method fails, change the method or gather new evidence before retrying.",
        ],
        "assumptions": [
            "The user wants the task completed end-to-end unless they explicitly stop or narrow the task.",
            "A brief direct answer is acceptable only when no tool, file, app, worker, or external-state action is needed.",
        ],
        "success_criteria": [
            "All material parts of the user's request are completed or an exact blocker is reported.",
            "Completion claims are backed by tool evidence when external state, files, apps, browser state, worker output, or system state were touched.",
        ],
        "verification_steps": [
            "Compare the final state against the original user request.",
            "Verify produced files, opened apps, sent messages, browser state, worker reports, or command results when relevant.",
            "Do not final-answer if a safe next action remains and success criteria are not verified.",
        ],
        "stop_conditions": [
            "The user stops the run.",
            "A security broker or provider rejects the action and no safe sanitized path exists.",
            "The task requires unavailable user login, identity choice, hardware, or external information.",
        ],
        "risk_notes": [
            "External sends, destructive actions, credentials, and sensitive surfaces still require the existing confirmation and security rules.",
        ],
        "requires_tool_evidence": tool_or_state_task,
        "original_user_request": text,
    }


def build_pending_planner_contract(user_message: str) -> Dict[str, Any]:
    fallback = build_planner_contract(user_message)
    if fallback.get("action") != "inject":
        return {"action": "no_op", "status": "skipped", "original_user_request": str(user_message or "").strip()}
    return {
        "action": "pending",
        "status": "pending",
        "original_user_request": str(user_message or "").strip(),
        "fallback_contract": fallback,
    }


def planner_contract_prompt_payload(user_message: str) -> Dict[str, Any]:
    return {
        "user_message": str(user_message or "").strip(),
        "instruction": (
            "Decide if the message is a task that benefits from a planner contract. "
            "If it is simple chat or a trivial answer-only request, return action='no_op'. "
            "If it is a task, return action='inject' with concise requirements, assumptions, "
            "success_criteria, verification_steps, stop_conditions, and risk_notes."
        ),
    }


def planner_contract_system_prompt() -> str:
    return (
        "You are the parallel planner for a desktop AI agent. The main agent is already working. "
        "Your job is not to solve the task or call tools. Produce only strict JSON. "
        "Be behavioral and general, not example-driven. Keep lists short and verifiable. "
        "Skip simple chat cheaply.\n\n"
        "Schema:\n"
        "{\n"
        '  "action": "no_op" | "inject",\n'
        '  "requirements": [string],\n'
        '  "assumptions": [string],\n'
        '  "success_criteria": [string],\n'
        '  "verification_steps": [string],\n'
        '  "stop_conditions": [string],\n'
        '  "risk_notes": [string],\n'
        '  "requires_tool_evidence": boolean\n'
        "}"
    )


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def normalize_planner_contract_response(raw: str, *, user_message: str) -> Dict[str, Any]:
    parsed = _extract_json_object(raw) or {}
    action = str(parsed.get("action") or "").strip().lower()
    if action not in {"inject", "no_op"}:
        return build_planner_contract(user_message)
    if action == "no_op":
        return {"action": "no_op", "status": "complete", "original_user_request": str(user_message or "").strip()}

    def _list(name: str, fallback: list[str]) -> list[str]:
        value = parsed.get(name)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items[:8]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return fallback

    fallback = build_planner_contract(user_message)
    if fallback.get("action") != "inject":
        fallback = {
            "action": "inject",
            "requirements": [],
            "assumptions": [],
            "success_criteria": [],
            "verification_steps": [],
            "stop_conditions": [],
            "risk_notes": [],
            "requires_tool_evidence": False,
            "original_user_request": str(user_message or "").strip(),
        }
    return {
        "action": "inject",
        "status": "complete",
        "requirements": _list("requirements", list(fallback.get("requirements") or [])),
        "assumptions": _list("assumptions", list(fallback.get("assumptions") or [])),
        "success_criteria": _list("success_criteria", list(fallback.get("success_criteria") or [])),
        "verification_steps": _list("verification_steps", list(fallback.get("verification_steps") or [])),
        "stop_conditions": _list("stop_conditions", list(fallback.get("stop_conditions") or [])),
        "risk_notes": _list("risk_notes", list(fallback.get("risk_notes") or [])),
        "requires_tool_evidence": bool(parsed.get("requires_tool_evidence", fallback.get("requires_tool_evidence", False))),
        "original_user_request": str(user_message or "").strip(),
    }


def contract_system_message(contract: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not contract:
        return None
    if contract.get("action") == "pending":
        fallback = contract.get("fallback_contract")
        if isinstance(fallback, dict) and fallback.get("action") == "inject":
            contract = dict(fallback)
            contract["status"] = "fallback_pending_model"
        else:
            return None
    if contract.get("action") != "inject":
        return None
    return {
        "role": "system",
        "content": (
            "PROACTIVE PLANNER CONTRACT\n"
            "A lightweight planner generated this task contract. Treat it as success and verification guidance, "
            "not as a separate user request. Keep working until the success criteria are met, a true blocker is reached, "
            "or the user stops the run.\n\n"
            f"{json.dumps(contract, ensure_ascii=False, indent=2)}"
        ),
    }
