from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


WORKER_REPORT_FIELDS = {
    "status",
    "summary",
    "evidence",
    "artifacts",
    "blockers",
    "confidence",
    "next_suggested_action",
}


def coerce_worker_report_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        chunks = [item.strip(" -\t") for item in re.split(r"\n|;", value) if item.strip(" -\t")]
        return chunks or [value.strip()]
    return [value]


def extract_worker_report(text: str) -> Dict[str, Any]:
    """Extract the structured Fleet worker report from JSON or labeled text."""

    raw_text = str(text or "").strip()
    if not raw_text:
        return {}

    candidates: list[str] = []
    candidates.extend(
        re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.IGNORECASE | re.DOTALL)
    )
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(raw_text[first_brace:last_brace + 1])
    candidates.append(raw_text)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict) and WORKER_REPORT_FIELDS.intersection(parsed.keys()):
            return _normalized_report_payload(parsed, raw={"worker_report": parsed})

    labeled: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(
            r"^(status|summary|evidence|artifacts|blockers|confidence|next_suggested_action)\s*:\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            current_key = match.group(1).lower()
            labeled[current_key] = match.group(2).strip()
            continue
        if current_key:
            labeled[current_key] = f"{labeled.get(current_key, '')}\n{line}".strip()

    if WORKER_REPORT_FIELDS.intersection(labeled.keys()):
        return _normalized_report_payload(labeled, raw={"worker_report": labeled})
    return {}


def _normalized_report_payload(payload: Dict[str, Any], *, raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": str(payload.get("status") or "").strip() or None,
        "summary": str(payload.get("summary") or "").strip() or None,
        "evidence": coerce_worker_report_list(payload.get("evidence")),
        "artifacts": coerce_worker_report_list(payload.get("artifacts")),
        "blockers": coerce_worker_report_list(payload.get("blockers")),
        "confidence": str(payload.get("confidence") or "").strip() or None,
        "next_suggested_action": str(payload.get("next_suggested_action") or "").strip() or None,
        "raw": raw,
    }
