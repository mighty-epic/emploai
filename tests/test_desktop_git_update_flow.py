from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_git_update_service_preserves_dirty_checkout_without_blocking_manual_update(tmp_path: Path):
    service_path = ROOT / "desktop_app" / "git_update_services.js"
    script = r"""
const {
  createGitUpdateServices,
  gitUpdateSafetyState,
  parseGitStatusOutput,
} = require(process.argv[1]);

const entries = parseGitStatusOutput(' M source.js\n?? local notes.txt\n');
if (entries.length !== 2 || entries[1].path !== 'local notes.txt') process.exit(2);

const safety = gitUpdateSafetyState({
  updateAvailable: true,
  dirty: true,
  diverged: false,
  pullTarget: { remote: 'origin', branch: 'main' },
});
if (safety.blocked || !safety.requiresManualUpdate) process.exit(3);
const diverged = gitUpdateSafetyState({
  updateAvailable: true,
  dirty: true,
  diverged: true,
  pullTarget: { remote: 'origin', branch: 'main' },
});
if (!diverged.blocked || diverged.requiresManualUpdate) process.exit(8);

const calls = [];
const runGit = async (args) => {
  calls.push(args);
  if (args[0] === 'status') return ' M source.js\n?? local notes.txt';
  if (args[0] === 'stash') return 'Saved working directory and index state';
  if (args[0] === 'rev-parse') return 'stash-commit-123';
  return '';
};

(async () => {
  const service = createGitUpdateServices({
    runGit,
    now: () => new Date('2026-07-13T10:00:00.000Z'),
  });
  const dirty = await service.getDirtyState();
  if (!dirty.dirty || dirty.count !== 2) process.exit(4);
  const backup = await service.preserveLocalChanges(dirty.count);
  if (!backup || backup.count !== 2 || backup.stashCommit !== 'stash-commit-123') process.exit(5);
  const stashCall = calls.find((args) => args[0] === 'stash');
  if (!stashCall || !stashCall.includes('--include-untracked')) process.exit(6);
})().catch(() => process.exit(7));
"""
    result = subprocess.run(
        ["node", "-e", script, str(service_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_desktop_update_ui_explains_local_data_and_keeps_manual_update_available():
    main = (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8")
    settings = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopSetupPanel.tsx"
    ).read_text(encoding="utf-8")
    shell_view = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopAppShellView.tsx"
    ).read_text(encoding="utf-8")
    overlay = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopUpdateOverlay.tsx"
    ).read_text(encoding="utf-8")

    assert "!status.requiresManualUpdate" in main
    assert "preserveLocalChanges(status.dirtyCount)" in main
    assert "Chats, credentials, memory, and other local runtime data stay in place" in settings
    assert "Update Safely & Restart" in settings
    assert "emitUpdateProgress('pulling'" in main
    assert "emitUpdateProgress('building'" in main
    assert "quitAfterManagedShutdown = true" in main
    assert "setTimeout(() => app.exit(0), 250)" in main
    assert "DesktopUpdateOverlay" in shell_view
    assert 'pointerEvents="auto"' in overlay
    assert "Controls are paused while the project is updated" in overlay


def test_git_update_backup_round_trip_with_real_tracked_and_untracked_files(tmp_path: Path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "update-test@example.invalid")
    _git(repo, "config", "user.name", "Update Test")
    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")

    tracked.write_text("local edit\n", encoding="utf-8")
    untracked = repo / "untracked notes.txt"
    untracked.write_text("local note\n", encoding="utf-8")

    service_path = ROOT / "desktop_app" / "git_update_services.js"
    script = r"""
const { execFile } = require('child_process');
const { createGitUpdateServices } = require(process.argv[1]);
const repo = process.argv[2];
const runGit = (args) => new Promise((resolve, reject) => {
  execFile('git', args, { cwd: repo }, (error, stdout, stderr) => {
    if (error) return reject(new Error(String(stderr || stdout || error.message).trim()));
    resolve(String(stdout || '').trim());
  });
});
(async () => {
  const service = createGitUpdateServices({ runGit });
  const dirty = await service.getDirtyState();
  if (!dirty.dirty || dirty.count !== 2) process.exit(2);
  const backup = await service.preserveLocalChanges(dirty.count);
  if (!backup || (await service.getDirtyState()).dirty) process.exit(3);
  if (!(await service.restoreLocalChanges(backup))) process.exit(4);
  const restored = await service.getDirtyState();
  if (!restored.dirty || restored.count !== 2) process.exit(5);
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(6);
});
"""
    result = subprocess.run(
        ["node", "-e", script, str(service_path), str(repo)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert tracked.read_text(encoding="utf-8") == "local edit\n"
    assert untracked.read_text(encoding="utf-8") == "local note\n"
