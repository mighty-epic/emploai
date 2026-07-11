"""Safety helpers for local memory files.

These helpers keep durable memory useful without letting raw secrets become
part of the agent's long-term prompt context.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from shared.atomic_io import atomic_write_text


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "secret assignment",
        re.compile(
            r"(?i)\b(api[_ -]?key|secret|token|password|passwd|private[_ -]?key)\b\s*[:=]\s*['\"]?[^'\"\s]{8,}"
        ),
    ),
    ("openai api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}\b")),
    (
        "private key block",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ),
)


class MemorySafetyError(ValueError):
    """Raised when a memory write would persist unsafe content."""


def detect_secret_like_text(text: str) -> List[str]:
    """Return human-readable matches for secret-like content."""
    if not text:
        return []
    matches: List[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            matches.append(label)
    return matches


def assert_safe_memory_text(text: str, *, context: str = "memory") -> None:
    """Reject memory writes that look like they contain raw secrets."""
    matches = detect_secret_like_text(text)
    if matches:
        labels = ", ".join(sorted(set(matches)))
        raise MemorySafetyError(
            f"Refusing to save {context} because it appears to contain raw secret material: {labels}."
        )


def backup_file(path: Path, backup_dir: Path, *, label: str = "backup") -> Path | None:
    """Create a timestamped backup of a file if it exists."""
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"{path.name}.{label}.{timestamp}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def strip_placeholder_lines(lines: Iterable[str]) -> list[str]:
    """Remove generated placeholder lines from curated memory context."""
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("*(") and stripped.endswith(")*"):
            continue
        filtered.append(line)
    return filtered
