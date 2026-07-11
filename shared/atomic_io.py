from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional


def _sync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    backup_path: Optional[Path] = None,
) -> None:
    """Durably replace a file without exposing a partially-written target."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(bytes(content))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        _sync_directory(target.parent)
        if backup_path is not None:
            atomic_write_bytes(Path(backup_path), bytes(content))
    finally:
        try:
            if temporary_path.exists():
                temporary_path.unlink()
        except OSError:
            pass


def atomic_write_text(
    path: Path,
    content: str,
    *,
    backup_path: Optional[Path] = None,
) -> None:
    atomic_write_bytes(
        path,
        str(content).encode("utf-8"),
        backup_path=backup_path,
    )


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    backup_path: Optional[Path] = None,
    ensure_ascii: bool = False,
    indent: Optional[int] = 2,
    sort_keys: bool = False,
    default: Optional[Callable[[Any], Any]] = None,
) -> None:
    atomic_write_text(
        path,
        f"{json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys, default=default)}\n",
        backup_path=backup_path,
    )
