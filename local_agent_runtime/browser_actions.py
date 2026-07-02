"""Shared browser action result helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def stable_snapshot_hash(formatted: str = "", elements: Optional[Any] = None) -> str:
    """Return a stable FNV-1a hash for snapshot text or structured elements."""
    if not formatted and elements is not None:
        formatted = json.dumps(elements, sort_keys=True, separators=(",", ":"))

    value = 2166136261
    for character in formatted:
        value ^= ord(character)
        value = (value * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


@dataclass
class BrowserActionResult:
    """Normalized browser action envelope used by both browser backends."""

    success: bool
    backend: str
    tab_id: Any = None
    window_id: Any = None
    url: Optional[str] = None
    title: Optional[str] = None
    wait_reason: Optional[str] = None
    snapshot_hash: Optional[str] = None
    interactive_count: Optional[int] = None
    focused_ref: Optional[int] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "success": self.success,
            "backend": self.backend,
            "tab_id": self.tab_id,
            "window_id": self.window_id,
            "url": self.url,
            "title": self.title,
            "wait_reason": self.wait_reason,
            "snapshot_hash": self.snapshot_hash,
            "interactive_count": self.interactive_count,
            "focused_ref": self.focused_ref,
        }
        if self.error:
            data["error"] = self.error
        if self.error_type:
            data["error_type"] = self.error_type
        data.update(self.extras)
        return data


def browser_error(
    backend: str,
    error: str,
    *,
    error_type: str = "command",
    wait_reason: Optional[str] = None,
    tab_id: Any = None,
    window_id: Any = None,
    url: Optional[str] = None,
    title: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return BrowserActionResult(
        success=False,
        backend=backend,
        tab_id=tab_id,
        window_id=window_id,
        url=url,
        title=title,
        wait_reason=wait_reason,
        error=error,
        error_type=error_type,
        extras=extras or {},
    ).to_dict()


def browser_success(
    backend: str,
    *,
    tab_id: Any = None,
    window_id: Any = None,
    url: Optional[str] = None,
    title: Optional[str] = None,
    wait_reason: Optional[str] = None,
    snapshot_hash: Optional[str] = None,
    interactive_count: Optional[int] = None,
    focused_ref: Optional[int] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return BrowserActionResult(
        success=True,
        backend=backend,
        tab_id=tab_id,
        window_id=window_id,
        url=url,
        title=title,
        wait_reason=wait_reason,
        snapshot_hash=snapshot_hash,
        interactive_count=interactive_count,
        focused_ref=focused_ref,
        extras=extras or {},
    ).to_dict()
