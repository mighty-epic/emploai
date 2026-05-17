from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import threading
import time
import wave
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

INTERNAL_PY_DEPS = Path(__file__).resolve().parents[2] / "desktop_app" / "backend" / "_internal"
if os.name == "nt":
    os.add_dll_directory(str(INTERNAL_PY_DEPS))
sys.path.insert(0, str(INTERNAL_PY_DEPS))

from mobile_app.backend.voice_runtime import (
    APP_STT_HEBREW_CPU_THREADS_ENV,
    APP_STT_HEBREW_DRAFT_MODEL_REPO_ENV,
    APP_STT_HEBREW_LANGUAGE_ENV,
    APP_STT_HEBREW_MODEL_REPO_ENV,
    APP_STT_KNOWN_TERMS_ENV,
    _transcribe_wav_bytes_hebrew,
    ensure_hebrew_model_downloaded,
    preload_hebrew_models,
)
from mobile_app.backend.whisper_cpp_live import run_gated_cli_session
from mobile_app.backend.whisper_cpp_live import build_segment_prompt
from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_RELEASE_TAG,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    list_input_devices,
    output_root,
    pcm16le_dbfs,
    pyaudio,
    recommended_thread_count,
)


DEFAULT_BACKEND = "whisper-cpp"
DEFAULT_LANGUAGE = "he"
DEFAULT_GATE_DBFS = -48.0
DEFAULT_GATE_ATTACK_MS = 20
DEFAULT_GATE_MIN_MS = 40
DEFAULT_GATE_RELEASE_MS = 900
DEFAULT_GATE_PREROLL_MS = 380
DEFAULT_GATE_FRAME_MS = 20
DEFAULT_GATE_MAX_MS = 6000
DEFAULT_CONTEXT_CHARS = 220
DEFAULT_DRAFT_INTERVAL_MS = 900
DEFAULT_DRAFT_MIN_MS = 900
DEFAULT_DRAFT_CONFIDENCE = 0.58
DEFAULT_DRAFT_MIN_CHARS = 1
DEFAULT_KNOWN_TERMS: tuple[str, ...] = ()
DEFAULT_MODEL_REPO = "ivrit-ai/whisper-large-v3-turbo-ct2"
DEFAULT_CPP_MODEL = "base"
DEFAULT_SAMPLE_RATE = 16_000
ADAPTIVE_GATE_WINDOW_MS = 1800
ADAPTIVE_GATE_PERCENTILE = 0.85
ADAPTIVE_GATE_MARGIN_DB = 6.0
ADAPTIVE_GATE_MAX_DBFS = -21.0
DEFAULT_CORRECTION_MIN_DURATION_MS = 900
DEFAULT_CORRECTION_MIN_CONFIDENCE = 0.76
DEFAULT_CORRECTION_MAX_BACKLOG = 2
DEFAULT_CORRECTION_MIN_SCORE_DELTA = 0.01
_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")
_LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")


def _respawn_current_module_without_spawn_window() -> int:
    command = [
        sys.executable,
        "-m",
        "mobile_app.backend.hebrew_voice_live",
        *[arg for arg in sys.argv[1:] if arg != "--spawn-window"],
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    subprocess.Popen(command, creationflags=creationflags)
    return 0


def _find_default_input_device_index() -> Optional[int]:
    for device in list_input_devices():
        if device.get("is_default"):
            return int(device["index"])
    return None


def _combined_wav_bytes(*, frames: list[bytes], sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(frames))
    return output.getvalue()


def _build_runtime_prompt(
    *,
    base_prompt: Optional[str],
    recent_transcripts: list[str],
    context_chars: int,
    known_terms: list[str],
) -> Optional[str]:
    term_prompt = ""
    if known_terms:
        term_prompt = "Prefer these literal project terms and filenames exactly if heard: " + ", ".join(known_terms) + "."
    merged_base = "\n".join(part for part in ((base_prompt or "").strip(), term_prompt) if part)
    return build_segment_prompt(
        base_prompt=merged_base or None,
        recent_transcripts=recent_transcripts,
        context_chars=context_chars,
    )


def _adaptive_gate_dbfs(*, configured_gate_dbfs: float, ambient_levels: deque[float]) -> float:
    if not ambient_levels:
        return configured_gate_dbfs
    ordered_levels = sorted(float(level) for level in ambient_levels)
    if not ordered_levels:
        return configured_gate_dbfs
    index = min(len(ordered_levels) - 1, max(0, int(round((len(ordered_levels) - 1) * ADAPTIVE_GATE_PERCENTILE))))
    ambient_anchor = ordered_levels[index]
    return min(ADAPTIVE_GATE_MAX_DBFS, max(configured_gate_dbfs, ambient_anchor + ADAPTIVE_GATE_MARGIN_DB))


def _hebrew_char_ratio(text: str) -> float:
    content = [char for char in text if not char.isspace() and not re.match(r"[.,!?;:'\"()\[\]{}\-_/]", char)]
    if not content:
        return 0.0
    hebrew_chars = sum(1 for char in content if _HEBREW_CHAR_PATTERN.fullmatch(char))
    return hebrew_chars / float(len(content))


def _contains_garbled_chars(text: str) -> bool:
    for char in text:
        if char.isspace() or char.isdigit():
            continue
        if _HEBREW_CHAR_PATTERN.fullmatch(char) or _LATIN_CHAR_PATTERN.fullmatch(char):
            continue
        if re.match(r"[.,!?;:'\"()\[\]{}\-_/]", char):
            continue
        if ord(char) > 127:
            return True
    return False


def _looks_suspicious(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return True
    compact = normalized.replace(" ", "")
    if "?" * 5 in normalized:
        return True
    if re.search(r"(.)\1{5,}", compact):
        return True
    if _contains_garbled_chars(normalized):
        return True
    alpha_chars = sum(1 for char in normalized if char.isalpha())
    if alpha_chars and _hebrew_char_ratio(normalized) < 0.45:
        return True
    return False


def _transcript_quality_score(text: str, confidence: Optional[float]) -> float:
    normalized = (text or "").strip()
    if not normalized:
        return -1.0
    words = [part for part in normalized.split() if part]
    score = 0.45 * _hebrew_char_ratio(normalized)
    score += 0.35 * max(0.0, min(1.0, float(confidence))) if confidence is not None else 0.0
    score += 0.20 * min(len(words), 4) / 4.0
    if _looks_suspicious(normalized):
        score -= 0.55
    return score


def _should_request_correction(*, transcript: str, confidence: Optional[float], duration_ms: int) -> bool:
    if _looks_suspicious(transcript):
        return True
    if duration_ms >= DEFAULT_CORRECTION_MIN_DURATION_MS and (confidence is None or confidence < DEFAULT_CORRECTION_MIN_CONFIDENCE):
        return True
    return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standalone Hebrew faster-whisper microphone tester.")
    parser.add_argument(
        "--backend",
        choices=["whisper-cpp", "faster-whisper"],
        default=DEFAULT_BACKEND,
        help="live Hebrew backend: faster multilingual whisper.cpp by default, or the slower fine-tuned faster-whisper path",
    )
    parser.add_argument("--device-index", type=int, default=None, help="PyAudio input device index")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE, help="preferred microphone sample rate; falls back to the device default if unsupported")
    parser.add_argument("--threads", type=int, default=None, help="number of CPU threads for the Hebrew model")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="spoken language code")
    parser.add_argument("--cpp-model", default=DEFAULT_CPP_MODEL, help="whisper.cpp multilingual model name for the live Hebrew path")
    parser.add_argument("--model-repo", default=DEFAULT_MODEL_REPO, help="final Hebrew faster-whisper repo to use")
    parser.add_argument("--draft-model-repo", default="", help="optional draft Hebrew faster-whisper repo; defaults to the final repo")
    parser.add_argument("--initial-prompt", default="", help="optional transcription prompt")
    parser.add_argument("--known-term", action="append", default=[], help="extra literal term or filename to bias into the prompt")
    parser.add_argument("--gate-dbfs", type=float, default=DEFAULT_GATE_DBFS, help="microphone gate threshold in dBFS")
    parser.add_argument("--gate-attack-ms", type=int, default=DEFAULT_GATE_ATTACK_MS, help="audio must stay above threshold this long before capture opens")
    parser.add_argument("--gate-release-ms", type=int, default=DEFAULT_GATE_RELEASE_MS, help="audio must stay below threshold this long before capture closes")
    parser.add_argument("--gate-preroll-ms", type=int, default=DEFAULT_GATE_PREROLL_MS, help="audio kept before the gate opens")
    parser.add_argument("--gate-min-ms", type=int, default=DEFAULT_GATE_MIN_MS, help="minimum above-threshold speech window before transcription runs")
    parser.add_argument("--gate-max-ms", type=int, default=DEFAULT_GATE_MAX_MS, help="maximum gated segment length before forced transcription")
    parser.add_argument("--gate-frame-ms", type=int, default=DEFAULT_GATE_FRAME_MS, help="internal gate analysis frame size in milliseconds")
    parser.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS, help="trailing transcript characters to feed back as rolling context")
    parser.add_argument("--draft-interval-ms", type=int, default=DEFAULT_DRAFT_INTERVAL_MS, help="how often to transcribe an open segment preview")
    parser.add_argument("--draft-min-ms", type=int, default=DEFAULT_DRAFT_MIN_MS, help="minimum open-segment duration before preview streaming starts")
    parser.add_argument("--draft-confidence", type=float, default=DEFAULT_DRAFT_CONFIDENCE, help="minimum Hebrew segment confidence before a draft is shown")
    parser.add_argument("--draft-min-chars", type=int, default=DEFAULT_DRAFT_MIN_CHARS, help="minimum draft transcript length to emit")
    parser.add_argument("--no-context-memory", action="store_true", help="disable rolling transcript context")
    parser.add_argument("--no-draft-streaming", action="store_true", help="disable preview streaming for open segments")
    parser.add_argument("--force-model-download", action="store_true", help="re-download the Hebrew model before starting")
    parser.add_argument("--list-input-devices", action="store_true", help="list input devices and exit")
    parser.add_argument("--spawn-window", action="store_true", help="launch the tester in a dedicated console window")
    return parser.parse_args()


def _compose_initial_prompt(*, base_prompt: Optional[str], known_terms: list[str]) -> Optional[str]:
    term_prompt = ""
    if known_terms:
        term_prompt = "Prefer these literal project terms and filenames exactly if heard: " + ", ".join(known_terms) + "."
    merged = "\n".join(part for part in (((base_prompt or "").strip()), term_prompt) if part)
    return merged or None


def _run_whisper_cpp_hebrew_session(
    *,
    device_index: int,
    threads: Optional[int],
    base_prompt: Optional[str],
    known_terms: list[str],
    language: str,
    cpp_model: str,
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
) -> int:
    whisper_cli = ensure_prebuilt_whisper_cpp(release_tag=DEFAULT_RELEASE_TAG, flavor=DEFAULT_BINARY_FLAVOR)
    model_path = ensure_ggml_model(cpp_model)
    effective_threads = int(threads) if threads is not None and int(threads) > 0 else recommended_thread_count()
    initial_prompt = _compose_initial_prompt(base_prompt=base_prompt, known_terms=known_terms)
    correction_queue: Queue = Queue()
    correction_sentinel = object()

    def correction_worker() -> None:
        try:
            ensure_hebrew_model_downloaded(final=True)
            preload_hebrew_models()
            print("Hebrew correction model ready.", flush=True)
        except Exception as exc:
            print(f"Hebrew correction model unavailable: {exc}", flush=True)
            while True:
                item = correction_queue.get()
                correction_queue.task_done()
                if item is correction_sentinel:
                    break
            return

        while True:
            item = correction_queue.get()
            if item is correction_sentinel:
                correction_queue.task_done()
                break

            audio_path = Path(str(item["audio_path"]))
            segment_index = int(item["segment_index"])
            baseline_text = str(item["transcript"])
            baseline_confidence = item.get("confidence")
            prompt = str(item.get("prompt") or "") or None
            started_at = time.perf_counter()
            try:
                candidate_text, candidate_confidence = _transcribe_wav_bytes_hebrew(
                    audio_path.read_bytes(),
                    sequence=segment_index,
                    revision=segment_index,
                    initial_prompt=prompt,
                    final=True,
                )
                candidate_text = candidate_text.strip()
                if candidate_text:
                    baseline_score = _transcript_quality_score(baseline_text, baseline_confidence if isinstance(baseline_confidence, (int, float)) else None)
                    candidate_score = _transcript_quality_score(candidate_text, candidate_confidence)
                    confidence_improved = (
                        candidate_confidence is not None
                        and isinstance(baseline_confidence, (int, float))
                        and candidate_confidence >= float(baseline_confidence) + 0.03
                    )
                    if candidate_text != baseline_text and (
                        (_looks_suspicious(baseline_text) and not _looks_suspicious(candidate_text))
                        or confidence_improved
                        or candidate_score >= baseline_score + DEFAULT_CORRECTION_MIN_SCORE_DELTA
                    ):
                        print(
                            f"[correction {segment_index}] {time.perf_counter() - started_at:.2f}s | "
                            f"base {baseline_score:.2f} -> heb {candidate_score:.2f}\n"
                            f"[{time.strftime('%H:%M:%S')}] {candidate_text}",
                            flush=True,
                        )
            except Exception as exc:
                print(f"[correction {segment_index}] failed: {exc}", flush=True)
            finally:
                correction_queue.task_done()

    correction_thread = threading.Thread(target=correction_worker, daemon=True)
    correction_thread.start()

    def on_final_result(result: dict[str, object]) -> None:
        transcript = str(result.get("transcript") or "")
        confidence_value = result.get("confidence")
        confidence = float(confidence_value) if isinstance(confidence_value, (int, float)) else None
        duration_ms = int(result.get("duration_ms") or 0)
        if not _should_request_correction(transcript=transcript, confidence=confidence, duration_ms=duration_ms):
            return
        if correction_queue.qsize() >= DEFAULT_CORRECTION_MAX_BACKLOG:
            return
        correction_queue.put(result)

    print(
        f"Starting Hebrew live session with whisper.cpp backend.\n"
        f"Model: {cpp_model} | Threads: {effective_threads} | Gate threshold: {gate_dbfs:.1f} dBFS | "
        f"Draft streaming: off"
    )
    try:
        return run_gated_cli_session(
            whisper_cli=whisper_cli,
            model_path=model_path,
            model_name=cpp_model,
            draft_model_path=None,
            draft_model_name=None,
            device_index=device_index,
            language=language,
            threads=effective_threads,
            no_gpu=True,
            initial_prompt=initial_prompt,
            gate_dbfs=gate_dbfs,
            gate_attack_ms=gate_attack_ms,
            gate_release_ms=gate_release_ms,
            gate_preroll_ms=gate_preroll_ms,
            gate_min_ms=gate_min_ms,
            gate_max_ms=gate_max_ms,
            gate_frame_ms=gate_frame_ms,
            context_chars=context_chars,
            draft_interval_ms=draft_interval_ms,
            draft_min_ms=draft_min_ms,
            draft_confidence=draft_confidence,
            draft_min_chars=draft_min_chars,
            draft_streaming_enabled=False,
            voice_engine=None,
            on_final_result=on_final_result,
        )
    finally:
        correction_queue.put(correction_sentinel)
        try:
            correction_queue.join()
        except Exception:
            pass
        correction_thread.join(timeout=2)


def run_hebrew_live_session(
    *,
    device_index: int,
    preferred_sample_rate: int,
    base_prompt: Optional[str],
    known_terms: list[str],
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
) -> int:
    if pyaudio is None:
        raise SystemExit("PyAudio is not installed, so Hebrew microphone capture is unavailable")

    chunk_ms = max(10, int(gate_frame_ms))
    live_output_dir = output_root() / "live_hebrew"
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

    def log(message: str) -> None:
        with print_lock:
            print(message, flush=True)

    def final_worker() -> None:
        while True:
            item = transcription_queue.get()
            if item is None:
                transcription_queue.task_done()
                break

            wav_bytes, queued_segment_index, queued_peak_dbfs, queued_duration_ms = item
            try:
                with state_lock:
                    recent_transcripts = list(shared_state["recent_transcripts"])
                segment_prompt = _build_runtime_prompt(
                    base_prompt=base_prompt,
                    recent_transcripts=recent_transcripts,
                    context_chars=context_chars,
                    known_terms=known_terms,
                )
                started_at = time.perf_counter()
                transcript, _confidence = _transcribe_wav_bytes_hebrew(
                    wav_bytes,
                    sequence=queued_segment_index,
                    revision=queued_segment_index,
                    initial_prompt=segment_prompt,
                    final=True,
                )
                elapsed_s = time.perf_counter() - started_at
                transcript = transcript.strip()
                if transcript:
                    with state_lock:
                        shared_state["recent_transcripts"].append(transcript)
                        shared_state["last_partial_by_segment"].pop(queued_segment_index, None)
                    log(
                        f"[segment {queued_segment_index}] {queued_duration_ms} ms captured | peak {queued_peak_dbfs:.1f} dBFS | transcribe {elapsed_s:.2f}s\n"
                        f"[{time.strftime('%H:%M:%S')}] {transcript}"
                    )
                else:
                    log(f"[segment {queued_segment_index}] empty transcript after {queued_duration_ms} ms capture | transcribe {elapsed_s:.2f}s")
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

            wav_bytes, preview_segment_id, preview_duration_ms = item
            try:
                with state_lock:
                    recent_transcripts = list(shared_state["recent_transcripts"])
                    active_segment_id = shared_state["active_segment_id"]
                    previous_partial = shared_state["last_partial_by_segment"].get(preview_segment_id, "")
                if active_segment_id != preview_segment_id:
                    continue

                segment_prompt = _build_runtime_prompt(
                    base_prompt=base_prompt,
                    recent_transcripts=recent_transcripts,
                    context_chars=context_chars,
                    known_terms=known_terms,
                )
                started_at = time.perf_counter()
                transcript, confidence = _transcribe_wav_bytes_hebrew(
                    wav_bytes,
                    sequence=preview_segment_id,
                    revision=preview_segment_id,
                    initial_prompt=segment_prompt,
                    final=False,
                )
                elapsed_s = time.perf_counter() - started_at
                transcript = transcript.strip()
                if not transcript:
                    continue
                with state_lock:
                    active_segment_id = shared_state["active_segment_id"]
                if active_segment_id != preview_segment_id:
                    continue
                if confidence is None or confidence < draft_confidence:
                    continue
                if len(transcript) < draft_min_chars:
                    continue
                if transcript == previous_partial:
                    continue
                with state_lock:
                    shared_state["last_partial_by_segment"][preview_segment_id] = transcript
                conf_label = "n/a" if confidence is None else f"{confidence:.2f}"
                log(
                    f"[draft {preview_segment_id}] {preview_duration_ms} ms | conf {conf_label} | transcribe {elapsed_s:.2f}s\n"
                    f"[{time.strftime('%H:%M:%S')}] {transcript}"
                )
            except Exception as exc:
                log(f"[draft {preview_segment_id}] preview failed: {exc}")
            finally:
                with state_lock:
                    if shared_state["preview_inflight_for"] == preview_segment_id:
                        shared_state["preview_inflight_for"] = None
                preview_queue.task_done()

    final_thread = threading.Thread(target=final_worker, daemon=True)
    preview_thread = threading.Thread(target=preview_worker, daemon=True)
    final_thread.start()
    preview_thread.start()

    pa = pyaudio.PyAudio()
    try:
        device_info = pa.get_device_info_by_index(int(device_index))
        fallback_sample_rate = int(float(device_info.get("defaultSampleRate") or DEFAULT_SAMPLE_RATE))
        sample_rate = max(8_000, int(preferred_sample_rate or fallback_sample_rate))
        chunk_frames = max(1, int(sample_rate * chunk_ms / 1000.0))
        attack_chunks = max(1, int(round(gate_attack_ms / float(chunk_ms))))
        release_chunks = max(1, int(round(gate_release_ms / float(chunk_ms))))
        preroll_chunks = max(1, int(round(gate_preroll_ms / float(chunk_ms))))
        min_chunks = max(1, int(round(gate_min_ms / float(chunk_ms))))
        max_chunks = max(min_chunks, int(round(gate_max_ms / float(chunk_ms))))
        ambient_window_chunks = max(12, int(round(ADAPTIVE_GATE_WINDOW_MS / float(chunk_ms))))

        log(
            f"Standalone Hebrew live tester armed on [{device_index}] {device_info.get('name')}.\n"
            f"Gate: {gate_dbfs:.1f} dBFS | attack {gate_attack_ms} ms | release {gate_release_ms} ms | "
            f"min speech {gate_min_ms} ms | max segment {gate_max_ms} ms | frame {chunk_ms} ms | "
            f"context memory {context_chars} chars | draft streaming {draft_interval_ms} ms | "
            f"draft confidence {draft_confidence:.2f} | preferred sample rate {sample_rate} Hz"
        )
        log(
            f"Model: {os.environ.get(APP_STT_HEBREW_MODEL_REPO_ENV, DEFAULT_MODEL_REPO)} | "
            f"Known terms: {', '.join(known_terms) if known_terms else '(none)'}"
        )
        log("Speak above the threshold. Press Ctrl+C to stop.")
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=int(device_index),
                frames_per_buffer=chunk_frames,
            )
        except Exception:
            sample_rate = fallback_sample_rate
            chunk_frames = max(1, int(sample_rate * chunk_ms / 1000.0))
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=int(device_index),
                frames_per_buffer=chunk_frames,
            )
            log(f"Preferred sample rate was unsupported. Falling back to device default {sample_rate} Hz.")
        try:
            pre_roll: deque[bytes] = deque(maxlen=preroll_chunks)
            ambient_levels: deque[float] = deque(maxlen=ambient_window_chunks)
            above_threshold_count = 0
            below_threshold_count = 0
            active_voice_chunks = 0
            peak_dbfs = -120.0
            segment_index = 0
            recording = False
            idle_gate_dbfs = gate_dbfs
            recording_gate_dbfs = gate_dbfs
            recording_frames: list[bytes] = []

            while True:
                frame_bytes = stream.read(chunk_frames, exception_on_overflow=False)
                level_dbfs = pcm16le_dbfs(frame_bytes)

                if not recording:
                    ambient_levels.append(level_dbfs)
                    idle_gate_dbfs = _adaptive_gate_dbfs(
                        configured_gate_dbfs=gate_dbfs,
                        ambient_levels=ambient_levels,
                    )
                    above_threshold = level_dbfs >= idle_gate_dbfs
                    pre_roll.append(frame_bytes)
                    above_threshold_count = above_threshold_count + 1 if above_threshold else 0
                    if above_threshold_count >= attack_chunks:
                        recording = True
                        recording_gate_dbfs = idle_gate_dbfs
                        recording_frames = list(pre_roll)
                        active_voice_chunks = above_threshold_count
                        below_threshold_count = 0
                        peak_dbfs = level_dbfs
                        with state_lock:
                            shared_state["active_segment_id"] = segment_index + 1
                            shared_state["last_preview_ms"] = 0
                            shared_state["preview_inflight_for"] = None
                        log(f"[gate open] level={level_dbfs:.1f} dBFS | threshold {recording_gate_dbfs:.1f} dBFS")
                    continue

                recording_frames.append(frame_bytes)
                peak_dbfs = max(peak_dbfs, level_dbfs)
                above_threshold = level_dbfs >= recording_gate_dbfs
                if above_threshold:
                    active_voice_chunks += 1
                    below_threshold_count = 0
                else:
                    below_threshold_count += 1

                should_close = below_threshold_count >= release_chunks or len(recording_frames) >= max_chunks
                current_duration_ms = len(recording_frames) * chunk_ms
                current_segment_id = segment_index + 1
                with state_lock:
                    preview_inflight_for = shared_state["preview_inflight_for"]
                    last_preview_ms = shared_state["last_preview_ms"]
                should_preview = (
                    preview_inflight_for is None
                    and current_duration_ms >= draft_min_ms
                    and (current_duration_ms - last_preview_ms) >= draft_interval_ms
                )
                if should_preview:
                    preview_queue.put(
                        (
                            _combined_wav_bytes(frames=list(recording_frames), sample_rate=sample_rate),
                            current_segment_id,
                            current_duration_ms,
                        )
                    )
                    with state_lock:
                        shared_state["preview_inflight_for"] = current_segment_id
                        shared_state["last_preview_ms"] = current_duration_ms

                if not should_close:
                    continue

                segment_duration_ms = len(recording_frames) * chunk_ms
                voiced_duration_ms = active_voice_chunks * chunk_ms

                if voiced_duration_ms >= gate_min_ms and len(recording_frames) >= min_chunks:
                    segment_index += 1
                    transcription_queue.put(
                        (
                            _combined_wav_bytes(frames=recording_frames, sample_rate=sample_rate),
                            segment_index,
                            peak_dbfs,
                            segment_duration_ms,
                        )
                    )
                    log(
                        f"[gate close] queued segment {segment_index} | {segment_duration_ms} ms captured | "
                        f"peak {peak_dbfs:.1f} dBFS | threshold {recording_gate_dbfs:.1f} dBFS | pending {transcription_queue.qsize()}"
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
                recording_gate_dbfs = idle_gate_dbfs
                recording_frames = []
        except KeyboardInterrupt:
            log("Stopping Hebrew live tester...")
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        pa.terminate()
        transcription_queue.put(None)
        preview_queue.put(None)
        transcription_queue.join()
        preview_queue.join()

    return 0


def main() -> int:
    args = _parse_args()
    if args.list_input_devices:
        for device in list_input_devices():
            marker = "*" if device["is_default"] else " "
            print(
                f"{marker} [{device['index']}] {device['name']} "
                f"(channels={device['max_input_channels']}, default_rate={device['default_sample_rate']})"
            )
        return 0

    if args.spawn_window:
        return _respawn_current_module_without_spawn_window()

    device_index = args.device_index if args.device_index is not None else _find_default_input_device_index()
    if device_index is None:
        raise SystemExit("No microphone input device was found")

    os.environ[APP_STT_HEBREW_MODEL_REPO_ENV] = (args.model_repo or DEFAULT_MODEL_REPO).strip()
    os.environ[APP_STT_HEBREW_DRAFT_MODEL_REPO_ENV] = (args.draft_model_repo or args.model_repo or DEFAULT_MODEL_REPO).strip()
    os.environ[APP_STT_HEBREW_LANGUAGE_ENV] = (args.language or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    if args.threads is not None and int(args.threads) > 0:
        os.environ[APP_STT_HEBREW_CPU_THREADS_ENV] = str(int(args.threads))
    known_terms = [*DEFAULT_KNOWN_TERMS, *[item.strip() for item in args.known_term if item and item.strip()]]
    deduped_known_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in known_terms:
        key = term.lower()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        deduped_known_terms.append(term)
    os.environ[APP_STT_KNOWN_TERMS_ENV] = ",".join(deduped_known_terms)

    if args.backend == "whisper-cpp":
        return _run_whisper_cpp_hebrew_session(
            device_index=device_index,
            threads=args.threads,
            base_prompt=(args.initial_prompt or "").strip() or None,
            known_terms=deduped_known_terms,
            language=(args.language or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE,
            cpp_model=(args.cpp_model or DEFAULT_CPP_MODEL).strip() or DEFAULT_CPP_MODEL,
            gate_dbfs=args.gate_dbfs,
            gate_attack_ms=args.gate_attack_ms,
            gate_release_ms=args.gate_release_ms,
            gate_preroll_ms=args.gate_preroll_ms,
            gate_min_ms=args.gate_min_ms,
            gate_max_ms=args.gate_max_ms,
            gate_frame_ms=args.gate_frame_ms,
            context_chars=0 if args.no_context_memory else max(0, args.context_chars),
            draft_interval_ms=max(200, int(args.draft_interval_ms)),
            draft_min_ms=max(300, int(args.draft_min_ms)),
            draft_confidence=max(0.0, min(1.0, float(args.draft_confidence))),
            draft_min_chars=max(1, int(args.draft_min_chars)),
        )

    ensure_hebrew_model_downloaded(force=args.force_model_download, final=True)
    ensure_hebrew_model_downloaded(force=args.force_model_download, final=False)
    preload_timings = preload_hebrew_models()
    print(
        f"Preloaded Hebrew model(s): final {preload_timings['final_seconds']}s"
        + (f" | draft {preload_timings['draft_seconds']}s" if preload_timings["draft_seconds"] else "")
    )

    return run_hebrew_live_session(
        device_index=device_index,
        preferred_sample_rate=max(8_000, int(args.sample_rate)),
        base_prompt=(args.initial_prompt or "").strip() or None,
        known_terms=deduped_known_terms,
        gate_dbfs=args.gate_dbfs,
        gate_attack_ms=args.gate_attack_ms,
        gate_release_ms=args.gate_release_ms,
        gate_preroll_ms=args.gate_preroll_ms,
        gate_min_ms=args.gate_min_ms,
        gate_max_ms=args.gate_max_ms,
        gate_frame_ms=args.gate_frame_ms,
        context_chars=0 if args.no_context_memory else max(0, args.context_chars),
        draft_interval_ms=max(200, int(args.draft_interval_ms)),
        draft_min_ms=max(300, int(args.draft_min_ms)),
        draft_confidence=max(0.0, min(1.0, float(args.draft_confidence))),
        draft_min_chars=max(1, int(args.draft_min_chars)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
