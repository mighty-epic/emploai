"""Local bundled-skill sync.

Seeds bundled skills into a user-owned local skills directory without
overwriting user edits. This keeps standalone installs useful on first launch
while making local disk the source of truth.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict


MANIFEST_NAME = ".emploai-skill-sync.json"
OPT_OUT_MARKER = ".no-bundled-skills"


def _hash_skill_dir(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name == MANIFEST_NAME:
            continue
        rel = file_path.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "skills": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "skills": {}}
    if not isinstance(data, dict):
        return {"version": 1, "skills": {}}
    data.setdefault("version", 1)
    data.setdefault("skills", {})
    return data


def _write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def sync_bundled_skills(bundled_dir: Path, user_dir: Path) -> Dict[str, Any]:
    """Copy/update bundled skills into a user-owned directory.

    Existing user-modified skills are left alone. Skills deleted by the user are
    respected after they have appeared in the manifest once.
    """
    bundled_dir = Path(bundled_dir).resolve()
    user_dir = Path(user_dir).resolve()
    if bundled_dir == user_dir or not bundled_dir.exists():
        return {"copied": [], "updated": [], "skipped": [], "deleted_respected": []}

    user_dir.mkdir(parents=True, exist_ok=True)
    if (user_dir / OPT_OUT_MARKER).exists():
        return {"copied": [], "updated": [], "skipped": ["opted-out"], "deleted_respected": []}

    manifest_path = user_dir / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    tracked: dict[str, Any] = manifest.setdefault("skills", {})
    copied: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    deleted_respected: list[str] = []

    for bundled_skill in sorted(bundled_dir.iterdir()):
        if not bundled_skill.is_dir() or not (bundled_skill / "SKILL.md").exists():
            continue
        name = bundled_skill.name
        bundled_hash = _hash_skill_dir(bundled_skill)
        target = user_dir / name
        record = tracked.get(name)

        if not target.exists():
            if record:
                record["deleted"] = True
                record["bundled_hash"] = bundled_hash
                deleted_respected.append(name)
                continue
            shutil.copytree(bundled_skill, target)
            tracked[name] = {"bundled_hash": bundled_hash, "deleted": False}
            copied.append(name)
            continue

        if record and record.get("deleted"):
            deleted_respected.append(name)
            continue

        local_hash = _hash_skill_dir(target)
        previous_hash = record.get("bundled_hash") if isinstance(record, dict) else None
        if previous_hash and local_hash != previous_hash:
            skipped.append(name)
            continue

        if local_hash != bundled_hash:
            shutil.rmtree(target)
            shutil.copytree(bundled_skill, target)
            updated.append(name)
        tracked[name] = {"bundled_hash": bundled_hash, "deleted": False}

    _write_manifest(manifest_path, manifest)
    return {
        "copied": copied,
        "updated": updated,
        "skipped": skipped,
        "deleted_respected": deleted_respected,
    }
