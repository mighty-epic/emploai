"""Process restart helpers for the Telegram bot."""

from __future__ import annotations

import os
import sys
from typing import Iterable, List, Optional


def build_restart_exec_args(
    *,
    executable: Optional[str] = None,
    orig_argv: Optional[Iterable[str]] = None,
    argv: Optional[Iterable[str]] = None,
    script_path_fallback: Optional[str] = None,
) -> List[str]:
    """Build the exact argv list used to restart the current Python process."""
    python_executable = executable or sys.executable
    raw_orig = list(orig_argv if orig_argv is not None else (getattr(sys, "orig_argv", None) or []))
    raw_argv = list(argv if argv is not None else sys.argv)

    if raw_orig:
        tail = raw_orig[1:]
    else:
        tail = list(raw_argv)

    if not tail and script_path_fallback:
        tail = [script_path_fallback]

    if tail and not str(tail[0]).startswith("-") and str(tail[0]).endswith(".py"):
        tail[0] = os.path.abspath(str(tail[0]))

    return [python_executable, *tail]


def exec_current_process(
    *,
    executable: Optional[str] = None,
    orig_argv: Optional[Iterable[str]] = None,
    argv: Optional[Iterable[str]] = None,
    env: Optional[dict[str, str]] = None,
    execve_func=None,
    script_path_fallback: Optional[str] = None,
) -> None:
    """Replace the current process with a fresh copy of the bot."""
    python_executable = executable or sys.executable
    exec_args = build_restart_exec_args(
        executable=python_executable,
        orig_argv=orig_argv,
        argv=argv,
        script_path_fallback=script_path_fallback,
    )
    runner = execve_func or os.execve
    runner(python_executable, exec_args, env or os.environ.copy())
