import asyncio
import base64
import io
import wave

import pytest

from mobile_app.backend import voice_runtime


def _silent_wav_bytes(sample_rate: int = 16_000, seconds: float = 1.0) -> bytes:
    sample_count = int(sample_rate * seconds)
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * sample_count)
    return output.getvalue()


def test_voice_draft_state_uses_local_whisper_draft_and_final_models(monkeypatch):
    calls: list[str] = []

    def fake_transcribe(data: bytes, *, model_name: str, sequence: int, revision: int, initial_prompt: str | None):
        calls.append(model_name)
        with wave.open(io.BytesIO(data), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == 16_000
        if model_name == "tiny.en":
            return "draft transcript", 0.95
        if model_name == "base.en-q5_1":
            return "final transcript", 0.98
        raise AssertionError(f"unexpected model: {model_name}")

    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(voice_runtime, "_local_draft_model_name", lambda: "tiny.en")
    monkeypatch.setattr(voice_runtime, "_local_model_name", lambda: "base.en-q5_1")
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_local", fake_transcribe)
    monkeypatch.setenv("EMPLO_APP_STT_DRAFT_MIN_MS", "300")
    monkeypatch.setenv("EMPLO_APP_STT_DRAFT_INTERVAL_MS", "200")

    state = voice_runtime.VoiceDraftState()
    wav_base64 = base64.b64encode(_silent_wav_bytes()).decode("utf-8")

    draft = asyncio.run(
        state.transcribe_chunk(
            audio_base64=wav_base64,
            mime_type="audio/wav",
            sequence=1,
        )
    )
    final = asyncio.run(state.final_transcript())

    assert draft == "draft transcript"
    assert final == "final transcript"
    assert calls == ["tiny.en", "base.en-q5_1"]


def test_local_voice_rejects_non_wav_chunks(monkeypatch):
    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    state = voice_runtime.VoiceDraftState()

    with pytest.raises(RuntimeError, match="audio/wav"):
        asyncio.run(
            state.transcribe_chunk(
                audio_base64=base64.b64encode(b"not a wav").decode("utf-8"),
                mime_type="audio/webm",
                sequence=1,
            )
        )


def test_voice_draft_state_uses_hebrew_local_engine_for_draft_and_final(monkeypatch):
    call_kinds: list[str] = []

    def fake_hebrew(data: bytes, *, sequence: int, revision: int, initial_prompt: str | None, final: bool):
        call_kinds.append("final" if final else "draft")
        with wave.open(io.BytesIO(data), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == 16_000
        return ("draft hebrew", None) if not final else ("final hebrew", None)

    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_HEBREW,
            "english_requested": True,
            "hebrew_requested": True,
        },
    )
    monkeypatch.setattr(voice_runtime, "_hebrew_support_issues", lambda require_model: [])
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_hebrew", fake_hebrew)
    monkeypatch.setenv("EMPLO_APP_STT_DRAFT_MIN_MS", "300")
    monkeypatch.setenv("EMPLO_APP_STT_DRAFT_INTERVAL_MS", "200")

    state = voice_runtime.VoiceDraftState()
    wav_base64 = base64.b64encode(_silent_wav_bytes()).decode("utf-8")

    draft = asyncio.run(
        state.transcribe_chunk(
            audio_base64=wav_base64,
            mime_type="audio/wav",
            sequence=1,
        )
    )
    final = asyncio.run(state.final_transcript())

    assert draft == "draft hebrew"
    assert final == "final hebrew"
    assert call_kinds == ["draft", "final"]


def test_get_voice_runtime_status_reports_voice_pack_statuses(monkeypatch):
    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_HEBREW,
            "english_requested": True,
            "hebrew_requested": True,
        },
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_english_pack_status",
        lambda: {"installed": True, "available": True, "issues": [], "source": "managed"},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": True, "available": True, "issues": [], "source": "managed", "model_dir": "C:/models/hebrew"},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["hebrew_pack_ready"] is True
    assert status["english_pack_ready"] is True
    assert status["stt_model"] == "C:/models/hebrew"
    assert status["hebrew_pack_status"]["source"] == "managed"


def test_get_voice_runtime_status_exposes_verified_hebrew_pack_manifest(monkeypatch):
    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_HEBREW,
            "english_requested": False,
            "hebrew_requested": True,
        },
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_english_pack_status",
        lambda: {"installed": False, "available": False, "issues": []},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {
            "installed": True,
            "available": True,
            "issues": [],
            "source": "managed",
            "model_dir": "C:/models/hebrew",
            "manifest": {
                "pack_id": "hebrew-pass3-knesset",
                "asset_name": "hebrew-whisper-small-pass3-knesset-runtime-ready.zip",
            },
            "manifest_verified": True,
        },
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["stt_model"] == "hebrew-whisper-small-pass3-knesset-runtime-ready.zip"
    assert status["hebrew_pack_manifest_verified"] is True
    assert status["hebrew_pack_manifest"]["pack_id"] == "hebrew-pass3-knesset"


def test_get_voice_runtime_status_exposes_verified_english_pack_manifest(monkeypatch):
    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_ENGLISH,
            "english_requested": True,
            "hebrew_requested": False,
        },
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_english_pack_status",
        lambda: {
            "installed": True,
            "available": True,
            "issues": [],
            "source": "managed",
            "manifest": {
                "pack_id": "english-whisper-cpp-desktop",
                "repo_id": "org/english-pack",
                "model_name": "base.en-q5_1",
            },
            "manifest_verified": True,
        },
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": False, "available": False, "issues": []},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["english_pack_manifest_verified"] is True
    assert status["english_pack_manifest"]["pack_id"] == "english-whisper-cpp-desktop"


def test_hebrew_final_transcript_falls_back_to_draft_when_final_is_repetitive(monkeypatch):
    def fake_hebrew(data: bytes, *, sequence: int, revision: int, initial_prompt: str | None, final: bool):
        del data, sequence, revision, initial_prompt
        if final:
            return ("בוא נראה אם עוד עוד עוד עוד עוד", 0.91)
        return ("בוא נראה אם הדבר הזה שונה", 0.9)

    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_HEBREW,
            "english_requested": True,
            "hebrew_requested": True,
        },
    )
    monkeypatch.setattr(voice_runtime, "_hebrew_support_issues", lambda require_model: [])
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_hebrew", fake_hebrew)

    state = voice_runtime.VoiceDraftState()
    wav_base64 = base64.b64encode(_silent_wav_bytes()).decode("utf-8")
    asyncio.run(
        state.transcribe_chunk(
            audio_base64=wav_base64,
            mime_type="audio/wav",
            sequence=1,
        )
    )

    final = asyncio.run(state.final_transcript())

    assert final == "בוא נראה אם הדבר הזה שונה"


def test_hebrew_final_transcript_discards_low_confidence_without_draft(monkeypatch):
    def fake_hebrew(data: bytes, *, sequence: int, revision: int, initial_prompt: str | None, final: bool):
        del data, sequence, revision, initial_prompt, final
        return ("שלום", 0.2)

    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_HEBREW,
            "english_requested": True,
            "hebrew_requested": True,
        },
    )
    monkeypatch.setattr(voice_runtime, "_hebrew_support_issues", lambda require_model: [])
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_hebrew", fake_hebrew)

    state = voice_runtime.VoiceDraftState()
    state.wav_chunks[1] = _silent_wav_bytes()
    state.last_sequence = 1
    state.sample_rate = 16000

    final = asyncio.run(state.final_transcript())

    assert final == ""
