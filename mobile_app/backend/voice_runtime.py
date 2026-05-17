from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import time
import wave
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Dict, Optional, Set

from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_LANGUAGE,
    DEFAULT_RELEASE_TAG,
    WhisperFixture,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    models_root,
    output_root,
    recommended_thread_count,
    runtime_root,
    run_whisper_cli_once,
    transcript_confidence_from_output_json,
    write_pcm16_mono_wav,
)
from mobile_app.backend.hebrew_transformers_runtime import (
    looks_repetitive as hebrew_looks_repetitive,
    transcribe_wav_bytes as transcribe_hebrew_wav_bytes,
)
from mobile_app.backend.voice_pack_manager import (
    VOICE_ENGINE_ENGLISH,
    VOICE_ENGINE_HEBREW,
    get_english_pack_status,
    get_hebrew_pack_status,
    hebrew_pack_runtime_dir,
    install_voice_pack,
)
from shared.live_config import get_live_config

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
APP_STT_BINARY_FLAVOR_ENV = "EMPLO_APP_STT_BINARY_FLAVOR"
APP_STT_CONTEXT_CHARS_ENV = "EMPLO_APP_STT_CONTEXT_CHARS"
APP_STT_DRAFT_INTERVAL_MS_ENV = "EMPLO_APP_STT_DRAFT_INTERVAL_MS"
APP_STT_DRAFT_MIN_MS_ENV = "EMPLO_APP_STT_DRAFT_MIN_MS"
APP_STT_DRAFT_CONFIDENCE_ENV = "EMPLO_APP_STT_DRAFT_CONFIDENCE"
APP_STT_DRAFT_MIN_CHARS_ENV = "EMPLO_APP_STT_DRAFT_MIN_CHARS"
APP_STT_KNOWN_TERMS_ENV = "EMPLO_APP_STT_KNOWN_TERMS"
APP_STT_HEBREW_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_MODEL_REPO"
APP_STT_HEBREW_DRAFT_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_DRAFT_MODEL_REPO"
APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
APP_STT_HEBREW_LANGUAGE_ENV = "EMPLO_APP_STT_HEBREW_LANGUAGE"
APP_STT_HEBREW_CPU_THREADS_ENV = "EMPLO_APP_STT_HEBREW_CPU_THREADS"
APP_TTS_ENABLED_ENV = "EMPLO_APP_TTS_ENABLED"
APP_TTS_MODEL_ENV = "EMPLO_APP_TTS_MODEL"
APP_TTS_VOICE_ENV = "EMPLO_APP_TTS_VOICE"
APP_TTS_FORMAT_ENV = "EMPLO_APP_TTS_FORMAT"
APP_TTS_SPEED_ENV = "EMPLO_APP_TTS_SPEED"
APP_TTS_INSTRUCTIONS_ENV = "EMPLO_APP_TTS_INSTRUCTIONS"
DEFAULT_STT_BACKEND = "local_whisper"
OPENAI_STT_MODEL = "gpt-4o-mini-transcribe"
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
DEFAULT_KNOWN_TERMS = ("telegram_agent.py", ".env")
DEFAULT_HEBREW_LANGUAGE = "he"
HEBREW_SEQUENCE_MS = 1200
HEBREW_DRAFT_INTERVAL_MS = 1200
HEBREW_DRAFT_MIN_MS = 1400
HEBREW_DRAFT_CONFIDENCE = 0.82
HEBREW_DRAFT_MIN_CHARS = 4
HEBREW_FINAL_DISCARD_CONFIDENCE = 0.35
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "ash"
DEFAULT_TTS_FORMAT = "mp3"
MAX_TTS_CHARS = 4000

_stt_client: Optional[OpenAI] = None
_whisper_cli_cache: Optional[Path] = None
_model_cache: dict[str, Path] = {}
_WHISPER_ASSET_DIRS = {
    "plain": "whisper-bin-x64",
    "blas": "whisper-blas-bin-x64",
    "cublas-11.8": "whisper-cublas-11.8.0-bin-x64",
    "cublas-12.4": "whisper-cublas-12.4.0-bin-x64",
}


def _get_stt_client() -> Optional[OpenAI]:
    global _stt_client
    if _stt_client is not None:
        return _stt_client

    if OpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    _stt_client = OpenAI(api_key=api_key)
    return _stt_client


def _voice_engine_selection() -> Dict[str, object]:
    config = get_live_config(runtime_root() / "config.json")
    english_requested = bool(config.get("voice.packs.english_local.requested", True))
    hebrew_requested = bool(config.get("voice.packs.hebrew_local.requested", False))
    default_engine = str(config.get("voice.default_engine", VOICE_ENGINE_ENGLISH) or VOICE_ENGINE_ENGLISH).strip().lower()
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
    return {
        "final_seconds": round(time.perf_counter() - start, 3),
        "draft_seconds": 0.0,
    }


def _voice_input_selection_issue() -> Optional[str]:
    default_engine = _selected_voice_engine()
    if default_engine == VOICE_ENGINE_NONE:
        return "Voice input is disabled in setup and settings."
    if default_engine == VOICE_ENGINE_HEBREW:
        issues = _hebrew_support_issues(require_model=True)
        return issues[0] if issues else None
    return None


def get_voice_runtime_status() -> Dict[str, object]:
    issues: list[str] = []
    input_issues: list[str] = []
    stt_backend = _stt_backend()
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

    if default_engine == VOICE_ENGINE_NONE:
        input_issues.append("Voice input is disabled in setup and settings.")
    elif default_engine == VOICE_ENGINE_HEBREW:
        input_issues.extend(hebrew_pack_issues)
    elif stt_backend == "openai":
        if OpenAI is None:
            input_issues.append("The `openai` Python package is not installed, so app voice transcription is unavailable.")
        elif not os.getenv("OPENAI_API_KEY"):
            input_issues.append("OPENAI_API_KEY is not configured, so app voice transcription is unavailable.")
    else:
        input_issues.extend(english_pack_issues)

    tts_enabled = os.getenv(APP_TTS_ENABLED_ENV, "1").strip().lower() not in {"0", "false", "off", "no"}
    if tts_enabled and OpenAI is None:
        issues.append("Assistant audio is enabled but the `openai` Python package is missing.")
    issues = [*input_issues, *issues]

    return {
        "ok": not issues,
        "input_ok": not input_issues,
        "issues": issues,
        "stt_backend": stt_backend,
        "stt_model": (
            str(hebrew_pack_status.get("model_dir") or "")
            if default_engine == VOICE_ENGINE_HEBREW
            else _local_model_name()
            if stt_backend != "openai"
            else os.getenv(APP_STT_MODEL_ENV, OPENAI_STT_MODEL)
        ),
        "draft_model": (
            str(hebrew_pack_status.get("model_dir") or "")
            if default_engine == VOICE_ENGINE_HEBREW
            else None
            if stt_backend == "openai"
            else _local_draft_model_name()
        ),
        "binary_flavor": (
            None
            if default_engine == VOICE_ENGINE_HEBREW or stt_backend == "openai"
            else _local_binary_flavor()
        ),
        "tts_enabled": tts_enabled,
        "selected_engine": default_engine,
        "english_requested": english_requested,
        "hebrew_requested": hebrew_requested,
        "english_pack_ready": english_pack_ready,
        "hebrew_pack_ready": hebrew_pack_ready,
        "english_pack_status": english_pack_status,
        "hebrew_pack_status": hebrew_pack_status,
        "hebrew_model_root": str(hebrew_pack_status.get("model_dir") or ""),
        "hebrew_draft_model_root": str(hebrew_pack_status.get("model_dir") or ""),
    }


def _normalize_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_tts_text(text: str) -> str:
    normalized = _normalize_transcript(text)
    if len(normalized) <= MAX_TTS_CHARS:
        return normalized
    clipped = normalized[:MAX_TTS_CHARS].rsplit(" ", 1)[0].strip()
    return clipped or normalized[:MAX_TTS_CHARS]


def _stt_backend() -> str:
    return (os.getenv(APP_STT_BACKEND_ENV, DEFAULT_STT_BACKEND).strip().lower() or DEFAULT_STT_BACKEND)


def _local_model_name() -> str:
    return os.getenv(APP_STT_MODEL_ENV, DEFAULT_LOCAL_STT_MODEL).strip() or DEFAULT_LOCAL_STT_MODEL


def _local_draft_model_name() -> str:
    return os.getenv(APP_STT_DRAFT_MODEL_ENV, DEFAULT_LOCAL_DRAFT_MODEL).strip() or DEFAULT_LOCAL_DRAFT_MODEL


def _local_binary_flavor() -> str:
    return os.getenv(APP_STT_BINARY_FLAVOR_ENV, DEFAULT_BINARY_FLAVOR).strip() or DEFAULT_BINARY_FLAVOR


def _expected_local_whisper_cli() -> Path:
    asset_dir = _WHISPER_ASSET_DIRS.get(_local_binary_flavor(), _local_binary_flavor())
    return models_root().parent / asset_dir / "Release" / "whisper-cli.exe"


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


def _resolve_whisper_cli() -> Path:
    global _whisper_cli_cache
    if _whisper_cli_cache is None:
        _whisper_cli_cache = ensure_prebuilt_whisper_cpp(
            release_tag=DEFAULT_RELEASE_TAG,
            flavor=_local_binary_flavor(),
        )
    return _whisper_cli_cache


def _resolve_model(model_name: str) -> Path:
    if model_name not in _model_cache:
        _model_cache[model_name] = ensure_ggml_model(model_name)
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
        raise RuntimeError("NumPy is required to resample Hebrew voice audio locally")
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

    result = client.audio.transcriptions.create(**kwargs)
    if isinstance(result, str):
        return _normalize_transcript(result)
    return _normalize_transcript(getattr(result, "text", ""))


def synthesize_assistant_audio(text: str) -> Optional[Dict[str, object]]:
    if os.getenv(APP_TTS_ENABLED_ENV, "1").strip().lower() in {"0", "false", "off", "no"}:
        return None

    client = _get_stt_client()
    normalized = _normalize_tts_text(text)
    if not client or not normalized:
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

    result = client.audio.speech.create(**kwargs)
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
        "text": normalized,
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
    state: str = "idle"
    revision: int = 0
    pending_tasks: Set[asyncio.Task] = field(default_factory=set, repr=False)
    transcription_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1), repr=False)

    def reset(self) -> int:
        self.revision += 1
        self.segment_texts.clear()
        self.wav_chunks.clear()
        self.last_sequence = 0
        self.last_draft_sequence = 0
        self.sample_rate = None
        self.draft_text = ""
        self.final_text = ""
        self.state = "idle"
        return self.revision

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
            return HEBREW_DRAFT_MIN_MS
        return max(300, _int_env(APP_STT_DRAFT_MIN_MS_ENV, DEFAULT_DRAFT_MIN_MS))

    def _draft_interval_ms(self) -> int:
        if _selected_voice_engine() == VOICE_ENGINE_HEBREW:
            return HEBREW_DRAFT_INTERVAL_MS
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

    async def wait_for_pending(self) -> None:
        pending = list(self.pending_tasks)
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)

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
        if selected_engine == VOICE_ENGINE_HEBREW or _stt_backend() != "openai":
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

            min_confidence = self._draft_confidence_threshold()
            min_chars = self._draft_min_chars()
            if selected_engine == VOICE_ENGINE_HEBREW and hebrew_looks_repetitive(text):
                text = self.draft_text or ""
            if text and len(text) >= min_chars and (confidence is None or confidence >= min_confidence):
                self.draft_text = text
                self.segment_texts[seq] = text
                self.last_draft_sequence = seq
            return self.transcript()

        async with self.transcription_slots:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, _transcribe_audio_bytes, raw, mime_type)
        if active_revision != self.revision:
            return self.transcript()

        self.segment_texts[seq] = text
        self.last_sequence = max(self.last_sequence, seq)
        return self.transcript()

    async def final_transcript(self) -> str:
        selection_issue = _voice_input_selection_issue()
        if selection_issue:
            raise RuntimeError(selection_issue)
        selected_engine = _selected_voice_engine()
        if selected_engine != VOICE_ENGINE_HEBREW and _stt_backend() == "openai":
            return self.transcript()

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
                        model_name=_local_model_name(),
                        sequence=max(1, self.last_sequence),
                        revision=active_revision,
                        initial_prompt=self._prompt(),
                    ),
                )
        if active_revision != self.revision:
            return self.transcript()

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
        return self.transcript()
