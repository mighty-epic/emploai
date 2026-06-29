from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    runtime_root,
    tools_root,
)
from shared.live_config import get_live_config

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover
    snapshot_download = None


VOICE_ENGINE_ENGLISH = "english_local"
VOICE_ENGINE_HEBREW = "hebrew_local"
VOICE_ENGINE_KOKORO_TTS = "kokoro_tts"
VOICE_ENGINE_KYUTAI_TTS = "kyutai_clone_tts"
STT_VOICE_PACK_IDS = (VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW)
TTS_VOICE_PACK_IDS = (VOICE_ENGINE_KOKORO_TTS, VOICE_ENGINE_KYUTAI_TTS)
VOICE_PACK_IDS = (*STT_VOICE_PACK_IDS, *TTS_VOICE_PACK_IDS)

APP_STT_MODEL_ENV = "EMPLO_APP_STT_MODEL"
APP_STT_DRAFT_MODEL_ENV = "EMPLO_APP_STT_DRAFT_MODEL"
APP_STT_BINARY_FLAVOR_ENV = "EMPLO_APP_STT_BINARY_FLAVOR"
APP_STT_ENGLISH_PACK_REPO_ENV = "EMPLO_APP_STT_ENGLISH_PACK_REPO"
APP_STT_ENGLISH_PACK_DIR_ENV = "EMPLO_APP_STT_ENGLISH_PACK_DIR"
ENGLISH_PACK_ARCHIVE_URL_ENV = "EMPLOAI_ENGLISH_VOICE_PACK_ARCHIVE_URL"
ENGLISH_PACK_SOURCE_DIR_ENV = "EMPLOAI_ENGLISH_VOICE_PACK_SOURCE_DIR"
ENGLISH_PACK_REVISION_ENV = "EMPLOAI_ENGLISH_VOICE_PACK_REVISION"
APP_STT_HEBREW_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_MODEL_REPO"
APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
HEBREW_PACK_ARCHIVE_URL_ENV = "EMPLOAI_HEBREW_VOICE_PACK_ARCHIVE_URL"
HEBREW_PACK_SOURCE_DIR_ENV = "EMPLOAI_HEBREW_VOICE_PACK_SOURCE_DIR"
HEBREW_PACK_REVISION_ENV = "EMPLOAI_HEBREW_VOICE_PACK_REVISION"
APP_TTS_KOKORO_PACK_REPO_ENV = "EMPLO_APP_TTS_KOKORO_PACK_REPO"
APP_TTS_KOKORO_PACK_DIR_ENV = "EMPLO_APP_TTS_KOKORO_PACK_DIR"
KOKORO_TTS_PACK_ARCHIVE_URL_ENV = "EMPLOAI_KOKORO_TTS_PACK_ARCHIVE_URL"
KOKORO_TTS_PACK_SOURCE_DIR_ENV = "EMPLOAI_KOKORO_TTS_PACK_SOURCE_DIR"
KOKORO_TTS_PACK_REVISION_ENV = "EMPLOAI_KOKORO_TTS_PACK_REVISION"
APP_TTS_KYUTAI_PACK_REPO_ENV = "EMPLO_APP_TTS_KYUTAI_PACK_REPO"
APP_TTS_KYUTAI_PACK_DIR_ENV = "EMPLO_APP_TTS_KYUTAI_PACK_DIR"
KYUTAI_TTS_PACK_ARCHIVE_URL_ENV = "EMPLOAI_KYUTAI_TTS_PACK_ARCHIVE_URL"
KYUTAI_TTS_PACK_SOURCE_DIR_ENV = "EMPLOAI_KYUTAI_TTS_PACK_SOURCE_DIR"
KYUTAI_TTS_PACK_REVISION_ENV = "EMPLOAI_KYUTAI_TTS_PACK_REVISION"
ALLOW_DEV_VOICE_PACK_SOURCES_ENV = "EMPLOAI_ALLOW_DEV_VOICE_PACK_SOURCES"

DEFAULT_LOCAL_STT_MODEL = "base.en-q5_1"
DEFAULT_LOCAL_DRAFT_MODEL = "tiny.en"
DEFAULT_ENGLISH_PACK_ID = "english-whisper-cpp-desktop"
DEFAULT_ENGLISH_PACK_ENGINE = "whisper_cpp"
DEFAULT_ENGLISH_PACK_REVISION = "main"
DEFAULT_ENGLISH_PACK_TUNING_PRESET = "desktop_base_en_q5_1_plus_tiny_en"
DEFAULT_HEBREW_MODEL_REPO = "Mighty1234/whisper-small-3rd-pass-knesset"
DEFAULT_HEBREW_PACK_ID = "hebrew-pass3-knesset"
DEFAULT_HEBREW_PACK_ASSET_NAME = "hebrew-whisper-small-pass3-knesset-runtime-ready.zip"
DEFAULT_HEBREW_PACK_REVISION = "main"
DEFAULT_HEBREW_PACK_ENGINE = "transformers"
DEFAULT_HEBREW_PACK_TUNING_PRESET = "pass3_knesset_desktop"
DEFAULT_KOKORO_TTS_PACK_ID = "kokoro-onnx-emploai-desktop"
DEFAULT_KOKORO_TTS_PACK_ENGINE = "kokoro_onnx"
DEFAULT_KOKORO_TTS_PACK_REVISION = "main"
DEFAULT_KOKORO_TTS_MODEL_FILENAME = "kokoro-v1.0.onnx"
DEFAULT_KOKORO_TTS_VOICES_FILENAME = "voices-emploai-v1.0.bin"
FALLBACK_KOKORO_TTS_VOICES_FILENAME = "voices-v1.0.bin"
DEFAULT_KOKORO_TTS_VOICE = "jarvis"
DEFAULT_KYUTAI_TTS_PACK_ID = "kyutai-pocket-tts-emploai-clone-desktop"
DEFAULT_KYUTAI_TTS_PACK_ENGINE = "pocket"
DEFAULT_KYUTAI_TTS_PACK_REVISION = "main"
DEFAULT_KYUTAI_TTS_VOICE_FILENAME = "jarvis.safetensors"
DEFAULT_KYUTAI_TTS_LANGUAGE = "english"
VOICE_PACK_MANIFEST_FILENAME = "pack_manifest.json"

MANAGED_VOICE_PACKS_DIRNAME = "voice_packs"
ENGLISH_RUNTIME_DIRNAME = "runtime"
ENGLISH_MODELS_DIRNAME = "models"
HEBREW_RUNTIME_DIRNAME = "model"
TTS_MODELS_DIRNAME = "models"
TTS_SITE_PACKAGES_DIRNAME = "site-packages"
TTS_VOICES_DIRNAME = "voices"
HEBREW_REQUIRED_MODEL_FILES = (
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "normalizer.json",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)

VoicePackProgressCallback = Callable[[dict[str, Any]], None]


def managed_voice_packs_root() -> Path:
    return runtime_root() / MANAGED_VOICE_PACKS_DIRNAME


def _managed_english_pack_root() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_ENGLISH).resolve()


def _managed_hebrew_pack_root() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_HEBREW).resolve()


def _managed_kokoro_tts_pack_root() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_KOKORO_TTS).resolve()


def _managed_kyutai_tts_pack_root() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_KYUTAI_TTS).resolve()


def _legacy_kokoro_tts_runtime_root() -> Path:
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home()))).expanduser()
    return local_app_data / "EmploAI" / "tts_runtimes" / "kokoro_onnx"


def _legacy_pocket_tts_site_packages() -> Path:
    return Path(os.getenv("TEMP", str(Path.home()))).expanduser() / "emploai-pocket-tts-bench" / ".venv" / "Lib" / "site-packages"


def _allow_dev_voice_pack_sources() -> bool:
    return os.getenv(ALLOW_DEV_VOICE_PACK_SOURCES_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _managed_release_voice_mode() -> bool:
    return bool(getattr(sys, "frozen", False)) and not _allow_dev_voice_pack_sources()


def _voice_pack_label(pack_id: str) -> str:
    if pack_id == VOICE_ENGINE_HEBREW:
        return "Hebrew"
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return "Kokoro"
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return "Kyutai clone"
    return "English"


def _emit_progress(
    progress_callback: VoicePackProgressCallback | None,
    *,
    pack_id: str,
    state: str,
    phase: str,
    message: str,
    percent: float | int | None = None,
    downloaded_bytes: int | None = None,
    total_bytes: int | None = None,
) -> None:
    if progress_callback is None:
        return
    payload: dict[str, Any] = {
        "packId": pack_id,
        "state": state,
        "phase": phase,
        "message": message,
    }
    if percent is not None:
        payload["percent"] = max(0.0, min(100.0, round(float(percent), 1)))
    if downloaded_bytes is not None:
        payload["downloadedBytes"] = max(0, int(downloaded_bytes))
    if total_bytes is not None:
        payload["totalBytes"] = max(0, int(total_bytes))
    progress_callback(payload)


def _snapshot_progress_tqdm_class(
    *,
    pack_id: str,
    progress_callback: VoicePackProgressCallback | None,
) -> type | None:
    if progress_callback is None:
        return None
    try:
        from tqdm.auto import tqdm as base_tqdm
    except Exception:  # pragma: no cover
        return None

    label = _voice_pack_label(pack_id)

    class VoicePackDownloadTqdm(base_tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._last_reported_n = -1
            self._last_reported_percent = -1.0
            self._maybe_emit(force=True)

        def update(self, n=1):
            result = super().update(n)
            self._maybe_emit()
            return result

        def close(self):
            self._maybe_emit(force=True)
            return super().close()

        def _maybe_emit(self, *, force: bool = False) -> None:
            total = int(self.total) if self.total else None
            current = int(self.n)
            percent = (current * 100.0 / total) if total and total > 0 else None

            if not force:
                if total and percent is not None:
                    if (
                        current - self._last_reported_n < 4 * 1024 * 1024
                        and percent - self._last_reported_percent < 1.0
                        and current < total
                    ):
                        return
                elif current - self._last_reported_n < 4 * 1024 * 1024:
                    return

            self._last_reported_n = current
            self._last_reported_percent = percent if percent is not None else self._last_reported_percent
            _emit_progress(
                progress_callback,
                pack_id=pack_id,
                state="downloading",
                phase="download",
                message=f"Downloading {label} voice pack...",
                percent=percent,
                downloaded_bytes=current,
                total_bytes=total,
            )

    return VoicePackDownloadTqdm


def _local_model_name() -> str:
    return os.getenv(APP_STT_MODEL_ENV, DEFAULT_LOCAL_STT_MODEL).strip() or DEFAULT_LOCAL_STT_MODEL


def _local_draft_model_name() -> str:
    return os.getenv(APP_STT_DRAFT_MODEL_ENV, DEFAULT_LOCAL_DRAFT_MODEL).strip() or DEFAULT_LOCAL_DRAFT_MODEL


def _local_binary_flavor() -> str:
    return os.getenv(APP_STT_BINARY_FLAVOR_ENV, DEFAULT_BINARY_FLAVOR).strip() or DEFAULT_BINARY_FLAVOR


def _release_asset_dir_name(*, flavor: str) -> str:
    if flavor == "plain":
        return "whisper-bin-x64"
    if flavor == "blas":
        return "whisper-blas-bin-x64"
    if flavor == "cublas-11.8":
        return "whisper-cublas-11.8.0-bin-x64"
    if flavor == "cublas-12.4":
        return "whisper-cublas-12.4.0-bin-x64"
    raise RuntimeError(f"Unsupported whisper.cpp binary flavor: {flavor}")


def english_pack_repo() -> str:
    return os.getenv(APP_STT_ENGLISH_PACK_REPO_ENV, "").strip()


def _english_pack_revision() -> str:
    return os.getenv(ENGLISH_PACK_REVISION_ENV, "").strip() or DEFAULT_ENGLISH_PACK_REVISION


def _english_model_names() -> tuple[str, str]:
    return (_local_model_name(), _local_draft_model_name())


def _expected_english_pack_manifest() -> dict[str, Any]:
    return {
        "pack_id": DEFAULT_ENGLISH_PACK_ID,
        "engine": DEFAULT_ENGLISH_PACK_ENGINE,
        "repo_id": english_pack_repo(),
        "revision": _english_pack_revision(),
        "binary_flavor": _local_binary_flavor(),
        "model_name": _local_model_name(),
        "draft_model_name": _local_draft_model_name(),
        "tuning_preset": DEFAULT_ENGLISH_PACK_TUNING_PRESET,
    }


def _english_manifest_path(pack_root: Path) -> Path:
    return pack_root / VOICE_PACK_MANIFEST_FILENAME


def _read_english_pack_manifest(pack_root: Path) -> dict[str, Any] | None:
    manifest_path = _english_manifest_path(pack_root)
    if not manifest_path.exists():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _write_english_pack_manifest(pack_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = _english_manifest_path(pack_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _is_expected_english_manifest(manifest: dict[str, Any] | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    expected = _expected_english_pack_manifest()
    for key in ("pack_id", "engine", "repo_id", "revision", "binary_flavor", "model_name", "draft_model_name", "tuning_preset"):
        if str(manifest.get(key) or "").strip() != str(expected[key]).strip():
            return False
    return True


def _required_english_pack_root() -> Path:
    if _managed_release_voice_mode():
        return _managed_english_pack_root()
    configured = os.getenv(APP_STT_ENGLISH_PACK_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _managed_english_pack_root()


def _managed_english_runtime_dir() -> Path:
    return (_managed_english_pack_root() / ENGLISH_RUNTIME_DIRNAME / "Release").resolve()


def _managed_english_models_dir() -> Path:
    return (_managed_english_pack_root() / ENGLISH_MODELS_DIRNAME).resolve()


def _legacy_english_binary_dir() -> Path:
    return tools_root() / _release_asset_dir_name(flavor=_local_binary_flavor())


def _legacy_english_cli_path() -> Path:
    return _legacy_english_binary_dir() / "Release" / "whisper-cli.exe"


def _legacy_english_model_path(model_name: str) -> Path:
    return tools_root() / "whisper_cpp_models" / f"ggml-{model_name}.bin"


def _legacy_english_assets_ready() -> bool:
    cli_path = _legacy_english_cli_path()
    if not cli_path.exists():
        return False
    return all(_legacy_english_model_path(model_name).exists() for model_name in _english_model_names())


def _english_cli_candidates(pack_root: Path) -> list[Path]:
    return [
        pack_root / ENGLISH_RUNTIME_DIRNAME / "Release" / "whisper-cli.exe",
        pack_root / ENGLISH_RUNTIME_DIRNAME / "Release" / "whisper.exe",
        pack_root / ENGLISH_RUNTIME_DIRNAME / "whisper-cli.exe",
        pack_root / ENGLISH_RUNTIME_DIRNAME / "whisper.exe",
        pack_root / "Release" / "whisper-cli.exe",
        pack_root / "Release" / "whisper.exe",
        pack_root / "whisper-cli.exe",
        pack_root / "whisper.exe",
    ]


def _english_model_dir_candidates(pack_root: Path) -> list[Path]:
    return [
        pack_root / ENGLISH_MODELS_DIRNAME,
        pack_root / "models",
        pack_root,
    ]


def _english_model_path(pack_root: Path, model_name: str) -> Path:
    filename = f"ggml-{model_name}.bin"
    for candidate_dir in _english_model_dir_candidates(pack_root):
        candidate = candidate_dir / filename
        if candidate.exists():
            return candidate
    if not _managed_release_voice_mode():
        legacy_candidate = _legacy_english_model_path(model_name)
        if legacy_candidate.exists():
            return legacy_candidate
    return (_managed_english_models_dir() if pack_root.resolve() == _managed_english_pack_root() else pack_root / ENGLISH_MODELS_DIRNAME) / filename


def english_pack_model_path(model_name: str) -> Path:
    return _english_model_path(_required_english_pack_root(), model_name)


def _english_pack_cli_path(pack_root: Path) -> Path:
    for candidate in _english_cli_candidates(pack_root):
        if candidate.exists():
            return candidate
    if not _managed_release_voice_mode():
        legacy_candidate = _legacy_english_cli_path()
        if legacy_candidate.exists():
            return legacy_candidate
    if pack_root.resolve() == _managed_english_pack_root():
        return _managed_english_runtime_dir() / "whisper-cli.exe"
    return pack_root / ENGLISH_RUNTIME_DIRNAME / "Release" / "whisper-cli.exe"


def english_pack_cli_path() -> Path:
    return _english_pack_cli_path(_required_english_pack_root())


def _english_pack_ready(pack_root: Path, *, allow_legacy: bool = True) -> bool:
    cli_path = _english_pack_cli_path(pack_root) if allow_legacy else next(
        (candidate for candidate in _english_cli_candidates(pack_root) if candidate.exists()),
        pack_root / ENGLISH_RUNTIME_DIRNAME / "Release" / "whisper-cli.exe",
    )
    if not cli_path.exists():
        return False
    for model_name in _english_model_names():
        if allow_legacy:
            model_path = _english_model_path(pack_root, model_name)
        else:
            filename = f"ggml-{model_name}.bin"
            model_path = next(
                (
                    candidate_dir / filename
                    for candidate_dir in _english_model_dir_candidates(pack_root)
                    if (candidate_dir / filename).exists()
                ),
                pack_root / ENGLISH_MODELS_DIRNAME / filename,
            )
        if not model_path.exists():
            return False
    return True


def _candidate_english_source_dir() -> Path | None:
    if _managed_release_voice_mode():
        return None
    configured = os.getenv(ENGLISH_PACK_SOURCE_DIR_ENV, "").strip()
    if not configured:
        return None
    candidate = Path(configured).expanduser().resolve()
    if not candidate.exists():
        return None
    return candidate


def _find_file(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        direct = root / name
        if direct.exists():
            return direct
    lowered = {name.lower() for name in names}
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.name.lower() in lowered:
            return candidate
    return None


def _promote_english_pack_layout(target_root: Path) -> Path:
    cli_source = _find_file(target_root, ("whisper-cli.exe", "whisper.exe"))
    if cli_source is None:
        return target_root

    runtime_dir = target_root / ENGLISH_RUNTIME_DIRNAME / "Release"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    cli_target = runtime_dir / "whisper-cli.exe"
    if cli_source.resolve() != cli_target.resolve():
        shutil.copy2(cli_source, cli_target)
    for dll_path in cli_source.parent.glob("*.dll"):
        dll_target = runtime_dir / dll_path.name
        if dll_path.resolve() == dll_target.resolve():
            continue
        shutil.copy2(dll_path, dll_target)

    model_dir = target_root / ENGLISH_MODELS_DIRNAME
    model_dir.mkdir(parents=True, exist_ok=True)
    for model_name in _english_model_names():
        filename = f"ggml-{model_name}.bin"
        source_path = _find_file(target_root, (filename,))
        if source_path is None:
            continue
        target_path = model_dir / filename
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
    return target_root


def _required_hebrew_runtime_dir() -> Path:
    if _managed_release_voice_mode():
        return _managed_hebrew_runtime_dir()
    configured = os.getenv(APP_STT_HEBREW_MODEL_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (managed_voice_packs_root() / VOICE_ENGINE_HEBREW / HEBREW_RUNTIME_DIRNAME).resolve()


def _managed_hebrew_runtime_dir() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_HEBREW / HEBREW_RUNTIME_DIRNAME).resolve()


def _expected_hebrew_pack_manifest() -> dict[str, Any]:
    revision = os.getenv(HEBREW_PACK_REVISION_ENV, "").strip() or DEFAULT_HEBREW_PACK_REVISION
    return {
        "pack_id": DEFAULT_HEBREW_PACK_ID,
        "engine": DEFAULT_HEBREW_PACK_ENGINE,
        "repo_id": hebrew_pack_repo(),
        "revision": revision,
        "asset_name": DEFAULT_HEBREW_PACK_ASSET_NAME,
        "tuning_preset": DEFAULT_HEBREW_PACK_TUNING_PRESET,
    }


def _manifest_storage_dir(model_dir: Path) -> Path:
    return model_dir.parent if model_dir.name == HEBREW_RUNTIME_DIRNAME else model_dir


def _hebrew_pack_manifest_path(model_dir: Path) -> Path:
    return _manifest_storage_dir(model_dir) / VOICE_PACK_MANIFEST_FILENAME


def _read_hebrew_pack_manifest(model_dir: Path) -> dict[str, Any] | None:
    manifest_path = _hebrew_pack_manifest_path(model_dir)
    if not manifest_path.exists():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _write_hebrew_pack_manifest(model_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = _hebrew_pack_manifest_path(model_dir)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _is_expected_hebrew_manifest(manifest: dict[str, Any] | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    expected = _expected_hebrew_pack_manifest()
    return (
        str(manifest.get("pack_id") or "").strip() == expected["pack_id"]
        and str(manifest.get("engine") or "").strip().lower() == expected["engine"]
        and str(manifest.get("repo_id") or "").strip() == expected["repo_id"]
        and str(manifest.get("tuning_preset") or "").strip() == expected["tuning_preset"]
    )


def _ensure_managed_hebrew_manifest(model_dir: Path) -> dict[str, Any] | None:
    manifest = _read_hebrew_pack_manifest(model_dir)
    if manifest is not None:
        return manifest
    if os.getenv(APP_STT_HEBREW_MODEL_DIR_ENV, "").strip():
        return None
    if model_dir.resolve() != _managed_hebrew_runtime_dir():
        return None
    if not _hebrew_pack_ready(model_dir):
        return None
    return _write_hebrew_pack_manifest(
        model_dir,
        {
            **_expected_hebrew_pack_manifest(),
            "source_kind": "managed_default",
        },
    )


def _hebrew_pack_ready(model_dir: Path) -> bool:
    return all((model_dir / filename).exists() for filename in HEBREW_REQUIRED_MODEL_FILES)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _find_nested_hebrew_runtime_dir(root: Path) -> Path | None:
    if _hebrew_pack_ready(root):
        return root
    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        if _hebrew_pack_ready(candidate):
            return candidate
    return None


def _promote_hebrew_runtime_dir(target_dir: Path) -> Path:
    if _hebrew_pack_ready(target_dir):
        return target_dir
    nested = _find_nested_hebrew_runtime_dir(target_dir)
    if nested is None or nested == target_dir:
        return target_dir

    with tempfile.TemporaryDirectory(prefix="emploai-hebrew-pack-") as temp_dir:
        staging = Path(temp_dir) / "model"
        shutil.copytree(nested, staging)
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, target_dir)
    return target_dir


def _candidate_hebrew_source_dir() -> Path | None:
    if _managed_release_voice_mode():
        return None
    configured = os.getenv(HEBREW_PACK_SOURCE_DIR_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if _hebrew_pack_ready(candidate):
            return candidate
    return None


def hebrew_pack_repo() -> str:
    return os.getenv(APP_STT_HEBREW_MODEL_REPO_ENV, DEFAULT_HEBREW_MODEL_REPO).strip()


def hebrew_pack_runtime_dir() -> Path:
    return _required_hebrew_runtime_dir()


def kokoro_tts_pack_repo() -> str:
    return os.getenv(APP_TTS_KOKORO_PACK_REPO_ENV, "").strip()


def kyutai_tts_pack_repo() -> str:
    return os.getenv(APP_TTS_KYUTAI_PACK_REPO_ENV, "").strip()


def _kokoro_tts_pack_revision() -> str:
    return os.getenv(KOKORO_TTS_PACK_REVISION_ENV, "").strip() or DEFAULT_KOKORO_TTS_PACK_REVISION


def _kyutai_tts_pack_revision() -> str:
    return os.getenv(KYUTAI_TTS_PACK_REVISION_ENV, "").strip() or DEFAULT_KYUTAI_TTS_PACK_REVISION


def _required_kokoro_tts_pack_root() -> Path:
    if _managed_release_voice_mode():
        return _managed_kokoro_tts_pack_root()
    configured = os.getenv(APP_TTS_KOKORO_PACK_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _managed_kokoro_tts_pack_root()


def _required_kyutai_tts_pack_root() -> Path:
    if _managed_release_voice_mode():
        return _managed_kyutai_tts_pack_root()
    configured = os.getenv(APP_TTS_KYUTAI_PACK_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _managed_kyutai_tts_pack_root()


def kokoro_tts_pack_root() -> Path:
    return _required_kokoro_tts_pack_root()


def kyutai_tts_pack_root() -> Path:
    return _required_kyutai_tts_pack_root()


def kokoro_tts_model_path() -> Path:
    return kokoro_tts_pack_root() / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_MODEL_FILENAME


def kokoro_tts_voices_path() -> Path:
    custom = kokoro_tts_pack_root() / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_VOICES_FILENAME
    if custom.exists():
        return custom
    return kokoro_tts_pack_root() / TTS_MODELS_DIRNAME / FALLBACK_KOKORO_TTS_VOICES_FILENAME


def kokoro_tts_site_packages_path() -> Path:
    return kokoro_tts_pack_root() / TTS_SITE_PACKAGES_DIRNAME


def kyutai_tts_voice_path() -> Path:
    return kyutai_tts_pack_root() / TTS_VOICES_DIRNAME / DEFAULT_KYUTAI_TTS_VOICE_FILENAME


def kyutai_tts_site_packages_path() -> Path:
    return kyutai_tts_pack_root() / TTS_SITE_PACKAGES_DIRNAME


def _tts_manifest_path(pack_root: Path) -> Path:
    return pack_root / VOICE_PACK_MANIFEST_FILENAME


def _read_tts_pack_manifest(pack_root: Path) -> dict[str, Any] | None:
    manifest_path = _tts_manifest_path(pack_root)
    if not manifest_path.exists():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _write_tts_pack_manifest(pack_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = _tts_manifest_path(pack_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _expected_kokoro_tts_pack_manifest() -> dict[str, Any]:
    return {
        "pack_id": DEFAULT_KOKORO_TTS_PACK_ID,
        "engine": DEFAULT_KOKORO_TTS_PACK_ENGINE,
        "repo_id": kokoro_tts_pack_repo(),
        "revision": _kokoro_tts_pack_revision(),
        "model_filename": DEFAULT_KOKORO_TTS_MODEL_FILENAME,
        "voices_filename": DEFAULT_KOKORO_TTS_VOICES_FILENAME,
        "default_voice": DEFAULT_KOKORO_TTS_VOICE,
    }


def _expected_kyutai_tts_pack_manifest() -> dict[str, Any]:
    return {
        "pack_id": DEFAULT_KYUTAI_TTS_PACK_ID,
        "engine": DEFAULT_KYUTAI_TTS_PACK_ENGINE,
        "repo_id": kyutai_tts_pack_repo(),
        "revision": _kyutai_tts_pack_revision(),
        "voice_filename": DEFAULT_KYUTAI_TTS_VOICE_FILENAME,
        "language": DEFAULT_KYUTAI_TTS_LANGUAGE,
    }


def _is_expected_tts_manifest(manifest: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    if not isinstance(manifest, dict):
        return False
    for key in ("pack_id", "engine", "repo_id", "revision"):
        if str(manifest.get(key) or "").strip() != str(expected[key]).strip():
            return False
    return True


def _kokoro_tts_pack_ready(pack_root: Path) -> bool:
    voices_ready = (
        (pack_root / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_VOICES_FILENAME).exists()
        or (pack_root / TTS_MODELS_DIRNAME / FALLBACK_KOKORO_TTS_VOICES_FILENAME).exists()
    )
    return (
        (pack_root / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_MODEL_FILENAME).exists()
        and voices_ready
        and (pack_root / TTS_SITE_PACKAGES_DIRNAME / "kokoro_onnx").exists()
    )


def _kyutai_tts_pack_ready(pack_root: Path) -> bool:
    return (
        (pack_root / TTS_VOICES_DIRNAME / DEFAULT_KYUTAI_TTS_VOICE_FILENAME).exists()
        and (pack_root / TTS_SITE_PACKAGES_DIRNAME / "pocket_tts").exists()
    )


def _candidate_kokoro_tts_source_dir() -> Path | None:
    if _managed_release_voice_mode():
        return None
    configured = os.getenv(KOKORO_TTS_PACK_SOURCE_DIR_ENV, "").strip()
    candidates = [Path(configured).expanduser().resolve()] if configured else []
    candidates.append(_legacy_kokoro_tts_runtime_root().resolve())
    for candidate in candidates:
        if candidate.exists() and _kokoro_tts_pack_ready(candidate):
            return candidate
    return None


def _candidate_kyutai_tts_source_dir() -> Path | None:
    if _managed_release_voice_mode():
        return None
    configured = os.getenv(KYUTAI_TTS_PACK_SOURCE_DIR_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if _kyutai_tts_pack_ready(candidate):
            return candidate
    return None


def _find_nested_kokoro_tts_pack_root(root: Path) -> Path | None:
    if _kokoro_tts_pack_ready(root):
        return root
    for candidate in root.rglob("*"):
        if candidate.is_dir() and _kokoro_tts_pack_ready(candidate):
            return candidate
    return None


def _find_nested_kyutai_tts_pack_root(root: Path) -> Path | None:
    if _kyutai_tts_pack_ready(root):
        return root
    for candidate in root.rglob("*"):
        if candidate.is_dir() and _kyutai_tts_pack_ready(candidate):
            return candidate
    return None


def _tts_pack_status(
    *,
    pack_id: str,
    pack_root: Path,
    managed_root: Path,
    ready_fn: Callable[[Path], bool],
    expected_manifest_fn: Callable[[], dict[str, Any]],
    repo_fn: Callable[[], str],
    archive_env: str,
    source_env: str,
    configured_dir_env: str,
    primary_path: Path,
) -> dict[str, Any]:
    installed = ready_fn(pack_root)
    managed = installed and pack_root.resolve() == managed_root.resolve()
    manifest = _read_tts_pack_manifest(pack_root) if installed else None
    if manifest is None and installed and managed:
        manifest = _write_tts_pack_manifest(
            pack_root,
            {
                **expected_manifest_fn(),
                "source_kind": "managed_default",
            },
        )
    expected = expected_manifest_fn()
    manifest_verified = installed and _is_expected_tts_manifest(manifest, expected)
    source = (
        str(manifest.get("pack_id") or "").strip()
        if isinstance(manifest, dict) and str(manifest.get("pack_id") or "").strip()
        else "managed"
        if managed
        else "local_override"
        if installed
        else "missing"
    )

    issues: list[str] = []
    if not installed:
        configured_dir = "" if _managed_release_voice_mode() else os.getenv(configured_dir_env, "").strip()
        if configured_dir:
            issues.append(f"Configured {_voice_pack_label(pack_id)} voice pack path is missing required files: {pack_root}")
        elif os.getenv(archive_env, "").strip():
            issues.append(f"{_voice_pack_label(pack_id)} voice pack is not installed yet. Expected files under {pack_root}")
        elif repo_fn():
            issues.append(f"{_voice_pack_label(pack_id)} voice pack is not installed yet. Expected files under {pack_root}")
        elif os.getenv(source_env, "").strip():
            issues.append(f"Configured {_voice_pack_label(pack_id)} local source is missing required files.")
        else:
            issues.append(
                f"{_voice_pack_label(pack_id)} voice pack is not installed and no public source is configured. "
                f"Set a Hugging Face repo or {source_env} to a runtime-ready folder."
            )
    elif not manifest_verified:
        issues.append(f"The installed {_voice_pack_label(pack_id)} voice pack is not the pinned desktop pack. Reinstall it from setup.")

    return {
        "id": pack_id,
        "installed": installed,
        "available": installed and manifest_verified,
        "managed": managed,
        "removable": managed,
        "source": source,
        "issues": issues,
        "model_dir": str(pack_root),
        "path": str(primary_path),
        "repo_id": repo_fn() or None,
        "manifest": manifest,
        "manifest_verified": manifest_verified,
        "expected_manifest": expected,
    }


def get_kokoro_tts_pack_status() -> dict[str, Any]:
    pack_root = kokoro_tts_pack_root()
    return _tts_pack_status(
        pack_id=VOICE_ENGINE_KOKORO_TTS,
        pack_root=pack_root,
        managed_root=_managed_kokoro_tts_pack_root(),
        ready_fn=_kokoro_tts_pack_ready,
        expected_manifest_fn=_expected_kokoro_tts_pack_manifest,
        repo_fn=kokoro_tts_pack_repo,
        archive_env=KOKORO_TTS_PACK_ARCHIVE_URL_ENV,
        source_env=KOKORO_TTS_PACK_SOURCE_DIR_ENV,
        configured_dir_env=APP_TTS_KOKORO_PACK_DIR_ENV,
        primary_path=kokoro_tts_voices_path(),
    )


def get_kyutai_tts_pack_status() -> dict[str, Any]:
    pack_root = kyutai_tts_pack_root()
    return _tts_pack_status(
        pack_id=VOICE_ENGINE_KYUTAI_TTS,
        pack_root=pack_root,
        managed_root=_managed_kyutai_tts_pack_root(),
        ready_fn=_kyutai_tts_pack_ready,
        expected_manifest_fn=_expected_kyutai_tts_pack_manifest,
        repo_fn=kyutai_tts_pack_repo,
        archive_env=KYUTAI_TTS_PACK_ARCHIVE_URL_ENV,
        source_env=KYUTAI_TTS_PACK_SOURCE_DIR_ENV,
        configured_dir_env=APP_TTS_KYUTAI_PACK_DIR_ENV,
        primary_path=kyutai_tts_voice_path(),
    )


def get_english_pack_status() -> dict[str, Any]:
    pack_root = _required_english_pack_root()
    managed_root = _managed_english_pack_root()
    resolved_cli = _english_pack_cli_path(pack_root)
    legacy_allowed = not _managed_release_voice_mode()
    legacy_cli = _legacy_english_cli_path()
    managed_ready = _english_pack_ready(pack_root, allow_legacy=False)
    legacy_ready = legacy_allowed and _legacy_english_assets_ready() and not managed_ready and legacy_cli.exists() and resolved_cli.resolve() == legacy_cli.resolve()
    installed = managed_ready or legacy_ready
    managed = managed_ready and pack_root.resolve() == managed_root.resolve()
    manifest = _read_english_pack_manifest(pack_root) if installed else None
    if manifest is None and installed and pack_root.resolve() == managed_root:
        manifest = _write_english_pack_manifest(
            pack_root,
            {
                **_expected_english_pack_manifest(),
                "source_kind": "managed_default",
            },
        )
    manifest_verified = installed and _is_expected_english_manifest(manifest)
    source = (
        str(manifest.get("pack_id") or "").strip()
        if isinstance(manifest, dict) and str(manifest.get("pack_id") or "").strip()
        else "managed" if managed else "legacy_local_assets" if legacy_ready else "local_override" if installed else "missing"
    )

    issues: list[str] = []
    if os.name != "nt":
        issues.append("The English voice pack currently expects Windows whisper.cpp binaries.")
    if not installed:
        configured_dir = "" if _managed_release_voice_mode() else os.getenv(APP_STT_ENGLISH_PACK_DIR_ENV, "").strip()
        archive_url = os.getenv(ENGLISH_PACK_ARCHIVE_URL_ENV, "").strip()
        repo_id = english_pack_repo()
        if configured_dir:
            issues.append(f"Configured English voice pack path is missing required files: {pack_root}")
        elif archive_url:
            issues.append(f"English voice pack is not installed yet. Expected files under {pack_root}")
        elif repo_id:
            issues.append(f"English voice pack is not installed yet. Expected files under {pack_root}")
        elif _candidate_english_source_dir() is not None:
            issues.append(f"English voice pack is available locally but not installed into {managed_root}")
        else:
            issues.append(
                "English voice pack is not installed and no public source is configured. "
                f"Set {APP_STT_ENGLISH_PACK_REPO_ENV} to a public model repo, "
                f"{ENGLISH_PACK_ARCHIVE_URL_ENV} to a downloadable zip, or "
                f"{ENGLISH_PACK_SOURCE_DIR_ENV} to a local runtime-ready folder."
            )
    elif not manifest_verified and not legacy_ready:
        issues.append(
            "The installed English voice pack is not the pinned desktop pack. Reinstall it from setup to restore the verified path."
        )

    cli_path = resolved_cli
    model_paths = [str(_english_model_path(pack_root, model_name)) for model_name in _english_model_names()]
    model_dir = (
        _legacy_english_model_path(_local_model_name()).parent
        if legacy_ready
        else (pack_root / ENGLISH_MODELS_DIRNAME)
    )

    return {
        "id": VOICE_ENGINE_ENGLISH,
        "installed": installed,
        "available": installed and (manifest_verified or legacy_ready),
        "managed": managed,
        "removable": managed or legacy_ready,
        "source": source,
        "issues": issues,
        "binary_path": str(cli_path) if installed else None,
        "model_paths": model_paths if installed else [],
        "model_dir": str(model_dir.resolve()) if installed else str((pack_root / ENGLISH_MODELS_DIRNAME)),
        "repo_id": english_pack_repo() or None,
        "manifest": manifest,
        "manifest_verified": manifest_verified,
        "expected_manifest": _expected_english_pack_manifest(),
    }


def get_hebrew_pack_status() -> dict[str, Any]:
    model_dir = hebrew_pack_runtime_dir()
    managed_dir = _managed_hebrew_runtime_dir()
    installed = _hebrew_pack_ready(model_dir)
    managed = installed and model_dir == managed_dir
    manifest = _ensure_managed_hebrew_manifest(model_dir) if installed else None
    if manifest is None and installed:
        manifest = _read_hebrew_pack_manifest(model_dir)
    manifest_verified = installed and _is_expected_hebrew_manifest(manifest)
    source = (
        str(manifest.get("pack_id") or "").strip()
        if isinstance(manifest, dict) and str(manifest.get("pack_id") or "").strip()
        else "managed" if managed else "local_override" if installed else "missing"
    )

    issues: list[str] = []
    if not installed:
        configured_dir = "" if _managed_release_voice_mode() else os.getenv(APP_STT_HEBREW_MODEL_DIR_ENV, "").strip()
        if configured_dir:
            issues.append(f"Configured Hebrew voice pack path is missing required files: {model_dir}")
        elif os.getenv(HEBREW_PACK_ARCHIVE_URL_ENV, "").strip():
            issues.append(f"Hebrew voice pack is not installed yet. Expected files under {model_dir}")
        elif hebrew_pack_repo():
            issues.append(f"Hebrew voice pack is not installed yet. Expected files under {model_dir}")
        elif _candidate_hebrew_source_dir() is not None:
            issues.append(f"Hebrew voice pack is available locally but not installed into {managed_dir}")
        else:
            issues.append(
                "Hebrew voice pack is not installed and no public source is configured. "
                f"Set {APP_STT_HEBREW_MODEL_REPO_ENV} to a public model repo or "
                f"{HEBREW_PACK_ARCHIVE_URL_ENV} to a downloadable zip."
            )
    elif not manifest_verified:
        issues.append(
            "The installed Hebrew voice pack is not the pinned pass-3 desktop pack. Reinstall it from setup to restore the verified pass-3 path."
        )

    return {
        "id": VOICE_ENGINE_HEBREW,
        "installed": installed,
        "available": installed and manifest_verified,
        "managed": managed,
        "removable": managed,
        "source": source,
        "issues": issues,
        "model_dir": str(model_dir),
        "repo_id": hebrew_pack_repo() or None,
        "manifest": manifest,
        "manifest_verified": manifest_verified,
        "expected_manifest": _expected_hebrew_pack_manifest(),
    }


def get_voice_pack_status(pack_id: str) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return get_english_pack_status()
    if pack_id == VOICE_ENGINE_HEBREW:
        return get_hebrew_pack_status()
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return get_kokoro_tts_pack_status()
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return get_kyutai_tts_pack_status()
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def install_english_voice_pack(
    *,
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    target_root = _managed_english_pack_root()
    if _english_pack_ready(target_root, allow_legacy=False) and not force:
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_ENGLISH,
            state="ready",
            phase="complete",
            message="English voice pack is already installed.",
            percent=100,
        )
        return get_english_pack_status()

    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_ENGLISH,
        state="starting",
        phase="prepare",
        message="Preparing English voice pack install...",
        percent=0,
    )

    source_dir = _candidate_english_source_dir()
    archive_url = os.getenv(ENGLISH_PACK_ARCHIVE_URL_ENV, "").strip()
    repo_id = english_pack_repo()
    revision = _english_pack_revision() or None

    if source_dir is not None:
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_ENGLISH,
            state="downloading",
            phase="copy",
            message="Copying English voice pack from local source...",
        )
        _copy_tree(source_dir, target_root)
        manifest = {
            **_expected_english_pack_manifest(),
            "source_kind": "local_source_dir",
            "source_dir": str(source_dir),
        }
    elif not _managed_release_voice_mode() and _legacy_english_assets_ready():
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_ENGLISH,
            state="downloading",
            phase="copy",
            message="Copying English voice pack from local runtime assets...",
        )
        runtime_release_dir = target_root / ENGLISH_RUNTIME_DIRNAME / "Release"
        models_dir = target_root / ENGLISH_MODELS_DIRNAME
        runtime_release_dir.mkdir(parents=True, exist_ok=True)
        models_dir.mkdir(parents=True, exist_ok=True)
        for source_path in _legacy_english_cli_path().parent.iterdir():
            if source_path.is_file():
                shutil.copy2(source_path, runtime_release_dir / source_path.name)
        for model_name in _english_model_names():
            source_model = _legacy_english_model_path(model_name)
            shutil.copy2(source_model, models_dir / source_model.name)
        manifest = {
            **_expected_english_pack_manifest(),
            "source_kind": "legacy_local_assets",
            "source_root": str(tools_root()),
        }
    elif archive_url:
        _download_pack_archive(
            archive_url=archive_url,
            target_dir=target_root,
            nested_dir_resolver=lambda root: _promote_english_pack_layout(root),
            missing_files_message="Downloaded English voice pack archive did not contain the required runtime files",
            pack_id=VOICE_ENGINE_ENGLISH,
            progress_callback=progress_callback,
        )
        manifest = {
            **_expected_english_pack_manifest(),
            "source_kind": "archive_url",
            "archive_url": archive_url,
        }
    elif repo_id:
        if snapshot_download is None:
            raise RuntimeError("The `huggingface_hub` package is required to download the English voice pack.")
        if target_root.exists():
            shutil.rmtree(target_root)
        target_root.parent.mkdir(parents=True, exist_ok=True)
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_ENGLISH,
            state="downloading",
            phase="download",
            message="Downloading English voice pack from Hugging Face...",
            percent=0,
        )
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_root),
            revision=revision,
            local_dir_use_symlinks=False,
            tqdm_class=_snapshot_progress_tqdm_class(
                pack_id=VOICE_ENGINE_ENGLISH,
                progress_callback=progress_callback,
            ),
        )
        manifest = {
            **_expected_english_pack_manifest(),
            "source_kind": "huggingface_repo",
            "repo_id": repo_id,
            "revision": revision or DEFAULT_ENGLISH_PACK_REVISION,
        }
    else:
        raise RuntimeError(
            "No English voice pack source is configured. "
            f"Set {APP_STT_ENGLISH_PACK_REPO_ENV} to a public repo, "
            f"{ENGLISH_PACK_ARCHIVE_URL_ENV} to a downloadable zip, or "
            f"{ENGLISH_PACK_SOURCE_DIR_ENV} to a local runtime-ready folder."
        )

    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_ENGLISH,
        state="verifying",
        phase="verify",
        message="Verifying English voice pack files...",
        percent=92,
    )
    _promote_english_pack_layout(target_root)
    if not _english_pack_ready(target_root, allow_legacy=False):
        raise RuntimeError(f"English voice pack installation completed, but required files are still missing in {target_root}")
    _write_english_pack_manifest(target_root, manifest)
    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_ENGLISH,
        state="ready",
        phase="complete",
        message="English voice pack installed.",
        percent=100,
    )
    return get_english_pack_status()


def _download_pack_archive(
    *,
    archive_url: str,
    target_dir: Path,
    nested_dir_resolver,
    missing_files_message: str,
    pack_id: str,
    progress_callback: VoicePackProgressCallback | None = None,
) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="emploai-pack-download-") as temp_dir:
        archive_path = Path(temp_dir) / "voice-pack.zip"
        label = _voice_pack_label(pack_id)
        with urllib.request.urlopen(archive_url) as response, archive_path.open("wb") as handle:
            total_header = response.headers.get("Content-Length")
            total_bytes = int(total_header) if total_header and total_header.isdigit() else None
            downloaded_bytes = 0
            _emit_progress(
                progress_callback,
                pack_id=pack_id,
                state="downloading",
                phase="download",
                message=f"Downloading {label} voice pack...",
                percent=0 if total_bytes else None,
                downloaded_bytes=0,
                total_bytes=total_bytes,
            )
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded_bytes += len(chunk)
                percent = (downloaded_bytes * 100.0 / total_bytes) if total_bytes else None
                _emit_progress(
                    progress_callback,
                    pack_id=pack_id,
                    state="downloading",
                    phase="download",
                    message=f"Downloading {label} voice pack...",
                    percent=percent,
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes,
                )
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_root)
        nested_dir = nested_dir_resolver(extract_root)
        if nested_dir is None:
            raise RuntimeError(f"{missing_files_message}: {archive_url}")
        _copy_tree(nested_dir, target_dir)


def _download_hebrew_pack_archive(
    archive_url: str,
    target_dir: Path,
    *,
    progress_callback: VoicePackProgressCallback | None = None,
) -> None:
    _download_pack_archive(
        archive_url=archive_url,
        target_dir=target_dir,
        nested_dir_resolver=_find_nested_hebrew_runtime_dir,
        missing_files_message="Downloaded Hebrew voice pack archive did not contain the required runtime files",
        pack_id=VOICE_ENGINE_HEBREW,
        progress_callback=progress_callback,
    )


def install_hebrew_voice_pack(
    *,
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    target_dir = _managed_hebrew_runtime_dir()
    if _hebrew_pack_ready(target_dir) and not force:
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_HEBREW,
            state="ready",
            phase="complete",
            message="Hebrew voice pack is already installed.",
            percent=100,
        )
        return get_hebrew_pack_status()

    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_HEBREW,
        state="starting",
        phase="prepare",
        message="Preparing Hebrew voice pack install...",
        percent=0,
    )

    source_dir = _candidate_hebrew_source_dir()
    archive_url = os.getenv(HEBREW_PACK_ARCHIVE_URL_ENV, "").strip()
    repo_id = hebrew_pack_repo()
    revision = os.getenv(HEBREW_PACK_REVISION_ENV, "").strip() or None

    if source_dir is not None:
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_HEBREW,
            state="downloading",
            phase="copy",
            message="Copying Hebrew voice pack from local source...",
        )
        _copy_tree(source_dir, target_dir)
        manifest = {
            **_expected_hebrew_pack_manifest(),
            "source_kind": "local_source_dir",
            "source_dir": str(source_dir),
        }
    elif archive_url:
        _download_hebrew_pack_archive(
            archive_url,
            target_dir,
            progress_callback=progress_callback,
        )
        manifest = {
            **_expected_hebrew_pack_manifest(),
            "source_kind": "archive_url",
            "archive_url": archive_url,
        }
    elif repo_id:
        if snapshot_download is None:
            raise RuntimeError("The `huggingface_hub` package is required to download the Hebrew voice pack.")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        _emit_progress(
            progress_callback,
            pack_id=VOICE_ENGINE_HEBREW,
            state="downloading",
            phase="download",
            message="Downloading Hebrew voice pack from Hugging Face...",
            percent=0,
        )
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            revision=revision,
            local_dir_use_symlinks=False,
            tqdm_class=_snapshot_progress_tqdm_class(
                pack_id=VOICE_ENGINE_HEBREW,
                progress_callback=progress_callback,
            ),
        )
        manifest = {
            **_expected_hebrew_pack_manifest(),
            "source_kind": "huggingface_repo",
            "repo_id": repo_id,
            "revision": revision or DEFAULT_HEBREW_PACK_REVISION,
        }
    else:
        raise RuntimeError(
            "No Hebrew voice pack source is configured. "
            f"Set {APP_STT_HEBREW_MODEL_REPO_ENV} to a public repo, "
            f"{HEBREW_PACK_ARCHIVE_URL_ENV} to a downloadable zip, or "
            f"{HEBREW_PACK_SOURCE_DIR_ENV} to a local runtime-ready folder."
        )

    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_HEBREW,
        state="verifying",
        phase="verify",
        message="Verifying Hebrew voice pack files...",
        percent=92,
    )
    _promote_hebrew_runtime_dir(target_dir)
    if not _hebrew_pack_ready(target_dir):
        raise RuntimeError(f"Hebrew voice pack installation completed, but required files are still missing in {target_dir}")
    _write_hebrew_pack_manifest(target_dir, manifest)
    _emit_progress(
        progress_callback,
        pack_id=VOICE_ENGINE_HEBREW,
        state="ready",
        phase="complete",
        message="Hebrew voice pack installed.",
        percent=100,
    )
    return get_hebrew_pack_status()


def _install_tts_voice_pack(
    *,
    pack_id: str,
    target_root: Path,
    ready_fn: Callable[[Path], bool],
    nested_dir_resolver: Callable[[Path], Path | None],
    candidate_source_dir: Callable[[], Path | None],
    archive_env: str,
    repo_fn: Callable[[], str],
    revision_fn: Callable[[], str],
    expected_manifest_fn: Callable[[], dict[str, Any]],
    status_fn: Callable[[], dict[str, Any]],
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    label = _voice_pack_label(pack_id)
    if ready_fn(target_root) and not force:
        _emit_progress(
            progress_callback,
            pack_id=pack_id,
            state="ready",
            phase="complete",
            message=f"{label} voice pack is already installed.",
            percent=100,
        )
        return status_fn()

    _emit_progress(
        progress_callback,
        pack_id=pack_id,
        state="starting",
        phase="prepare",
        message=f"Preparing {label} voice pack install...",
        percent=0,
    )

    source_dir = candidate_source_dir()
    archive_url = os.getenv(archive_env, "").strip()
    repo_id = repo_fn()
    revision = revision_fn() or None

    if source_dir is not None:
        _emit_progress(
            progress_callback,
            pack_id=pack_id,
            state="downloading",
            phase="copy",
            message=f"Copying {label} voice pack from local source...",
        )
        _copy_tree(source_dir, target_root)
        manifest = {
            **expected_manifest_fn(),
            "source_kind": "local_source_dir",
            "source_dir": str(source_dir),
        }
    elif archive_url:
        _download_pack_archive(
            archive_url=archive_url,
            target_dir=target_root,
            nested_dir_resolver=nested_dir_resolver,
            missing_files_message=f"Downloaded {label} voice pack archive did not contain the required runtime files",
            pack_id=pack_id,
            progress_callback=progress_callback,
        )
        manifest = {
            **expected_manifest_fn(),
            "source_kind": "archive_url",
            "archive_url": archive_url,
        }
    elif repo_id:
        if snapshot_download is None:
            raise RuntimeError(f"The `huggingface_hub` package is required to download the {label} voice pack.")
        if target_root.exists():
            shutil.rmtree(target_root)
        target_root.parent.mkdir(parents=True, exist_ok=True)
        _emit_progress(
            progress_callback,
            pack_id=pack_id,
            state="downloading",
            phase="download",
            message=f"Downloading {label} voice pack from Hugging Face...",
            percent=0,
        )
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_root),
            revision=revision,
            local_dir_use_symlinks=False,
            tqdm_class=_snapshot_progress_tqdm_class(
                pack_id=pack_id,
                progress_callback=progress_callback,
            ),
        )
        manifest = {
            **expected_manifest_fn(),
            "source_kind": "huggingface_repo",
            "repo_id": repo_id,
            "revision": revision or "main",
        }
    else:
        raise RuntimeError(
            f"No {label} voice pack source is configured. "
            "Set a Hugging Face repo, archive URL, or local runtime-ready source folder."
        )

    _emit_progress(
        progress_callback,
        pack_id=pack_id,
        state="verifying",
        phase="verify",
        message=f"Verifying {label} voice pack files...",
        percent=92,
    )
    if not ready_fn(target_root):
        raise RuntimeError(f"{label} voice pack installation completed, but required files are still missing in {target_root}")
    _write_tts_pack_manifest(target_root, manifest)
    _emit_progress(
        progress_callback,
        pack_id=pack_id,
        state="ready",
        phase="complete",
        message=f"{label} voice pack installed.",
        percent=100,
    )
    return status_fn()


def install_kokoro_tts_voice_pack(
    *,
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    return _install_tts_voice_pack(
        pack_id=VOICE_ENGINE_KOKORO_TTS,
        target_root=_managed_kokoro_tts_pack_root(),
        ready_fn=_kokoro_tts_pack_ready,
        nested_dir_resolver=_find_nested_kokoro_tts_pack_root,
        candidate_source_dir=_candidate_kokoro_tts_source_dir,
        archive_env=KOKORO_TTS_PACK_ARCHIVE_URL_ENV,
        repo_fn=kokoro_tts_pack_repo,
        revision_fn=_kokoro_tts_pack_revision,
        expected_manifest_fn=_expected_kokoro_tts_pack_manifest,
        status_fn=get_kokoro_tts_pack_status,
        force=force,
        progress_callback=progress_callback,
    )


def install_kyutai_tts_voice_pack(
    *,
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    return _install_tts_voice_pack(
        pack_id=VOICE_ENGINE_KYUTAI_TTS,
        target_root=_managed_kyutai_tts_pack_root(),
        ready_fn=_kyutai_tts_pack_ready,
        nested_dir_resolver=_find_nested_kyutai_tts_pack_root,
        candidate_source_dir=_candidate_kyutai_tts_source_dir,
        archive_env=KYUTAI_TTS_PACK_ARCHIVE_URL_ENV,
        repo_fn=kyutai_tts_pack_repo,
        revision_fn=_kyutai_tts_pack_revision,
        expected_manifest_fn=_expected_kyutai_tts_pack_manifest,
        status_fn=get_kyutai_tts_pack_status,
        force=force,
        progress_callback=progress_callback,
    )


def install_voice_pack(
    pack_id: str,
    *,
    force: bool = False,
    progress_callback: VoicePackProgressCallback | None = None,
) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return install_english_voice_pack(force=force, progress_callback=progress_callback)
    if pack_id == VOICE_ENGINE_HEBREW:
        return install_hebrew_voice_pack(force=force, progress_callback=progress_callback)
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return install_kokoro_tts_voice_pack(force=force, progress_callback=progress_callback)
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return install_kyutai_tts_voice_pack(force=force, progress_callback=progress_callback)
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def remove_english_voice_pack() -> dict[str, Any]:
    try:
        shutil.rmtree(_managed_english_pack_root(), ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.rmtree(_legacy_english_binary_dir(), ignore_errors=True)
    except Exception:
        pass
    for model_name in _english_model_names():
        try:
            _legacy_english_model_path(model_name).unlink(missing_ok=True)
        except Exception:
            pass
    return get_english_pack_status()


def remove_hebrew_voice_pack() -> dict[str, Any]:
    managed_dir = _managed_hebrew_runtime_dir().parent
    try:
        shutil.rmtree(managed_dir, ignore_errors=True)
    except Exception:
        pass
    return get_hebrew_pack_status()


def remove_kokoro_tts_voice_pack() -> dict[str, Any]:
    try:
        shutil.rmtree(_managed_kokoro_tts_pack_root(), ignore_errors=True)
    except Exception:
        pass
    return get_kokoro_tts_pack_status()


def remove_kyutai_tts_voice_pack() -> dict[str, Any]:
    try:
        shutil.rmtree(_managed_kyutai_tts_pack_root(), ignore_errors=True)
    except Exception:
        pass
    return get_kyutai_tts_pack_status()


def remove_voice_pack(pack_id: str) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return remove_english_voice_pack()
    if pack_id == VOICE_ENGINE_HEBREW:
        return remove_hebrew_voice_pack()
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return remove_kokoro_tts_voice_pack()
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return remove_kyutai_tts_voice_pack()
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def requested_voice_pack_ids(config_path: Path | None = None) -> list[str]:
    config = get_live_config(config_path or (runtime_root() / "config.json"))
    requested: list[str] = []
    if bool(config.get("voice.packs.english_local.requested", False)):
        requested.append(VOICE_ENGINE_ENGLISH)
    if bool(config.get("voice.packs.hebrew_local.requested", False)):
        requested.append(VOICE_ENGINE_HEBREW)
    if bool(config.get("voice.tts_packs.kokoro_tts.requested", False)):
        requested.append(VOICE_ENGINE_KOKORO_TTS)
    if bool(config.get("voice.tts_packs.kyutai_clone_tts.requested", False)):
        requested.append(VOICE_ENGINE_KYUTAI_TTS)
    return requested


def ensure_requested_voice_packs(*, config_path: Path | None = None, force: bool = False) -> dict[str, Any]:
    installed: list[str] = []
    errors: dict[str, str] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for pack_id in requested_voice_pack_ids(config_path=config_path):
        status = get_voice_pack_status(pack_id)
        if status.get("installed") and not force:
            statuses[pack_id] = status
            continue
        try:
            statuses[pack_id] = install_voice_pack(pack_id, force=force)
            installed.append(pack_id)
        except Exception as exc:
            errors[pack_id] = str(exc)
            statuses[pack_id] = get_voice_pack_status(pack_id)

    return {
        "ok": not errors,
        "installed": installed,
        "errors": errors,
        "statuses": statuses,
    }
