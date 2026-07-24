from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional


_REQUESTED_COMPANY_ID: ContextVar[Optional[str]] = ContextVar(
    "emploai_requested_company_id",
    default=None,
)


def bind_requested_company_id(value: object) -> Token:
    clean_value = str(value or "").strip()
    return _REQUESTED_COMPANY_ID.set(clean_value or None)


def reset_requested_company_id(token: Token) -> None:
    _REQUESTED_COMPANY_ID.reset(token)


def requested_company_id() -> Optional[str]:
    return _REQUESTED_COMPANY_ID.get()
