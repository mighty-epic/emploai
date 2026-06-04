from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List


DEFAULT_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary"


@dataclass
class FinalQualityVerdict:
    action: str
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    continuation_instruction: str = ""


_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: Dict[str, Any] = {}


def final_quality_guard_enabled() -> bool:
    return final_quality_guard_mode() in {"nli", "planner"}


def final_quality_guard_mode() -> str:
    return os.getenv("EMPLOAI_FINAL_QUALITY_GUARD", "").strip().lower()


def max_auto_continues() -> int:
    raw = os.getenv("EMPLOAI_FINAL_QUALITY_MAX_AUTO_CONTINUES", "").strip()
    if not raw:
        return 1
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _load_nli_model(model_name: str):
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(model_name)
        if cached:
            return cached
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        id2label = dict(getattr(model.config, "id2label", {}) or {})
        entailment_index = 0
        for index, label in id2label.items():
            lowered = str(label).lower()
            if "entail" in lowered and not lowered.startswith("not"):
                entailment_index = int(index)
                break
        cached = (torch, tokenizer, model, entailment_index)
        _MODEL_CACHE[model_name] = cached
        return cached


def _plain_text(value: Any, *, limit: int = 700) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_final_quality_premise(
    *,
    user_request: str,
    assistant_final: str,
    tool_trace: List[Dict[str, Any]],
) -> str:
    parts = [
        f"User request: {_plain_text(user_request, limit=1000)}",
        f"Assistant final answer: {_plain_text(assistant_final, limit=1000)}",
    ]
    if tool_trace:
        parts.append("Tool trace:")
        for index, item in enumerate(tool_trace[-18:], start=1):
            tool = _plain_text(item.get("tool"), limit=80)
            args = _plain_text(item.get("args"), limit=260)
            result = _plain_text(item.get("result"), limit=520)
            parts.append(f"{index}. {tool} args={args} result={result}")
    else:
        parts.append("Tool trace: no tools were used.")
    return "\n".join(parts)


_HYPOTHESES = {
    "task_incomplete": "The assistant did not complete the user request.",
    "task_completed": "The assistant completed the user request.",
    "safe_routes_remain": "Safe relevant next actions remained available.",
    "assistant_named_next": "The assistant named a next action it could try.",
    "login_required": "The task cannot continue until the user logs in or provides account authentication.",
    "identity_required": "The task cannot continue until the user confirms their identity or chooses an account.",
}


def _score_hypotheses(premise: str, *, model_name: str) -> Dict[str, float]:
    torch, tokenizer, model, entailment_index = _load_nli_model(model_name)
    labels = list(_HYPOTHESES)
    hypotheses = [_HYPOTHESES[label] for label in labels]
    with torch.no_grad():
        batch = tokenizer(
            [premise] * len(hypotheses),
            hypotheses,
            truncation="only_first",
            padding=True,
            max_length=512,
            return_tensors="pt",
        )
        probs = torch.softmax(model(**batch).logits, dim=-1)[:, entailment_index].tolist()
    return {label: round(float(score), 4) for label, score in zip(labels, probs)}


def judge_final_quality_with_nli(
    *,
    user_request: str,
    assistant_final: str,
    tool_trace: List[Dict[str, Any]],
) -> FinalQualityVerdict:
    model_name = os.getenv("EMPLOAI_FINAL_QUALITY_NLI_MODEL", "").strip() or DEFAULT_NLI_MODEL
    incomplete_threshold = _float_env("EMPLOAI_FINAL_QUALITY_INCOMPLETE_THRESHOLD", 0.75)
    blocker_threshold = _float_env("EMPLOAI_FINAL_QUALITY_BLOCKER_THRESHOLD", 0.78)
    completed_threshold = _float_env("EMPLOAI_FINAL_QUALITY_COMPLETE_THRESHOLD", 0.82)
    premise = build_final_quality_premise(
        user_request=user_request,
        assistant_final=assistant_final,
        tool_trace=tool_trace,
    )
    try:
        scores = _score_hypotheses(premise, model_name=model_name)
    except Exception as exc:
        return FinalQualityVerdict(action="allow", reason=f"nli_unavailable:{exc}")

    if scores.get("login_required", 0.0) >= blocker_threshold or scores.get("identity_required", 0.0) >= blocker_threshold:
        return FinalQualityVerdict(action="allow", reason="nli_user_blocker", scores=scores)

    if scores.get("task_completed", 0.0) >= completed_threshold and scores.get("task_incomplete", 0.0) < incomplete_threshold:
        return FinalQualityVerdict(action="allow", reason="nli_complete", scores=scores)

    if scores.get("task_incomplete", 0.0) >= incomplete_threshold:
        instruction = (
            "[Hidden runtime continuation: your previous answer was not shown to the user.] "
            "Continue the user's original task now. Do not ask whether to continue. "
            "Take the next safe relevant action, use a materially different route when the last route failed, "
            "and verify the result before final-answering."
        )
        return FinalQualityVerdict(
            action="continue",
            reason="nli_task_incomplete",
            scores=scores,
            continuation_instruction=instruction,
        )

    return FinalQualityVerdict(action="allow", reason="nli_allow_low_incomplete", scores=scores)
