from __future__ import annotations

from typing import Any, Optional

import httpx
from openai import OpenAI


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def create_gemini_openai_client(api_key: str) -> OpenAI:
    """Create the official Gemini OpenAI-compatible client."""
    return OpenAI(api_key=api_key, base_url=GEMINI_OPENAI_BASE_URL)


def is_openai_compatible_client(client: Any) -> bool:
    chat = getattr(client, "chat", None)
    completions = getattr(chat, "completions", None)
    return callable(getattr(completions, "create", None))


def validate_gemini_api_key(api_key: Optional[str], *, timeout: float = 10.0) -> tuple[bool, str]:
    key = str(api_key or "").strip()
    if not key:
        return False, "No API key configured"

    try:
        response = httpx.get(
            GEMINI_MODELS_URL,
            params={"key": key},
            timeout=timeout,
        )
        if response.status_code == 200:
            return True, "OK"
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        return False, str(detail)[:200] or f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)[:200]
