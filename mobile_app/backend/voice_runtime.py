from __future__ import annotations

import asyncio
import base64
import io
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from openai import OpenAI


APP_STT_MODEL_ENV = "EMPLO_APP_STT_MODEL"
APP_STT_LANGUAGE_ENV = "EMPLO_APP_STT_LANGUAGE"
APP_STT_PROMPT_ENV = "EMPLO_APP_STT_PROMPT"
APP_TTS_ENABLED_ENV = "EMPLO_APP_TTS_ENABLED"
APP_TTS_MODEL_ENV = "EMPLO_APP_TTS_MODEL"
APP_TTS_VOICE_ENV = "EMPLO_APP_TTS_VOICE"
APP_TTS_FORMAT_ENV = "EMPLO_APP_TTS_FORMAT"
APP_TTS_SPEED_ENV = "EMPLO_APP_TTS_SPEED"
APP_TTS_INSTRUCTIONS_ENV = "EMPLO_APP_TTS_INSTRUCTIONS"
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "ash"
DEFAULT_TTS_FORMAT = "mp3"
MAX_TTS_CHARS = 4000

_stt_client: Optional[OpenAI] = None


def _get_stt_client() -> Optional[OpenAI]:
    global _stt_client
    if _stt_client is not None:
        return _stt_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    _stt_client = OpenAI(api_key=api_key)
    return _stt_client


def _normalize_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_tts_text(text: str) -> str:
    normalized = _normalize_transcript(text)
    if len(normalized) <= MAX_TTS_CHARS:
        return normalized
    clipped = normalized[:MAX_TTS_CHARS].rsplit(" ", 1)[0].strip()
    return clipped or normalized[:MAX_TTS_CHARS]


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
        raise RuntimeError("OPENAI_API_KEY is required for app voice transcription")
    if not data:
        return ""

    audio_file = io.BytesIO(data)
    audio_file.name = f"voice_chunk.{_extension_for_mime(mime_type)}"

    kwargs = {
        "file": audio_file,
        "model": os.getenv(APP_STT_MODEL_ENV, DEFAULT_STT_MODEL),
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
    last_sequence: int = 0
    state: str = "idle"
    revision: int = 0
    pending_tasks: Set[asyncio.Task] = field(default_factory=set, repr=False)
    transcription_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2), repr=False)

    def reset(self) -> int:
        self.revision += 1
        self.segment_texts.clear()
        self.last_sequence = 0
        self.state = "idle"
        return self.revision

    def transcript(self) -> str:
        parts = [self.segment_texts[idx] for idx in sorted(self.segment_texts) if self.segment_texts[idx]]
        return _normalize_transcript(" ".join(parts))

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
        if not audio_base64:
            return self.transcript()

        raw = base64.b64decode(audio_base64)
        seq = int(sequence or (self.last_sequence + 1))
        active_revision = self.revision if revision is None else revision

        async with self.transcription_slots:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, _transcribe_audio_bytes, raw, mime_type)
        if active_revision != self.revision:
            return self.transcript()

        self.segment_texts[seq] = text
        self.last_sequence = max(self.last_sequence, seq)
        return self.transcript()
