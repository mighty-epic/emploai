"""File-related slash commands for the TUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Callable


def pwd(context, args, result_cls):
    return result_cls(True, str(context.cwd))


def cd(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /cd <path>")
    target = context._resolve_path(args[0])
    if not target.exists() or not target.is_dir():
        return result_cls(False, f"Not a directory: {target}")
    context.cwd = target
    return result_cls(True, str(context.cwd))


def ls(context, args, result_cls):
    target = context._resolve_path(args[0]) if args else context.cwd
    if not target.exists():
        return result_cls(False, f"Not found: {target}")
    if not target.is_dir():
        return result_cls(False, f"Not a directory: {target}")
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    rendered = []
    for entry in entries:
        suffix = "/" if entry.is_dir() else ""
        rendered.append(f"{entry.name}{suffix}")
    return result_cls(True, "\n".join(rendered) if rendered else "(empty)")


def cat(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /cat <path>")
    target = context._resolve_path(args[0])
    if not target.exists() or not target.is_file():
        return result_cls(False, f"Not a file: {target}")
    content = target.read_text(encoding="utf-8")
    return result_cls(True, content)


def touch(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /touch <path>")
    target = context._resolve_path(args[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return result_cls(True, f"Touched {target}")


def write(context, args, result_cls):
    if len(args) < 2:
        return result_cls(False, "Usage: /write <path> <text>")
    target = context._resolve_path(args[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    text = " ".join(args[1:])
    target.write_text(text, encoding="utf-8")
    return result_cls(True, f"Wrote {target}")


def append(context, args, result_cls):
    if len(args) < 2:
        return result_cls(False, "Usage: /append <path> <text>")
    target = context._resolve_path(args[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    text = " ".join(args[1:])
    with target.open("a", encoding="utf-8") as handle:
        handle.write(text)
    return result_cls(True, f"Appended {target}")


def mv(context, args, result_cls):
    if len(args) < 2:
        return result_cls(False, "Usage: /mv <src> <dest>")
    source = context._resolve_path(args[0])
    dest = context._resolve_path(args[1])
    if not source.exists():
        return result_cls(False, f"Not found: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    return result_cls(True, f"Moved {source} -> {dest}")


def cp(context, args, result_cls):
    if len(args) < 2:
        return result_cls(False, "Usage: /cp <src> <dest>")
    source = context._resolve_path(args[0])
    dest = context._resolve_path(args[1])
    if not source.exists() or not source.is_file():
        return result_cls(False, f"Not a file: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return result_cls(True, f"Copied {source} -> {dest}")


def mkdir(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /mkdir <path>")
    target = context._resolve_path(args[0])
    target.mkdir(parents=True, exist_ok=True)
    return result_cls(True, f"Created {target}")


def rm(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /rm [-r] <path>")
    recursive = False
    target_arg = args[0]
    if target_arg == "-r":
        if len(args) < 2:
            return result_cls(False, "Usage: /rm [-r] <path>")
        recursive = True
        target_arg = args[1]
    target = context._resolve_path(target_arg)
    if not target.exists():
        return result_cls(False, f"Not found: {target}")
    if target.is_dir():
        if not recursive:
            return result_cls(False, "Use /rm -r for directories")
        for item in sorted(target.rglob("*"), reverse=True):
            if item.is_file() or item.is_symlink():
                item.unlink()
            else:
                item.rmdir()
        target.rmdir()
        return result_cls(True, f"Removed directory {target}")
    target.unlink()
    return result_cls(True, f"Removed {target}")


def stat(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /stat <path>")
    target = context._resolve_path(args[0])
    if not target.exists():
        return result_cls(False, f"Not found: {target}")
    stat_info = target.stat()
    lines = [
        f"Path: {target}",
        f"Type: {'directory' if target.is_dir() else 'file'}",
        f"Size: {stat_info.st_size} bytes",
        f"Modified: {datetime.fromtimestamp(stat_info.st_mtime)}",
    ]
    return result_cls(True, "\n".join(lines))


def search(context, args, result_cls):
    if len(args) < 2:
        return result_cls(False, "Usage: /search <pattern> <path>")
    pattern = re.compile(args[0])
    target = context._resolve_path(args[1])
    if not target.exists():
        return result_cls(False, f"Not found: {target}")
    matches = []
    paths = [target] if target.is_file() else list(target.rglob("*"))
    for file_path in paths:
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                matches.append(f"{file_path}:{index}: {line.strip()}")
    return result_cls(True, "\n".join(matches) if matches else "(no matches)")


def edit(context, args, result_cls, open_editor: Callable[[Path, str], None]):
    if not args:
        return result_cls(False, "Usage: /edit <path>")
    target = context._resolve_path(args[0])
    content = target.read_text(encoding="utf-8") if target.exists() else ""
    open_editor(target, content)
    return result_cls(True, f"Opened editor for {target}")
