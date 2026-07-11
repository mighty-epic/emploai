from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable, Optional

from shared.bundled_python_runtime import configure_bundled_python_dependencies


configure_bundled_python_dependencies()

from app_backend.standalone_voice_engine import (
    DEFAULT_AWAKE_TIMEOUT_S,
    DEFAULT_COMMAND_GAP_S,
    DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    DEFAULT_PROJECT_TERM_LIMIT,
    DEFAULT_PROMPT_TERM_LIMIT,
    DEFAULT_WAKE_PHRASE,
    StandaloneVoiceEngine,
    default_voice_engine_state_dir,
)
from app_backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_LANGUAGE,
    DEFAULT_RELEASE_TAG,
    WhisperFixture,
    _decode_subprocess_output,
    _hidden_subprocess_kwargs,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    list_input_devices,
    output_root,
    pcm16le_dbfs,
    pyaudio,
    recommended_thread_count,
    run_whisper_cli_once,
    transcript_confidence_from_output_json,
    write_pcm16_mono_wav,
)


DEFAULT_LIVE_MODEL = "base.en-q5_1"
DEFAULT_LIVE_ENGINE = "stream"
DEFAULT_LIVE_PRESET = "balanced"
DEFAULT_GATED_CONTEXT_CHARS = 220
DEFAULT_DRAFT_MODEL = "tiny.en"
DEFAULT_DRAFT_INTERVAL_MS = 900
DEFAULT_DRAFT_MIN_MS = 1400
DEFAULT_DRAFT_CONFIDENCE = 0.82
DEFAULT_DRAFT_MIN_CHARS = 12


@dataclass(frozen=True)
class LivePreset:
    description: str
    binary_flavor: str
    model: str
    step_ms: int
    length_ms: int
    keep_ms: int
    vad_threshold: float
    freq_threshold: float
    max_tokens: int
    keep_context: bool
    audio_ctx: int
    beam_size: int
    no_fallback: bool
    gate_dbfs: float
    gate_attack_ms: int
    gate_release_ms: int
    gate_preroll_ms: int
    gate_min_ms: int
    gate_max_ms: int
    gate_frame_ms: int


LIVE_PRESETS: dict[str, LivePreset] = {
    "fast": LivePreset(
        description="Lowest practical latency on this laptop-class CPU. Best for short commands.",
        binary_flavor="blas",
        model="tiny.en",
        step_ms=1000,
        length_ms=4000,
        keep_ms=150,
        vad_threshold=0.68,
        freq_threshold=120.0,
        max_tokens=16,
        keep_context=False,
        audio_ctx=0,
        beam_size=1,
        no_fallback=True,
        gate_dbfs=-34.0,
        gate_attack_ms=150,
        gate_release_ms=500,
        gate_preroll_ms=250,
        gate_min_ms=450,
        gate_max_ms=5000,
        gate_frame_ms=30,
    ),
    "balanced": LivePreset(
        description="Responsive live mode with stricter noise rejection than the upstream defaults.",
        binary_flavor="blas",
        model=DEFAULT_LIVE_MODEL,
        step_ms=1500,
        length_ms=6000,
        keep_ms=200,
        vad_threshold=0.66,
        freq_threshold=120.0,
        max_tokens=24,
        keep_context=False,
        audio_ctx=0,
        beam_size=1,
        no_fallback=True,
        gate_dbfs=-32.0,
        gate_attack_ms=150,
        gate_release_ms=650,
        gate_preroll_ms=300,
        gate_min_ms=500,
        gate_max_ms=6500,
        gate_frame_ms=30,
    ),
    "strict": LivePreset(
        description="Most conservative speech detection. Best when false positives are worse than missed quiet words.",
        binary_flavor="blas",
        model="tiny.en",
        step_ms=1200,
        length_ms=4500,
        keep_ms=100,
        vad_threshold=0.75,
        freq_threshold=150.0,
        max_tokens=12,
        keep_context=False,
        audio_ctx=0,
        beam_size=1,
        no_fallback=True,
        gate_dbfs=-29.0,
        gate_attack_ms=180,
        gate_release_ms=500,
        gate_preroll_ms=250,
        gate_min_ms=500,
        gate_max_ms=5000,
        gate_frame_ms=30,
    ),
    "dictation": LivePreset(
        description="Longer chunks and context carry-over for freer speech, with higher latency.",
        binary_flavor="blas",
        model=DEFAULT_LIVE_MODEL,
        step_ms=2000,
        length_ms=8000,
        keep_ms=250,
        vad_threshold=0.55,
        freq_threshold=100.0,
        max_tokens=48,
        keep_context=True,
        audio_ctx=0,
        beam_size=3,
        no_fallback=False,
        gate_dbfs=-38.0,
        gate_attack_ms=200,
        gate_release_ms=900,
        gate_preroll_ms=350,
        gate_min_ms=700,
        gate_max_ms=10000,
        gate_frame_ms=40,
    ),
}


def _find_default_input_device_index() -> Optional[int]:
    for device in list_input_devices():
        if device.get("is_default"):
            return int(device["index"])
    return None


def build_whisper_stream_command(
    *,
    whisper_stream_exe: Path,
    model_path: Path,
    capture_device: int,
    language: str = DEFAULT_LANGUAGE,
    threads: int,
    step_ms: int,
    length_ms: int,
    keep_ms: int,
    vad_threshold: float,
    freq_threshold: float,
    max_tokens: int,
    audio_ctx: int = 0,
    beam_size: int = 1,
    no_fallback: bool = False,
    no_gpu: bool = True,
    keep_context: bool = False,
    save_audio: bool = False,
    output_file: Optional[Path] = None,
) -> list[str]:
    command = [
        str(whisper_stream_exe),
        "-c",
        str(capture_device),
        "-m",
        str(model_path),
        "-l",
        language,
        "-t",
        str(threads),
        "--step",
        str(step_ms),
        "--length",
        str(length_ms),
        "--keep",
        str(keep_ms),
        "-vth",
        str(vad_threshold),
        "-fth",
        str(freq_threshold),
        "-mt",
        str(max_tokens),
    ]
    if audio_ctx >= 0:
        command.extend(["-ac", str(audio_ctx)])
    if beam_size > 0:
        command.extend(["-bs", str(beam_size)])
    if no_fallback:
        command.append("-nf")
    if no_gpu:
        command.append("-ng")
    if keep_context:
        command.append("-kc")
    if save_audio:
        command.append("-sa")
    if output_file:
        command.extend(["-f", str(output_file)])
    return command


def _preset_lines() -> list[str]:
    lines = []
    for name, preset in LIVE_PRESETS.items():
        lines.append(
            f"{name}: {preset.description} "
            f"[model={preset.model}, binary={preset.binary_flavor}, step={preset.step_ms}ms, length={preset.length_ms}ms]"
        )
    return lines


def _gate_args_present(args: argparse.Namespace) -> bool:
    return any(
        value is not None
        for value in (
            args.gate_dbfs,
            args.gate_attack_ms,
            args.gate_release_ms,
            args.gate_preroll_ms,
            args.gate_min_ms,
            args.gate_max_ms,
            args.gate_frame_ms,
        )
    )


def _respawn_current_module_without_spawn_window() -> int:
    command = [
        sys.executable,
        "-m",
        "app_backend.whisper_cpp_live",
        *[arg for arg in sys.argv[1:] if arg != "--spawn-window"],
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    subprocess.Popen(command, creationflags=creationflags)
    return 0


def build_segment_prompt(
    *,
    base_prompt: Optional[str],
    recent_transcripts: list[str],
    context_chars: int,
) -> Optional[str]:
    base = (base_prompt or "").strip()
    cleaned_recent = [item.strip() for item in recent_transcripts if item and item.strip()]

    if context_chars > 0 and cleaned_recent:
        recent_text = " ".join(cleaned_recent)
        if len(recent_text) > context_chars:
            recent_text = recent_text[-context_chars:].lstrip()
        context_block = f"Recent confirmed transcript context: {recent_text}"
        if base:
            return f"{base}\n{context_block}"
        return context_block

    return base or None


def run_whisper_cli_preview_once(
    *,
    whisper_cli: Path,
    model_path: Path,
    model_name: str,
    fixture: WhisperFixture,
    iteration: int,
    language: str,
    initial_prompt: Optional[str],
    no_gpu: bool,
    threads: int,
    output_dir: Path,
) -> tuple[str, Optional[float]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_slug = f"preview_{model_name.replace('.', '_')}_{fixture.name}_run{iteration}"
    output_base = output_dir / run_slug
    output_json_path = output_base.with_suffix(".json")
    if output_json_path.exists():
        output_json_path.unlink()

    command = [
        str(whisper_cli),
        "-m",
        str(model_path),
        "-f",
        str(fixture.audio_path),
        "-l",
        language,
        "-nt",
        "-np",
        "-ojf",
        "-of",
        str(output_base),
    ]
    if no_gpu:
        command.append("-ng")
    if threads:
        command.extend(["-t", str(threads)])
    if initial_prompt:
        command.extend(["--prompt", initial_prompt, "--carry-initial-prompt"])

    completed = subprocess.run(command, capture_output=True, text=False, check=False, **_hidden_subprocess_kwargs())
    if completed.returncode != 0:
        raise RuntimeError(
            f"whisper.cpp preview failed for {fixture.audio_path.name}: "
            f"{_decode_subprocess_output(completed.stderr).strip() or _decode_subprocess_output(completed.stdout).strip() or 'unknown error'}"
        )
    if not output_json_path.exists():
        raise RuntimeError(f"whisper.cpp preview did not produce {output_json_path}")
    return transcript_confidence_from_output_json(output_json_path)


def run_gated_cli_session(
    *,
    whisper_cli: Path,
    model_path: Path,
    model_name: str,
    draft_model_path: Optional[Path],
    draft_model_name: Optional[str],
    device_index: int,
    language: str,
    threads: int,
    no_gpu: bool,
    initial_prompt: Optional[str],
    gate_dbfs: float,
    gate_attack_ms: int,
    gate_release_ms: int,
    gate_preroll_ms: int,
    gate_min_ms: int,
    gate_max_ms: int,
    gate_frame_ms: int,
    context_chars: int,
    draft_interval_ms: int,
    draft_min_ms: int,
    draft_confidence: float,
    draft_min_chars: int,
    draft_streaming_enabled: bool,
    voice_engine: Optional[StandaloneVoiceEngine] = None,
    on_final_result: Optional[Callable[[dict[str, object]], None]] = None,
) -> int:
    if pyaudio is None:
        raise SystemExit("PyAudio is not installed, so gated microphone capture is unavailable")

    chunk_ms = max(10, int(gate_frame_ms))
    live_output_dir = output_root() / "live_gated"
    live_output_dir.mkdir(parents=True, exist_ok=True)
    print_lock = threading.Lock()
    transcription_queue: Queue = Queue()
    preview_queue: Queue = Queue()
    state_lock = threading.Lock()
    shared_state = {
        "active_segment_id": None,
        "last_preview_ms": 0,
        "preview_inflight_for": None,
        "last_partial_by_segment": {},
        "recent_transcripts": deque(maxlen=8),
    }
    preview_threads = max(1, min(3, max(1, threads // 2)))

    def log(message: str) -> None:
        with print_lock:
            print(message, flush=True)

    def build_runtime_prompt(recent_transcripts: list[str]) -> Optional[str]:
        if voice_engine is not None:
            return voice_engine.build_prompt(
                base_prompt=initial_prompt,
                recent_transcripts=recent_transcripts,
                context_chars=context_chars,
            )
        return build_segment_prompt(
            base_prompt=initial_prompt,
            recent_transcripts=recent_transcripts,
            context_chars=context_chars,
        )

    def transcription_worker() -> None:
        while True:
            item = transcription_queue.get()
            if item is None:
                transcription_queue.task_done()
                break

            audio_path, queued_segment_index, queued_peak_dbfs, queued_duration_ms = item
            try:
                with state_lock:
                    recent_transcripts = list(shared_state["recent_transcripts"])
                segment_prompt = build_runtime_prompt(recent_transcripts)
                fixture = WhisperFixture(
                    name=audio_path.stem,
                    audio_path=audio_path,
                    source="live_gate",
                )
                result = run_whisper_cli_once(
                    whisper_cli=whisper_cli,
                    model_path=model_path,
                    model_name=model_name,
                    fixture=fixture,
                    iteration=queued_segment_index,
                    language=language,
                    initial_prompt=segment_prompt,
                    no_gpu=no_gpu,
                    threads=threads,
                    output_dir=live_output_dir,
                )
                transcript = result.transcript.strip()
                _, final_confidence = transcript_confidence_from_output_json(result.output_json_path)
                if transcript:
                    with state_lock:
                        shared_state["recent_transcripts"].append(transcript)
                        shared_state["last_partial_by_segment"].pop(queued_segment_index, None)
                    log(
                        f"[segment {queued_segment_index}] {queued_duration_ms} ms captured | peak {queued_peak_dbfs:.1f} dBFS\n"
                        f"[{time.strftime('%H:%M:%S')}] {transcript}"
                    )
                    if voice_engine is not None:
                        for event in voice_engine.observe_final(transcript=transcript, confidence=final_confidence):
                            log(event)
                    if on_final_result is not None:
                        try:
                            on_final_result(
                                {
                                    "audio_path": audio_path,
                                    "segment_index": queued_segment_index,
                                    "peak_dbfs": queued_peak_dbfs,
                                    "duration_ms": queued_duration_ms,
                                    "transcript": transcript,
                                    "confidence": final_confidence,
                                    "prompt": segment_prompt,
                                }
                            )
                        except Exception as callback_exc:
                            log(f"[segment {queued_segment_index}] postprocess failed: {callback_exc}")
                else:
                    log(f"[segment {queued_segment_index}] empty transcript after {queued_duration_ms} ms capture")
            except Exception as exc:
                log(f"[segment {queued_segment_index}] transcription failed: {exc}")
            finally:
                transcription_queue.task_done()

    def preview_worker() -> None:
        while True:
            item = preview_queue.get()
            if item is None:
                preview_queue.task_done()
                break

            audio_path, preview_segment_id, preview_iteration, preview_duration_ms = item
            try:
                with state_lock:
                    recent_transcripts = list(shared_state["recent_transcripts"])
                    active_segment_id = shared_state["active_segment_id"]
                if active_segment_id != preview_segment_id:
                    continue

                segment_prompt = build_runtime_prompt(recent_transcripts)
                fixture = WhisperFixture(
                    name=audio_path.stem,
                    audio_path=audio_path,
                    source="live_gate_preview",
                )
                preview_model_path = draft_model_path or model_path
                preview_model_name = draft_model_name or model_name
                transcript, confidence = run_whisper_cli_preview_once(
                    whisper_cli=whisper_cli,
                    model_path=preview_model_path,
                    model_name=preview_model_name,
                    fixture=fixture,
                    iteration=preview_iteration,
                    language=language,
                    initial_prompt=segment_prompt,
                    no_gpu=no_gpu,
                    threads=preview_threads,
                    output_dir=live_output_dir,
                )
                transcript = transcript.strip()
                if not transcript:
                    continue

                with state_lock:
                    active_segment_id = shared_state["active_segment_id"]
                    previous_partial = shared_state["last_partial_by_segment"].get(preview_segment_id, "")
                if active_segment_id != preview_segment_id:
                    continue
                if confidence is None or confidence < draft_confidence:
                    continue
                if len(transcript) < draft_min_chars:
                    continue
                if transcript == previous_partial:
                    continue
                if previous_partial and not transcript.startswith(previous_partial[: max(1, min(len(previous_partial), 8))]):
                    # Allow self-correction, but avoid spamming entirely unrelated unstable drafts.
                    pass

                with state_lock:
                    shared_state["last_partial_by_segment"][preview_segment_id] = transcript
                log(
                    f"[draft {preview_segment_id}] {preview_duration_ms} ms | conf {confidence:.2f}\n"
                    f"[{time.strftime('%H:%M:%S')}] {transcript}"
                )
                if voice_engine is not None:
                    for event in voice_engine.observe_preview(transcript=transcript, confidence=confidence):
                        log(event)
            except Exception as exc:
                log(f"[draft {preview_segment_id}] preview failed: {exc}")
            finally:
                with state_lock:
                    if shared_state["preview_inflight_for"] == preview_segment_id:
                        shared_state["preview_inflight_for"] = None
                preview_queue.task_done()

    worker = threading.Thread(target=transcription_worker, daemon=True)
    worker.start()
    preview_thread = threading.Thread(target=preview_worker, daemon=True)
    preview_thread.start()

    pa = pyaudio.PyAudio()
    try:
        device_info = pa.get_device_info_by_index(int(device_index))
        sample_rate = int(float(device_info.get("defaultSampleRate") or 16000))
        chunk_frames = max(1, int(sample_rate * chunk_ms / 1000.0))
        attack_chunks = max(1, int(round(gate_attack_ms / float(chunk_ms))))
        release_chunks = max(1, int(round(gate_release_ms / float(chunk_ms))))
        preroll_chunks = max(1, int(round(gate_preroll_ms / float(chunk_ms))))
        min_chunks = max(1, int(round(gate_min_ms / float(chunk_ms))))
        max_chunks = max(min_chunks, int(round(gate_max_ms / float(chunk_ms))))
        effective_attack_ms = attack_chunks * chunk_ms
        effective_release_ms = release_chunks * chunk_ms
        effective_min_ms = min_chunks * chunk_ms
        effective_max_ms = max_chunks * chunk_ms

        log(
            f"Gated CLI mode armed on [{device_index}] {device_info.get('name')}.\n"
            f"Noise gate: open at {gate_dbfs:.1f} dBFS | attack {gate_attack_ms} ms | release {gate_release_ms} ms | "
            f"min speech {gate_min_ms} ms | max segment {gate_max_ms} ms | frame {chunk_ms} ms | "
            f"context memory {context_chars} chars | draft streaming {draft_streaming_enabled}"
        )
        log(
            f"Effective gate timing after frame quantization: open {effective_attack_ms} ms | "
            f"min speech {effective_min_ms} ms | release {effective_release_ms} ms | max segment {effective_max_ms} ms"
        )
        if draft_streaming_enabled:
            log(
                f"Final model: {model_name} | Draft model: {draft_model_name or model_name} | "
                f"Final threads: {threads} | Draft threads: {preview_threads}"
            )
        if initial_prompt:
            log("Initial prompt is enabled for gated transcription.")
        if draft_streaming_enabled:
            log(
                f"Draft streaming is enabled: interval {draft_interval_ms} ms | min open duration {draft_min_ms} ms | "
                f"min confidence {draft_confidence:.2f}"
            )
        if voice_engine is not None:
            summary = voice_engine.profile_summary()
            log(
                f'Standalone voice engine enabled. Wake phrase: "{summary["wake_phrase"]}" | '
                f"known terms {summary['known_terms_count']} | project terms {summary['project_term_count']} | "
                f"pending review {summary['pending_review_count']}"
            )
            log(f'Voice engine state directory: {summary["state_dir"]}')
        log("Speak above the threshold. Quiet background noise and very soft whispers should be ignored. Press Ctrl+C to stop.")

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            input_device_index=int(device_index),
            frames_per_buffer=chunk_frames,
        )
        try:
            pre_roll: deque[bytes] = deque(maxlen=preroll_chunks)
            above_threshold_count = 0
            below_threshold_count = 0
            active_voice_chunks = 0
            peak_dbfs = -120.0
            segment_index = 0
            recording = False
            recording_frames: list[bytes] = []

            while True:
                frame_bytes = stream.read(chunk_frames, exception_on_overflow=False)
                level_dbfs = pcm16le_dbfs(frame_bytes)
                above_threshold = level_dbfs >= gate_dbfs
                if voice_engine is not None:
                    for event in voice_engine.poll(recording_active=recording):
                        log(event)

                if not recording:
                    pre_roll.append(frame_bytes)
                    above_threshold_count = above_threshold_count + 1 if above_threshold else 0
                    if above_threshold_count >= attack_chunks:
                        recording = True
                        recording_frames = list(pre_roll)
                        active_voice_chunks = above_threshold_count
                        below_threshold_count = 0
                        peak_dbfs = level_dbfs
                        with state_lock:
                            shared_state["active_segment_id"] = segment_index + 1
                            shared_state["last_preview_ms"] = 0
                            shared_state["preview_inflight_for"] = None
                        log(f"[gate open] level={level_dbfs:.1f} dBFS")
                    continue

                recording_frames.append(frame_bytes)
                peak_dbfs = max(peak_dbfs, level_dbfs)
                if above_threshold:
                    active_voice_chunks += 1
                    below_threshold_count = 0
                else:
                    below_threshold_count += 1

                should_close = below_threshold_count >= release_chunks or len(recording_frames) >= max_chunks
                current_duration_ms = len(recording_frames) * chunk_ms
                current_segment_id = segment_index + 1
                if draft_streaming_enabled:
                    with state_lock:
                        preview_inflight_for = shared_state["preview_inflight_for"]
                        last_preview_ms = shared_state["last_preview_ms"]
                    should_preview = (
                        preview_inflight_for is None
                        and current_duration_ms >= draft_min_ms
                        and (current_duration_ms - last_preview_ms) >= draft_interval_ms
                    )
                    if should_preview:
                        preview_iteration = max(1, int(current_duration_ms / max(1, draft_interval_ms)))
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        preview_audio_path = live_output_dir / f"preview_segment_{timestamp}_{current_segment_id:03d}_{preview_iteration:03d}.wav"
                        write_pcm16_mono_wav(preview_audio_path, list(recording_frames), sample_rate)
                        with state_lock:
                            shared_state["preview_inflight_for"] = current_segment_id
                            shared_state["last_preview_ms"] = current_duration_ms
                        preview_queue.put(
                            (
                                preview_audio_path,
                                current_segment_id,
                                preview_iteration,
                                current_duration_ms,
                            )
                        )
                if not should_close:
                    continue

                segment_duration_ms = len(recording_frames) * chunk_ms
                voiced_duration_ms = active_voice_chunks * chunk_ms

                if voiced_duration_ms >= gate_min_ms and len(recording_frames) >= min_chunks:
                    segment_index += 1
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    audio_path = live_output_dir / f"segment_{timestamp}_{segment_index:03d}.wav"
                    write_pcm16_mono_wav(audio_path, recording_frames, sample_rate)
                    transcription_queue.put(
                        (
                            audio_path,
                            segment_index,
                            peak_dbfs,
                            segment_duration_ms,
                        )
                    )
                    log(
                        f"[gate close] queued segment {segment_index} | {segment_duration_ms} ms captured | "
                        f"peak {peak_dbfs:.1f} dBFS | pending {transcription_queue.qsize()}"
                    )
                else:
                    log(
                        f"[discarded] segment too weak or short "
                        f"({segment_duration_ms} ms total, {voiced_duration_ms} ms above threshold, peak {peak_dbfs:.1f} dBFS)"
                    )

                pre_roll.clear()
                above_threshold_count = 0
                below_threshold_count = 0
                active_voice_chunks = 0
                peak_dbfs = -120.0
                with state_lock:
                    shared_state["active_segment_id"] = None
                    shared_state["preview_inflight_for"] = None
                recording = False
                recording_frames = []
        finally:
            stream.stop_stream()
            stream.close()
    except KeyboardInterrupt:
        log("\nStopping gated live session. Finishing queued transcriptions...")
    finally:
        pa.terminate()
        preview_queue.put(None)
        transcription_queue.put(None)
        preview_queue.join()
        transcription_queue.join()
        preview_thread.join(timeout=5)
        worker.join(timeout=5)
        if voice_engine is not None:
            for event in voice_engine.flush():
                log(event)
            for line in voice_engine.session_summary_lines():
                log(line)

    return 0


def resolve_live_settings(args: argparse.Namespace) -> dict:
    preset = LIVE_PRESETS[args.preset]
    keep_context = preset.keep_context
    no_fallback = preset.no_fallback
    engine = args.engine
    voice_engine_enabled = engine == "voice-engine" or bool((args.wake_phrase or "").strip())
    if engine == DEFAULT_LIVE_ENGINE and _gate_args_present(args):
        engine = "gated-cli"
    if voice_engine_enabled:
        engine = "gated-cli"
    if args.keep_context:
        keep_context = True
    if args.no_keep_context:
        keep_context = False
    if args.no_fallback:
        no_fallback = True
    if args.allow_fallback:
        no_fallback = False

    return {
        "engine": engine,
        "engine_label": "voice-engine" if voice_engine_enabled else engine,
        "voice_engine_enabled": voice_engine_enabled,
        "preset_name": args.preset,
        "preset_description": preset.description,
        "binary_flavor": args.binary_flavor or preset.binary_flavor or DEFAULT_BINARY_FLAVOR,
        "model": args.model or preset.model or DEFAULT_LIVE_MODEL,
        "draft_model": args.draft_model.strip() if args.draft_model else DEFAULT_DRAFT_MODEL,
        "threads": args.threads if args.threads is not None else recommended_thread_count(),
        "language": args.language,
        "step_ms": args.step_ms if args.step_ms is not None else preset.step_ms,
        "length_ms": args.length_ms if args.length_ms is not None else preset.length_ms,
        "keep_ms": args.keep_ms if args.keep_ms is not None else preset.keep_ms,
        "vad_threshold": args.vad_threshold if args.vad_threshold is not None else preset.vad_threshold,
        "freq_threshold": args.freq_threshold if args.freq_threshold is not None else preset.freq_threshold,
        "max_tokens": args.max_tokens if args.max_tokens is not None else preset.max_tokens,
        "audio_ctx": args.audio_ctx if args.audio_ctx is not None else preset.audio_ctx,
        "beam_size": args.beam_size if args.beam_size is not None else preset.beam_size,
        "no_fallback": no_fallback,
        "keep_context": keep_context,
        "no_gpu": not args.gpu,
        "initial_prompt": args.initial_prompt.strip() or None,
        "gate_dbfs": args.gate_dbfs if args.gate_dbfs is not None else preset.gate_dbfs,
        "gate_attack_ms": args.gate_attack_ms if args.gate_attack_ms is not None else preset.gate_attack_ms,
        "gate_release_ms": args.gate_release_ms if args.gate_release_ms is not None else preset.gate_release_ms,
        "gate_preroll_ms": args.gate_preroll_ms if args.gate_preroll_ms is not None else preset.gate_preroll_ms,
        "gate_min_ms": args.gate_min_ms if args.gate_min_ms is not None else preset.gate_min_ms,
        "gate_max_ms": args.gate_max_ms if args.gate_max_ms is not None else preset.gate_max_ms,
        "gate_frame_ms": args.gate_frame_ms if args.gate_frame_ms is not None else preset.gate_frame_ms,
        "context_chars": 0 if args.no_context_memory else max(0, args.context_chars),
        "draft_interval_ms": max(200, args.draft_interval_ms),
        "draft_min_ms": max(300, args.draft_min_ms),
        "draft_confidence": max(0.0, min(1.0, args.draft_confidence)),
        "draft_min_chars": max(1, args.draft_min_chars),
        "draft_streaming_enabled": not args.no_draft_streaming,
        "wake_phrase": ((args.wake_phrase or "").strip() or DEFAULT_WAKE_PHRASE) if voice_engine_enabled else None,
        "wake_aliases": [item.strip() for item in (args.wake_alias or []) if item and item.strip()],
        "known_terms": [item.strip() for item in (args.known_term or []) if item and item.strip()],
        "awake_timeout_s": max(1.0, float(args.awake_timeout_s)),
        "command_gap_s": max(0.2, float(args.command_gap_s)),
        "low_confidence_threshold": max(0.0, min(1.0, float(args.low_confidence_threshold))),
        "project_term_limit": max(0, int(args.project_term_limit)),
        "prompt_term_limit": max(0, int(args.prompt_term_limit)),
        "voice_profile_dir": Path(args.voice_profile_dir).expanduser().resolve()
        if (args.voice_profile_dir or "").strip()
        else default_voice_engine_state_dir(output_root()),
        "save_audio": args.save_audio,
        "output_file": Path(args.output_file).expanduser().resolve() if args.output_file else None,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a live local whisper.cpp transcription session from the microphone.")
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG, help="whisper.cpp release tag for prebuilt binaries")
    parser.add_argument(
        "--engine",
        default=DEFAULT_LIVE_ENGINE,
        choices=["stream", "gated-cli", "voice-engine"],
        help="live engine: raw whisper-stream, gated microphone capture feeding whisper-cli, or the standalone passive wake voice engine",
    )
    parser.add_argument(
        "--preset",
        default=DEFAULT_LIVE_PRESET,
        choices=sorted(LIVE_PRESETS),
        help="live-transcription preset tuned for this class of Windows laptop",
    )
    parser.add_argument(
        "--binary-flavor",
        default=None,
        choices=["plain", "blas", "cublas-11.8", "cublas-12.4"],
        help="prebuilt binary flavor; defaults to the selected preset",
    )
    parser.add_argument("--model", default=None, help="ggml model name to use for live transcription; defaults to the selected preset")
    parser.add_argument("--draft-model", default=DEFAULT_DRAFT_MODEL, help="for gated-cli draft streaming, model name to use for fast partials")
    parser.add_argument("--device-index", type=int, default=None, help="PyAudio input device index")
    parser.add_argument("--threads", type=int, default=None, help="number of CPU threads; defaults to an auto-tuned value")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="spoken language")
    parser.add_argument("--initial-prompt", default="", help="optional transcription prompt; used only by the gated-cli engine")
    parser.add_argument("--step-ms", type=int, default=None, help="audio step size in milliseconds; defaults to the selected preset")
    parser.add_argument("--length-ms", type=int, default=None, help="audio chunk length in milliseconds; defaults to the selected preset")
    parser.add_argument("--keep-ms", type=int, default=None, help="audio overlap to keep between chunks; defaults to the selected preset")
    parser.add_argument("--vad-threshold", type=float, default=None, help="voice activity detection threshold; defaults to the selected preset")
    parser.add_argument("--freq-threshold", type=float, default=None, help="high-pass frequency cutoff; defaults to the selected preset")
    parser.add_argument("--max-tokens", type=int, default=None, help="maximum tokens per audio chunk; defaults to the selected preset")
    parser.add_argument("--audio-ctx", type=int, default=None, help="audio context size; defaults to the selected preset")
    parser.add_argument("--beam-size", type=int, default=None, help="beam size for decoding; defaults to the selected preset")
    parser.add_argument("--gate-dbfs", type=float, default=None, help="microphone gate threshold in dBFS; when set, the launcher switches to gated-cli mode")
    parser.add_argument("--gate-attack-ms", type=int, default=None, help="how long audio must stay above the gate threshold before capture starts")
    parser.add_argument("--gate-release-ms", type=int, default=None, help="how long audio must stay below the gate threshold before capture stops")
    parser.add_argument("--gate-preroll-ms", type=int, default=None, help="how much audio to keep before the gate opens")
    parser.add_argument("--gate-min-ms", type=int, default=None, help="minimum above-threshold speech window before transcription runs")
    parser.add_argument("--gate-max-ms", type=int, default=None, help="maximum gated segment length before forced transcription")
    parser.add_argument("--gate-frame-ms", type=int, default=None, help="internal gate analysis frame size in milliseconds")
    parser.add_argument("--context-chars", type=int, default=DEFAULT_GATED_CONTEXT_CHARS, help="for gated-cli, trailing transcript characters to feed back as rolling context")
    parser.add_argument("--no-context-memory", action="store_true", help="disable rolling transcript context in gated-cli mode")
    parser.add_argument("--draft-interval-ms", type=int, default=DEFAULT_DRAFT_INTERVAL_MS, help="for gated-cli, how often to transcribe an open segment preview")
    parser.add_argument("--draft-min-ms", type=int, default=DEFAULT_DRAFT_MIN_MS, help="for gated-cli, minimum open-segment duration before preview streaming starts")
    parser.add_argument("--draft-confidence", type=float, default=DEFAULT_DRAFT_CONFIDENCE, help="for gated-cli, minimum average token confidence before a draft is streamed")
    parser.add_argument("--draft-min-chars", type=int, default=DEFAULT_DRAFT_MIN_CHARS, help="for gated-cli, minimum draft transcript length to emit")
    parser.add_argument("--no-draft-streaming", action="store_true", help="disable preview streaming for open gated segments")
    parser.add_argument("--wake-phrase", default="", help="enable the standalone voice engine with this wake phrase; defaults to EmploAI when voice-engine mode is selected")
    parser.add_argument("--wake-alias", action="append", default=[], help="additional acceptable wake-phrase variants")
    parser.add_argument("--known-term", action="append", default=[], help="manually seed the voice-engine vocabulary with a literal term or filename")
    parser.add_argument("--awake-timeout-s", type=float, default=DEFAULT_AWAKE_TIMEOUT_S, help="for the standalone voice engine, how long it stays awake after hearing the wake phrase")
    parser.add_argument("--command-gap-s", type=float, default=DEFAULT_COMMAND_GAP_S, help="for the standalone voice engine, idle gap before a spoken command is finalized")
    parser.add_argument("--low-confidence-threshold", type=float, default=DEFAULT_LOW_CONFIDENCE_THRESHOLD, help="for the standalone voice engine, confidence cutoff below which terms are added to review memory")
    parser.add_argument("--project-term-limit", type=int, default=DEFAULT_PROJECT_TERM_LIMIT, help="maximum number of repo-derived project terms to seed into the voice-engine vocabulary")
    parser.add_argument("--prompt-term-limit", type=int, default=DEFAULT_PROMPT_TERM_LIMIT, help="maximum number of literal terms and filenames to bias into the transcription prompt")
    parser.add_argument("--voice-profile-dir", default="", help="optional directory for standalone voice-engine profile and session state")
    parser.add_argument("--show-voice-profile", action="store_true", help="print the standalone voice-engine profile summary and exit")
    parser.add_argument("--gpu", action="store_true", help="allow GPU inference if the binary/backend supports it")
    keep_context_group = parser.add_mutually_exclusive_group()
    keep_context_group.add_argument("--keep-context", action="store_true", help="force context carry-over between chunks")
    keep_context_group.add_argument("--no-keep-context", action="store_true", help="disable context carry-over between chunks")
    fallback_group = parser.add_mutually_exclusive_group()
    fallback_group.add_argument("--no-fallback", action="store_true", help="disable decoder fallback to reduce hallucinated text")
    fallback_group.add_argument("--allow-fallback", action="store_true", help="allow decoder fallback even if the preset disables it")
    parser.add_argument("--save-audio", action="store_true", help="tell whisper-stream to save recorded audio")
    parser.add_argument("--output-file", default="", help="optional output text file path for whisper-stream")
    parser.add_argument("--list-input-devices", action="store_true", help="list input devices and exit")
    parser.add_argument("--show-presets", action="store_true", help="print the available live presets and exit")
    parser.add_argument("--spawn-window", action="store_true", help="launch whisper-stream in a dedicated console window")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = resolve_live_settings(args)

    if args.show_presets:
        print("Available whisper.cpp live presets:")
        for line in _preset_lines():
            print(f"  {line}")
        return 0

    if args.list_input_devices:
        for device in list_input_devices():
            marker = "*" if device["is_default"] else " "
            print(
                f"{marker} [{device['index']}] {device['name']} "
                f"(channels={device['max_input_channels']}, default_rate={device['default_sample_rate']})"
            )
        return 0

    voice_engine: Optional[StandaloneVoiceEngine] = None
    if settings["voice_engine_enabled"] or args.show_voice_profile:
        voice_engine = StandaloneVoiceEngine(
            repo_root=Path(__file__).resolve().parents[2],
            state_dir=settings["voice_profile_dir"],
            wake_phrase=settings["wake_phrase"] or DEFAULT_WAKE_PHRASE,
            wake_aliases=settings["wake_aliases"],
            known_terms=settings["known_terms"],
            awake_timeout_s=settings["awake_timeout_s"],
            command_gap_s=settings["command_gap_s"],
            low_confidence_threshold=settings["low_confidence_threshold"],
            project_term_limit=settings["project_term_limit"],
            prompt_term_limit=settings["prompt_term_limit"],
        )

    if args.show_voice_profile:
        print(json.dumps((voice_engine or StandaloneVoiceEngine(
            repo_root=Path(__file__).resolve().parents[2],
            state_dir=settings["voice_profile_dir"],
        )).profile_summary(), indent=2))
        return 0

    device_index = args.device_index if args.device_index is not None else _find_default_input_device_index()
    if device_index is None:
        raise SystemExit("No microphone input device was found")

    if args.spawn_window and settings["engine"] == "gated-cli":
        return _respawn_current_module_without_spawn_window()

    whisper_cli = ensure_prebuilt_whisper_cpp(release_tag=args.release_tag, flavor=settings["binary_flavor"])
    model_path = ensure_ggml_model(settings["model"])
    if settings["engine"] == "gated-cli":
        draft_model_name = settings["draft_model"] if settings["draft_streaming_enabled"] else None
        draft_model_path = ensure_ggml_model(draft_model_name) if draft_model_name else None
        return run_gated_cli_session(
            whisper_cli=whisper_cli,
            model_path=model_path,
            model_name=settings["model"],
            draft_model_path=draft_model_path,
            draft_model_name=draft_model_name,
            device_index=device_index,
            language=settings["language"],
            threads=settings["threads"],
            no_gpu=settings["no_gpu"],
            initial_prompt=settings["initial_prompt"],
            gate_dbfs=settings["gate_dbfs"],
            gate_attack_ms=settings["gate_attack_ms"],
            gate_release_ms=settings["gate_release_ms"],
            gate_preroll_ms=settings["gate_preroll_ms"],
            gate_min_ms=settings["gate_min_ms"],
            gate_max_ms=settings["gate_max_ms"],
            gate_frame_ms=settings["gate_frame_ms"],
            context_chars=settings["context_chars"],
            draft_interval_ms=settings["draft_interval_ms"],
            draft_min_ms=settings["draft_min_ms"],
            draft_confidence=settings["draft_confidence"],
            draft_min_chars=settings["draft_min_chars"],
            draft_streaming_enabled=settings["draft_streaming_enabled"],
            voice_engine=voice_engine,
        )

    whisper_stream_exe = whisper_cli.with_name("whisper-stream.exe")
    if not whisper_stream_exe.exists():
        raise SystemExit(f"Could not locate whisper-stream.exe next to {whisper_cli}")

    command = build_whisper_stream_command(
        whisper_stream_exe=whisper_stream_exe,
        model_path=model_path,
        capture_device=device_index,
        language=settings["language"],
        threads=settings["threads"],
        step_ms=settings["step_ms"],
        length_ms=settings["length_ms"],
        keep_ms=settings["keep_ms"],
        vad_threshold=settings["vad_threshold"],
        freq_threshold=settings["freq_threshold"],
        max_tokens=settings["max_tokens"],
        audio_ctx=settings["audio_ctx"],
        beam_size=settings["beam_size"],
        no_fallback=settings["no_fallback"],
        no_gpu=settings["no_gpu"],
        keep_context=settings["keep_context"],
        save_audio=settings["save_audio"],
        output_file=settings["output_file"],
    )

    print(
        f"Engine: {settings['engine_label']} | Preset: {settings['preset_name']} | {settings['preset_description']}\n"
        f"Model: {settings['model']} | Binary: {settings['binary_flavor']} | Threads: {settings['threads']}\n"
        f"Step: {settings['step_ms']} ms | Length: {settings['length_ms']} ms | Keep: {settings['keep_ms']} ms | "
        f"Keep context: {settings['keep_context']}\n"
        f"VAD: {settings['vad_threshold']} | Freq cutoff: {settings['freq_threshold']} | Max tokens: {settings['max_tokens']} | "
        f"Beam: {settings['beam_size']} | No fallback: {settings['no_fallback']}"
    )
    if settings["initial_prompt"]:
        print("Note: initial prompt was provided, but whisper-stream cannot use it. Use --engine gated-cli if you want the prompt to apply.")
    print("Note: whisper-stream does not support an initial prompt, so brand terms like EmploAI can still be less accurate than prompt-assisted batch runs.")
    print("Launching whisper-stream with:")
    print(" ".join(f'"{part}"' if " " in part else part for part in command))
    print(f"Using capture device index: {device_index}")
    print("Close the whisper-stream window or press Ctrl+C there to stop.")

    if args.spawn_window:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(command, creationflags=creationflags)
        return 0

    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
