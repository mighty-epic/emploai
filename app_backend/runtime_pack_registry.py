from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from shared.runtime_paths import shared_state_root


CONTEXT_INDEX_ENGLISH_PACK_ID = "context_index_english"
CONTEXT_INDEX_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
CONTEXT_INDEX_APPROX_SIZE_MB = 90
RUNTIME_PACK_MANIFEST = "pack_manifest.json"

_PROGRESS_LOCK = threading.Lock()
_PROGRESS: Dict[str, Dict[str, Any]] = {}


def runtime_packs_root() -> Path:
    root = (shared_state_root() / "runtime_packs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def context_index_pack_root() -> Path:
    return (runtime_packs_root() / CONTEXT_INDEX_ENGLISH_PACK_ID).resolve()


def _manifest_path(pack_id: str) -> Path:
    return (runtime_packs_root() / pack_id / RUNTIME_PACK_MANIFEST).resolve()


def _set_progress(pack_id: str, **payload: Any) -> Dict[str, Any]:
    state = {"pack_id": pack_id, **payload}
    with _PROGRESS_LOCK:
        _PROGRESS[pack_id] = state
    return state


def runtime_pack_progress(pack_id: Optional[str] = None) -> Dict[str, Any]:
    with _PROGRESS_LOCK:
        if pack_id:
            return dict(_PROGRESS.get(pack_id) or {"pack_id": pack_id, "state": "idle"})
        return {key: dict(value) for key, value in _PROGRESS.items()}


def _context_pack_status() -> Dict[str, Any]:
    root = context_index_pack_root()
    manifest_path = _manifest_path(CONTEXT_INDEX_ENGLISH_PACK_ID)
    manifest = None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = None
    required = [root / "config.json", root / "tokenizer.json"]
    installed = all(path.exists() for path in required)
    verified = bool(
        installed
        and isinstance(manifest, dict)
        and manifest.get("model_id") == CONTEXT_INDEX_MODEL_ID
    )
    return {
        "id": CONTEXT_INDEX_ENGLISH_PACK_ID,
        "kind": "context_index",
        "title": "English semantic context",
        "description": "Local English embeddings for manager context search. Lexical search works without this pack.",
        "installed": installed,
        "available": installed and verified,
        "managed": True,
        "removable": installed,
        "approx_size_mb": CONTEXT_INDEX_APPROX_SIZE_MB,
        "model_id": CONTEXT_INDEX_MODEL_ID,
        "path": str(root),
        "manifest": manifest,
        "manifest_verified": verified,
        "issues": [] if verified else ["Install this optional pack to add semantic ranking; lexical fallback remains available."],
        "progress": runtime_pack_progress(CONTEXT_INDEX_ENGLISH_PACK_ID),
    }


def _voice_pack_view(pack_id: str) -> Dict[str, Any]:
    from app_backend.voice_pack_manager import get_voice_pack_status

    status = dict(get_voice_pack_status(pack_id))
    titles = {
        "english_local": "English voice input",
        "hebrew_local": "Hebrew voice input",
        "kokoro_tts": "Kokoro Jarvis voice",
        "kyutai_clone_tts": "Kyutai cloned Jarvis voice",
    }
    approximate_sizes = {
        "english_local": 320,
        "hebrew_local": 1100,
        "kokoro_tts": 420,
        "kyutai_clone_tts": 1300,
    }
    status.update(
        {
            "kind": "voice",
            "title": titles.get(pack_id, pack_id),
            "description": "Local voice runtime pack.",
            "approx_size_mb": approximate_sizes.get(pack_id),
            "progress": runtime_pack_progress(pack_id),
        }
    )
    return status


def runtime_pack_ids() -> list[str]:
    from app_backend.voice_pack_manager import VOICE_PACK_IDS

    return [*VOICE_PACK_IDS, CONTEXT_INDEX_ENGLISH_PACK_ID]


def runtime_pack_status(pack_id: str) -> Dict[str, Any]:
    clean = str(pack_id or "").strip()
    if clean == CONTEXT_INDEX_ENGLISH_PACK_ID:
        return _context_pack_status()
    if clean in runtime_pack_ids():
        return _voice_pack_view(clean)
    raise ValueError(f"Unsupported runtime pack: {clean}")


def runtime_pack_summary() -> Dict[str, Any]:
    packs = [runtime_pack_status(pack_id) for pack_id in runtime_pack_ids()]
    return {
        "packs": packs,
        "count": len(packs),
        "installed_count": sum(1 for pack in packs if pack.get("installed")),
    }


def install_runtime_pack(
    pack_id: str,
    *,
    force: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    clean = str(pack_id or "").strip()

    def progress(**payload: Any) -> None:
        state = _set_progress(clean, **payload)
        if progress_callback:
            progress_callback(state)

    if clean != CONTEXT_INDEX_ENGLISH_PACK_ID:
        from app_backend.voice_pack_manager import install_voice_pack

        def voice_progress(payload: Dict[str, Any]) -> None:
            state = _set_progress(clean, **{key: value for key, value in dict(payload or {}).items() if key != "pack_id"})
            if progress_callback:
                progress_callback(state)

        return _voice_pack_view(clean) if install_voice_pack(clean, force=force, progress_callback=voice_progress) else _voice_pack_view(clean)

    status = _context_pack_status()
    if status["available"] and not force:
        progress(state="ready", phase="complete", percent=100, message="English semantic context pack is ready.")
        return _context_pack_status()
    progress(state="installing", phase="prepare", percent=2, message="Preparing English semantic context pack download…")
    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        progress(state="error", phase="dependency", message="huggingface_hub is required to install this pack.")
        raise RuntimeError("huggingface_hub is required to install the English context pack") from exc
    root = context_index_pack_root()
    if force:
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    progress(state="installing", phase="download", percent=10, message="Downloading all-MiniLM-L6-v2 locally…")
    snapshot_download(
        repo_id=CONTEXT_INDEX_MODEL_ID,
        local_dir=str(root),
        local_dir_use_symlinks=False,
    )
    manifest = {
        "schema_version": 1,
        "pack_id": CONTEXT_INDEX_ENGLISH_PACK_ID,
        "kind": "context_index",
        "model_id": CONTEXT_INDEX_MODEL_ID,
    }
    _manifest_path(clean).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    status = _context_pack_status()
    if not status["available"]:
        progress(state="error", phase="verify", message="The downloaded context pack did not pass verification.")
        raise RuntimeError("Context pack installation completed but required files are missing")
    progress(state="ready", phase="complete", percent=100, message="English semantic context pack is ready.")
    try:
        from app_backend.context_inspection import vectorize_all_eligible_indexes

        vectorize_all_eligible_indexes()
    except Exception:
        pass
    return status


def remove_runtime_pack(pack_id: str) -> Dict[str, Any]:
    clean = str(pack_id or "").strip()
    if clean == CONTEXT_INDEX_ENGLISH_PACK_ID:
        shutil.rmtree(context_index_pack_root(), ignore_errors=True)
        _set_progress(clean, state="idle", phase="removed", percent=0, message="Context pack removed; lexical search remains available.")
        return _context_pack_status()
    from app_backend.voice_pack_manager import remove_voice_pack

    remove_voice_pack(clean)
    _set_progress(clean, state="idle", phase="removed", percent=0, message="Voice pack removed.")
    return _voice_pack_view(clean)
