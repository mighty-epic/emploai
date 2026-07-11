from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional


_GUARD_INSTALL_LOCK = threading.Lock()
_SESSION_PLANNER_LOCKS: dict[int, threading.Lock] = {}


def _hidden_planner_lock(session: Any) -> threading.Lock:
    lock = getattr(session, "_hidden_runtime_planner_lock", None)
    if lock is not None and callable(getattr(lock, "acquire", None)):
        return lock
    with _GUARD_INSTALL_LOCK:
        lock = getattr(session, "_hidden_runtime_planner_lock", None)
        if lock is not None and callable(getattr(lock, "acquire", None)):
            return lock
        session_key = id(session)
        lock = _SESSION_PLANNER_LOCKS.get(session_key)
        if lock is None:
            lock = threading.Lock()
            _SESSION_PLANNER_LOCKS[session_key] = lock
        try:
            setattr(session, "_hidden_runtime_planner_lock", lock)
        except Exception:
            pass
        return lock


@contextmanager
def hidden_runtime_planner(session: Any, *, owner: str) -> Iterator[bool]:
    """Allow only one hidden runtime planner to alter a session at a time."""
    lock = _hidden_planner_lock(session)
    acquired = lock.acquire(blocking=False)
    if acquired:
        try:
            setattr(session, "_hidden_runtime_planner_owner", owner)
        except Exception:
            pass
    try:
        yield acquired
    finally:
        if acquired:
            try:
                if getattr(session, "_hidden_runtime_planner_owner", None) == owner:
                    setattr(session, "_hidden_runtime_planner_owner", None)
            except Exception:
                pass
            lock.release()


def queue_runtime_system_context(
    session: Any,
    *,
    headline: str,
    prompt: str,
    merge_marker: Optional[str] = None,
    additional_label: str = "ADDITIONAL RUNTIME EVENT",
) -> bool:
    message = (
        "[RUNTIME SYSTEM CONTEXT]\n"
        f"{str(headline or '').strip()}\n\n"
        f"{str(prompt or '').strip()}"
    ).strip()
    if not message:
        return False

    if merge_marker:
        try:
            pending = getattr(session, "deferred_interrupt_queue", None)
            if isinstance(pending, list):
                marker = str(merge_marker)
                for index in range(len(pending) - 1, -1, -1):
                    existing = str(pending[index] or "")
                    if existing.startswith("[RUNTIME SYSTEM CONTEXT]") and marker in existing:
                        pending[index] = (
                            f"{existing.rstrip()}\n\n"
                            f"[{additional_label}]\n"
                            f"{str(prompt or '').strip()}"
                        )
                        return True
        except Exception:
            pass

    queue_interrupt = getattr(session, "queue_interrupt", None)
    if callable(queue_interrupt):
        try:
            queue_interrupt(message, deferred=True)
            return True
        except Exception:
            pass

    try:
        pending = list(getattr(session, "deferred_interrupt_queue", []) or [])
        pending.append(message)
        setattr(session, "deferred_interrupt_queue", pending)
        return True
    except Exception:
        return False
