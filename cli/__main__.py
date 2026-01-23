"""CLI entrypoint for the Textual TUI."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

from cli.tui_app import run

DEFAULT_WATCH_INTERVAL = 0.6


def _resolve_watch_paths(base_path: Path, watch_paths: list[str]) -> list[Path]:
    if watch_paths:
        return [Path(path).expanduser().resolve() for path in watch_paths]
    candidate_paths = [base_path / "cli", base_path / "agent"]
    existing = [path for path in candidate_paths if path.exists()]
    return existing or [base_path]


def _iter_watch_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            if "__pycache__" not in path.parts:
                files.append(path)
            continue
        if not path.is_dir():
            continue
        for file_path in path.rglob("*.py"):
            if "__pycache__" in file_path.parts:
                continue
            files.append(file_path)
    return files


def _snapshot(paths: Iterable[Path]) -> dict[Path, float]:
    snapshot: dict[Path, float] = {}
    for file_path in _iter_watch_files(paths):
        try:
            snapshot[file_path] = file_path.stat().st_mtime
        except FileNotFoundError:
            continue
    return snapshot


def _run_with_watch(args: argparse.Namespace) -> int:
    base_path = Path(__file__).resolve().parents[1]
    watch_paths = _resolve_watch_paths(base_path, args.watch_path)
    interval = max(args.watch_interval, 0.1)
    snapshot = _snapshot(watch_paths)
    print("Watching for changes in:")
    for watch_path in watch_paths:
        print(f"  - {watch_path}")

    while True:
        child = subprocess.Popen([sys.executable, "-m", "cli", "--run-once"])
        restart = False
        try:
            while child.poll() is None:
                time.sleep(interval)
                new_snapshot = _snapshot(watch_paths)
                if new_snapshot != snapshot:
                    restart = True
                    snapshot = new_snapshot
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                    break
        except KeyboardInterrupt:
            child.terminate()
            child.wait()
            return 1

        if not restart:
            return child.returncode or 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Textual TUI launcher")
    parser.add_argument("--watch", action="store_true", help="Reload the TUI on file changes")
    parser.add_argument(
        "--watch-path",
        action="append",
        default=[],
        help="Additional path to watch (repeatable)",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=DEFAULT_WATCH_INTERVAL,
        help="Polling interval in seconds",
    )
    parser.add_argument("--run-once", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.watch and not args.run_once:
        return _run_with_watch(args)

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
