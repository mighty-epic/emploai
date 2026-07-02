import asyncio
import base64
import io
import wave

import pytest

from app_backend import voice_runtime


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


def test_synthesize_assistant_audio_uses_pocket_tts_backend(monkeypatch):
    class FakePocketRuntime:
        voice = "C:/voices/test.safetensors"
        sample_rate = 24_000

        def synthesize_wav_bytes(self, text: str) -> bytes:
            assert text == "hello from jarvis"
            return _silent_wav_bytes(sample_rate=self.sample_rate, seconds=0.05)

    monkeypatch.setenv("EMPLO_APP_TTS_BACKEND", "pocket")
    monkeypatch.setenv("EMPLO_APP_TTS_ENABLED", "1")
    monkeypatch.setattr(voice_runtime, "_get_pocket_tts_runtime", lambda: FakePocketRuntime())

    payload = voice_runtime.synthesize_assistant_audio("hello from jarvis")

    assert payload is not None
    assert payload["mime_type"] == "audio/wav"
    assert payload["format"] == "wav"
    assert payload["backend"] == "pocket"
    assert payload["model"] == "pocket_tts"
    assert payload["voice"] == "C:/voices/test.safetensors"
    assert payload["audio_base64"]


def test_get_voice_runtime_status_reports_pocket_tts_ready(monkeypatch, tmp_path):
    voice_file = tmp_path / "voice.safetensors"
    voice_file.write_bytes(b"fake voice state")

    monkeypatch.setenv("EMPLO_APP_TTS_BACKEND", "pocket")
    monkeypatch.setenv("EMPLO_APP_POCKET_TTS_VOICE", str(voice_file))
    monkeypatch.setattr(voice_runtime, "np", object())
    monkeypatch.setattr(voice_runtime, "_pocket_tts_import_error", lambda extra_site_packages=None: None)
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
        lambda: {"installed": True, "available": True, "issues": [], "source": "managed"},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": False, "available": False, "issues": []},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["tts_enabled"] is True
    assert status["tts_backend"] == "pocket"
    assert status["tts_ready"] is True
    assert status["tts_voice"] == str(voice_file)
    assert status["tts_issues"] == []


def test_get_voice_runtime_status_keeps_input_ready_when_tts_pack_missing(monkeypatch, tmp_path):
    missing_voice = tmp_path / "missing.safetensors"

    monkeypatch.setenv("EMPLO_APP_TTS_BACKEND", "pocket")
    monkeypatch.setenv("EMPLO_APP_POCKET_TTS_VOICE", str(missing_voice))
    monkeypatch.setattr(voice_runtime, "np", object())
    monkeypatch.setattr(voice_runtime, "_pocket_tts_import_error", lambda extra_site_packages=None: None)
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
        lambda: {"installed": True, "available": True, "issues": [], "source": "managed"},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": False, "available": False, "issues": []},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["ok"] is True
    assert status["input_ok"] is True
    assert status["issues"] == []
    assert status["tts_ok"] is False
    assert status["tts_ready"] is False
    assert any("Pocket TTS voice file does not exist" in issue for issue in status["tts_issues"])


def test_synthesize_assistant_audio_uses_kokoro_onnx_backend(monkeypatch):
    class FakeKokoroRuntime:
        model_path = "C:/models/kokoro.onnx"
        sample_rate = 24_000

        def synthesize_wav_bytes(self, text: str, *, voice: str, speed: float, language: str) -> bytes:
            assert text == "opening gmail now"
            assert voice == "am_adam"
            assert speed == 1.2
            assert language == "en-us"
            return _silent_wav_bytes(sample_rate=self.sample_rate, seconds=0.05)

    monkeypatch.setenv("EMPLO_APP_TTS_BACKEND", "kokoro_onnx")
    monkeypatch.setenv("EMPLO_APP_TTS_ENABLED", "1")
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_VOICE", "am_adam")
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_SPEED", "1.2")
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_LANGUAGE", "en-us")
    monkeypatch.setattr(voice_runtime, "_get_kokoro_tts_runtime", lambda: FakeKokoroRuntime())

    payload = voice_runtime.synthesize_assistant_audio("opening gmail now")

    assert payload is not None
    assert payload["mime_type"] == "audio/wav"
    assert payload["format"] == "wav"
    assert payload["backend"] == "kokoro_onnx"
    assert payload["model"] == "C:/models/kokoro.onnx"
    assert payload["voice"] == "am_adam"
    assert payload["audio_base64"]


def test_get_voice_runtime_status_reports_kokoro_onnx_ready(monkeypatch, tmp_path):
    model_file = tmp_path / "kokoro.onnx"
    voices_file = tmp_path / "voices.bin"
    model_file.write_bytes(b"fake model")
    voices_file.write_bytes(b"fake voices")

    monkeypatch.setenv("EMPLO_APP_TTS_BACKEND", "kokoro")
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_MODEL", str(model_file))
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_VOICES", str(voices_file))
    monkeypatch.setenv("EMPLO_APP_KOKORO_TTS_VOICE", "af_heart")
    monkeypatch.setattr(voice_runtime, "np", object())
    monkeypatch.setattr(voice_runtime, "_kokoro_tts_import_error", lambda extra_site_packages=None: None)
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
        lambda: {"installed": True, "available": True, "issues": [], "source": "managed"},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": False, "available": False, "issues": []},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["tts_enabled"] is True
    assert status["tts_backend"] == "kokoro_onnx"
    assert status["tts_ready"] is True
    assert status["tts_voice"] == "af_heart"
    assert status["tts_model"] == str(model_file)
    assert status["tts_issues"] == []


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


def test_fast_final_transcript_reuses_confirmed_draft(monkeypatch):
    def fail_slow_transcribe(*args, **kwargs):
        raise AssertionError("fast final should not run a second transcription when a confirmed draft exists")

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
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_local", fail_slow_transcribe)

    state = voice_runtime.VoiceDraftState()
    state.draft_text = "open chrome"
    state.segment_texts[1] = "open chrome"
    state.fresh_output_confirmed = True
    state.wav_chunks[1] = _silent_wav_bytes()
    state.last_sequence = 1
    state.sample_rate = 16000

    final = asyncio.run(state.final_transcript(fast=True))

    assert final == "open chrome"


def test_fast_final_transcript_uses_draft_model_when_no_draft(monkeypatch):
    calls: list[str] = []

    def fake_transcribe(data: bytes, *, model_name: str, sequence: int, revision: int, initial_prompt: str | None):
        del data, sequence, revision, initial_prompt
        calls.append(model_name)
        return "quick final", 0.9

    monkeypatch.setattr(voice_runtime, "_stt_backend", lambda: "local_whisper")
    monkeypatch.setattr(voice_runtime, "_local_model_name", lambda: "base.en-q5_1")
    monkeypatch.setattr(voice_runtime, "_local_draft_model_name", lambda: "tiny.en")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_ENGLISH,
            "english_requested": True,
            "hebrew_requested": False,
        },
    )
    monkeypatch.setattr(voice_runtime, "_transcribe_wav_bytes_local", fake_transcribe)

    state = voice_runtime.VoiceDraftState()
    state.wav_chunks[1] = _silent_wav_bytes()
    state.last_sequence = 1
    state.sample_rate = 16000

    final = asyncio.run(state.final_transcript(fast=True))

    assert final == "quick final"
    assert calls == ["tiny.en"]


def test_get_voice_runtime_status_reports_openai_realtime_stt_ready(monkeypatch):
    monkeypatch.setenv("EMPLO_APP_STT_BACKEND", "openai_realtime")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EMPLO_APP_TTS_ENABLED", "0")
    monkeypatch.setattr(
        voice_runtime,
        "_voice_engine_selection",
        lambda: {
            "default_engine": voice_runtime.VOICE_ENGINE_NONE,
            "english_requested": False,
            "hebrew_requested": False,
        },
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_english_pack_status",
        lambda: {"installed": False, "available": False, "issues": ["missing local English pack"]},
    )
    monkeypatch.setattr(
        voice_runtime,
        "get_hebrew_pack_status",
        lambda: {"installed": False, "available": False, "issues": ["missing Hebrew pack"]},
    )

    status = voice_runtime.get_voice_runtime_status()

    assert status["input_ok"] is True
    assert status["selected_engine_state"] == "ready"
    assert status["stt_backend"] == "openai_realtime"
    assert status["draft_model"] is None
    assert status["binary_flavor"] is None
    assert "gpt-realtime-whisper" in str(status["stt_model"])


def test_openai_realtime_status_uses_saved_runtime_env_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path))
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")

    issues = voice_runtime._openai_realtime_stt_issues()

    assert not any("OPENAI_API_KEY" in issue for issue in issues)


def test_new_voice_draft_state_uses_openai_realtime_backend(monkeypatch):
    monkeypatch.setenv("EMPLO_APP_STT_BACKEND", "openai_realtime")

    state = voice_runtime.new_voice_draft_state()

    assert isinstance(state, voice_runtime.OpenAIRealtimeVoiceDraftState)


def test_wav_bytes_to_realtime_pcm24k_resamples_pcm16():
    if voice_runtime.np is None:
        pytest.skip("NumPy is required for realtime audio resampling")

    data = _silent_wav_bytes(sample_rate=16_000, seconds=0.1)

    pcm = voice_runtime._wav_bytes_to_realtime_pcm24k(data)

    assert len(pcm) == 24_000 // 10 * 2
