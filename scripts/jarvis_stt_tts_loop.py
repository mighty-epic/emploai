from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import math
import os
import queue
import sys
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.bundled_python_runtime import configure_bundled_python_dependencies


configure_bundled_python_dependencies(REPO_ROOT)

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None

try:
    import webrtcvad
except ImportError:  # pragma: no cover
    webrtcvad = None


from app_backend.whisper_cpp_runtime import (  # noqa: E402
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_LANGUAGE,
    WhisperFixture,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    output_root,
    pcm16le_dbfs,
    recommended_thread_count,
    run_whisper_cli_once,
    write_pcm16_mono_wav,
)


DEFAULT_STT_MODEL = "base.en-q5_1"
DEFAULT_STT_MODE = "whisper-cli"
DEFAULT_TTS_LANGUAGE = "english"
DEFAULT_TTS_VOICE = "alba"
DEFAULT_GATE_DBFS = -37.5
DEFAULT_ATTACK_MS = 1
DEFAULT_RELEASE_MS = 650
DEFAULT_PREROLL_MS = 350
DEFAULT_MIN_MS = 0
DEFAULT_MAX_MS = 8000
DEFAULT_FRAME_MS = 30
DEFAULT_INPUT_SAMPLE_RATE = 16000
DEFAULT_SPEECH_DETECTOR = "vad"
DEFAULT_VAD_MODE = 2
DEFAULT_VAD_MIN_DBFS = -62.0
DESKTOP_APP_VOICE_CHUNK_MS = 850
DEFAULT_STT_PAD_MS = 800
DEFAULT_BARGE_IN_GATE_DBFS = DEFAULT_GATE_DBFS
DEFAULT_BARGE_IN_ATTACK_MS = 60
DEFAULT_TTS_ECHO_COOLDOWN_MS = 120
DEFAULT_ECHO_MARGIN_DB = 3.0
POCKET_TTS_SITE_PACKAGES_ENV = "EMPLOAI_POCKET_TTS_SITE_PACKAGES"
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_STT_PROMPT = (
    "Transcribe the user's spoken English command or conversation exactly. "
    "Assistant names may include Jarvis and EmploAI. "
    "Preserve app names, file names, numbers, and short corrections literally."
)
SPEECH_CONVERSATION_SYSTEM_PROMPT = (
    "You are a voice conversation assistant in a local speech loop. "
    "Reply in short natural spoken sentences. "
    "Do not use bullet points, numbered lists, markdown, tables, code blocks, headings, or symbols that sound awkward aloud. "
    "Keep most replies under two sentences. "
    "If the user asks for something that would require tools, say briefly that this prototype is conversation only."
)


@dataclass
class RecordedUtterance:
    path: Path
    duration_seconds: float
    peak_dbfs: float
    capture_seconds: float
    sequence: int = 0
    queued_at: float = 0.0


class PlaybackState:
    def __init__(self) -> None:
        self.turn_busy = threading.Event()
        self.speaking = threading.Event()
        self.cancel_tts = threading.Event()
        self._lock = threading.Lock()
        self._active_turn_id: Optional[int] = None
        self._interrupted_turn_ids: set[int] = set()
        self._started_at = 0.0
        self._tts_dbfs = -120.0
        self._echo_floor_dbfs: Optional[float] = None
        self._barge_in_reason = ""

    def start_turn(self, turn_id: int) -> None:
        with self._lock:
            self._active_turn_id = int(turn_id)
            self._interrupted_turn_ids.discard(int(turn_id))
            self._barge_in_reason = ""
            self.cancel_tts.clear()
            self.turn_busy.set()

    def finish_turn(self, turn_id: int) -> None:
        with self._lock:
            turn_id = int(turn_id)
            if self._active_turn_id == turn_id:
                self._active_turn_id = None
                self.turn_busy.clear()
            self._interrupted_turn_ids.discard(turn_id)

    def is_turn_interrupted(self, turn_id: int) -> bool:
        with self._lock:
            return int(turn_id) in self._interrupted_turn_ids

    def start_speaking(self) -> None:
        with self._lock:
            self._started_at = time.perf_counter()
            self._tts_dbfs = -120.0
            self._echo_floor_dbfs = None
            self._barge_in_reason = ""
            self.cancel_tts.clear()
            self.speaking.set()

    def stop_speaking(self) -> None:
        with self._lock:
            self.speaking.clear()
            self._started_at = 0.0
            self._tts_dbfs = -120.0
            self._echo_floor_dbfs = None

    def update_tts_level(self, dbfs: float) -> None:
        with self._lock:
            self._tts_dbfs = float(dbfs)

    def observe_mic_echo(self, dbfs: float) -> None:
        with self._lock:
            if not self.speaking.is_set():
                return
            level = float(dbfs)
            if self._echo_floor_dbfs is None:
                self._echo_floor_dbfs = level
            else:
                # Track the louder recent echo envelope, but let it decay slowly.
                self._echo_floor_dbfs = max(level, self._echo_floor_dbfs - 0.6)

    def request_interrupt(self, reason: str) -> None:
        with self._lock:
            active_turn_id = self._active_turn_id
            if active_turn_id is not None:
                self._interrupted_turn_ids.add(active_turn_id)
            self._barge_in_reason = reason
            self.cancel_tts.set()

    def request_barge_in(self, reason: str) -> None:
        self.request_interrupt(reason)

    def snapshot(self) -> dict[str, float | bool | int | str | None]:
        with self._lock:
            started_at = self._started_at
            active_turn_id = self._active_turn_id
            return {
                "turn_busy": self.turn_busy.is_set(),
                "active_turn_id": active_turn_id,
                "turn_interrupted": (
                    active_turn_id in self._interrupted_turn_ids
                    if active_turn_id is not None
                    else False
                ),
                "speaking": self.speaking.is_set(),
                "cancelled": self.cancel_tts.is_set(),
                "started_seconds_ago": (
                    max(0.0, time.perf_counter() - started_at)
                    if started_at
                    else None
                ),
                "tts_dbfs": self._tts_dbfs,
                "echo_floor_dbfs": self._echo_floor_dbfs,
                "barge_in_reason": self._barge_in_reason,
            }


def _float_audio_dbfs(audio) -> float:
    try:
        squared = audio.astype("float32", copy=False) ** 2
        rms = float(squared.mean()) ** 0.5
    except Exception:
        return -120.0
    if rms <= 0.0:
        return -120.0
    return 20.0 * math.log10(max(rms, 1e-6))


class SpeechActivityDetector:
    _SUPPORTED_RATES = {8000, 16000, 32000, 48000}
    _SUPPORTED_FRAME_MS = {10, 20, 30}

    def __init__(
        self,
        *,
        detector: str,
        sample_rate: int,
        frame_ms: int,
        vad_mode: int,
        min_dbfs: float,
    ) -> None:
        self.detector = detector.strip().lower()
        self.sample_rate = int(sample_rate)
        self.frame_ms = int(frame_ms)
        self.min_dbfs = float(min_dbfs)
        self.vad_mode = max(0, min(3, int(vad_mode)))
        self._vad = None
        self.fallback_reason = ""

        if self.detector != "vad":
            self.detector = "level"
            return
        if webrtcvad is None:
            self.detector = "level"
            self.fallback_reason = "webrtcvad is not installed"
            return
        if self.sample_rate not in self._SUPPORTED_RATES:
            self.detector = "level"
            self.fallback_reason = f"sample_rate={self.sample_rate} is not supported by WebRTC VAD"
            return
        if self.frame_ms not in self._SUPPORTED_FRAME_MS:
            self.detector = "level"
            self.fallback_reason = f"frame_ms={self.frame_ms} is not supported by WebRTC VAD"
            return

        self._vad = webrtcvad.Vad(self.vad_mode)
        self.detector = "vad"

    @property
    def label(self) -> str:
        if self.detector == "vad":
            return (
                f"webrtcvad(mode={self.vad_mode}, "
                f"min_dbfs={self.min_dbfs:.1f})"
            )
        if self.fallback_reason:
            return f"level(fallback: {self.fallback_reason})"
        return "level"

    def is_speech(self, frame: bytes, *, level_dbfs: float, gate_dbfs: float) -> bool:
        if self.detector != "vad" or self._vad is None:
            return float(level_dbfs) >= float(gate_dbfs)
        if float(level_dbfs) < self.min_dbfs:
            return False
        try:
            return bool(self._vad.is_speech(frame, self.sample_rate))
        except Exception:
            return float(level_dbfs) >= float(gate_dbfs)


def _candidate_pocket_tts_site_packages() -> list[Path]:
    candidates: list[Path] = []
    configured = os.getenv(POCKET_TTS_SITE_PACKAGES_ENV, "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    # Convenience for the local benchmark install used while validating Kyutai.
    temp_root = Path(os.getenv("TEMP", str(Path.home()))) / "emploai-pocket-tts-bench"
    candidates.append(temp_root / ".venv" / "Lib" / "site-packages")
    return candidates


def ensure_pocket_tts_importable(extra_site_packages: Optional[str] = None) -> None:
    if extra_site_packages:
        candidate = Path(extra_site_packages).expanduser().resolve()
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    for candidate in _candidate_pocket_tts_site_packages():
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    try:
        import pocket_tts  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Pocket TTS is not importable. Install it with `py -m pip install pocket-tts` "
            f"or set {POCKET_TTS_SITE_PACKAGES_ENV} to a site-packages folder containing pocket_tts."
        ) from exc


class PocketTtsSpeaker:
    def __init__(
        self,
        *,
        language: str,
        voice: str,
        quantize: bool,
        site_packages: Optional[str],
    ) -> None:
        ensure_pocket_tts_importable(site_packages)
        from pocket_tts import TTSModel

        if sd is None:
            raise RuntimeError("sounddevice is required for streaming Pocket TTS playback.")

        start = time.perf_counter()
        self.model = TTSModel.load_model(language=language, quantize=quantize)
        self.load_seconds = time.perf_counter() - start
        start = time.perf_counter()
        self.voice_state = self.model.get_state_for_audio_prompt(voice)
        self.voice_state_seconds = time.perf_counter() - start
        self.sample_rate = int(self.model.sample_rate)

    def speak(self, text: str) -> dict[str, float | int]:
        return self.speak_streaming(text, playback_state=None)

    def speak_streaming(
        self,
        text: str,
        *,
        playback_state: Optional[PlaybackState],
    ) -> dict[str, float | int | bool]:
        text = " ".join(str(text or "").split())
        if not text:
            return {
                "chunks": 0,
                "first_chunk_seconds": 0.0,
                "total_seconds": 0.0,
                "audio_seconds": 0.0,
                "interrupted": False,
            }

        if sd is None:
            raise RuntimeError("sounddevice is required for streaming Pocket TTS playback.")

        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
        )
        stream.start()
        if playback_state is not None:
            playback_state.start_speaking()
        start = time.perf_counter()
        first_chunk_seconds: Optional[float] = None
        chunks = 0
        samples_written = 0
        interrupted = False
        try:
            for chunk in self.model.generate_audio_stream(self.voice_state, text):
                if playback_state is not None and playback_state.cancel_tts.is_set():
                    interrupted = True
                    print(f"[barge-in] TTS cancelled before chunk {chunks + 1}", flush=True)
                    break
                if first_chunk_seconds is None:
                    first_chunk_seconds = time.perf_counter() - start
                audio = chunk.detach().cpu().numpy()
                audio = audio.clip(-1.0, 1.0)
                if playback_state is not None:
                    playback_state.update_tts_level(_float_audio_dbfs(audio))
                stream.write(audio.astype("float32", copy=False).reshape(-1, 1))
                chunks += 1
                samples_written += int(audio.size)
                if playback_state is not None and playback_state.cancel_tts.is_set():
                    interrupted = True
                    print(f"[barge-in] TTS cancelled after chunk {chunks}", flush=True)
                    break
        finally:
            stream.stop()
            stream.close()
            if playback_state is not None:
                playback_state.stop_speaking()

        total_seconds = time.perf_counter() - start
        return {
            "chunks": chunks,
            "first_chunk_seconds": round(first_chunk_seconds or 0.0, 3),
            "total_seconds": round(total_seconds, 3),
            "audio_seconds": round(samples_written / float(self.sample_rate), 3),
            "interrupted": interrupted,
        }


class ConversationModel:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        temperature: float,
        max_history_turns: int,
        timeout: float,
    ) -> None:
        self.provider = provider.strip().lower()
        self.model = model.strip()
        self.temperature = float(temperature)
        self.max_history_turns = max(0, int(max_history_turns))
        self.timeout = float(timeout)
        self.messages: list[dict[str, str]] = [
            {"role": "system", "content": SPEECH_CONVERSATION_SYSTEM_PROMPT}
        ]
        self.client = None

        if self.provider == "none":
            return
        if self.provider != "openai":
            raise RuntimeError(f"Unsupported LLM provider for this prototype: {provider}")

        _load_dotenv_if_available()
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The `openai` package is required for --llm-provider openai.") from exc
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not configured for the conversational loop.")
        self.client = OpenAI(timeout=self.timeout)

    def _trim_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if self.max_history_turns <= 0:
            return messages[:1]
        retained = messages[:1]
        conversation = messages[1:]
        max_messages = self.max_history_turns * 2
        retained.extend(conversation[-max_messages:])
        return retained

    def _trim_history(self) -> None:
        self.messages = self._trim_messages(self.messages)

    def commit_exchange(self, transcript: str, reply_text: str) -> None:
        if self.provider == "none":
            return
        text = " ".join(str(transcript or "").split()).strip()
        reply_text = _speech_safe_text(reply_text)
        if not text or not reply_text:
            return
        self.messages.extend(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply_text},
            ]
        )
        self._trim_history()

    def reply(self, transcript: str, *, commit: bool = True) -> tuple[str, dict[str, object]]:
        text = " ".join(str(transcript or "").split()).strip()
        if not text:
            return "I did not catch that.", {"provider": self.provider, "model": self.model, "skipped": True}

        if self.provider == "none":
            return simple_reply(text), {"provider": "none", "model": "none", "skipped": True}

        request_messages = self._trim_messages(self.messages + [{"role": "user", "content": text}])
        start = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=request_messages,
            temperature=self.temperature,
            max_tokens=90,
        )
        elapsed = time.perf_counter() - start
        reply_text = str(response.choices[0].message.content or "").strip()
        reply_text = _speech_safe_text(reply_text)
        if not reply_text:
            reply_text = "I am here."
        if commit:
            self.messages = self._trim_messages(request_messages + [{"role": "assistant", "content": reply_text}])

        usage = getattr(response, "usage", None)
        usage_payload = {}
        if usage is not None:
            usage_payload = {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
        return reply_text, {
            "provider": self.provider,
            "model": self.model,
            "seconds": round(elapsed, 3),
            **usage_payload,
        }


def _default_input_device_index() -> Optional[int]:
    for device in list_input_devices():
        if device.get("is_default"):
            return int(device["index"])
    return None


def list_input_devices() -> list[dict[str, object]]:
    if sd is None:
        raise RuntimeError("sounddevice is not installed, so microphone device listing is unavailable.")

    try:
        default_input = sd.default.device[0]
    except Exception:
        default_input = None

    devices: list[dict[str, object]] = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0) or 0) <= 0:
            continue
        devices.append(
            {
                "index": index,
                "name": str(info.get("name") or f"Input {index}"),
                "max_input_channels": int(info.get("max_input_channels") or 0),
                "default_sample_rate": int(float(info.get("default_samplerate") or 16000)),
                "is_default": default_input == index,
            }
        )
    return devices


def _frame_count(sample_rate: int, frame_ms: int) -> int:
    return max(1, int(round(sample_rate * frame_ms / 1000.0)))


def _wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _load_dotenv_if_available() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def _speech_safe_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    for prefix in ("- ", "* ", "1. ", "2. ", "3. "):
        cleaned = cleaned.replace(prefix, "")
    return cleaned


def _normalize_wav_for_whisper(path: Path, *, output_dir: Path, pad_ms: int = 0) -> Path:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
        minimum_frames = max(0, int(frame_rate * max(0, pad_ms) / 1000.0)) if frame_rate > 0 else 0
        if channels == 1 and sample_width == 2 and frame_rate > 0 and frame_count >= minimum_frames:
            return path
    except wave.Error:
        pass

    try:
        import numpy as np
        from scipy.io import wavfile
    except ImportError as exc:
        raise RuntimeError(
            f"{path} is not a PCM16 mono WAV, and scipy/numpy are not available to normalize it."
        ) from exc

    sample_rate, audio = wavfile.read(str(path))
    array = np.asarray(audio)
    if array.ndim > 1:
        array = array.mean(axis=1)
    if np.issubdtype(array.dtype, np.floating):
        array = np.clip(array, -1.0, 1.0)
        pcm16 = (array * 32767.0).astype("<i2")
    elif array.dtype == np.int16:
        pcm16 = array.astype("<i2", copy=False)
    else:
        info = np.iinfo(array.dtype)
        normalized = array.astype("float32") / max(abs(float(info.min)), float(info.max))
        pcm16 = (np.clip(normalized, -1.0, 1.0) * 32767.0).astype("<i2")

    minimum_samples = max(0, int(int(sample_rate) * max(0, pad_ms) / 1000.0))
    if pcm16.size < minimum_samples:
        pcm16 = np.pad(pcm16, (0, minimum_samples - pcm16.size), mode="constant")

    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / f"{path.stem}_pcm16_mono.wav"
    with wave.open(str(normalized_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm16.tobytes())
    return normalized_path


def _read_pcm16_mono_wav(path: Path) -> tuple[int, bytes]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or sample_width != 2:
        raise RuntimeError(f"Expected PCM16 mono WAV after normalization, got channels={channels} width={sample_width}")
    return frame_rate, frames


def _pcm16_mono_wav_bytes(*, sample_rate: int, frames: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(frames)
    return buffer.getvalue()


def record_gated_utterance(
    *,
    output_dir: Path,
    device_index: Optional[int],
    input_sample_rate: Optional[int],
    gate_dbfs: float,
    attack_ms: int,
    release_ms: int,
    preroll_ms: int,
    min_ms: int,
    max_ms: int,
    frame_ms: int,
    playback_state: Optional[PlaybackState] = None,
    barge_in_enabled: bool = True,
    barge_in_gate_dbfs: float = DEFAULT_BARGE_IN_GATE_DBFS,
    barge_in_attack_ms: int = DEFAULT_BARGE_IN_ATTACK_MS,
    tts_echo_cooldown_ms: int = DEFAULT_TTS_ECHO_COOLDOWN_MS,
    echo_margin_db: float = DEFAULT_ECHO_MARGIN_DB,
    speech_detector_name: str = DEFAULT_SPEECH_DETECTOR,
    vad_mode: int = DEFAULT_VAD_MODE,
    vad_min_dbfs: float = DEFAULT_VAD_MIN_DBFS,
) -> Optional[RecordedUtterance]:
    if sd is None:
        raise RuntimeError("sounddevice is not installed, so microphone capture is unavailable.")

    if device_index is None:
        device_index = _default_input_device_index()
    if device_index is None:
        raise RuntimeError("No microphone input device was found.")

    device_info = sd.query_devices(int(device_index), "input")
    default_sample_rate = int(float(device_info.get("default_samplerate") or 16000))
    sample_rate = int(input_sample_rate or default_sample_rate)
    frame_samples = _frame_count(sample_rate, frame_ms)
    attack_frames = max(1, math.ceil(attack_ms / frame_ms))
    barge_in_attack_frames = max(1, math.ceil(barge_in_attack_ms / frame_ms))
    release_frames = max(1, math.ceil(release_ms / frame_ms))
    preroll_frames = max(1, math.ceil(preroll_ms / frame_ms))
    min_frames = max(0, math.ceil(min_ms / frame_ms))
    max_frames = max(min_frames, math.ceil(max_ms / frame_ms))

    try:
        stream = sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_samples,
            device=int(device_index),
            channels=1,
            dtype="int16",
        )
    except Exception:
        if sample_rate == default_sample_rate:
            raise
        print(
            f"[capture] sample_rate={sample_rate} failed; falling back to device default {default_sample_rate}Hz.",
            flush=True,
        )
        sample_rate = default_sample_rate
        frame_samples = _frame_count(sample_rate, frame_ms)
        stream = sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_samples,
            device=int(device_index),
            channels=1,
            dtype="int16",
        )
    speech_detector = SpeechActivityDetector(
        detector=speech_detector_name,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        vad_mode=vad_mode,
        min_dbfs=vad_min_dbfs,
    )
    stream.start()
    print(
        f"Listening on [{device_index}] {device_info.get('name')} "
        f"at {sample_rate} Hz. speech_detector={speech_detector.label}. "
        f"Energy floor/gate {gate_dbfs:.1f} dBFS."
    )
    preroll: deque[bytes] = deque(maxlen=preroll_frames)
    recording = False
    recorded_frames: list[bytes] = []
    above_frames = 0
    below_frames = 0
    voiced_frames = 0
    peak_dbfs = -120.0
    started_at = time.perf_counter()
    last_level_log_at = 0.0
    capture_started_at: Optional[float] = None

    try:
        while True:
            data, overflowed = stream.read(frame_samples)
            if overflowed:
                print("Microphone input overflowed; continuing.")
            frame = bytes(data)
            level = pcm16le_dbfs(frame)
            peak_dbfs = max(peak_dbfs, level)
            now = time.perf_counter()
            playback_snapshot = playback_state.snapshot() if playback_state is not None else {}
            assistant_speaking = bool(playback_snapshot.get("speaking"))
            turn_busy = bool(playback_snapshot.get("turn_busy"))
            interrupt_context = assistant_speaking or turn_busy
            base_interrupt_gate_dbfs = min(float(gate_dbfs), float(barge_in_gate_dbfs))
            effective_gate_dbfs = gate_dbfs
            gate_mode = "listen"
            speech_frame = speech_detector.is_speech(
                frame,
                level_dbfs=level,
                gate_dbfs=gate_dbfs,
            )
            above_threshold = speech_frame
            if assistant_speaking:
                if not barge_in_enabled:
                    gate_mode = "tts_ignore"
                    above_threshold = False
                    if playback_state is not None:
                        playback_state.observe_mic_echo(level)
                else:
                    gate_mode = "barge"
                    since_started = float(playback_snapshot.get("started_seconds_ago") or 0.0)
                    echo_floor = playback_snapshot.get("echo_floor_dbfs")
                    if since_started * 1000.0 < tts_echo_cooldown_ms:
                        effective_gate_dbfs = base_interrupt_gate_dbfs
                        above_threshold = False
                        if playback_state is not None:
                            playback_state.observe_mic_echo(level)
                    else:
                        speech_frame = speech_detector.is_speech(
                            frame,
                            level_dbfs=level,
                            gate_dbfs=base_interrupt_gate_dbfs,
                        )
                        echo_threshold = (
                            float(echo_floor) + float(echo_margin_db)
                            if echo_floor is not None
                            else base_interrupt_gate_dbfs
                        )
                        effective_gate_dbfs = max(base_interrupt_gate_dbfs, echo_threshold)
                        above_threshold = speech_frame and level >= effective_gate_dbfs
                        if not above_threshold and playback_state is not None:
                            playback_state.observe_mic_echo(level)
            elif turn_busy and barge_in_enabled:
                gate_mode = "interrupt"
                effective_gate_dbfs = base_interrupt_gate_dbfs
                speech_frame = speech_detector.is_speech(
                    frame,
                    level_dbfs=level,
                    gate_dbfs=effective_gate_dbfs,
                )
                above_threshold = speech_frame

            if not recording:
                preroll.append(frame)
                above_frames = above_frames + 1 if above_threshold else 0
                if now - last_level_log_at >= 1.0:
                    print(
                        f"[mic] level={level:.1f} dBFS peak={peak_dbfs:.1f} "
                        f"gate={effective_gate_dbfs:.1f} speech={int(speech_frame)} mode={gate_mode} waiting",
                        flush=True,
                    )
                    last_level_log_at = now
                required_attack_frames = barge_in_attack_frames if interrupt_context else attack_frames
                if above_frames >= required_attack_frames:
                    recording = True
                    capture_started_at = now
                    recorded_frames = list(preroll)
                    voiced_frames = above_frames
                    below_frames = 0
                    if interrupt_context and playback_state is not None and barge_in_enabled:
                        active_turn_id = playback_snapshot.get("active_turn_id")
                        reason = (
                            f"mic={level:.1f}dBFS required={effective_gate_dbfs:.1f}dBFS "
                            f"attack={barge_in_attack_ms}ms active_turn={active_turn_id}"
                        )
                        playback_state.request_interrupt(reason)
                        context = "tts playback" if assistant_speaking else "assistant turn"
                        print(f"[interrupt] user speech detected during {context}; {reason}", flush=True)
                    print(f"[capture] gate opened at {level:.1f} dBFS mode={gate_mode}", flush=True)
                elif now - started_at > 60:
                    print("No speech detected within 60 seconds.", flush=True)
                    return None
                continue

            recorded_frames.append(frame)
            if above_threshold:
                voiced_frames += 1
                below_frames = 0
            else:
                    below_frames += 1

            if below_frames >= release_frames or len(recorded_frames) >= max_frames:
                close_reason = "silence" if below_frames >= release_frames else "max_utterance"
                if voiced_frames < min_frames:
                    print("[capture] very short segment kept for STT", flush=True)
                output_dir.mkdir(parents=True, exist_ok=True)
                path = output_dir / f"jarvis_loop_{time.strftime('%Y%m%d_%H%M%S')}.wav"
                write_pcm16_mono_wav(path, recorded_frames, sample_rate)
                capture_seconds = (time.perf_counter() - capture_started_at) if capture_started_at else 0.0
                print(
                    f"[capture] closed by {close_reason}; audio={_wav_duration_seconds(path):.2f}s "
                    f"capture_wall={capture_seconds:.2f}s peak={peak_dbfs:.1f} dBFS",
                    flush=True,
                )
                return RecordedUtterance(
                    path=path,
                    duration_seconds=_wav_duration_seconds(path),
                    peak_dbfs=peak_dbfs,
                    capture_seconds=capture_seconds,
                )
    finally:
        stream.stop()
        stream.close()


def capture_utterances_forever(
    *,
    output_queue: "queue.Queue[RecordedUtterance]",
    stop_event: threading.Event,
    output_dir: Path,
    device_index: Optional[int],
    input_sample_rate: Optional[int],
    gate_dbfs: float,
    attack_ms: int,
    release_ms: int,
    preroll_ms: int,
    min_ms: int,
    max_ms: int,
    frame_ms: int,
    playback_state: Optional[PlaybackState],
    barge_in_enabled: bool,
    barge_in_gate_dbfs: float,
    barge_in_attack_ms: int,
    tts_echo_cooldown_ms: int,
    echo_margin_db: float,
    speech_detector_name: str,
    vad_mode: int,
    vad_min_dbfs: float,
) -> None:
    sequence = 0
    while not stop_event.is_set():
        try:
            utterance = record_gated_utterance(
                output_dir=output_dir,
                device_index=device_index,
                input_sample_rate=input_sample_rate,
                gate_dbfs=gate_dbfs,
                attack_ms=attack_ms,
                release_ms=release_ms,
                preroll_ms=preroll_ms,
                min_ms=min_ms,
                max_ms=max_ms,
                frame_ms=frame_ms,
                playback_state=playback_state,
                barge_in_enabled=barge_in_enabled,
                barge_in_gate_dbfs=barge_in_gate_dbfs,
                barge_in_attack_ms=barge_in_attack_ms,
                tts_echo_cooldown_ms=tts_echo_cooldown_ms,
                echo_margin_db=echo_margin_db,
                speech_detector_name=speech_detector_name,
                vad_mode=vad_mode,
                vad_min_dbfs=vad_min_dbfs,
            )
        except Exception as exc:
            print(f"[capture] error: {exc}", flush=True)
            time.sleep(0.5)
            continue
        if utterance is None:
            continue
        sequence += 1
        utterance.sequence = sequence
        utterance.queued_at = time.perf_counter()
        output_queue.put(utterance)
        print(
            f"[queue] utterance {utterance.sequence} queued; pending={output_queue.qsize()}",
            flush=True,
        )


def transcribe_wav_whisper_cli(
    *,
    audio_path: Path,
    stt_model: str,
    whisper_flavor: str,
    language: str,
    threads: Optional[int],
    output_dir: Path,
    stt_pad_ms: int,
    initial_prompt: Optional[str],
) -> tuple[str, float]:
    audio_path = _normalize_wav_for_whisper(audio_path, output_dir=output_dir, pad_ms=stt_pad_ms)
    whisper_cli = ensure_prebuilt_whisper_cpp(flavor=whisper_flavor)
    model_path = ensure_ggml_model(stt_model)
    fixture = WhisperFixture(
        name=audio_path.stem,
        audio_path=audio_path,
        expected_text=None,
        source="jarvis_stt_tts_loop",
    )
    start = time.perf_counter()
    result = run_whisper_cli_once(
        whisper_cli=whisper_cli,
        model_path=model_path,
        model_name=stt_model,
        fixture=fixture,
        iteration=1,
        language=language,
        no_gpu=True,
        threads=threads,
        output_dir=output_dir,
        initial_prompt=initial_prompt,
    )
    return result.transcript.strip(), time.perf_counter() - start


async def _transcribe_wav_desktop_voice_runtime_async(
    *,
    audio_path: Path,
    output_dir: Path,
    show_drafts: bool,
    stt_pad_ms: int,
) -> tuple[str, float]:
    from app_backend.voice_runtime import VoiceDraftState, get_voice_runtime_status

    normalized_path = _normalize_wav_for_whisper(audio_path, output_dir=output_dir, pad_ms=stt_pad_ms)
    sample_rate, frames = _read_pcm16_mono_wav(normalized_path)
    chunk_bytes = max(2, int(sample_rate * DESKTOP_APP_VOICE_CHUNK_MS / 1000.0) * 2)
    draft = VoiceDraftState()
    status = get_voice_runtime_status()
    print(
        "Desktop voice STT: "
        f"engine={status.get('selected_engine')} "
        f"state={status.get('selected_engine_state')} "
        f"model={status.get('stt_model')} "
        f"draft={status.get('draft_model')}",
        flush=True,
    )
    if status.get("issues"):
        print(f"Desktop voice STT issues: {status.get('issues')}", flush=True)

    start = time.perf_counter()
    last_draft = ""
    sequence = 0
    total_chunks = max(1, math.ceil(len(frames) / float(chunk_bytes)))
    print(
        f"[stt] started; audio={len(frames) / 2 / float(sample_rate):.2f}s "
        f"chunks={total_chunks} chunk_ms={DESKTOP_APP_VOICE_CHUNK_MS}",
        flush=True,
    )
    for offset in range(0, len(frames), chunk_bytes):
        sequence += 1
        chunk = frames[offset : offset + chunk_bytes]
        if not chunk:
            continue
        print(f"[stt] chunk {sequence}/{total_chunks} sent at {time.perf_counter() - start:.2f}s", flush=True)
        wav_bytes = _pcm16_mono_wav_bytes(sample_rate=sample_rate, frames=chunk)
        partial = await draft.transcribe_chunk(
            audio_base64=base64.b64encode(wav_bytes).decode("ascii"),
            mime_type="audio/wav",
            sequence=sequence,
            revision=draft.revision,
        )
        partial = " ".join(str(partial or "").split()).strip()
        if show_drafts and partial and partial != last_draft:
            print(f"STT draft after chunk {sequence} ({time.perf_counter() - start:.2f}s): {partial}", flush=True)
            last_draft = partial

    print(f"[stt] finalizing at {time.perf_counter() - start:.2f}s", flush=True)
    await draft.wait_for_pending()
    final = " ".join((await draft.final_transcript()).split()).strip()
    print(f"[stt] final done at {time.perf_counter() - start:.2f}s", flush=True)
    return final, time.perf_counter() - start


def transcribe_wav_desktop_voice_runtime(
    *,
    audio_path: Path,
    output_dir: Path,
    show_drafts: bool,
    stt_pad_ms: int,
) -> tuple[str, float]:
    return asyncio.run(
        _transcribe_wav_desktop_voice_runtime_async(
            audio_path=audio_path,
            output_dir=output_dir,
            show_drafts=show_drafts,
            stt_pad_ms=stt_pad_ms,
        )
    )


def simple_reply(transcript: str) -> str:
    text = " ".join(transcript.split()).strip()
    if not text:
        return "I did not catch that."
    lowered = text.lower()
    if is_stop_request(lowered):
        return "Stopping the local voice loop."
    return f"I heard: {text}"


def is_stop_request(transcript: str) -> bool:
    lowered = " ".join(str(transcript or "").split()).strip().lower()
    return lowered in {"stop", "exit", "quit", "goodbye"} or lowered.startswith(("stop ", "exit ", "quit "))


def print_devices() -> None:
    if sd is None:
        raise RuntimeError("sounddevice is not installed, so microphone device listing is unavailable.")
    for device in list_input_devices():
        marker = "*" if device.get("is_default") else " "
        print(
            f"{marker} [{device['index']}] {device['name']} "
            f"channels={device['max_input_channels']} rate={device['default_sample_rate']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone local STT -> TTS conversation loop. No agent, tools, memory, or harness.",
    )
    parser.add_argument("--list-input-devices", action="store_true", help="List microphone input devices and exit.")
    parser.add_argument("--input-wav", type=Path, help="Transcribe and reply to a WAV file once instead of using the mic.")
    parser.add_argument("--text", help="Skip STT and speak this text once.")
    parser.add_argument("--once", action="store_true", help="Run one mic utterance and exit.")
    parser.add_argument("--device-index", type=int, help="Microphone input device index.")
    parser.add_argument(
        "--stt-mode",
        choices=("desktop", "whisper-cli"),
        default=DEFAULT_STT_MODE,
        help="STT backend. `desktop` uses the same VoiceDraftState path as the desktop app.",
    )
    parser.add_argument("--no-stt-drafts", action="store_true", help="Hide desktop STT draft output.")
    parser.add_argument("--stt-model", default=DEFAULT_STT_MODEL, help="whisper.cpp GGML model name.")
    parser.add_argument(
        "--stt-pad-ms",
        type=int,
        default=DEFAULT_STT_PAD_MS,
        help="Pad short captured utterances with trailing silence before STT.",
    )
    parser.add_argument(
        "--stt-prompt",
        default=DEFAULT_STT_PROMPT,
        help="Initial prompt passed to whisper.cpp to bias command/conversation transcription.",
    )
    parser.add_argument(
        "--no-stt-prompt",
        action="store_true",
        help="Disable the default whisper.cpp initial prompt.",
    )
    parser.add_argument("--whisper-flavor", default=DEFAULT_BINARY_FLAVOR, help="whisper.cpp binary flavor.")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="STT language.")
    parser.add_argument("--threads", type=int, default=recommended_thread_count(), help="whisper.cpp CPU thread count.")
    parser.add_argument(
        "--input-sample-rate",
        type=int,
        default=DEFAULT_INPUT_SAMPLE_RATE,
        help="Preferred microphone capture rate. 16000 enables WebRTC VAD on most devices.",
    )
    parser.add_argument(
        "--speech-detector",
        default=DEFAULT_SPEECH_DETECTOR,
        choices=("vad", "level"),
        help="Use VAD for speech/no-speech endpointing, or old level-only gating.",
    )
    parser.add_argument("--vad-mode", type=int, default=DEFAULT_VAD_MODE, help="WebRTC VAD aggressiveness, 0-3.")
    parser.add_argument("--vad-min-dbfs", type=float, default=DEFAULT_VAD_MIN_DBFS)
    parser.add_argument("--gate-dbfs", type=float, default=DEFAULT_GATE_DBFS, help="Microphone gate threshold in dBFS.")
    parser.add_argument("--attack-ms", type=int, default=DEFAULT_ATTACK_MS)
    parser.add_argument("--release-ms", type=int, default=DEFAULT_RELEASE_MS)
    parser.add_argument("--preroll-ms", type=int, default=DEFAULT_PREROLL_MS)
    parser.add_argument("--min-ms", type=int, default=DEFAULT_MIN_MS)
    parser.add_argument("--max-ms", type=int, default=DEFAULT_MAX_MS)
    parser.add_argument("--frame-ms", type=int, default=DEFAULT_FRAME_MS)
    parser.add_argument("--tts-language", default=DEFAULT_TTS_LANGUAGE)
    parser.add_argument("--tts-voice", default=DEFAULT_TTS_VOICE, help="Built-in voice name or reference WAV path.")
    parser.add_argument("--tts-quantize", action="store_true", help="Load Pocket TTS with int8 quantization.")
    parser.add_argument("--pocket-tts-site-packages", help="site-packages path containing pocket_tts.")
    parser.add_argument("--no-speak", action="store_true", help="Print replies without playing TTS.")
    parser.add_argument("--disable-barge-in", action="store_true", help="Do not cancel TTS when user speech is detected.")
    parser.add_argument("--barge-in-gate-dbfs", type=float, default=DEFAULT_BARGE_IN_GATE_DBFS)
    parser.add_argument("--barge-in-attack-ms", type=int, default=DEFAULT_BARGE_IN_ATTACK_MS)
    parser.add_argument("--tts-echo-cooldown-ms", type=int, default=DEFAULT_TTS_ECHO_COOLDOWN_MS)
    parser.add_argument("--echo-margin-db", type=float, default=DEFAULT_ECHO_MARGIN_DB)
    parser.add_argument("--llm-provider", default=DEFAULT_LLM_PROVIDER, choices=("openai", "none"))
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL, help="Cheap conversational model for STT -> LLM -> TTS.")
    parser.add_argument("--llm-temperature", type=float, default=0.4)
    parser.add_argument("--llm-timeout", type=float, default=30.0)
    parser.add_argument("--llm-history-turns", type=int, default=6, help="In-memory recent turns to keep for this process.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_input_devices:
        print_devices()
        return 0

    stt_prompt = None if args.no_stt_prompt else (args.stt_prompt or None)
    run_dir = output_root() / "jarvis_stt_tts_loop"
    run_dir.mkdir(parents=True, exist_ok=True)

    speaker: Optional[PocketTtsSpeaker] = None
    playback_state = PlaybackState()
    if not args.no_speak:
        print("Loading Pocket TTS...")
        speaker = PocketTtsSpeaker(
            language=args.tts_language,
            voice=args.tts_voice,
            quantize=bool(args.tts_quantize),
            site_packages=args.pocket_tts_site_packages,
        )
        print(
            f"Pocket TTS ready: model_load={speaker.load_seconds:.2f}s "
            f"voice_load={speaker.voice_state_seconds:.3f}s sample_rate={speaker.sample_rate}"
        )

    print(f"Loading conversation model: provider={args.llm_provider} model={args.llm_model}")
    conversation = ConversationModel(
        provider=args.llm_provider,
        model=args.llm_model,
        temperature=args.llm_temperature,
        max_history_turns=args.llm_history_turns,
        timeout=args.llm_timeout,
    )

    def speak_or_print(reply: str) -> dict[str, float | int | bool]:
        print(f"TTS reply: {reply}", flush=True)
        if speaker is not None:
            stats = speaker.speak_streaming(reply, playback_state=playback_state)
            print(f"TTS stats: {stats}", flush=True)
            return stats
        return {
            "chunks": 0,
            "first_chunk_seconds": 0.0,
            "total_seconds": 0.0,
            "audio_seconds": 0.0,
            "interrupted": False,
        }

    if args.text:
        turn_start = time.perf_counter()
        reply, llm_stats = conversation.reply(args.text)
        print(f"LLM reply: {reply}", flush=True)
        print(f"LLM stats: {llm_stats}", flush=True)
        tts_start = time.perf_counter()
        tts_stats = speak_or_print(reply)
        print(
            "[latency] "
            f"llm={llm_stats.get('seconds', 0)}s "
            f"tts_first_audio={tts_stats.get('first_chunk_seconds', 0)}s "
            f"tts_total={tts_stats.get('total_seconds', 0)}s "
            f"tts_interrupted={tts_stats.get('interrupted', False)} "
            f"tts_stage={time.perf_counter() - tts_start:.2f}s "
            f"turn_total={time.perf_counter() - turn_start:.2f}s",
            flush=True,
        )
        return 0

    def handle_wav(
        path: Path,
        *,
        capture_audio_seconds: Optional[float] = None,
        queue_wait_seconds: Optional[float] = None,
        utterance_sequence: Optional[int] = None,
    ) -> bool:
        turn_start = time.perf_counter()
        turn_id = int(utterance_sequence or (time.time() * 1000))
        playback_state.start_turn(turn_id)
        if utterance_sequence is not None:
            print(
                f"[turn] processing queued utterance {utterance_sequence}; "
                f"queue_wait={queue_wait_seconds or 0.0:.2f}s",
                flush=True,
            )
        elapsed = 0.0
        llm_elapsed = 0.0
        tts_elapsed = 0.0
        tts_stats: dict[str, float | int | bool] = {
            "chunks": 0,
            "first_chunk_seconds": 0.0,
            "total_seconds": 0.0,
            "audio_seconds": 0.0,
            "interrupted": False,
        }

        def print_turn_latency(*, interrupted: bool, stage: str) -> None:
            capture_part = f"capture_audio={capture_audio_seconds:.2f}s " if capture_audio_seconds is not None else ""
            queue_part = f"queue_wait={queue_wait_seconds:.2f}s " if queue_wait_seconds is not None else ""
            print(
                "[latency] "
                f"{capture_part}"
                f"{queue_part}"
                f"stt={elapsed:.2f}s "
                f"llm={llm_elapsed:.2f}s "
                f"tts_first_audio={tts_stats.get('first_chunk_seconds', 0)}s "
                f"tts_total={tts_stats.get('total_seconds', 0)}s "
                f"tts_interrupted={tts_stats.get('interrupted', False)} "
                f"tts_stage={tts_elapsed:.2f}s "
                f"turn_total={time.perf_counter() - turn_start:.2f}s "
                f"interrupted={interrupted} stage={stage}",
                flush=True,
            )
        try:
            if args.stt_mode == "desktop":
                transcript, elapsed = transcribe_wav_desktop_voice_runtime(
                    audio_path=path,
                    output_dir=run_dir,
                    show_drafts=not args.no_stt_drafts,
                    stt_pad_ms=args.stt_pad_ms,
                )
            else:
                transcript, elapsed = transcribe_wav_whisper_cli(
                    audio_path=path,
                    stt_model=args.stt_model,
                    whisper_flavor=args.whisper_flavor,
                    language=args.language,
                    threads=args.threads,
                    output_dir=run_dir,
                    stt_pad_ms=args.stt_pad_ms,
                    initial_prompt=stt_prompt,
                )
            print(f"STT transcript ({elapsed:.2f}s): {transcript or '<empty>'}", flush=True)
            if playback_state.is_turn_interrupted(turn_id):
                print(
                    f"[interrupt] turn {turn_id} was interrupted during STT; skipping LLM and TTS.",
                    flush=True,
                )
                print_turn_latency(interrupted=True, stage="stt")
                return False

            if is_stop_request(transcript):
                reply = "Stopping the local voice loop."
                tts_start = time.perf_counter()
                print("[tts] stop playback started", flush=True)
                tts_stats = speak_or_print(reply)
                tts_elapsed = time.perf_counter() - tts_start
                print_turn_latency(
                    interrupted=playback_state.is_turn_interrupted(turn_id),
                    stage="stop",
                )
                return True

            llm_start = time.perf_counter()
            print("[llm] request started", flush=True)
            reply, llm_stats = conversation.reply(transcript, commit=False)
            llm_elapsed = time.perf_counter() - llm_start
            print(f"LLM reply ({llm_elapsed:.2f}s): {reply}", flush=True)
            print(f"LLM stats: {json.dumps(llm_stats)}", flush=True)
            if playback_state.is_turn_interrupted(turn_id):
                print(
                    f"[interrupt] turn {turn_id} was interrupted during LLM; discarding stale reply.",
                    flush=True,
                )
                print_turn_latency(interrupted=True, stage="llm")
                return False

            tts_start = time.perf_counter()
            print("[tts] playback started", flush=True)
            tts_stats = speak_or_print(reply)
            tts_elapsed = time.perf_counter() - tts_start
            if playback_state.is_turn_interrupted(turn_id) or bool(tts_stats.get("interrupted", False)):
                print(
                    f"[interrupt] turn {turn_id} was interrupted during TTS; assistant reply left out of history.",
                    flush=True,
                )
            else:
                conversation.commit_exchange(transcript, reply)
            print_turn_latency(
                interrupted=playback_state.is_turn_interrupted(turn_id),
                stage="tts",
            )
            return reply == "Stopping the local voice loop."
        finally:
            playback_state.finish_turn(turn_id)

    if args.input_wav:
        handle_wav(args.input_wav.expanduser().resolve())
        return 0

    print(
        "Local STT -> LLM -> TTS loop running with continuous capture queue. "
        "Say 'stop' or press Ctrl+C to exit.",
        flush=True,
    )
    print(
        f"STT mode: {args.stt_mode} model={args.stt_model}. "
        f"Max utterance={args.max_ms}ms. "
        f"STT prompt={'on' if stt_prompt else 'off'}. "
        f"Speech detector={args.speech_detector} input_rate={args.input_sample_rate}Hz. "
        "Use --stt-mode desktop only when testing exact desktop VoiceDraftState behavior.",
        flush=True,
    )
    print(
        "Barge-in: "
        f"enabled={not args.disable_barge_in} "
        f"gate={args.barge_in_gate_dbfs:.1f}dBFS "
        f"attack={args.barge_in_attack_ms}ms "
        f"echo_cooldown={args.tts_echo_cooldown_ms}ms "
        f"echo_margin={args.echo_margin_db:.1f}dB",
        flush=True,
    )
    utterance_queue: "queue.Queue[RecordedUtterance]" = queue.Queue()
    stop_event = threading.Event()
    capture_thread = threading.Thread(
        target=capture_utterances_forever,
        kwargs={
            "output_queue": utterance_queue,
            "stop_event": stop_event,
            "output_dir": run_dir,
            "device_index": args.device_index,
            "input_sample_rate": args.input_sample_rate,
            "gate_dbfs": args.gate_dbfs,
            "attack_ms": args.attack_ms,
            "release_ms": args.release_ms,
            "preroll_ms": args.preroll_ms,
            "min_ms": args.min_ms,
            "max_ms": args.max_ms,
            "frame_ms": args.frame_ms,
            "playback_state": playback_state,
            "barge_in_enabled": not args.disable_barge_in,
            "barge_in_gate_dbfs": args.barge_in_gate_dbfs,
            "barge_in_attack_ms": args.barge_in_attack_ms,
            "tts_echo_cooldown_ms": args.tts_echo_cooldown_ms,
            "echo_margin_db": args.echo_margin_db,
            "speech_detector_name": args.speech_detector,
            "vad_mode": args.vad_mode,
            "vad_min_dbfs": args.vad_min_dbfs,
        },
        daemon=True,
    )
    capture_thread.start()
    try:
        while True:
            try:
                utterance = utterance_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            print(
                f"Dequeued utterance {utterance.sequence}: audio={utterance.duration_seconds:.2f}s "
                f"capture_wall={utterance.capture_seconds:.2f}s "
                f"peak={utterance.peak_dbfs:.1f} dBFS pending={utterance_queue.qsize()} -> {utterance.path}",
                flush=True,
            )
            should_stop = handle_wav(
                utterance.path,
                capture_audio_seconds=utterance.duration_seconds,
                queue_wait_seconds=max(0.0, time.perf_counter() - utterance.queued_at) if utterance.queued_at else 0.0,
                utterance_sequence=utterance.sequence,
            )
            utterance_queue.task_done()
            if should_stop:
                stop_event.set()
                return 0
            if args.once:
                stop_event.set()
                return 0
    except KeyboardInterrupt:
        stop_event.set()
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
