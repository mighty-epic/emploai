from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from shared.subprocess_utils import hidden_subprocess_kwargs


def _run_git(git_root: Path | str, args: list[str], *, timeout: float = 5.0) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(git_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _resolve_git_root(workspace: Any) -> Optional[Path]:
    workspace_text = str(workspace or "").strip()
    if not workspace_text:
        return None
    workspace_path = Path(workspace_text).expanduser()
    output = _run_git(workspace_path, ["rev-parse", "--show-toplevel"])
    if not output:
        return None
    try:
        root = Path(output.strip()).expanduser().resolve()
    except Exception:
        return None
    return root if root.exists() and root.is_dir() else None


def _parse_numstat(output: Optional[str]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for raw_line in str(output or "").splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 3:
            continue
        add_text, del_text, path_text = parts[0], parts[1], "\t".join(parts[2:]).strip()
        if not path_text:
            continue
        binary = add_text == "-" or del_text == "-"
        additions = 0 if binary else max(0, int(add_text or "0"))
        deletions = 0 if binary else max(0, int(del_text or "0"))
        stats[path_text.replace("\\", "/")] = {
            "additions": additions,
            "deletions": deletions,
            "binary": binary,
        }
    return stats


def _text_line_count(path: Path) -> int:
    try:
        data = path.read_bytes()
    except Exception:
        return 0
    if not data:
        return 0
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _untracked_line_counts(git_root: Path) -> Dict[str, int]:
    output = _run_git(git_root, ["ls-files", "--others", "--exclude-standard", "-z"], timeout=8.0)
    counts: Dict[str, int] = {}
    for path_text in str(output or "").split("\0"):
        rel_path = path_text.strip().replace("\\", "/")
        if not rel_path:
            continue
        counts[rel_path] = _text_line_count(git_root / rel_path)
    return counts


def capture_workspace_edit_baseline(workspace: Any) -> Optional[Dict[str, Any]]:
    git_root = _resolve_git_root(workspace)
    if git_root is None:
        return None
    return {
        "git_root": str(git_root),
        "tracked": _parse_numstat(_run_git(git_root, ["diff", "--numstat", "HEAD", "--"], timeout=8.0)),
        "untracked": _untracked_line_counts(git_root),
    }


def _delta_line_counts(before: Dict[str, Any] | None, after: Dict[str, Any] | None) -> Dict[str, Any]:
    before_add = int((before or {}).get("additions") or 0)
    before_del = int((before or {}).get("deletions") or 0)
    after_add = int((after or {}).get("additions") or 0)
    after_del = int((after or {}).get("deletions") or 0)
    add_delta = after_add - before_add
    del_delta = after_del - before_del
    additions = max(0, add_delta) + max(0, -del_delta)
    deletions = max(0, del_delta) + max(0, -add_delta)
    return {
        "additions": additions,
        "deletions": deletions,
        "binary": bool((before or {}).get("binary") or (after or {}).get("binary")),
    }


def build_workspace_edit_summary(workspace: Any, baseline: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(baseline, dict):
        return None
    git_root_text = str(baseline.get("git_root") or "").strip()
    if not git_root_text:
        return None
    git_root = Path(git_root_text)
    if not git_root.exists():
        return None

    before_tracked = baseline.get("tracked") if isinstance(baseline.get("tracked"), dict) else {}
    before_untracked = baseline.get("untracked") if isinstance(baseline.get("untracked"), dict) else {}
    after_tracked = _parse_numstat(_run_git(git_root, ["diff", "--numstat", "HEAD", "--"], timeout=8.0))
    after_untracked = _untracked_line_counts(git_root)

    changed: list[Dict[str, Any]] = []
    all_tracked_paths = set(before_tracked) | set(after_tracked)
    for rel_path in sorted(all_tracked_paths):
        before = before_tracked.get(rel_path)
        after = after_tracked.get(rel_path)
        delta = _delta_line_counts(before, after)
        if not delta["binary"] and delta["additions"] == 0 and delta["deletions"] == 0:
            continue
        changed.append({"path": rel_path, **delta})

    all_untracked_paths = set(before_untracked) | set(after_untracked)
    for rel_path in sorted(all_untracked_paths):
        before_lines = int(before_untracked.get(rel_path) or 0)
        after_lines = int(after_untracked.get(rel_path) or 0)
        if before_lines == after_lines:
            continue
        changed.append(
            {
                "path": rel_path,
                "additions": max(0, after_lines - before_lines),
                "deletions": max(0, before_lines - after_lines),
                "binary": False,
            }
        )

    if not changed:
        return None

    changed.sort(key=lambda item: (str(item.get("path") or "").lower()))
    total_additions = sum(int(item.get("additions") or 0) for item in changed)
    total_deletions = sum(int(item.get("deletions") or 0) for item in changed)
    return {
        "kind": "workspace_edit_summary",
        "file_count": len(changed),
        "additions": total_additions,
        "deletions": total_deletions,
        "files": changed[:200],
        "truncated": len(changed) > 200,
        "git_root": str(git_root),
    }
