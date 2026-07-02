from pathlib import Path
import subprocess
from types import SimpleNamespace

from app_backend import standalone_voice_engine
from app_backend import whisper_cpp_runtime as runtime
from app_backend import whisper_cpp_live


def test_release_asset_name_supports_windows_x64(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")

    assert runtime._release_asset_name(flavor="plain") == "whisper-bin-x64.zip"
    assert runtime._release_asset_name(flavor="blas") == "whisper-blas-bin-x64.zip"


def test_word_error_rate_handles_exact_and_imperfect_matches():
    assert runtime._word_error_rate("EmploAI open GitHub in Chrome", "EmploAI open GitHub in Chrome") == 0.0

    wer = runtime._word_error_rate("EmploAI open GitHub in Chrome", "Employee iOpen GitHub in Chrome")
    assert wer is not None
    assert wer > 0.0


def test_pcm16le_dbfs_reports_silence_and_signal_levels():
    silence = (b"\x00\x00") * 32
    loud = (b"\xff\x1f") * 32

    assert runtime.pcm16le_dbfs(silence) <= -100.0
    assert runtime.pcm16le_dbfs(loud) > -20.0


def test_hidden_subprocess_kwargs_hide_windows_console():
    kwargs = runtime._hidden_subprocess_kwargs()
    if runtime.os.name != "nt":
        assert kwargs == {}
        return

    assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE


def test_build_segment_prompt_appends_recent_context():
    prompt = whisper_cpp_live.build_segment_prompt(
        base_prompt="The wake phrase is EmploAI.",
        recent_transcripts=["open GitHub", "then summarize the session"],
        context_chars=40,
    )

    assert prompt is not None
    assert "The wake phrase is EmploAI." in prompt
    assert "Recent confirmed transcript context:" in prompt
    assert "summarize the session" in prompt


def test_transcript_confidence_from_output_json_reads_average_token_probability(tmp_path: Path):
    payload = {
        "transcription": [
            {
                "text": " EmploAI open GitHub",
                "tokens": [
                    {"text": " EmploAI", "p": 0.9},
                    {"text": " open", "p": 0.8},
                    {"text": " GitHub", "p": 0.7},
                    {"text": "<|endoftext|>", "p": 0.99},
                ],
            }
        ]
    }
    path = tmp_path / "run_full.json"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    transcript, confidence = runtime.transcript_confidence_from_output_json(path)

    assert transcript == "EmploAI open GitHub"
    assert confidence == 0.8


def test_transcript_from_output_json_reads_segment_text(tmp_path: Path):
    payload = {
        "transcription": [
            {"text": " EmploAI open GitHub in Chrome."},
            {"text": " Then summarize the session."},
        ]
    }
    path = tmp_path / "run.json"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    assert runtime.transcript_from_output_json(path) == "EmploAI open GitHub in Chrome. Then summarize the session."


def test_summarize_runs_reports_command_input_recommendation(tmp_path: Path):
    sample = runtime.WhisperRunResult(
        model_name="tiny.en",
        fixture_name="command",
        fixture_source="windows_speech",
        audio_path=tmp_path / "command.wav",
        output_json_path=tmp_path / "command.json",
        iteration=1,
        elapsed_seconds=0.8,
        audio_duration_seconds=2.0,
        realtime_factor=0.4,
        transcript="EmploAI open GitHub in Chrome",
        expected_text="EmploAI open GitHub in Chrome",
        word_error_rate=0.0,
    )

    summary = runtime.summarize_runs([sample])

    assert summary["recommendation"] == "excellent_for_command_input"
    assert summary["faster_than_realtime_runs"] == 1


def test_custom_fixture_collection_uses_manifest_by_name_and_stem(tmp_path: Path):
    wav_path = tmp_path / "wake_phrase.wav"
    wav_path.write_bytes(b"RIFF")
    manifest = tmp_path / "expected.json"
    manifest.write_text('{"wake_phrase.wav": "EmploAI open GitHub in Chrome"}', encoding="utf-8")

    fixtures = runtime.custom_fixture_collection([wav_path], expected_manifest_path=manifest)

    assert len(fixtures) == 1
    assert fixtures[0].source == "custom_recording"
    assert fixtures[0].expected_text == "EmploAI open GitHub in Chrome"


def test_list_input_devices_filters_to_input_capable_devices(monkeypatch):
    class FakePyAudioInstance:
        def get_default_input_device_info(self):
            return {"index": 1}

        def get_device_count(self):
            return 3

        def get_device_info_by_index(self, index):
            items = [
                {"index": 0, "name": "Speakers", "maxInputChannels": 0, "defaultSampleRate": 44100},
                {"index": 1, "name": "Microphone", "maxInputChannels": 2, "defaultSampleRate": 48000},
                {"index": 2, "name": "Headset Mic", "maxInputChannels": 1, "defaultSampleRate": 16000},
            ]
            return items[index]

        def terminate(self):
            return None

    class FakePyAudioModule:
        @staticmethod
        def PyAudio():
            return FakePyAudioInstance()

    monkeypatch.setattr(runtime, "pyaudio", FakePyAudioModule)

    devices = runtime.list_input_devices()

    assert [device["index"] for device in devices] == [1, 2]
    assert devices[0]["is_default"] is True


def test_runtime_paths_use_employai_home_when_configured(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    assert runtime.runtime_root() == runtime_home.resolve()
    assert runtime.tools_root() == runtime_home.resolve() / ".tools"
    assert runtime.output_root() == runtime_home.resolve() / "test_outputs" / "whisper_cpp"


def test_bundled_whisper_assets_are_used_before_download(monkeypatch, tmp_path: Path):
    bundle_root = tmp_path / "bundle"
    release_dir = bundle_root / "whisper-blas-bin-x64" / "Release"
    model_dir = bundle_root / "models"
    release_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    cli_path = release_dir / "whisper-cli.exe"
    model_path = model_dir / "ggml-base.en-q5_1.bin"
    cli_path.write_bytes(b"cli")
    model_path.write_bytes(b"model")

    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EMPLOAI_WHISPER_BUNDLE", str(bundle_root))

    def fail_download(*_args, **_kwargs):
        raise AssertionError("download should not run when bundled Whisper assets exist")

    monkeypatch.setattr(runtime, "_download_file", fail_download)

    assert runtime.bundled_whisper_cli(flavor="blas") == cli_path.resolve()
    assert runtime.bundled_ggml_model("base.en-q5_1") == model_path.resolve()
    assert runtime.ensure_prebuilt_whisper_cpp(flavor="blas") == cli_path.resolve()
    assert runtime.ensure_ggml_model("base.en-q5_1") == model_path.resolve()


def test_build_whisper_stream_command_includes_expected_live_flags(tmp_path: Path):
    command = whisper_cpp_live.build_whisper_stream_command(
        whisper_stream_exe=tmp_path / "whisper-stream.exe",
        model_path=tmp_path / "ggml-base.en-q5_1.bin",
        capture_device=1,
        language="en",
        threads=4,
        step_ms=2500,
        length_ms=9000,
        keep_ms=250,
        vad_threshold=0.55,
        freq_threshold=120.0,
        max_tokens=48,
        audio_ctx=0,
        beam_size=1,
        no_fallback=True,
        no_gpu=True,
        keep_context=True,
        save_audio=False,
        output_file=tmp_path / "live.txt",
    )

    assert command[0].endswith("whisper-stream.exe")
    assert "-c" in command and "1" in command
    assert "-m" in command
    assert "-ng" in command
    assert "-kc" in command
    assert "-nf" in command
    assert "-ac" in command and "0" in command
    assert "-bs" in command
    assert "-f" in command


def test_recommended_thread_count_caps_and_reserves_headroom():
    assert runtime.recommended_thread_count(1) == 1
    assert runtime.recommended_thread_count(4) == 3
    assert runtime.recommended_thread_count(8) == 6
    assert runtime.recommended_thread_count(16) == 6


def test_resolve_live_settings_uses_preset_defaults_and_allows_overrides():
    args = SimpleNamespace(
        engine="stream",
        preset="fast",
        binary_flavor=None,
        model=None,
        draft_model="tiny.en",
        threads=None,
        language="en",
        initial_prompt="",
        step_ms=None,
        length_ms=None,
        keep_ms=None,
        vad_threshold=None,
        freq_threshold=None,
        max_tokens=None,
        audio_ctx=None,
        beam_size=None,
        gate_dbfs=None,
        gate_attack_ms=None,
        gate_release_ms=None,
        gate_preroll_ms=None,
        gate_min_ms=None,
        gate_max_ms=None,
        gate_frame_ms=None,
        context_chars=220,
        no_context_memory=False,
        draft_interval_ms=900,
        draft_min_ms=1400,
        draft_confidence=0.82,
        draft_min_chars=12,
        no_draft_streaming=False,
        wake_phrase="",
        wake_alias=[],
        known_term=[],
        awake_timeout_s=12.0,
        command_gap_s=1.6,
        low_confidence_threshold=0.72,
        project_term_limit=48,
        prompt_term_limit=24,
        voice_profile_dir="",
        gpu=False,
        keep_context=False,
        no_keep_context=False,
        no_fallback=False,
        allow_fallback=False,
        save_audio=False,
        output_file="",
    )

    settings = whisper_cpp_live.resolve_live_settings(args)

    assert settings["preset_name"] == "fast"
    assert settings["binary_flavor"] == "blas"
    assert settings["model"] == "tiny.en"
    assert settings["draft_model"] == "tiny.en"
    assert settings["step_ms"] == 1000
    assert settings["engine"] == "stream"
    assert settings["keep_context"] is False
    assert settings["no_fallback"] is True
    assert settings["beam_size"] == 1
    assert settings["gate_dbfs"] == -34.0
    assert settings["gate_frame_ms"] == 30
    assert settings["context_chars"] == 220
    assert settings["draft_streaming_enabled"] is True
    assert settings["draft_confidence"] == 0.82
    assert settings["voice_engine_enabled"] is False

    args.model = "base.en-q5_1"
    args.draft_model = "tiny.en"
    args.keep_context = True
    args.allow_fallback = True
    args.gate_dbfs = -30.0
    args.gate_frame_ms = 20
    args.no_context_memory = True
    args.no_draft_streaming = True
    settings = whisper_cpp_live.resolve_live_settings(args)

    assert settings["model"] == "base.en-q5_1"
    assert settings["engine"] == "gated-cli"
    assert settings["keep_context"] is True
    assert settings["no_fallback"] is False
    assert settings["gate_dbfs"] == -30.0
    assert settings["gate_frame_ms"] == 20
    assert settings["context_chars"] == 0
    assert settings["draft_streaming_enabled"] is False


def test_resolve_live_settings_enables_standalone_voice_engine():
    args = SimpleNamespace(
        engine="voice-engine",
        preset="balanced",
        binary_flavor=None,
        model=None,
        draft_model="tiny.en",
        threads=None,
        language="en",
        initial_prompt="",
        step_ms=None,
        length_ms=None,
        keep_ms=None,
        vad_threshold=None,
        freq_threshold=None,
        max_tokens=None,
        audio_ctx=None,
        beam_size=None,
        gate_dbfs=None,
        gate_attack_ms=None,
        gate_release_ms=None,
        gate_preroll_ms=None,
        gate_min_ms=None,
        gate_max_ms=None,
        gate_frame_ms=None,
        context_chars=220,
        no_context_memory=False,
        draft_interval_ms=900,
        draft_min_ms=1400,
        draft_confidence=0.82,
        draft_min_chars=12,
        no_draft_streaming=False,
        wake_phrase="EmploAI",
        wake_alias=["Emplo AI"],
        known_term=["telegram_agent.py"],
        awake_timeout_s=10.0,
        command_gap_s=1.3,
        low_confidence_threshold=0.7,
        project_term_limit=20,
        prompt_term_limit=10,
        voice_profile_dir="",
        gpu=False,
        keep_context=False,
        no_keep_context=False,
        no_fallback=False,
        allow_fallback=False,
        save_audio=False,
        output_file="",
    )

    settings = whisper_cpp_live.resolve_live_settings(args)

    assert settings["engine"] == "gated-cli"
    assert settings["engine_label"] == "voice-engine"
    assert settings["voice_engine_enabled"] is True
    assert settings["wake_phrase"] == "EmploAI"
    assert settings["wake_aliases"] == ["Emplo AI"]
    assert settings["known_terms"] == ["telegram_agent.py"]


def test_standalone_voice_engine_builds_prompt_with_project_terms(tmp_path: Path):
    (tmp_path / "telegram_agent.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test", encoding="utf-8")

    engine = standalone_voice_engine.StandaloneVoiceEngine(
        repo_root=tmp_path,
        state_dir=tmp_path / "voice_state",
        project_term_limit=10,
        prompt_term_limit=10,
    )

    prompt = engine.build_prompt(
        base_prompt="The assistant is listening.",
        recent_transcripts=["open GitHub"],
        context_chars=120,
    )

    assert prompt is not None
    assert "Wake phrase: EmploAI." in prompt
    assert "telegram_agent.py" in prompt
    assert ".env" in prompt
    assert "Recent confirmed transcript context: open GitHub" in prompt


def test_standalone_voice_engine_wakes_and_finalizes_command(tmp_path: Path):
    engine = standalone_voice_engine.StandaloneVoiceEngine(
        repo_root=tmp_path,
        state_dir=tmp_path / "voice_state",
        awake_timeout_s=5.0,
        command_gap_s=1.0,
    )

    wake_events = engine.observe_final(transcript="EmploAI open GitHub", confidence=0.92, now=0.0)
    idle_events = engine.poll(recording_active=False, now=1.2)

    assert any("[wake]" in event for event in wake_events)
    assert any("[command segment] open GitHub" == event for event in wake_events)
    assert any("[command ready] open GitHub" == event for event in idle_events)
    assert engine.profile_summary()["recent_commands"][-1]["text"] == "open GitHub"


def test_standalone_voice_engine_tracks_low_confidence_review_items(tmp_path: Path):
    engine = standalone_voice_engine.StandaloneVoiceEngine(
        repo_root=tmp_path,
        state_dir=tmp_path / "voice_state",
        low_confidence_threshold=0.8,
        command_gap_s=0.5,
    )

    engine.observe_final(transcript="EmploAI open telegram_agent.py", confidence=0.6, now=0.0)
    engine.poll(recording_active=False, now=0.7)
    profile = engine.export_profile()

    assert profile["pending_reviews"]
    assert "telegram_agent.py" in profile["known_terms"]
    assert "telegram_agent.py" in profile["low_confidence_terms"]
