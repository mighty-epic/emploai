from __future__ import annotations

import asyncio
import base64
import io
import importlib.util
import json
import os
import re
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional, Set

from app_backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_LANGUAGE,
    WhisperFixture,
    output_root,
    recommended_thread_count,
    runtime_root,
    run_whisper_cli_once,
    transcript_confidence_from_output_json,
    write_pcm16_mono_wav,
)
from app_backend.voice_pack_manager import (
    DEFAULT_KOKORO_TTS_VOICE as DEFAULT_PACK_KOKORO_TTS_VOICE,
    VOICE_ENGINE_ENGLISH,
    VOICE_ENGINE_HEBREW,
    english_pack_cli_path,
    english_pack_model_path,
    get_kokoro_tts_pack_status,
    get_kyutai_tts_pack_status,
    get_english_pack_status,
    get_hebrew_pack_status,
    hebrew_pack_runtime_dir,
    install_voice_pack,
    kokoro_tts_model_path as managed_kokoro_tts_model_path,
    kokoro_tts_pack_root as managed_kokoro_tts_pack_root,
    kokoro_tts_site_packages_path as managed_kokoro_tts_site_packages_path,
    kokoro_tts_voices_path as managed_kokoro_tts_voices_path,
    kyutai_tts_site_packages_path as managed_kyutai_tts_site_packages_path,
    kyutai_tts_voice_path as managed_kyutai_tts_voice_path,
)
from shared.live_config import get_live_config
from shared.provider_errors import normalize_provider_error
from shared.runtime_paths import runtime_home
from shared.security_policy import redact_text

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    dotenv_values = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

APP_STT_BACKEND_ENV = "EMPLO_APP_STT_BACKEND"
APP_STT_MODEL_ENV = "EMPLO_APP_STT_MODEL"
APP_STT_DRAFT_MODEL_ENV = "EMPLO_APP_STT_DRAFT_MODEL"
APP_STT_LANGUAGE_ENV = "EMPLO_APP_STT_LANGUAGE"
APP_STT_PROMPT_ENV = "EMPLO_APP_STT_PROMPT"
APP_STT_REALTIME_MODEL_ENV = "EMPLO_APP_STT_REALTIME_MODEL"
APP_STT_REALTIME_TRANSCRIPTION_MODEL_ENV = "EMPLO_APP_STT_REALTIME_TRANSCRIPTION_MODEL"
APP_STT_REALTIME_URL_ENV = "EMPLO_APP_STT_REALTIME_URL"
APP_STT_REALTIME_TIMEOUT_SECONDS_ENV = "EMPLO_APP_STT_REALTIME_TIMEOUT_SECONDS"
APP_STT_REALTIME_APPEND_TIMEOUT_SECONDS_ENV = "EMPLO_APP_STT_REALTIME_APPEND_TIMEOUT_SECONDS"
APP_STT_REALTIME_NOISE_REDUCTION_ENV = "EMPLO_APP_STT_REALTIME_NOISE_REDUCTION"
APP_STT_BINARY_FLAVOR_ENV = "EMPLO_APP_STT_BINARY_FLAVOR"
APP_STT_CONTEXT_CHARS_ENV = "EMPLO_APP_STT_CONTEXT_CHARS"
APP_STT_DRAFT_INTERVAL_MS_ENV = "EMPLO_APP_STT_DRAFT_INTERVAL_MS"
APP_STT_DRAFT_MIN_MS_ENV = "EMPLO_APP_STT_DRAFT_MIN_MS"
APP_STT_DRAFT_CONFIDENCE_ENV = "EMPLO_APP_STT_DRAFT_CONFIDENCE"
APP_STT_DRAFT_MIN_CHARS_ENV = "EMPLO_APP_STT_DRAFT_MIN_CHARS"
APP_STT_KNOWN_TERMS_ENV = "EMPLO_APP_STT_KNOWN_TERMS"
APP_JARVIS_FAST_FINAL_ENV = "EMPLO_APP_JARVIS_FAST_FINAL"
APP_JARVIS_PENDING_WAIT_MS_ENV = "EMPLO_APP_JARVIS_PENDING_WAIT_MS"
APP_STT_HEBREW_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_MODEL_REPO"
APP_STT_HEBREW_DRAFT_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_DRAFT_MODEL_REPO"
APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
APP_STT_HEBREW_LANGUAGE_ENV = "EMPLO_APP_STT_HEBREW_LANGUAGE"
APP_STT_HEBREW_CPU_THREADS_ENV = "EMPLO_APP_STT_HEBREW_CPU_THREADS"
APP_TTS_ENABLED_ENV = "EMPLO_APP_TTS_ENABLED"
APP_TTS_BACKEND_ENV = "EMPLO_APP_TTS_BACKEND"
APP_TTS_MODEL_ENV = "EMPLO_APP_TTS_MODEL"
APP_TTS_VOICE_ENV = "EMPLO_APP_TTS_VOICE"
APP_TTS_FORMAT_ENV = "EMPLO_APP_TTS_FORMAT"
APP_TTS_SPEED_ENV = "EMPLO_APP_TTS_SPEED"
APP_TTS_INSTRUCTIONS_ENV = "EMPLO_APP_TTS_INSTRUCTIONS"
APP_POCKET_TTS_LANGUAGE_ENV = "EMPLO_APP_POCKET_TTS_LANGUAGE"
APP_POCKET_TTS_VOICE_ENV = "EMPLO_APP_POCKET_TTS_VOICE"
APP_POCKET_TTS_QUANTIZE_ENV = "EMPLO_APP_POCKET_TTS_QUANTIZE"
APP_POCKET_TTS_SITE_PACKAGES_ENV = "EMPLO_APP_POCKET_TTS_SITE_PACKAGES"
LEGACY_POCKET_TTS_SITE_PACKAGES_ENV = "EMPLOAI_POCKET_TTS_SITE_PACKAGES"
APP_KOKORO_TTS_MODEL_ENV = "EMPLO_APP_KOKORO_TTS_MODEL"
APP_KOKORO_TTS_VOICES_ENV = "EMPLO_APP_KOKORO_TTS_VOICES"
APP_KOKORO_TTS_VOICE_ENV = "EMPLO_APP_KOKORO_TTS_VOICE"
APP_KOKORO_TTS_LANGUAGE_ENV = "EMPLO_APP_KOKORO_TTS_LANGUAGE"
APP_KOKORO_TTS_SPEED_ENV = "EMPLO_APP_KOKORO_TTS_SPEED"
APP_KOKORO_TTS_SITE_PACKAGES_ENV = "EMPLO_APP_KOKORO_TTS_SITE_PACKAGES"
APP_VOICE_GATE_DBFS_ENV = "EMPLO_APP_VOICE_GATE_DBFS"
APP_HEBREW_VOICE_GATE_DBFS_ENV = "EMPLO_APP_HEBREW_VOICE_GATE_DBFS"
APP_JARVIS_BARGE_IN_GATE_DBFS_ENV = "EMPLO_APP_JARVIS_BARGE_IN_GATE_DBFS"
DEFAULT_STT_BACKEND = "local_whisper"
OPENAI_STT_MODEL = "gpt-4o-mini-transcribe"
OPENAI_REALTIME_STT_BACKEND = "openai_realtime"
DEFAULT_REALTIME_STT_MODEL = "gpt-realtime-whisper"
REALTIME_STT_SAMPLE_RATE = 24_000
DEFAULT_REALTIME_STT_TIMEOUT_SECONDS = 8.0
DEFAULT_REALTIME_STT_APPEND_TIMEOUT_SECONDS = 6.0
DEFAULT_LOCAL_STT_MODEL = "base.en-q5_1"
DEFAULT_LOCAL_DRAFT_MODEL = "tiny.en"
VOICE_ENGINE_NONE = "none"
VOICE_ENGINE_ENGLISH = "english_local"
VOICE_ENGINE_HEBREW = "hebrew_local"
DEFAULT_CONTEXT_CHARS = 220
DEFAULT_DRAFT_INTERVAL_MS = 900
DEFAULT_DRAFT_MIN_MS = 1200
DEFAULT_DRAFT_CONFIDENCE = 0.82
DEFAULT_DRAFT_MIN_CHARS = 10
DEFAULT_JARVIS_PENDING_WAIT_MS = 180
DEFAULT_KNOWN_TERMS = ("telegram_agent.py", ".env")
DEFAULT_HEBREW_LANGUAGE = "he"
HEBREW_SEQUENCE_MS = 1200
HEBREW_DRAFT_INTERVAL_MS = 900
HEBREW_DRAFT_MIN_MS = 700
HEBREW_DRAFT_CONFIDENCE = 0.82
HEBREW_DRAFT_MIN_CHARS = 4
HEBREW_FINAL_DISCARD_CONFIDENCE = 0.35
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "ash"
DEFAULT_TTS_FORMAT = "mp3"
DEFAULT_TTS_BACKEND = "openai"
DEFAULT_POCKET_TTS_LANGUAGE = "english"
DEFAULT_KOKORO_TTS_VOICE = "af_heart"
DEFAULT_KOKORO_TTS_LANGUAGE = "en-us"
DEFAULT_KOKORO_TTS_SPEED = 1.0
DEFAULT_VOICE_GATE_DBFS = -35.5
DEFAULT_HEBREW_VOICE_GATE_DBFS = -39.5
DEFAULT_JARVIS_BARGE_IN_GATE_DBFS = -34.0
MAX_TTS_CHARS = 4000
SUPPORTED_TTS_BACKENDS = ("openai", "kokoro_onnx", "pocket")

_stt_client: Optional[OpenAI] = None
_whisper_cli_cache: Optional[Path] = None
_model_cache: dict[str, Path] = {}
_pocket_tts_runtime: Optional["_PocketTtsRuntime"] = None
_pocket_tts_runtime_key: Optional[tuple[str, str, bool, str]] = None
_pocket_tts_lock = threading.Lock()
_kokoro_tts_runtime: Optional["_KokoroOnnxRuntime"] = None
_kokoro_tts_runtime_key: Optional[tuple[str, str, str]] = None
_kokoro_tts_lock = threading.Lock()


def _runtime_env_value(name: str) -> str:
    home = runtime_home()
    if home is None:
        return ""
    env_file = home / ".env"
    if not env_file.exists():
        return ""
    try:
        if dotenv_values is not None:
            return str(dotenv_values(env_file).get(name) or "").strip()
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                return value.strip().strip("\"'")
    except Exception:
        return ""
    return ""


def _openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    api_key = _runtime_env_value("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    return api_key


def _hebrew_transformers_runtime():
    from app_backend import hebrew_transformers_runtime as module

    return module


def hebrew_looks_repetitive(text: str) -> bool:
    return bool(_hebrew_transformers_runtime().looks_repetitive(text))


def transcribe_hebrew_wav_bytes(*args, **kwargs):
    return _hebrew_transformers_runtime().transcribe_wav_bytes(*args, **kwargs)


def hebrew_model_bundle_loaded() -> bool:
    return bool(_hebrew_transformers_runtime().model_bundle_loaded())


def preload_hebrew_model_bundle() -> None:
    _hebrew_transformers_runtime().preload_model_bundle()


def _get_stt_client() -> Optional[OpenAI]:
    global _stt_client
    if _stt_client is not None:
        return _stt_client

    if OpenAI is None:
        return None

    api_key = _openai_api_key()
    if not api_key:
        return None

    _stt_client = OpenAI(api_key=api_key)
    return _stt_client


def _voice_engine_selection() -> Dict[str, object]:
    config = get_live_config(runtime_root() / "config.json")
    english_requested = bool(config.get("voice.packs.english_local.requested", False))
    hebrew_requested = bool(config.get("voice.packs.hebrew_local.requested", False))
    default_engine = str(config.get("voice.default_engine", VOICE_ENGINE_NONE) or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE
    return {
        "default_engine": default_engine,
        "english_requested": english_requested,
        "hebrew_requested": hebrew_requested,
    }


def _selected_voice_engine() -> str:
    return str(_voice_engine_selection()["default_engine"])


def _english_pack_issues() -> list[str]:
    return list(get_english_pack_status().get("issues") or [])


def _hebrew_language() -> str:
    return os.getenv(APP_STT_HEBREW_LANGUAGE_ENV, DEFAULT_HEBREW_LANGUAGE).strip() or DEFAULT_HEBREW_LANGUAGE


def _hebrew_support_issues(*, require_model: bool) -> list[str]:
    del require_model
    return list(get_hebrew_pack_status().get("issues") or [])


def ensure_hebrew_model_downloaded(*, force: bool = False, final: bool = True) -> Path:
    del final
    install_voice_pack(VOICE_ENGINE_HEBREW, force=force)
    return hebrew_pack_runtime_dir()


def preload_hebrew_models() -> dict[str, float]:
    start = time.perf_counter()
    ensure_hebrew_model_downloaded(force=False)
    preload_hebrew_model_bundle()
    return {
        "final_seconds": round(time.perf_counter() - start, 3),
        "draft_seconds": 0.0,
    }


def _voice_input_selection_issue() -> Optional[str]:
    stt_backend = _stt_backend()
    if stt_backend == "openai":
        issues = _openai_request_stt_issues()
        return issues[0] if issues else None
    if stt_backend == OPENAI_REALTIME_STT_BACKEND:
        issues = _openai_realtime_stt_issues()
        return issues[0] if issues else None

    default_engine = _selected_voice_engine()
    if default_engine == VOICE_ENGINE_NONE:
        return "Voice input is disabled in setup and settings."
    if default_engine == VOICE_ENGINE_HEBREW:
        issues = _hebrew_support_issues(require_model=True)
        return issues[0] if issues else None
    return None


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "off", "no"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value != value:
        return default
    return value


def _clamp_dbfs(value: float) -> float:
    return round(max(-90.0, min(0.0, value)), 1)


def _voice_gate_dbfs() -> float:
    return _clamp_dbfs(_env_float(APP_VOICE_GATE_DBFS_ENV, DEFAULT_VOICE_GATE_DBFS))


def _hebrew_voice_gate_dbfs() -> float:
    return _clamp_dbfs(_env_float(APP_HEBREW_VOICE_GATE_DBFS_ENV, DEFAULT_HEBREW_VOICE_GATE_DBFS))


def _jarvis_barge_in_gate_dbfs() -> float:
    return _clamp_dbfs(_env_float(APP_JARVIS_BARGE_IN_GATE_DBFS_ENV, DEFAULT_JARVIS_BARGE_IN_GATE_DBFS))


def _tts_enabled() -> bool:
    return os.getenv(APP_TTS_ENABLED_ENV, "1").strip().lower() not in {"0", "false", "off", "no"}


def _tts_backend() -> str:
    return normalize_tts_backend(os.getenv(APP_TTS_BACKEND_ENV, DEFAULT_TTS_BACKEND), strict=False)


def normalize_tts_backend(value: object, *, strict: bool = True) -> str:
    backend = str(value or DEFAULT_TTS_BACKEND).strip().lower().replace("-", "_")
    aliases = {
        "": "openai",
        "openai": "openai",
        "kokoro": "kokoro_onnx",
        "kokoro_onnx": "kokoro_onnx",
        "kyutai": "pocket",
        "kyutai_clone": "pocket",
        "pocket": "pocket",
        "pocket_tts": "pocket",
    }
    normalized = aliases.get(backend, backend)
    if normalized not in SUPPORTED_TTS_BACKENDS and strict:
        raise ValueError(f"Unknown TTS backend: {value}")
    return normalized


def reset_tts_runtime_cache() -> None:
    global _pocket_tts_runtime, _pocket_tts_runtime_key, _kokoro_tts_runtime, _kokoro_tts_runtime_key

    with _pocket_tts_lock:
        _pocket_tts_runtime = None
        _pocket_tts_runtime_key = None
    with _kokoro_tts_lock:
        _kokoro_tts_runtime = None
        _kokoro_tts_runtime_key = None


def _pocket_tts_language() -> str:
    return os.getenv(APP_POCKET_TTS_LANGUAGE_ENV, DEFAULT_POCKET_TTS_LANGUAGE).strip() or DEFAULT_POCKET_TTS_LANGUAGE


def _pocket_tts_voice_path() -> str:
    return os.getenv(APP_POCKET_TTS_VOICE_ENV, "").strip() or str(managed_kyutai_tts_voice_path())


def _pocket_tts_quantize() -> bool:
    return _env_truthy(APP_POCKET_TTS_QUANTIZE_ENV, default=False)


def _pocket_tts_site_packages() -> str:
    return (
        os.getenv(APP_POCKET_TTS_SITE_PACKAGES_ENV, "").strip()
        or os.getenv(LEGACY_POCKET_TTS_SITE_PACKAGES_ENV, "").strip()
        or str(managed_kyutai_tts_site_packages_path())
    )


def _kokoro_runtime_root() -> Path:
    return managed_kokoro_tts_pack_root()


def _kokoro_tts_model_path() -> str:
    configured = os.getenv(APP_KOKORO_TTS_MODEL_ENV, "").strip()
    if configured:
        return configured
    return str(managed_kokoro_tts_model_path())


def _kokoro_tts_voices_path() -> str:
    configured = os.getenv(APP_KOKORO_TTS_VOICES_ENV, "").strip()
    if configured:
        return configured
    return str(managed_kokoro_tts_voices_path())


def _kokoro_tts_voice() -> str:
    configured = os.getenv(APP_KOKORO_TTS_VOICE_ENV, "").strip()
    if configured:
        return configured
    voices_path = Path(_kokoro_tts_voices_path()).expanduser()
    if voices_path.name == "voices-emploai-v1.0.bin" and voices_path.exists():
        return DEFAULT_PACK_KOKORO_TTS_VOICE
    return DEFAULT_KOKORO_TTS_VOICE


def _kokoro_tts_language() -> str:
    return os.getenv(APP_KOKORO_TTS_LANGUAGE_ENV, DEFAULT_KOKORO_TTS_LANGUAGE).strip() or DEFAULT_KOKORO_TTS_LANGUAGE


def _kokoro_tts_speed() -> float:
    raw = os.getenv(APP_KOKORO_TTS_SPEED_ENV, "").strip()
    if not raw:
        return DEFAULT_KOKORO_TTS_SPEED
    try:
        return min(2.0, max(0.5, float(raw)))
    except ValueError:
        return DEFAULT_KOKORO_TTS_SPEED


def _kokoro_tts_site_packages() -> str:
    configured = os.getenv(APP_KOKORO_TTS_SITE_PACKAGES_ENV, "").strip()
    if configured:
        return configured
    return str(managed_kokoro_tts_site_packages_path())


def _candidate_kokoro_tts_site_packages(extra_site_packages: Optional[str] = None) -> list[Path]:
    candidates: list[Path] = []
    if extra_site_packages:
        candidates.append(Path(extra_site_packages).expanduser())
    configured = _kokoro_tts_site_packages()
    if configured:
        candidates.append(Path(configured).expanduser())
    return candidates


def _candidate_pocket_tts_site_packages(extra_site_packages: Optional[str] = None) -> list[Path]:
    candidates: list[Path] = []
    if extra_site_packages:
        candidates.append(Path(extra_site_packages).expanduser())
    configured = _pocket_tts_site_packages()
    if configured:
        candidates.append(Path(configured).expanduser())

    temp_root = Path(os.getenv("TEMP", str(Path.home()))) / "emploai-pocket-tts-bench"
    candidates.append(temp_root / ".venv" / "Lib" / "site-packages")
    return candidates


def _prepare_pocket_tts_sys_path(extra_site_packages: Optional[str] = None) -> None:
    for candidate in _candidate_pocket_tts_site_packages(extra_site_packages):
        if not candidate.exists():
            continue
        resolved = str(candidate.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def _pocket_tts_import_error(extra_site_packages: Optional[str] = None) -> Optional[str]:
    _prepare_pocket_tts_sys_path(extra_site_packages)
    if importlib.util.find_spec("pocket_tts") is None:
        return (
            "Pocket TTS is not importable. Install pocket-tts or set "
            f"{APP_POCKET_TTS_SITE_PACKAGES_ENV} to a site-packages folder containing pocket_tts."
        )
    try:
        import pocket_tts  # noqa: F401
    except ImportError as exc:
        return (
            "Pocket TTS is not importable. Install pocket-tts or set "
            f"{APP_POCKET_TTS_SITE_PACKAGES_ENV} to a site-packages folder containing pocket_tts. "
            f"Import failed with {type(exc).__name__}: {exc}"
        )
    return None


def _pocket_tts_module_available(extra_site_packages: Optional[str] = None) -> bool:
    return _pocket_tts_import_error(extra_site_packages) is None


def ensure_pocket_tts_importable(extra_site_packages: Optional[str] = None) -> None:
    import_error = _pocket_tts_import_error(extra_site_packages)
    if import_error:
        raise RuntimeError(import_error)


def _float_audio_to_wav_bytes(audio: Any, sample_rate: int) -> bytes:
    if np is None:
        raise RuntimeError("NumPy is required for local TTS audio encoding.")

    audio_array = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    audio_array = np.asarray(audio_array, dtype=np.float32).reshape(-1)
    if audio_array.size == 0:
        return b""

    clipped = np.clip(audio_array, -1.0, 1.0)
    pcm = np.rint(clipped * 32767.0).astype(np.int16).tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm)
    return output.getvalue()


class _PocketTtsRuntime:
    def __init__(self, *, language: str, voice: str, quantize: bool, site_packages: str) -> None:
        ensure_pocket_tts_importable(site_packages)
        from pocket_tts import TTSModel

        if np is None:
            raise RuntimeError("NumPy is required for local Pocket TTS audio encoding.")
        if not voice:
            raise RuntimeError(f"{APP_POCKET_TTS_VOICE_ENV} must point to a Pocket TTS voice .safetensors file.")
        voice_path = Path(voice).expanduser()
        if not voice_path.exists():
            raise RuntimeError(f"Pocket TTS voice file does not exist: {voice}")

        self.language = language
        self.voice = str(voice_path)
        self.quantize = quantize
        start = time.perf_counter()
        self.model = TTSModel.load_model(language=language, quantize=quantize)
        self.model_load_seconds = time.perf_counter() - start
        start = time.perf_counter()
        self.voice_state = self.model.get_state_for_audio_prompt(self.voice)
        self.voice_load_seconds = time.perf_counter() - start
        self.sample_rate = int(self.model.sample_rate)

    def synthesize_wav_bytes(self, text: str) -> bytes:
        if np is None:
            raise RuntimeError("NumPy is required for local Pocket TTS audio encoding.")

        frames: list[Any] = []
        for chunk in self.model.generate_audio_stream(self.voice_state, text):
            frames.append(chunk)

        if not frames:
            return b""
        return _float_audio_to_wav_bytes(np.concatenate([np.asarray(frame.detach().cpu().numpy() if hasattr(frame, "detach") else frame).reshape(-1) for frame in frames]), self.sample_rate)


def _get_pocket_tts_runtime() -> _PocketTtsRuntime:
    global _pocket_tts_runtime, _pocket_tts_runtime_key

    language = _pocket_tts_language()
    voice = _pocket_tts_voice_path()
    quantize = _pocket_tts_quantize()
    site_packages = _pocket_tts_site_packages()
    runtime_key = (language, str(Path(voice).expanduser()) if voice else "", quantize, site_packages)

    with _pocket_tts_lock:
        if _pocket_tts_runtime is None or _pocket_tts_runtime_key != runtime_key:
            _pocket_tts_runtime = _PocketTtsRuntime(
                language=language,
                voice=voice,
                quantize=quantize,
                site_packages=site_packages,
            )
            _pocket_tts_runtime_key = runtime_key
        return _pocket_tts_runtime


def _prepare_kokoro_tts_sys_path(extra_site_packages: Optional[str] = None) -> None:
    for candidate in _candidate_kokoro_tts_site_packages(extra_site_packages):
        if not candidate.exists():
            continue
        resolved = str(candidate.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def _kokoro_tts_import_error(extra_site_packages: Optional[str] = None) -> Optional[str]:
    _prepare_kokoro_tts_sys_path(extra_site_packages)
    if importlib.util.find_spec("kokoro_onnx") is None:
        return (
            "Kokoro ONNX TTS is not importable. Install kokoro-onnx or set "
            f"{APP_KOKORO_TTS_SITE_PACKAGES_ENV} to a site-packages folder containing kokoro_onnx."
        )
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError as exc:
        return (
            "Kokoro ONNX TTS is not importable. Install kokoro-onnx or set "
            f"{APP_KOKORO_TTS_SITE_PACKAGES_ENV} to a site-packages folder containing kokoro_onnx. "
            f"Import failed with {type(exc).__name__}: {exc}"
        )
    return None


def ensure_kokoro_tts_importable(extra_site_packages: Optional[str] = None) -> None:
    import_error = _kokoro_tts_import_error(extra_site_packages)
    if import_error:
        raise RuntimeError(import_error)


class _KokoroOnnxRuntime:
    def __init__(self, *, model_path: str, voices_path: str, site_packages: str) -> None:
        ensure_kokoro_tts_importable(site_packages)
        from kokoro_onnx import Kokoro

        if np is None:
            raise RuntimeError("NumPy is required for local Kokoro TTS audio encoding.")
        model = Path(model_path).expanduser()
        voices = Path(voices_path).expanduser()
        if not model.exists():
            raise RuntimeError(f"{APP_KOKORO_TTS_MODEL_ENV} must point to a Kokoro ONNX model file.")
        if not voices.exists():
            raise RuntimeError(f"{APP_KOKORO_TTS_VOICES_ENV} must point to a Kokoro voices file.")

        self.model_path = str(model)
        self.voices_path = str(voices)
        start = time.perf_counter()
        self.model = Kokoro(self.model_path, self.voices_path)
        self.model_load_seconds = time.perf_counter() - start
        self.sample_rate = 24_000

    def available_voices(self) -> list[str]:
        voices = getattr(self.model, "get_voices", None)
        if callable(voices):
            return [str(item) for item in voices()]
        return []

    def synthesize_wav_bytes(self, text: str, *, voice: str, speed: float, language: str) -> bytes:
        audio, sample_rate = self.model.create(text, voice=voice, speed=speed, lang=language)
        self.sample_rate = int(sample_rate)
        return _float_audio_to_wav_bytes(audio, self.sample_rate)


def _get_kokoro_tts_runtime() -> _KokoroOnnxRuntime:
    global _kokoro_tts_runtime, _kokoro_tts_runtime_key

    model_path = _kokoro_tts_model_path()
    voices_path = _kokoro_tts_voices_path()
    site_packages = _kokoro_tts_site_packages()
    runtime_key = (str(Path(model_path).expanduser()), str(Path(voices_path).expanduser()), site_packages)

    with _kokoro_tts_lock:
        if _kokoro_tts_runtime is None or _kokoro_tts_runtime_key != runtime_key:
            _kokoro_tts_runtime = _KokoroOnnxRuntime(
                model_path=model_path,
                voices_path=voices_path,
                site_packages=site_packages,
            )
            _kokoro_tts_runtime_key = runtime_key
        return _kokoro_tts_runtime


def preload_tts_engine() -> Dict[str, object]:
    if not _tts_enabled():
        return {"ok": True, "enabled": False, "backend": _tts_backend(), "timings": None}

    backend = _tts_backend()
    if backend == "pocket":
        start = time.perf_counter()
        runtime = _get_pocket_tts_runtime()
        return {
            "ok": True,
            "enabled": True,
            "backend": backend,
            "voice": runtime.voice,
            "language": runtime.language,
            "sample_rate": runtime.sample_rate,
            "timings": {
                "total_seconds": round(time.perf_counter() - start, 3),
                "model_load_seconds": round(runtime.model_load_seconds, 3),
                "voice_load_seconds": round(runtime.voice_load_seconds, 3),
            },
        }
    if backend == "kokoro_onnx":
        start = time.perf_counter()
        runtime = _get_kokoro_tts_runtime()
        return {
            "ok": True,
            "enabled": True,
            "backend": backend,
            "voice": _kokoro_tts_voice(),
            "model": runtime.model_path,
            "voices_path": runtime.voices_path,
            "language": _kokoro_tts_language(),
            "sample_rate": runtime.sample_rate,
            "available_voices": runtime.available_voices(),
            "timings": {
                "total_seconds": round(time.perf_counter() - start, 3),
                "model_load_seconds": round(runtime.model_load_seconds, 3),
            },
        }
    if backend == "openai":
        return {"ok": True, "enabled": True, "backend": backend, "timings": None}
    raise RuntimeError(f"Unknown TTS backend: {backend}")


def get_tts_runtime_status() -> Dict[str, object]:
    enabled = _tts_enabled()
    backend = _tts_backend()
    kokoro_pack_status = get_kokoro_tts_pack_status()
    kyutai_pack_status = get_kyutai_tts_pack_status()
    issues: list[str] = []
    ready = False
    voice: Optional[str] = None
    model: Optional[str] = None

    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "ready": False,
            "backend": backend,
            "available_backends": list(SUPPORTED_TTS_BACKENDS),
            "issues": [],
            "voice": None,
            "model": None,
            "kokoro_tts_pack_status": kokoro_pack_status,
            "kyutai_tts_pack_status": kyutai_pack_status,
        }

    if backend == "openai":
        voice = os.getenv(APP_TTS_VOICE_ENV, DEFAULT_TTS_VOICE)
        model = os.getenv(APP_TTS_MODEL_ENV, DEFAULT_TTS_MODEL)
        if OpenAI is None:
            issues.append("Assistant audio is enabled but the `openai` Python package is missing.")
        elif not _openai_api_key():
            issues.append("Assistant audio is enabled with OpenAI TTS but OPENAI_API_KEY is not configured.")
        else:
            ready = True
    elif backend == "pocket":
        voice = _pocket_tts_voice_path()
        model = "pocket_tts"
        if np is None:
            issues.append("Pocket TTS requires NumPy for audio encoding.")
        if not voice:
            issues.append(f"{APP_POCKET_TTS_VOICE_ENV} must point to a Pocket TTS voice .safetensors file.")
        elif not Path(voice).expanduser().exists():
            issues.append(f"Pocket TTS voice file does not exist: {voice}")
        import_error = _pocket_tts_import_error(_pocket_tts_site_packages())
        if import_error:
            issues.append(import_error)
        ready = not issues
    elif backend == "kokoro_onnx":
        voice = _kokoro_tts_voice()
        model = _kokoro_tts_model_path()
        voices_path = _kokoro_tts_voices_path()
        if np is None:
            issues.append("Kokoro ONNX TTS requires NumPy for audio encoding.")
        if not Path(model).expanduser().exists():
            issues.append(f"Kokoro ONNX model file does not exist: {model}")
        if not Path(voices_path).expanduser().exists():
            issues.append(f"Kokoro ONNX voices file does not exist: {voices_path}")
        import_error = _kokoro_tts_import_error(_kokoro_tts_site_packages())
        if import_error:
            issues.append(import_error)
        ready = not issues
    else:
        issues.append(f"Unknown TTS backend: {backend}")

    return {
        "ok": not issues,
        "enabled": True,
        "ready": ready,
        "backend": backend,
        "available_backends": list(SUPPORTED_TTS_BACKENDS),
        "issues": issues,
        "voice": voice,
        "model": model,
        "kokoro_tts_pack_status": kokoro_pack_status,
        "kyutai_tts_pack_status": kyutai_pack_status,
    }


def get_voice_runtime_status() -> Dict[str, object]:
    input_issues: list[str] = []
    stt_backend = _stt_backend()
    api_stt_backend = _is_api_stt_backend(stt_backend)
    selection = _voice_engine_selection()
    default_engine = str(selection["default_engine"])
    english_requested = bool(selection["english_requested"])
    hebrew_requested = bool(selection["hebrew_requested"])
    english_pack_status = get_english_pack_status()
    hebrew_pack_status = get_hebrew_pack_status()
    english_pack_issues = list(english_pack_status.get("issues") or [])
    hebrew_pack_issues = list(hebrew_pack_status.get("issues") or [])
    english_pack_ready = bool(english_pack_status.get("available"))
    hebrew_pack_ready = bool(hebrew_pack_status.get("available"))

    if default_engine == VOICE_ENGINE_NONE and not api_stt_backend:
        input_issues.append("Voice input is disabled in setup and settings.")
    elif stt_backend == "openai":
        input_issues.extend(_openai_request_stt_issues())
    elif stt_backend == OPENAI_REALTIME_STT_BACKEND:
        input_issues.extend(_openai_realtime_stt_issues())
    elif default_engine == VOICE_ENGINE_HEBREW:
        input_issues.extend(hebrew_pack_issues)
    else:
        input_issues.extend(english_pack_issues)

    tts_status = get_tts_runtime_status()
    tts_enabled = bool(tts_status.get("enabled"))
    tts_issues = [str(item) for item in (tts_status.get("issues") or [])]

    if default_engine == VOICE_ENGINE_NONE and not api_stt_backend:
        selected_engine_state = "disabled"
    elif input_issues:
        selected_engine_state = "error"
    elif api_stt_backend:
        selected_engine_state = "ready"
    elif default_engine == VOICE_ENGINE_HEBREW:
        selected_engine_state = "ready" if hebrew_model_bundle_loaded() else "warming"
    else:
        selected_engine_state = "ready"

    if stt_backend == OPENAI_REALTIME_STT_BACKEND:
        stt_model = f"{_realtime_transcription_model()} realtime transcription"
        draft_model = None
        binary_flavor = None
    elif stt_backend == "openai":
        stt_model = os.getenv(APP_STT_MODEL_ENV, OPENAI_STT_MODEL)
        draft_model = None
        binary_flavor = None
    elif default_engine == VOICE_ENGINE_HEBREW:
        stt_model = str(
            (hebrew_pack_status.get("manifest") or {}).get("asset_name")
            or (hebrew_pack_status.get("manifest") or {}).get("pack_id")
            or hebrew_pack_status.get("model_dir")
            or ""
        )
        draft_model = str(hebrew_pack_status.get("model_dir") or "")
        binary_flavor = None
    else:
        stt_model = _local_model_name()
        draft_model = _local_draft_model_name()
        binary_flavor = _local_binary_flavor()

    return {
        "ok": not input_issues,
        "input_ok": not input_issues,
        "issues": input_issues,
        "stt_backend": stt_backend,
        "stt_model": stt_model,
        "draft_model": draft_model,
        "binary_flavor": binary_flavor,
        "tts_enabled": tts_enabled,
        "tts_ok": (not tts_enabled) or bool(tts_status.get("ok")),
        "tts_backend": tts_status.get("backend"),
        "tts_available_backends": list(tts_status.get("available_backends") or SUPPORTED_TTS_BACKENDS),
        "tts_ready": bool(tts_status.get("ready")),
        "tts_voice": tts_status.get("voice"),
        "tts_model": tts_status.get("model"),
        "tts_issues": tts_issues,
        "kokoro_tts_pack_status": tts_status.get("kokoro_tts_pack_status"),
        "kyutai_tts_pack_status": tts_status.get("kyutai_tts_pack_status"),
        "voice_gate_dbfs": _voice_gate_dbfs(),
        "hebrew_voice_gate_dbfs": _hebrew_voice_gate_dbfs(),
        "jarvis_barge_in_gate_dbfs": _jarvis_barge_in_gate_dbfs(),
        "selected_engine": default_engine,
        "english_requested": english_requested,
        "hebrew_requested": hebrew_requested,
        "english_pack_ready": english_pack_ready,
        "hebrew_pack_ready": hebrew_pack_ready,
        "english_pack_status": english_pack_status,
        "hebrew_pack_status": hebrew_pack_status,
        "english_pack_manifest": english_pack_status.get("manifest"),
        "english_pack_manifest_verified": bool(english_pack_status.get("manifest_verified")),
        "hebrew_pack_manifest": hebrew_pack_status.get("manifest"),
        "hebrew_pack_manifest_verified": bool(hebrew_pack_status.get("manifest_verified")),
        "hebrew_model_root": str(hebrew_pack_status.get("model_dir") or ""),
        "hebrew_draft_model_root": str(hebrew_pack_status.get("model_dir") or ""),
        "selected_engine_state": selected_engine_state,
        "selected_engine_ready": selected_engine_state == "ready",
    }


def _normalize_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _collapse_repeated_phrase(text: str) -> str:
    normalized = _normalize_transcript(text)
    words = [part for part in normalized.split(" ") if part]
    if len(words) < 2:
        return normalized
    if len(set(words)) == 1:
        return words[0]

    max_phrase_words = min(len(words) // 2, 6)
    for phrase_words in range(1, max_phrase_words + 1):
        if len(words) % phrase_words != 0:
            continue
        phrase = words[:phrase_words]
        repetitions = len(words) // phrase_words
        if repetitions < 2:
            continue
        if phrase * repetitions == words:
            return " ".join(phrase)
    return normalized


def _normalize_tts_text(text: str) -> str:
    normalized = _normalize_transcript(text)
    if len(normalized) <= MAX_TTS_CHARS:
        return normalized
    clipped = normalized[:MAX_TTS_CHARS].rsplit(" ", 1)[0].strip()
    return clipped or normalized[:MAX_TTS_CHARS]


def _stt_backend() -> str:
    return (os.getenv(APP_STT_BACKEND_ENV, DEFAULT_STT_BACKEND).strip().lower() or DEFAULT_STT_BACKEND)


def _is_api_stt_backend(stt_backend: Optional[str] = None) -> bool:
    return (stt_backend or _stt_backend()) in {"openai", OPENAI_REALTIME_STT_BACKEND}


def _realtime_stt_model() -> str:
    return os.getenv(APP_STT_REALTIME_MODEL_ENV, DEFAULT_REALTIME_STT_MODEL).strip() or DEFAULT_REALTIME_STT_MODEL


def _realtime_transcription_model() -> str:
    configured = (
        os.getenv(APP_STT_REALTIME_TRANSCRIPTION_MODEL_ENV, "").strip()
        or _realtime_stt_model()
    )
    return configured


def _realtime_ws_url() -> str:
    configured = os.getenv(APP_STT_REALTIME_URL_ENV, "").strip()
    if configured:
        return configured
    return "wss://api.openai.com/v1/realtime?intent=transcription"


def _realtime_final_timeout_seconds() -> float:
    return max(0.5, _float_env(APP_STT_REALTIME_TIMEOUT_SECONDS_ENV, DEFAULT_REALTIME_STT_TIMEOUT_SECONDS))


def _realtime_append_timeout_seconds() -> float:
    return max(0.5, _float_env(APP_STT_REALTIME_APPEND_TIMEOUT_SECONDS_ENV, DEFAULT_REALTIME_STT_APPEND_TIMEOUT_SECONDS))


def _realtime_noise_reduction_type() -> Optional[str]:
    configured = os.getenv(APP_STT_REALTIME_NOISE_REDUCTION_ENV, "near_field").strip().lower()
    if configured in {"", "0", "false", "off", "none", "no"}:
        return None
    if configured in {"near_field", "far_field"}:
        return configured
    return "near_field"


def _openai_request_stt_issues() -> list[str]:
    if OpenAI is None:
        return ["The `openai` Python package is not installed, so app voice transcription is unavailable."]
    if not _openai_api_key():
        return ["OPENAI_API_KEY is not configured, so app voice transcription is unavailable."]
    return []


def _openai_realtime_stt_issues() -> list[str]:
    issues: list[str] = []
    if not _openai_api_key():
        issues.append("OPENAI_API_KEY is not configured, so OpenAI Realtime voice transcription is unavailable.")
    try:
        import websockets  # noqa: F401
    except ImportError:
        issues.append("The `websockets` Python package is not installed, so OpenAI Realtime voice transcription is unavailable.")
    return issues


def _local_model_name() -> str:
    return os.getenv(APP_STT_MODEL_ENV, DEFAULT_LOCAL_STT_MODEL).strip() or DEFAULT_LOCAL_STT_MODEL


def _local_draft_model_name() -> str:
    return os.getenv(APP_STT_DRAFT_MODEL_ENV, DEFAULT_LOCAL_DRAFT_MODEL).strip() or DEFAULT_LOCAL_DRAFT_MODEL


def _local_binary_flavor() -> str:
    return os.getenv(APP_STT_BINARY_FLAVOR_ENV, DEFAULT_BINARY_FLAVOR).strip() or DEFAULT_BINARY_FLAVOR


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _known_terms_list() -> list[str]:
    configured = os.getenv(APP_STT_KNOWN_TERMS_ENV, "").strip()
    raw_terms = [item.strip() for item in configured.split(",") if item.strip()] if configured else list(DEFAULT_KNOWN_TERMS)
    terms: list[str] = []
    seen_terms: set[str] = set()
    for term in raw_terms:
        normalized = term.casefold()
        if normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        terms.append(term)
    return terms


def _known_terms_hotwords() -> Optional[str]:
    terms = _known_terms_list()
    return ", ".join(terms) if terms else None


def _known_terms_prompt() -> str:
    terms = _known_terms_list()
    prompt = os.getenv(APP_STT_PROMPT_ENV, "").strip()
    if terms:
        literal = "Prefer these literal project terms and filenames exactly if heard: " + ", ".join(terms) + "."
        return f"{prompt}\n{literal}".strip() if prompt else literal
    return prompt


def jarvis_fast_final_enabled() -> bool:
    return _env_truthy(APP_JARVIS_FAST_FINAL_ENV, default=True)


def jarvis_pending_wait_seconds() -> float:
    return max(0, _int_env(APP_JARVIS_PENDING_WAIT_MS_ENV, DEFAULT_JARVIS_PENDING_WAIT_MS)) / 1000.0


def _resolve_whisper_cli() -> Path:
    global _whisper_cli_cache
    if _whisper_cli_cache is None:
        _whisper_cli_cache = english_pack_cli_path()
    return _whisper_cli_cache


def _resolve_model(model_name: str) -> Path:
    if model_name not in _model_cache:
        _model_cache[model_name] = english_pack_model_path(model_name)
    return _model_cache[model_name]


def _voice_output_dir() -> Path:
    path = output_root() / "app_voice"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_pcm16_mono_wav(data: bytes) -> tuple[int, bytes]:
    with wave.open(io.BytesIO(data), "rb") as handle:
        channels = int(handle.getnchannels())
        sample_width = int(handle.getsampwidth())
        sample_rate = int(handle.getframerate())
        frames = handle.readframes(handle.getnframes())

    if channels != 1:
        raise RuntimeError(f"Expected mono WAV audio from desktop voice capture, got {channels} channels")
    if sample_width != 2:
        raise RuntimeError(f"Expected 16-bit PCM WAV audio from desktop voice capture, got {sample_width * 8}-bit samples")
    if sample_rate <= 0:
        raise RuntimeError("Desktop voice capture sent WAV audio with an invalid sample rate")
    return sample_rate, frames


def _resample_pcm16_mono(frames: bytes, *, source_rate: int, target_rate: int) -> bytes:
    if source_rate == target_rate:
        return frames
    if np is None:
        raise RuntimeError("NumPy is required to resample voice audio")
    if not frames:
        return b""
    samples = np.frombuffer(frames, dtype=np.int16)
    if samples.size == 0:
        return b""
    target_count = max(1, int(round(samples.size * float(target_rate) / float(source_rate))))
    source_positions = np.linspace(0.0, float(samples.size - 1), num=samples.size, dtype=np.float32)
    target_positions = np.linspace(0.0, float(samples.size - 1), num=target_count, dtype=np.float32)
    resampled = np.interp(target_positions, source_positions, samples.astype(np.float32))
    clipped = np.clip(np.rint(resampled), -32768, 32767).astype(np.int16)
    return clipped.tobytes()


def _wav_bytes_to_realtime_pcm24k(data: bytes) -> bytes:
    sample_rate, frames = _read_pcm16_mono_wav(data)
    return _resample_pcm16_mono(frames, source_rate=sample_rate, target_rate=REALTIME_STT_SAMPLE_RATE)


def _wav_bytes_to_float32_audio(data: bytes, *, target_rate: int = 16000) -> tuple["np.ndarray", int]:
    sample_rate, frames = _read_pcm16_mono_wav(data)
    if np is None:
        raise RuntimeError("NumPy is required for the Hebrew local voice runtime")
    resampled_frames = _resample_pcm16_mono(frames, source_rate=sample_rate, target_rate=target_rate)
    pcm = np.frombuffer(resampled_frames, dtype=np.int16).astype(np.float32)
    if pcm.size == 0:
        return np.zeros((0,), dtype=np.float32), target_rate
    return pcm / 32768.0, target_rate


def _transcribe_wav_bytes_local(
    data: bytes,
    *,
    model_name: str,
    sequence: int,
    revision: int,
    initial_prompt: Optional[str],
) -> tuple[str, Optional[float]]:
    sample_rate, frames = _read_pcm16_mono_wav(data)
    run_id = f"{int(time.time() * 1000)}_r{revision}_s{sequence}"
    audio_path = _voice_output_dir() / f"app_voice_{run_id}.wav"
    write_pcm16_mono_wav(audio_path, [frames], sample_rate)
    fixture = WhisperFixture(name=audio_path.stem, audio_path=audio_path, source="desktop_app_voice")
    result = run_whisper_cli_once(
        whisper_cli=_resolve_whisper_cli(),
        model_path=_resolve_model(model_name),
        model_name=model_name,
        fixture=fixture,
        iteration=max(1, sequence),
        language=os.getenv(APP_STT_LANGUAGE_ENV, DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE,
        initial_prompt=initial_prompt,
        no_gpu=True,
        threads=recommended_thread_count(),
        output_dir=_voice_output_dir(),
    )
    _, confidence = transcript_confidence_from_output_json(result.output_json_path)
    return _normalize_transcript(result.transcript), confidence


def _transcribe_wav_bytes_hebrew(
    data: bytes,
    *,
    sequence: int,
    revision: int,
    initial_prompt: Optional[str],
    final: bool,
    use_vad: Optional[bool] = None,
) -> tuple[str, Optional[float]]:
    del sequence, revision, final, use_vad
    text, confidence = transcribe_hebrew_wav_bytes(
        data,
        initial_prompt=initial_prompt or _known_terms_prompt() or None,
        language="hebrew",
        task="transcribe",
    )
    return _normalize_transcript(text), confidence


def _extension_for_mime(mime_type: Optional[str]) -> str:
    mime = (mime_type or "").lower()
    if "wav" in mime:
        return "wav"
    if "mpeg" in mime or "mp3" in mime:
        return "mp3"
    if "webm" in mime:
        return "webm"
    if "ogg" in mime:
        return "ogg"
    return "m4a"


def _mime_for_audio_format(audio_format: str) -> str:
    fmt = (audio_format or "").lower()
    if fmt == "wav":
        return "audio/wav"
    if fmt == "aac":
        return "audio/aac"
    if fmt == "flac":
        return "audio/flac"
    if fmt == "opus":
        return "audio/opus"
    if fmt == "pcm":
        return "audio/pcm"
    return "audio/mpeg"


def _transcribe_audio_bytes(data: bytes, mime_type: Optional[str]) -> str:
    client = _get_stt_client()
    if not client:
        if OpenAI is None:
            raise RuntimeError("The `openai` Python package is not installed, so app voice transcription is unavailable")
        raise RuntimeError("OPENAI_API_KEY is required for app voice transcription")
    if not data:
        return ""

    audio_file = io.BytesIO(data)
    audio_file.name = f"voice_chunk.{_extension_for_mime(mime_type)}"

    kwargs = {
        "file": audio_file,
        "model": os.getenv(APP_STT_MODEL_ENV, OPENAI_STT_MODEL),
        "response_format": "text",
    }

    language = os.getenv(APP_STT_LANGUAGE_ENV, "").strip()
    if language:
        kwargs["language"] = language

    prompt = os.getenv(APP_STT_PROMPT_ENV, "").strip()
    if prompt:
        kwargs["prompt"] = prompt

    try:
        result = client.audio.transcriptions.create(**kwargs)
    except Exception as exc:
        info = normalize_provider_error(exc, payload_kind="audio")
        raise RuntimeError(f"{info.error_type}: {info.message}") from exc
    if isinstance(result, str):
        return _normalize_transcript(result)
    return _normalize_transcript(getattr(result, "text", ""))


def synthesize_assistant_audio(text: str) -> Optional[Dict[str, object]]:
    if not _tts_enabled():
        return None

    normalized = _normalize_tts_text(text)
    if not normalized:
        return None

    backend = _tts_backend()
    if backend == "pocket":
        runtime = _get_pocket_tts_runtime()
        audio_bytes = runtime.synthesize_wav_bytes(normalized)
        if not audio_bytes:
            return None
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "mime_type": "audio/wav",
            "format": "wav",
            "voice": runtime.voice,
            "model": "pocket_tts",
            "backend": backend,
            "text": redact_text(normalized),
            "sample_rate": runtime.sample_rate,
        }

    if backend == "kokoro_onnx":
        runtime = _get_kokoro_tts_runtime()
        voice = _kokoro_tts_voice()
        speed = _kokoro_tts_speed()
        language = _kokoro_tts_language()
        audio_bytes = runtime.synthesize_wav_bytes(
            normalized,
            voice=voice,
            speed=speed,
            language=language,
        )
        if not audio_bytes:
            return None
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "mime_type": "audio/wav",
            "format": "wav",
            "voice": voice,
            "model": runtime.model_path,
            "backend": backend,
            "text": redact_text(normalized),
            "sample_rate": runtime.sample_rate,
            "language": language,
            "speed": speed,
        }

    if backend != "openai":
        raise RuntimeError(f"Unknown TTS backend: {backend}")

    client = _get_stt_client()
    if not client:
        return None

    response_format = os.getenv(APP_TTS_FORMAT_ENV, DEFAULT_TTS_FORMAT).strip().lower() or DEFAULT_TTS_FORMAT
    kwargs = {
        "input": normalized,
        "model": os.getenv(APP_TTS_MODEL_ENV, DEFAULT_TTS_MODEL),
        "voice": os.getenv(APP_TTS_VOICE_ENV, DEFAULT_TTS_VOICE),
        "response_format": response_format,
    }

    instructions = os.getenv(APP_TTS_INSTRUCTIONS_ENV, "").strip()
    if instructions:
        kwargs["instructions"] = instructions

    speed_text = os.getenv(APP_TTS_SPEED_ENV, "").strip()
    if speed_text:
        try:
            kwargs["speed"] = float(speed_text)
        except ValueError:
            pass

    try:
        result = client.audio.speech.create(**kwargs)
    except Exception as exc:
        info = normalize_provider_error(exc, payload_kind="text")
        raise RuntimeError(f"{info.error_type}: {info.message}") from exc
    try:
        audio_bytes = getattr(result, "content", None) or result.read()
    finally:
        close = getattr(result, "close", None)
        if callable(close):
            close()

    if not audio_bytes:
        return None

    return {
        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
        "mime_type": _mime_for_audio_format(response_format),
        "format": response_format,
        "voice": kwargs["voice"],
        "model": kwargs["model"],
        "backend": backend,
        "text": redact_text(normalized),
    }


@dataclass
class VoiceDraftState:
    segment_texts: Dict[int, str] = field(default_factory=dict)
    wav_chunks: Dict[int, bytes] = field(default_factory=dict, repr=False)
    last_sequence: int = 0
    last_draft_sequence: int = 0
    sample_rate: Optional[int] = None
    draft_text: str = ""
    final_text: str = ""
    previous_final_text: str = ""
    fresh_output_confirmed: bool = False
    state: str = "idle"
    revision: int = 0
    pending_tasks: Set[asyncio.Task] = field(default_factory=set, repr=False)
    transcription_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1), repr=False)

    def reset(self) -> int:
        self.revision += 1
        previous_text = _normalize_transcript(self.final_text or self.draft_text or self.transcript())
        self.segment_texts.clear()
        self.wav_chunks.clear()
        self.last_sequence = 0
        self.last_draft_sequence = 0
        self.sample_rate = None
        self.draft_text = ""
        self.final_text = ""
        self.previous_final_text = previous_text
        self.fresh_output_confirmed = False
        self.state = "idle"
        return self.revision

    def _strip_stale_prefix(self, text: str) -> str:
        normalized = _normalize_transcript(text)
        if self.fresh_output_confirmed:
            return normalized
        previous = _normalize_transcript(self.previous_final_text)
        if not previous:
            return normalized
        prefix = f"{previous} "
        if normalized.startswith(prefix):
            return _normalize_transcript(normalized[len(prefix):])
        return normalized

    def transcript(self) -> str:
        if self.final_text:
            return self.final_text
        if self.draft_text:
            return self.draft_text
        parts = [self.segment_texts[idx] for idx in sorted(self.segment_texts) if self.segment_texts[idx]]
        return _normalize_transcript(" ".join(parts))

    def _combined_wav_bytes(self) -> bytes:
        frames: list[bytes] = []
        sample_rate: Optional[int] = None
        for idx in sorted(self.wav_chunks):
            chunk_sample_rate, chunk_frames = _read_pcm16_mono_wav(self.wav_chunks[idx])
            if sample_rate is None:
                sample_rate = chunk_sample_rate
            elif sample_rate != chunk_sample_rate:
                raise RuntimeError("Desktop voice capture changed sample rate mid-utterance")
            frames.append(chunk_frames)

        if not frames or sample_rate is None:
            return b""

        output = io.BytesIO()
        with wave.open(output, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(frames))
        return output.getvalue()

    def _prompt(self) -> Optional[str]:
        return _known_terms_prompt() or None

    def _draft_min_ms(self) -> int:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return max(300, _int_env(APP_STT_DRAFT_MIN_MS_ENV, HEBREW_DRAFT_MIN_MS))
        return max(300, _int_env(APP_STT_DRAFT_MIN_MS_ENV, DEFAULT_DRAFT_MIN_MS))

    def _draft_interval_ms(self) -> int:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return max(200, _int_env(APP_STT_DRAFT_INTERVAL_MS_ENV, HEBREW_DRAFT_INTERVAL_MS))
        return max(200, _int_env(APP_STT_DRAFT_INTERVAL_MS_ENV, DEFAULT_DRAFT_INTERVAL_MS))

    def _draft_min_chars(self) -> int:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return HEBREW_DRAFT_MIN_CHARS
        return max(1, _int_env(APP_STT_DRAFT_MIN_CHARS_ENV, DEFAULT_DRAFT_MIN_CHARS))

    def _draft_confidence_threshold(self) -> float:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return HEBREW_DRAFT_CONFIDENCE
        return max(0.0, min(1.0, _float_env(APP_STT_DRAFT_CONFIDENCE_ENV, DEFAULT_DRAFT_CONFIDENCE)))

    def _final_discard_threshold(self) -> float | None:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return HEBREW_FINAL_DISCARD_CONFIDENCE
        return None

    def _sequence_duration_ms(self) -> int:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return HEBREW_SEQUENCE_MS
        return 850

    def _should_run_draft(self, sequence: int) -> bool:
        if sequence <= self.last_draft_sequence:
            return False
        draft_min_ms = self._draft_min_ms()
        draft_interval_ms = self._draft_interval_ms()
        if not self.sample_rate:
            return False
        total_samples = 0
        for raw in self.wav_chunks.values():
            _, frames = _read_pcm16_mono_wav(raw)
            total_samples += len(frames) // 2
        duration_ms = int(total_samples * 1000 / max(1, self.sample_rate))
        if duration_ms < draft_min_ms:
            return False
        sequence_gap_ms = (sequence - self.last_draft_sequence) * self._sequence_duration_ms()
        return sequence_gap_ms >= draft_interval_ms

    def register_task(self, task: asyncio.Task) -> None:
        self.pending_tasks.add(task)
        task.add_done_callback(lambda finished: self.pending_tasks.discard(finished))

    async def wait_for_pending(self, timeout: Optional[float] = None) -> None:
        pending = list(self.pending_tasks)
        if not pending:
            return
        if timeout is None:
            await asyncio.gather(*pending, return_exceptions=True)
            return
        if timeout <= 0:
            return
        await asyncio.wait(pending, timeout=timeout)

    def cancel_pending(self) -> None:
        for task in list(self.pending_tasks):
            task.cancel()
        self.pending_tasks.clear()

    async def transcribe_chunk(
        self,
        *,
        audio_base64: Optional[str],
        mime_type: Optional[str],
        sequence: Optional[int],
        revision: Optional[int] = None,
    ) -> str:
        selection_issue = _voice_input_selection_issue()
        if selection_issue:
            raise RuntimeError(selection_issue)
        if not audio_base64:
            return self.transcript()

        raw = base64.b64decode(audio_base64)
        seq = int(sequence or (self.last_sequence + 1))
        active_revision = self.revision if revision is None else revision
        mime = (mime_type or "").lower()
        selected_engine = _selected_voice_engine()
        if selected_engine == VOICE_ENGINE_HEBREW or not _is_api_stt_backend():
            if "wav" not in mime:
                raise RuntimeError("Local desktop voice transcription expects audio/wav chunks")
            chunk_sample_rate, _ = _read_pcm16_mono_wav(raw)
            if self.sample_rate is None:
                self.sample_rate = chunk_sample_rate
            elif self.sample_rate != chunk_sample_rate:
                raise RuntimeError("Desktop voice capture changed sample rate mid-utterance")
            self.wav_chunks[seq] = raw
            self.last_sequence = max(self.last_sequence, seq)
            if not self._should_run_draft(seq):
                return self.transcript()

            combined = self._combined_wav_bytes()
            if not combined:
                return self.transcript()

            async with self.transcription_slots:
                loop = asyncio.get_running_loop()
                if selected_engine == VOICE_ENGINE_HEBREW:
                    text, confidence = await loop.run_in_executor(
                        None,
                        partial(
                            _transcribe_wav_bytes_hebrew,
                            combined,
                            sequence=seq,
                            revision=active_revision,
                            initial_prompt=self._prompt(),
                            final=False,
                        ),
                    )
                else:
                    text, confidence = await loop.run_in_executor(
                        None,
                        partial(
                            _transcribe_wav_bytes_local,
                            combined,
                            model_name=_local_draft_model_name(),
                            sequence=seq,
                            revision=active_revision,
                            initial_prompt=self._prompt(),
                        ),
                    )
            if active_revision != self.revision:
                return self.transcript()

            text = self._strip_stale_prefix(_collapse_repeated_phrase(text))
            min_confidence = self._draft_confidence_threshold()
            min_chars = self._draft_min_chars()
            if selected_engine == VOICE_ENGINE_HEBREW and hebrew_looks_repetitive(text):
                text = self.draft_text or ""
            if text and len(text) >= min_chars and (confidence is None or confidence >= min_confidence):
                self.draft_text = text
                self.segment_texts[seq] = text
                self.last_draft_sequence = seq
                self.fresh_output_confirmed = True
            return self.transcript()

        async with self.transcription_slots:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, _transcribe_audio_bytes, raw, mime_type)
        if active_revision != self.revision:
            return self.transcript()

        self.segment_texts[seq] = text
        self.last_sequence = max(self.last_sequence, seq)
        return self.transcript()

    async def final_transcript(self, *, fast: bool = False) -> str:
        selection_issue = _voice_input_selection_issue()
        if selection_issue:
            raise RuntimeError(selection_issue)
        selected_engine = _selected_voice_engine()
        if selected_engine != VOICE_ENGINE_HEBREW and _is_api_stt_backend():
            return self.transcript()

        if fast and selected_engine != VOICE_ENGINE_HEBREW:
            current = self.transcript()
            if current and self.fresh_output_confirmed:
                self.final_text = current
                return current

        combined = self._combined_wav_bytes()
        if not combined:
            return ""

        active_revision = self.revision
        async with self.transcription_slots:
            loop = asyncio.get_running_loop()
            if selected_engine == VOICE_ENGINE_HEBREW:
                text, _confidence = await loop.run_in_executor(
                    None,
                    partial(
                        _transcribe_wav_bytes_hebrew,
                        combined,
                        sequence=max(1, self.last_sequence),
                        revision=active_revision,
                        initial_prompt=self._prompt(),
                        final=True,
                    ),
                )
            else:
                text, _confidence = await loop.run_in_executor(
                    None,
                    partial(
                        _transcribe_wav_bytes_local,
                        combined,
                        model_name=_local_draft_model_name() if fast else _local_model_name(),
                        sequence=max(1, self.last_sequence),
                        revision=active_revision,
                        initial_prompt=self._prompt(),
                    ),
                )
        if active_revision != self.revision:
            return self.transcript()

        text = self._strip_stale_prefix(_collapse_repeated_phrase(text))
        if selected_engine == VOICE_ENGINE_HEBREW:
            min_chars = self._draft_min_chars()
            discard_threshold = self._final_discard_threshold()
            if hebrew_looks_repetitive(text) and self.draft_text:
                text = self.draft_text
            if (not text or len(text) < min_chars) and self.draft_text:
                text = self.draft_text
            if (
                discard_threshold is not None
                and _confidence is not None
                and _confidence < discard_threshold
                and not self.draft_text
            ):
                text = ""

        self.final_text = text
        if text:
            self.segment_texts[max(1, self.last_sequence)] = text
            self.fresh_output_confirmed = True
        return self.transcript()


@dataclass
class OpenAIRealtimeVoiceDraftState:
    cancel_empty_pending_before_final: bool = False
    segment_texts: Dict[int, str] = field(default_factory=dict)
    pcm_chunks: Dict[int, bytes] = field(default_factory=dict, repr=False)
    appended_sequences: Set[int] = field(default_factory=set, repr=False)
    last_sequence: int = 0
    draft_text: str = ""
    final_text: str = ""
    state: str = "idle"
    revision: int = 0
    pending_tasks: Set[asyncio.Task] = field(default_factory=set, repr=False)
    transcription_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1), repr=False)
    websocket: Any = field(default=None, repr=False)
    listener_task: Optional[asyncio.Task] = field(default=None, repr=False)
    final_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    commit_sent: bool = False
    error_text: Optional[str] = None

    def reset(self) -> int:
        self.revision += 1
        self.cancel_pending()
        self.segment_texts.clear()
        self.pcm_chunks.clear()
        self.appended_sequences.clear()
        self.last_sequence = 0
        self.draft_text = ""
        self.final_text = ""
        self.state = "idle"
        self.final_event = asyncio.Event()
        self.commit_sent = False
        self.error_text = None
        return self.revision

    def transcript(self) -> str:
        if self.final_text:
            return self.final_text
        if self.draft_text:
            return self.draft_text
        parts = [self.segment_texts[idx] for idx in sorted(self.segment_texts) if self.segment_texts[idx]]
        return _normalize_transcript(" ".join(parts))

    def register_task(self, task: asyncio.Task) -> None:
        self.pending_tasks.add(task)
        task.add_done_callback(lambda finished: self.pending_tasks.discard(finished))

    async def wait_for_pending(self, timeout: Optional[float] = None) -> None:
        pending = list(self.pending_tasks)
        if not pending:
            return
        effective_timeout = timeout
        if effective_timeout is not None:
            effective_timeout = max(float(effective_timeout), _realtime_append_timeout_seconds())
        if effective_timeout is None:
            await asyncio.gather(*pending, return_exceptions=True)
            return
        if effective_timeout <= 0:
            return
        await asyncio.wait(pending, timeout=effective_timeout)

    def cancel_pending(self) -> None:
        for task in list(self.pending_tasks):
            task.cancel()
        self.pending_tasks.clear()

        listener = self.listener_task
        self.listener_task = None
        if listener:
            listener.cancel()

        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            try:
                asyncio.get_running_loop().create_task(websocket.close())
            except RuntimeError:
                pass

        self.final_event.set()

    async def _connect_websocket(self, url: str, headers: dict[str, str]) -> Any:
        import websockets

        try:
            return await websockets.connect(url, additional_headers=headers, max_size=16 * 1024 * 1024)
        except TypeError:
            return await websockets.connect(url, extra_headers=headers, max_size=16 * 1024 * 1024)

    async def _ensure_session(self) -> Any:
        if self.websocket is not None:
            return self.websocket

        issues = _openai_realtime_stt_issues()
        if issues:
            raise RuntimeError(issues[0])

        api_key = _openai_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        websocket = await self._connect_websocket(_realtime_ws_url(), headers)
        self.websocket = websocket
        self.listener_task = asyncio.create_task(self._listen(websocket))

        transcription_model = _realtime_transcription_model()
        transcription: dict[str, object] = {"model": transcription_model}
        language = os.getenv(APP_STT_LANGUAGE_ENV, "").strip()
        if language:
            transcription["language"] = language
        prompt = _known_terms_prompt()
        if prompt and transcription_model != "gpt-realtime-whisper":
            transcription["prompt"] = prompt

        input_config: dict[str, object] = {
            "format": {"type": "audio/pcm", "rate": REALTIME_STT_SAMPLE_RATE},
            "transcription": transcription,
            "turn_detection": None,
        }
        noise_reduction_type = _realtime_noise_reduction_type()
        if noise_reduction_type:
            input_config["noise_reduction"] = {"type": noise_reduction_type}

        await websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {"input": input_config},
                    },
                }
            )
        )
        return websocket

    async def _append_pending_pcm_locked(self, websocket: Any) -> None:
        for seq in sorted(self.pcm_chunks):
            if seq in self.appended_sequences:
                continue
            pcm24k = self.pcm_chunks.get(seq) or b""
            if not pcm24k:
                self.appended_sequences.add(seq)
                continue
            await websocket.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm24k).decode("utf-8"),
                    }
                )
            )
            self.appended_sequences.add(seq)

    async def preconnect(self) -> None:
        async with self.transcription_slots:
            await self._ensure_session()

    async def _close_session(self) -> None:
        websocket = self.websocket
        listener = self.listener_task
        self.websocket = None
        self.listener_task = None

        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass

        if listener and listener is not asyncio.current_task():
            listener.cancel()
            try:
                await listener
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _listen(self, websocket: Any) -> None:
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                event_type = str(data.get("type") or "")
                if event_type == "conversation.item.input_audio_transcription.delta":
                    delta = str(data.get("delta") or data.get("text") or "")
                    if delta:
                        self.draft_text = _normalize_transcript(f"{self.draft_text}{delta}")
                        self.state = "listening"
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    text = str(data.get("transcript") or data.get("text") or self.draft_text or "")
                    self.final_text = _normalize_transcript(text)
                    if self.final_text:
                        self.segment_texts[max(1, self.last_sequence)] = self.final_text
                    self.state = "ready"
                    self.final_event.set()
                elif event_type == "error":
                    error = data.get("error") or {}
                    if isinstance(error, dict):
                        self.error_text = redact_text(str(error.get("message") or error.get("type") or error))
                    else:
                        self.error_text = redact_text(str(error))
                    self.state = "error"
                    self.final_event.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            info = normalize_provider_error(exc, payload_kind="audio")
            self.error_text = f"{info.error_type}: {info.message}"
            self.state = "error"
            self.final_event.set()

    async def transcribe_chunk(
        self,
        *,
        audio_base64: Optional[str],
        mime_type: Optional[str],
        sequence: Optional[int],
        revision: Optional[int] = None,
    ) -> str:
        selection_issue = _voice_input_selection_issue()
        if selection_issue:
            raise RuntimeError(selection_issue)
        if not audio_base64:
            return self.transcript()

        active_revision = self.revision if revision is None else revision
        seq = int(sequence or (self.last_sequence + 1))
        mime = (mime_type or "").lower()
        if "wav" not in mime:
            raise RuntimeError("OpenAI Realtime desktop voice transcription expects audio/wav chunks")

        raw = base64.b64decode(audio_base64)
        pcm24k = _wav_bytes_to_realtime_pcm24k(raw)
        if active_revision != self.revision:
            return self.transcript()
        if not pcm24k:
            return self.transcript()

        self.pcm_chunks[seq] = pcm24k
        self.last_sequence = max(self.last_sequence, seq)

        async with self.transcription_slots:
            websocket = await self._ensure_session()
            await self._append_pending_pcm_locked(websocket)
            self.state = "listening"

        return self.transcript()

    async def final_transcript(self, *, fast: bool = False) -> str:
        del fast
        selection_issue = _voice_input_selection_issue()
        if selection_issue:
            raise RuntimeError(selection_issue)
        if self.last_sequence <= 0:
            return ""

        async with self.transcription_slots:
            websocket = await self._ensure_session()
            await self._append_pending_pcm_locked(websocket)
            if not self.commit_sent:
                self.final_event.clear()
                await websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                self.commit_sent = True

        try:
            await asyncio.wait_for(self.final_event.wait(), timeout=_realtime_final_timeout_seconds())
        except asyncio.TimeoutError:
            pass
        finally:
            await self._close_session()

        text = self.transcript()
        if not text and self.error_text:
            raise RuntimeError(f"OpenAI Realtime voice transcription failed: {self.error_text}")
        return text


def new_voice_draft_state() -> VoiceDraftState | OpenAIRealtimeVoiceDraftState:
    if _stt_backend() == OPENAI_REALTIME_STT_BACKEND:
        return OpenAIRealtimeVoiceDraftState()
    return VoiceDraftState()
