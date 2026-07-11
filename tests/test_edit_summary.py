from __future__ import annotations

import subprocess
from pathlib import Path

from shared.edit_summary import build_workspace_edit_summary, capture_workspace_edit_baseline


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def test_edit_summary_ignores_preexisting_dirty_files(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")

    (tmp_path / "existing.txt").write_text("clean\n", encoding="utf-8")
    _git(tmp_path, "add", "existing.txt")
    _git(tmp_path, "commit", "-m", "initial")

    (tmp_path / "existing.txt").write_text("dirty before run\n", encoding="utf-8")
    (tmp_path / "old-untracked.txt").write_text("old\n", encoding="utf-8")
    baseline = capture_workspace_edit_baseline(tmp_path)

    (tmp_path / "new-file.txt").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "changed-by-run.txt").write_text("created\n", encoding="utf-8")

    summary = build_workspace_edit_summary(tmp_path, baseline)

    assert summary is not None
    paths = {item["path"] for item in summary["files"]}
    assert paths == {"changed-by-run.txt", "new-file.txt"}
    assert summary["file_count"] == 2
    assert summary["additions"] == 3
    assert summary["deletions"] == 0
