from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from shared.runtime_paths import user_state_root
from shared.atomic_io import atomic_write_bytes, atomic_write_json


MAX_OBJECT_BYTES = 100 * 1024 * 1024
MAX_ACCOUNT_BYTES = 2 * 1024 * 1024 * 1024
_CLOUD_OBJECT_LOCK = threading.RLock()


def _now() -> float:
    return time.time()


def _safe_name(value: str, *, fallback: str = "artifact") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(value or "").strip())
    return cleaned.strip(".-")[:120] or fallback


@dataclass
class CloudObjectResult:
    status: str
    object_key: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: int = 0
    reason: Optional[str] = None
    stored_at: Optional[float] = None

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "cloud_sync_status": self.status,
            "cloud_object_key": self.object_key,
            "cloud_sha256": self.sha256,
            "cloud_size_bytes": self.size_bytes,
            "cloud_skip_reason": self.reason,
            "cloud_synced_at": self.stored_at,
            "cloud_storage_backend": "vps_object_store",
            "cloud_object_max_bytes": MAX_OBJECT_BYTES,
            "cloud_account_max_bytes": MAX_ACCOUNT_BYTES,
        }


class CloudObjectStore:
    """Small VPS/local-disk backed object store for beta cloud recovery.

    This intentionally stores opaque content-addressed blobs and metadata only.
    It is shaped so the same object_key metadata can later point at S3/R2.
    """

    def __init__(self, *, user_id: int) -> None:
        self.user_id = int(user_id)
        self.root = (user_state_root(self.user_id) / "cloud_object_store").resolve()
        self.objects_dir = self.root / "objects"
        self.manifest_path = self.root / "manifest.json"
        self.manifest_backup_path = self.root / ".recovery" / "manifest.json.bak"
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _usage_bytes(self) -> int:
        total = 0
        if not self.objects_dir.exists():
            return 0
        for path in self.objects_dir.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def _read_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists() and not self.manifest_backup_path.exists():
            return {"objects": {}}
        for candidate in (self.manifest_path, self.manifest_backup_path):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            payload.setdefault("objects", {})
            if candidate == self.manifest_backup_path:
                atomic_write_json(
                    self.manifest_path,
                    payload,
                    backup_path=self.manifest_backup_path,
                    sort_keys=True,
                )
            return payload
        return {"objects": {}}

    def _write_manifest(self, payload: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.manifest_path,
            payload,
            backup_path=self.manifest_backup_path,
            sort_keys=True,
        )

    def put_bytes(
        self,
        *,
        data: bytes,
        file_name: str,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CloudObjectResult:
        with _CLOUD_OBJECT_LOCK:
            return self._put_bytes_locked(
                data=data,
                file_name=file_name,
                content_type=content_type,
                metadata=metadata,
            )

    def _put_bytes_locked(
        self,
        *,
        data: bytes,
        file_name: str,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CloudObjectResult:
        raw = bytes(data or b"")
        size = len(raw)
        digest = hashlib.sha256(raw).hexdigest()
        if size > MAX_OBJECT_BYTES:
            return CloudObjectResult(status="metadata_only", sha256=digest, size_bytes=size, reason="object_too_large")
        current_usage = self._usage_bytes()
        if current_usage + size > MAX_ACCOUNT_BYTES:
            return CloudObjectResult(status="metadata_only", sha256=digest, size_bytes=size, reason="account_quota_exceeded")

        safe_name = _safe_name(file_name)
        object_key = f"objects/{digest[:2]}/{digest}-{safe_name}"
        target = (self.root / object_key).resolve()
        if self.root not in target.parents:
            return CloudObjectResult(status="metadata_only", sha256=digest, size_bytes=size, reason="invalid_object_key")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            atomic_write_bytes(target, raw)

        manifest = self._read_manifest()
        manifest["objects"][object_key] = {
            "object_key": object_key,
            "sha256": digest,
            "size_bytes": size,
            "file_name": safe_name,
            "content_type": content_type,
            "metadata": dict(metadata or {}),
            "stored_at": _now(),
        }
        self._write_manifest(manifest)
        return CloudObjectResult(status="synced", object_key=object_key, sha256=digest, size_bytes=size, stored_at=manifest["objects"][object_key]["stored_at"])

    def object_path(self, object_key: str) -> Path:
        target = (self.root / str(object_key or "")).resolve()
        if target == self.root or self.root not in target.parents:
            raise ValueError("Invalid object key")
        return target

    def list_objects(self) -> list[Dict[str, Any]]:
        manifest = self._read_manifest()
        objects = list(dict(manifest.get("objects") or {}).values())
        objects.sort(key=lambda item: float(item.get("stored_at") or 0), reverse=True)
        return objects

    def delete_object(self, object_key: str) -> Dict[str, Any]:
        with _CLOUD_OBJECT_LOCK:
            return self._delete_object_locked(object_key)

    def _delete_object_locked(self, object_key: str) -> Dict[str, Any]:
        key = str(object_key or "").strip()
        if not key:
            return {"deleted": False, "object_key": key, "reason": "missing_object_key"}
        path = self.object_path(key)
        deleted_file = False
        if path.exists() and path.is_file():
            path.unlink()
            deleted_file = True
        manifest = self._read_manifest()
        objects = dict(manifest.get("objects") or {})
        deleted_manifest = key in objects
        if deleted_manifest:
            objects.pop(key, None)
            manifest["objects"] = objects
            self._write_manifest(manifest)
        return {
            "deleted": bool(deleted_file or deleted_manifest),
            "object_key": key,
            "deleted_file": deleted_file,
            "deleted_manifest": deleted_manifest,
        }

    def restore_object(
        self,
        *,
        object_key: str,
        target_dir: Path,
        file_name: str,
        preserve_conflicts: bool = True,
    ) -> Dict[str, Any]:
        source = self.object_path(object_key)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(object_key)
        target_dir = Path(target_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        base_name = _safe_name(file_name)
        destination = (target_dir / base_name).resolve()
        if target_dir not in destination.parents:
            raise ValueError("Invalid restore destination")
        conflict = destination.exists()
        if conflict and preserve_conflicts:
            stem = destination.stem
            suffix = destination.suffix
            counter = 1
            while destination.exists():
                destination = target_dir / f"{stem}.cloud-copy-{counter}{suffix}"
                counter += 1
        shutil.copy2(source, destination)
        return {
            "object_key": object_key,
            "restored_path": str(destination),
            "conflict_preserved": bool(conflict and preserve_conflicts),
        }

    def restore_object_to_relative_path(
        self,
        *,
        object_key: str,
        target_dir: Path,
        relative_path: str,
        fallback_file_name: str,
        preserve_conflicts: bool = True,
    ) -> Dict[str, Any]:
        source = self.object_path(object_key)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(object_key)
        target_dir = Path(target_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        raw_parts = [
            _safe_name(part, fallback="")
            for part in str(relative_path or "").replace("\\", "/").split("/")
            if str(part or "").strip() and str(part or "").strip() not in {".", ".."}
        ]
        if not raw_parts:
            raw_parts = [_safe_name(fallback_file_name)]
        raw_parts[-1] = raw_parts[-1] or _safe_name(fallback_file_name)
        destination = (target_dir.joinpath(*raw_parts)).resolve()
        if destination == target_dir or target_dir not in destination.parents:
            raise ValueError("Invalid restore destination")
        destination.parent.mkdir(parents=True, exist_ok=True)
        conflict = destination.exists()
        if conflict and preserve_conflicts:
            stem = destination.stem
            suffix = destination.suffix
            counter = 1
            while destination.exists():
                destination = destination.with_name(f"{stem}.cloud-copy-{counter}{suffix}")
                counter += 1
        shutil.copy2(source, destination)
        return {
            "object_key": object_key,
            "restored_path": str(destination),
            "relative_path": "/".join(raw_parts),
            "conflict_preserved": bool(conflict and preserve_conflicts),
        }
