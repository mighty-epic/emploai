from __future__ import annotations

import functools
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

from shared.subprocess_utils import hidden_subprocess_kwargs


_WINDOWS = os.name == "nt"
_ACL_LOCK = threading.Lock()
_HARDENED_WINDOWS_PATHS: dict[str, tuple[int, int, int]] = {}


def _path_signature(path: Path) -> Optional[tuple[int, int, int]]:
    try:
        state = path.stat()
    except OSError:
        return None
    return (int(state.st_dev), int(state.st_ino), int(state.st_ctime_ns))


@functools.lru_cache(maxsize=1)
def _windows_account_name() -> str:
    if not _WINDOWS:
        return ""
    try:
        completed = subprocess.run(
            ["whoami"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(completed.stdout or "").strip()


def _harden_windows_acl(path: Path, *, is_directory: bool) -> bool:
    account_name = _windows_account_name()
    if not account_name:
        return False

    signature = _path_signature(path)
    if signature is None:
        return False
    cache_key = str(path.resolve()).casefold()
    with _ACL_LOCK:
        if _HARDENED_WINDOWS_PATHS.get(cache_key) == signature:
            return True

    permission = "(OI)(CI)F" if is_directory else "F"
    try:
        completed = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{account_name}:{permission}",
                f"*S-1-5-18:{permission}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False

    with _ACL_LOCK:
        _HARDENED_WINDOWS_PATHS[cache_key] = signature
    return True


def harden_private_path(path: Path, mode: int = 0o600, *, is_directory: Optional[bool] = None) -> bool:
    """Best-effort owner-only protection, including a real Windows DACL."""

    target = Path(path)
    if not target.exists():
        return False
    try:
        target.chmod(mode)
    except OSError:
        pass
    if not _WINDOWS:
        return True
    directory = target.is_dir() if is_directory is None else bool(is_directory)
    return _harden_windows_acl(target, is_directory=directory)
