import argparse
import math
import os
import queue
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.signal import resample_poly

INTERNAL_PY_DEPS = Path(__file__).resolve().parents[1] / "desktop_app" / "backend" / "_internal"
if os.name == "nt":
    os.add_dll_directory(str(INTERNAL_PY_DEPS))
sys.path.insert(0, str(INTERNAL_PY_DEPS))

import sounddevice as sd
import torch
from faster_whisper import WhisperModel
from transformers import WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperTokenizerFast
from transformers.utils import logging as hf_logging

APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
DEFAULT_MODEL_DIR = Path(
    os.getenv(
        APP_STT_HEBREW_MODEL_DIR_ENV,
        str(Path.home() / "Documents" / "Models" / "hebrew-whisper-small-continue-public-v1-runtime-ready"),
    )
)
# Mirror the English whisper.cpp gated "balanced" preset as the starting point.
DEFAULT_GATE_DBFS = -38.0
DEFAULT_ATTACK_MS = 150
DEFAULT_RELEASE_MS = 650
DEFAULT_PREROLL_MS = 300
DEFAULT_MIN_MS = 500
DEFAULT_MAX_MS = 6500
DEFAULT_FRAME_MS = 30
# 0 means "use the device default capture rate", then resample to 16 kHz for Whisper.
DEFAULT_SAMPLE_RATE = 0
DEFAULT_LANGUAGE = "hebrew"
DEFAULT_TASK = "transcribe"
DEFAULT_RUNTIME = "transformers"
WHISPER_SAMPLE_RATE = 16000
DEFAULT_ENGINE = "app-chunks"
DEFAULT_SEGMENT_MS = 850
DEFAULT_SILENCE_DBFS = -46.0
DEFAULT_COMMIT_SILENCE_MS = 850
DEFAULT_DRAFT_INTERVAL_MS = 850
DEFAULT_DRAFT_MIN_MS = 850
DEFAULT_DRAFT_MIN_CHARS = 4
DEFAULT_MAX_UTTERANCE_MS = 2550
DEFAULT_SHOW_DRAFTS = False
DEFAULT_EARLY_FINISH_MIN_MS = 850
DEFAULT_EARLY_FINISH_CONFIDENCE = 0.82
DEFAULT_DISCARD_CONFIDENCE = 0.62
APP_CHUNK_START_MARGIN_DB = 2.0
DEFAULT_MAX_NEW_TOKENS = 48
APP_CHUNK_PREROLL_MS = 300
DEFAULT_CT2_COMPUTE_TYPE = "int8_float32"
DEFAULT_CT2_QUANTIZATION = "int8_float32"
CT2_REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json")


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    hf_logging.set_verbosity_error()


def pcm16le_dbfs(frame: bytes) -> float:
    if not frame:
        return -120.0
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= 0.0:
        return -120.0
    return 20.0 * math.log10(rms / 32768.0)


def list_input_devices() -> list[dict]:
    devices = []
    default_input_index = None
    try:
        default_input_index = sd.default.device[0]
    except Exception:
        default_input_index = None
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        devices.append(
            {
                "index": index,
                "name": str(info.get("name", "")),
                "channels": int(info.get("max_input_channels", 0)),
                "default_sample_rate": int(info.get("default_samplerate", 0)),
                "is_default": bool(default_input_index == index),
            }
        )
    return devices


def default_input_device_index() -> int | None:
    for device in list_input_devices():
        if device["is_default"]:
            return int(device["index"])
    return None


def frame_bytes_from_ms(sample_rate: int, frame_ms: int) -> int:
    samples = max(1, int(sample_rate * frame_ms / 1000.0))
    return samples * 2


def frame_count_from_ms(sample_rate: int, frame_ms: int) -> int:
    return max(1, int(sample_rate * frame_ms / 1000.0))


def default_ct2_model_dir(model_dir: Path) -> Path:
    return model_dir.parent / f"{model_dir.name}-ct2"


def _normalize_runtime_language(language: str) -> str:
    value = (language or "").strip().lower()
    if value in {"he", "heb", "he-il", "hebrew"}:
        return "he"
    return value or "he"


def _ct2_model_ready(model_dir: Path) -> bool:
    return all((model_dir / filename).exists() for filename in CT2_REQUIRED_FILES)


def ensure_ct2_model(
    *,
    model_dir: Path,
    ct2_model_dir: Path,
    quantization: str,
    force: bool,
) -> Path:
    if _ct2_model_ready(ct2_model_dir) and not force:
        return ct2_model_dir

    copy_candidates = [
        "tokenizer.json",
        "preprocessor_config.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "normalizer.json",
        "processor_config.json",
        "vocab.json",
        "merges.txt",
    ]
    available = [name for name in copy_candidates if (model_dir / name).exists()]
    cmd = [
        sys.executable,
        "-m",
        "ctranslate2.converters.transformers",
        "--model",
        str(model_dir),
        "--output_dir",
        str(ct2_model_dir),
        "--quantization",
        quantization,
        "--force",
    ]
    if available:
        cmd.append("--copy_files")
        cmd.extend(available)

    ct2_model_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Converting Whisper model to CT2: {model_dir} -> {ct2_model_dir}")
    subprocess.run(cmd, check=True)
    if not _ct2_model_ready(ct2_model_dir):
        raise RuntimeError(f"CT2 conversion finished but required files are missing under {ct2_model_dir}")
    return ct2_model_dir


@dataclass
class TransformersRuntime:
    feature_extractor: WhisperFeatureExtractor
    tokenizer: WhisperTokenizerFast
    model: WhisperForConditionalGeneration


@dataclass
class FasterWhisperRuntime:
    model: WhisperModel


def load_transformers_model(model_dir: Path) -> TransformersRuntime:
    feature_extractor = WhisperFeatureExtractor.from_pretrained(model_dir)
    tokenizer = WhisperTokenizerFast.from_pretrained(model_dir)
    model = WhisperForConditionalGeneration.from_pretrained(model_dir)
    model.generation_config.suppress_tokens = None
    model.generation_config.begin_suppress_tokens = None
    model.config.suppress_tokens = None
    model.config.begin_suppress_tokens = None
    if not torch.cuda.is_available():
        model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    model.eval()
    return TransformersRuntime(feature_extractor=feature_extractor, tokenizer=tokenizer, model=model)


def load_faster_whisper_model(
    *,
    model_dir: Path,
    ct2_model_dir: Path,
    compute_type: str,
    quantization: str,
    cpu_threads: int | None,
    force_ct2_convert: bool,
) -> FasterWhisperRuntime:
    resolved_ct2_dir = ensure_ct2_model(
        model_dir=model_dir,
        ct2_model_dir=ct2_model_dir,
        quantization=quantization,
        force=force_ct2_convert,
    )
    model = WhisperModel(
        str(resolved_ct2_dir),
        device="cpu",
        compute_type=compute_type,
        cpu_threads=max(1, int(cpu_threads)) if cpu_threads else max(1, min(8, os.cpu_count() or 1)),
        num_workers=1,
    )
    return FasterWhisperRuntime(model=model)


def _pcm16_to_float32_audio(pcm: bytes, sample_rate: int) -> np.ndarray:
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate != WHISPER_SAMPLE_RATE:
        audio = resample_poly(audio, up=WHISPER_SAMPLE_RATE, down=sample_rate).astype(np.float32)
    return audio


def transcribe_pcm16_transformers(
    *,
    runtime: TransformersRuntime,
    pcm: bytes,
    sample_rate: int,
    language: str,
    task: str,
) -> tuple[str, float | None]:
    audio = _pcm16_to_float32_audio(pcm, sample_rate)
    inputs = runtime.feature_extractor(
        audio,
        sampling_rate=WHISPER_SAMPLE_RATE,
        return_tensors="pt",
        return_attention_mask=True,
    )
    with torch.inference_mode():
        outputs = runtime.model.generate(
            inputs["input_features"],
            attention_mask=inputs.get("attention_mask"),
            language=language,
            task=task,
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS,
            return_dict_in_generate=True,
            output_scores=True,
        )
    predicted_ids = outputs.sequences
    confidence = None
    scores = list(getattr(outputs, "scores", []) or [])
    if scores:
        generated_ids = predicted_ids[:, -len(scores) :]
        token_probs: list[float] = []
        for step, logits in enumerate(scores):
            probabilities = torch.softmax(logits.float(), dim=-1)
            token_id = int(generated_ids[0, step].item())
            token_probs.append(float(probabilities[0, token_id].item()))
        if token_probs:
            confidence = sum(token_probs) / len(token_probs)
    text = runtime.tokenizer.batch_decode(
        predicted_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()
    return text, confidence


def transcribe_pcm16_faster_whisper(
    *,
    runtime: FasterWhisperRuntime,
    pcm: bytes,
    sample_rate: int,
    language: str,
    task: str,
) -> tuple[str, Optional[float]]:
    audio = _pcm16_to_float32_audio(pcm, sample_rate)
    segments, _info = runtime.model.transcribe(
        audio,
        language=_normalize_runtime_language(language),
        task=task,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        without_timestamps=True,
        vad_filter=False,
        word_timestamps=False,
        suppress_blank=False,
    )
    text_parts: list[str] = []
    for segment in segments:
        chunk = (segment.text or "").strip()
        if chunk:
            text_parts.append(chunk)
    return " ".join(text_parts).strip(), None


def transcribe_pcm16(
    *,
    runtime_kind: str,
    runtime: TransformersRuntime | FasterWhisperRuntime,
    pcm: bytes,
    sample_rate: int,
    language: str,
    task: str,
) -> tuple[str, Optional[float]]:
    if runtime_kind == "faster-whisper":
        return transcribe_pcm16_faster_whisper(
            runtime=runtime,
            pcm=pcm,
            sample_rate=sample_rate,
            language=language,
            task=task,
        )
    return transcribe_pcm16_transformers(
        runtime=runtime,
        pcm=pcm,
        sample_rate=sample_rate,
        language=language,
        task=task,
    )


def transcribe_bytes(
    *,
    runtime_kind: str,
    runtime: TransformersRuntime | FasterWhisperRuntime,
    frames: list[bytes],
    sample_rate: int,
    language: str,
    task: str,
) -> tuple[str, float | None]:
    if not frames:
        return "", None
    return transcribe_pcm16(
        runtime_kind=runtime_kind,
        runtime=runtime,
        pcm=b"".join(frames),
        sample_rate=sample_rate,
        language=language,
        task=task,
    )


def chunk_duration_ms(frames: list[bytes], sample_rate: int) -> int:
    if not frames or sample_rate <= 0:
        return 0
    total_samples = sum(len(frame) // 2 for frame in frames)
    return int(total_samples * 1000 / sample_rate)


def normalize_transcript_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def transcript_words(text: str) -> list[str]:
    return [part for part in normalize_transcript_text(text).split(" ") if part]


def repeated_ngram_count(words: list[str], n: int) -> int:
    if len(words) < n:
        return 0
    counts: dict[tuple[str, ...], int] = {}
    best = 0
    for index in range(0, len(words) - n + 1):
        key = tuple(words[index : index + n])
        counts[key] = counts.get(key, 0) + 1
        best = max(best, counts[key])
    return best


def looks_repetitive(text: str) -> bool:
    words = transcript_words(text)
    if len(words) < 12:
        return False
    unique_ratio = len(set(words)) / float(len(words))
    if len(words) >= 24 and unique_ratio < 0.45:
        return True
    for n in (2, 3, 4):
        if repeated_ngram_count(words, n) >= 4:
            return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live terminal Hebrew transcription using a fine-tuned Whisper checkpoint.")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR), help="Path to the local fine-tuned Whisper model directory.")
    parser.add_argument(
        "--runtime",
        choices=["transformers", "faster-whisper"],
        default=DEFAULT_RUNTIME,
        help="Inference runtime to use for the Hebrew model.",
    )
    parser.add_argument(
        "--ct2-model-dir",
        default="",
        help="Optional CT2 model directory for the faster-whisper runtime. Defaults to a sibling *-ct2 folder.",
    )
    parser.add_argument(
        "--ct2-compute-type",
        default=DEFAULT_CT2_COMPUTE_TYPE,
        help="CTranslate2 compute type for faster-whisper (for example int8_float32 or float32).",
    )
    parser.add_argument(
        "--ct2-quantization",
        default=DEFAULT_CT2_QUANTIZATION,
        help="Quantization used when converting the HF model to CT2.",
    )
    parser.add_argument("--force-ct2-convert", action="store_true", help="Rebuild the CT2 model before starting faster-whisper.")
    parser.add_argument(
        "--engine",
        choices=["app-chunks", "gated"],
        default=DEFAULT_ENGINE,
        help="Capture mode. 'app-chunks' mimics the current English app voice path; 'gated' keeps the old noise-gated terminal behavior.",
    )
    parser.add_argument("--device-index", type=int, default=None, help="PyAudio input device index.")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="Microphone capture sample rate. Use 0 to follow the device default, like the English live engine.",
    )
    parser.add_argument("--gate-dbfs", type=float, default=DEFAULT_GATE_DBFS, help="Noise gate threshold in dBFS.")
    parser.add_argument("--gate-attack-ms", type=int, default=DEFAULT_ATTACK_MS, help="Time above threshold before opening the gate.")
    parser.add_argument("--gate-release-ms", type=int, default=DEFAULT_RELEASE_MS, help="Time below threshold before closing the gate.")
    parser.add_argument("--gate-preroll-ms", type=int, default=DEFAULT_PREROLL_MS, help="Audio to keep before gate open.")
    parser.add_argument("--gate-min-ms", type=int, default=DEFAULT_MIN_MS, help="Minimum above-threshold speech window.")
    parser.add_argument("--gate-max-ms", type=int, default=DEFAULT_MAX_MS, help="Maximum captured segment before forced close.")
    parser.add_argument("--gate-frame-ms", type=int, default=DEFAULT_FRAME_MS, help="Capture frame size for gating.")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Whisper language for generation.")
    parser.add_argument("--task", default=DEFAULT_TASK, help="Whisper generation task.")
    parser.add_argument("--segment-ms", type=int, default=DEFAULT_SEGMENT_MS, help="Chunk duration for app-chunks mode.")
    parser.add_argument("--silence-dbfs", type=float, default=DEFAULT_SILENCE_DBFS, help="Silence floor for app-chunks mode.")
    parser.add_argument("--commit-silence-ms", type=int, default=DEFAULT_COMMIT_SILENCE_MS, help="How much quiet audio ends the current app-chunks utterance.")
    parser.add_argument("--draft-interval-ms", type=int, default=DEFAULT_DRAFT_INTERVAL_MS, help="How often app-chunks mode refreshes the running transcript.")
    parser.add_argument("--draft-min-ms", type=int, default=DEFAULT_DRAFT_MIN_MS, help="Minimum accumulated utterance duration before app-chunks mode shows a draft.")
    parser.add_argument("--draft-min-chars", type=int, default=DEFAULT_DRAFT_MIN_CHARS, help="Minimum characters before a draft/final transcript is printed in app-chunks mode.")
    parser.add_argument("--max-utterance-ms", type=int, default=DEFAULT_MAX_UTTERANCE_MS, help="Force-finalize a single app-chunks utterance before the model starts drifting.")
    parser.add_argument("--show-drafts", action="store_true", default=DEFAULT_SHOW_DRAFTS, help="Print intermediate draft transcripts in app-chunks mode.")
    parser.add_argument("--early-finish-min-ms", type=int, default=DEFAULT_EARLY_FINISH_MIN_MS, help="Earliest point where a high-confidence app-chunks transcript can finalize immediately.")
    parser.add_argument("--early-finish-confidence", type=float, default=DEFAULT_EARLY_FINISH_CONFIDENCE, help="If app-chunks confidence reaches this level, finalize immediately.")
    parser.add_argument("--discard-confidence", type=float, default=DEFAULT_DISCARD_CONFIDENCE, help="Discard weak final transcripts below this confidence.")
    parser.add_argument(
        "--max-run-seconds",
        type=float,
        default=None,
        help="Optional self-test limit for how long to keep the stream open before exiting.",
    )
    parser.add_argument("--list-input-devices", action="store_true", help="List microphone devices and exit.")
    return parser.parse_args()


def run_app_chunk_session(
    *,
    runtime_kind: str,
    runtime: TransformersRuntime | FasterWhisperRuntime,
    device_index: int,
    sample_rate: int,
    language: str,
    task: str,
    segment_ms: int,
    silence_dbfs: float,
    commit_silence_ms: int,
    draft_interval_ms: int,
    draft_min_ms: int,
    draft_min_chars: int,
    max_utterance_ms: int,
    show_drafts: bool,
    early_finish_min_ms: int,
    early_finish_confidence: float,
    discard_confidence: float,
    max_run_seconds: float | None,
) -> int:
    block_ms = 50
    block_frames = frame_count_from_ms(sample_rate, block_ms)
    segment_frames_target = frame_count_from_ms(sample_rate, segment_ms)
    preroll_blocks = max(1, math.ceil(APP_CHUNK_PREROLL_MS / block_ms))
    started_at = time.perf_counter()
    audio_queue: queue.Queue[tuple[bytes, str | None]] = queue.Queue()

    def on_audio(indata, frames, stream_time, status) -> None:
        del frames, stream_time
        status_text = str(status).strip() if status else None
        audio_queue.put((bytes(indata), status_text))

    current_chunk_frames: list[bytes] = []
    current_chunk_samples = 0
    preroll_frame_buffer: deque[bytes] = deque(maxlen=preroll_blocks)
    current_chunk_preroll_frames: list[bytes] = []
    utterance_frames: list[bytes] = []
    silence_run_ms = 0
    utterance_peak_dbfs = -120.0
    last_draft_text = ""
    last_draft_ms = 0
    last_stable_text = ""
    segment_index = 0
    utterance_open = False
    start_open_dbfs = silence_dbfs + APP_CHUNK_START_MARGIN_DB

    print(
        "App-chunks mode: "
        f"{segment_ms} ms chunks | draft after {draft_min_ms} ms | "
        f"refresh every {draft_interval_ms} ms | quiet floor {silence_dbfs:.1f} dBFS | "
        f"start margin +{APP_CHUNK_START_MARGIN_DB:.1f} dB | "
        f"preroll {APP_CHUNK_PREROLL_MS} ms | "
        f"commit after {commit_silence_ms} ms quiet | max utterance {max_utterance_ms} ms | "
        f"early finish >= {early_finish_confidence:.2f} | discard < {discard_confidence:.2f}"
    )
    print("Listening. Press Ctrl+C to stop.")

    def maybe_emit_final(
        reason: str = "flush",
        prefetched_text: str | None = None,
        prefetched_confidence: float | None = None,
        prefetched_elapsed_s: float | None = None,
    ) -> None:
        nonlocal utterance_frames, silence_run_ms, utterance_peak_dbfs, last_draft_text, last_draft_ms, last_stable_text, segment_index, utterance_open
        utterance_ms = chunk_duration_ms(utterance_frames, sample_rate)
        if utterance_ms < draft_min_ms:
            if utterance_open:
                print(f"[capture stop] {utterance_ms} ms | reason={reason} | discarded")
            utterance_frames = []
            silence_run_ms = 0
            utterance_peak_dbfs = -120.0
            last_draft_text = ""
            last_draft_ms = 0
            last_stable_text = ""
            utterance_open = False
            return
        if prefetched_text is not None:
            text = normalize_transcript_text(prefetched_text)
            confidence = prefetched_confidence
            elapsed_s = max(0.0, float(prefetched_elapsed_s or 0.0))
        else:
            started = time.perf_counter()
            text, confidence = transcribe_bytes(
                runtime_kind=runtime_kind,
                runtime=runtime,
                frames=utterance_frames,
                sample_rate=sample_rate,
                language=language,
                task=task,
            )
            text = normalize_transcript_text(text)
            elapsed_s = time.perf_counter() - started
        speed_x = (utterance_ms / 1000.0) / elapsed_s if elapsed_s > 0 else 0.0
        if looks_repetitive(text) and last_stable_text:
            text = last_stable_text
        segment_index += 1
        confidence_label = "n/a" if confidence is None else f"{confidence:.2f}"
        if confidence is not None and confidence < discard_confidence:
            print(
                f"[capture stop] {utterance_ms} ms | peak {utterance_peak_dbfs:.1f} dBFS | "
                f"reason={reason} | conf {confidence_label} | discarded low confidence"
            )
        elif text and len(text) >= draft_min_chars:
            print(
                f"[capture stop] {utterance_ms} ms | peak {utterance_peak_dbfs:.1f} dBFS | "
                f"reason={reason} | conf {confidence_label} | "
                f"transcribe {elapsed_s:.2f}s | {speed_x:.1f}x realtime"
            )
            print(f"[final {segment_index}]")
            print(f"[transcript] {text}")
        else:
            print(
                f"[capture stop] {utterance_ms} ms | peak {utterance_peak_dbfs:.1f} dBFS | "
                f"reason={reason} | conf {confidence_label} | "
                f"transcribe {elapsed_s:.2f}s | no usable transcript"
            )
        utterance_frames = []
        silence_run_ms = 0
        utterance_peak_dbfs = -120.0
        last_draft_text = ""
        last_draft_ms = 0
        last_stable_text = ""
        utterance_open = False

    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=block_frames,
            device=device_index,
            channels=1,
            dtype="int16",
            callback=on_audio,
        ):
            while True:
                if max_run_seconds is not None and (time.perf_counter() - started_at) >= max_run_seconds:
                    if utterance_frames:
                        maybe_emit_final()
                    print(f"Reached max run time of {max_run_seconds:.1f}s. Stopping.")
                    return 0

                frame, status_text = audio_queue.get()
                if status_text:
                    print(f"[warn] {status_text}")
                if current_chunk_samples == 0:
                    current_chunk_preroll_frames = list(preroll_frame_buffer)
                current_chunk_frames.append(frame)
                preroll_frame_buffer.append(frame)
                current_chunk_samples += len(frame) // 2
                if current_chunk_samples < segment_frames_target:
                    continue

                chunk_pcm = b"".join(current_chunk_frames)
                current_chunk_frames = []
                current_chunk_samples = 0
                chunk_level = pcm16le_dbfs(chunk_pcm)
                open_threshold = silence_dbfs if utterance_open else start_open_dbfs
                if chunk_level >= open_threshold:
                    if not utterance_open:
                        utterance_open = True
                        if current_chunk_preroll_frames:
                            utterance_frames.extend(current_chunk_preroll_frames)
                        print(f"[capture start] level {chunk_level:.1f} dBFS | threshold {open_threshold:.1f} dBFS")
                    utterance_frames.append(chunk_pcm)
                    utterance_peak_dbfs = max(utterance_peak_dbfs, chunk_level)
                    silence_run_ms = 0
                elif utterance_frames:
                    silence_run_ms += segment_ms

                utterance_ms = chunk_duration_ms(utterance_frames, sample_rate)
                if utterance_frames and utterance_ms >= draft_min_ms and (utterance_ms - last_draft_ms) >= draft_interval_ms:
                    draft_started = time.perf_counter()
                    draft_text, draft_confidence = transcribe_bytes(
                        runtime_kind=runtime_kind,
                        runtime=runtime,
                        frames=utterance_frames,
                        sample_rate=sample_rate,
                        language=language,
                        task=task,
                    )
                    draft_elapsed_s = time.perf_counter() - draft_started
                    draft_text = normalize_transcript_text(draft_text)
                    if (
                        show_drafts
                        and
                        draft_text
                        and len(draft_text) >= draft_min_chars
                        and draft_text != last_draft_text
                        and not looks_repetitive(draft_text)
                    ):
                        confidence_label = "n/a" if draft_confidence is None else f"{draft_confidence:.2f}"
                        print(f"[draft] {utterance_ms} ms | peak {utterance_peak_dbfs:.1f} dBFS | conf {confidence_label}")
                        print(f"[transcript] {draft_text}")
                        last_draft_text = draft_text
                        last_stable_text = draft_text
                        last_draft_ms = utterance_ms
                    elif draft_text and len(draft_text) >= draft_min_chars and not looks_repetitive(draft_text):
                        last_stable_text = draft_text
                        last_draft_text = draft_text
                        last_draft_ms = utterance_ms

                    if (
                        utterance_ms >= early_finish_min_ms
                        and not last_stable_text
                        and draft_confidence is not None
                        and draft_confidence < discard_confidence
                    ):
                        maybe_emit_final("low_confidence", draft_text, draft_confidence, draft_elapsed_s)
                        continue

                    if (
                        draft_text
                        and len(draft_text) >= draft_min_chars
                        and not looks_repetitive(draft_text)
                        and draft_confidence is not None
                        and draft_confidence >= early_finish_confidence
                        and utterance_ms >= early_finish_min_ms
                    ):
                        maybe_emit_final("high_confidence", draft_text, draft_confidence, draft_elapsed_s)
                        continue

                if utterance_frames and silence_run_ms >= commit_silence_ms:
                    maybe_emit_final("silence")
                elif utterance_frames and utterance_ms >= max_utterance_ms:
                    maybe_emit_final("max_utterance")
    except KeyboardInterrupt:
        if utterance_frames:
            maybe_emit_final("keyboard_interrupt")
        print("\nStopped.")
        return 0


def main() -> int:
    configure_stdout()
    args = parse_args()

    if args.list_input_devices:
        for device in list_input_devices():
            marker = " (default)" if device["is_default"] else ""
            print(
                f"[{device['index']}] {device['name']}{marker} | "
                f"channels={device['channels']} | default_rate={device['default_sample_rate']}"
            )
        return 0

    model_dir = Path(args.model_dir).expanduser().resolve()
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    device_index = args.device_index if args.device_index is not None else default_input_device_index()
    if device_index is None:
        raise RuntimeError("No default input device found. Run with --list-input-devices and pass --device-index.")

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    runtime_kind = (args.runtime or DEFAULT_RUNTIME).strip().lower()
    started = time.perf_counter()
    if runtime_kind == "faster-whisper":
        ct2_model_dir = Path(args.ct2_model_dir).expanduser().resolve() if args.ct2_model_dir else default_ct2_model_dir(model_dir)
        runtime = load_faster_whisper_model(
            model_dir=model_dir,
            ct2_model_dir=ct2_model_dir,
            compute_type=(args.ct2_compute_type or DEFAULT_CT2_COMPUTE_TYPE).strip() or DEFAULT_CT2_COMPUTE_TYPE,
            quantization=(args.ct2_quantization or DEFAULT_CT2_QUANTIZATION).strip() or DEFAULT_CT2_QUANTIZATION,
            cpu_threads=max(1, min(8, os.cpu_count() or 1)),
            force_ct2_convert=bool(args.force_ct2_convert),
        )
    else:
        runtime = load_transformers_model(model_dir)
    load_elapsed = time.perf_counter() - started
    device_info = sd.query_devices(device_index)
    fallback_sample_rate = int(float(device_info.get("default_samplerate", 0) or WHISPER_SAMPLE_RATE))
    sample_rate = int(args.sample_rate) if int(args.sample_rate) > 0 else fallback_sample_rate
    print(f"Loaded model: {model_dir}")
    if runtime_kind == "faster-whisper":
        print(f"Runtime: {runtime_kind} | CT2: {ct2_model_dir} | loaded in {load_elapsed:.2f}s")
    else:
        print(f"Runtime: {runtime_kind} | loaded in {load_elapsed:.2f}s")
    print(f"Using input device index: {device_index}")
    print(f"Capture sample rate: {sample_rate} Hz (device default: {fallback_sample_rate} Hz)")
    print(f"Engine: {args.engine}")

    if args.engine == "app-chunks":
        return run_app_chunk_session(
            runtime_kind=runtime_kind,
            runtime=runtime,
            device_index=device_index,
            sample_rate=sample_rate,
            language=args.language,
            task=args.task,
            segment_ms=max(200, int(args.segment_ms)),
            silence_dbfs=float(args.silence_dbfs),
            commit_silence_ms=max(400, int(args.commit_silence_ms)),
            draft_interval_ms=max(200, int(args.draft_interval_ms)),
            draft_min_ms=max(400, int(args.draft_min_ms)),
            draft_min_chars=max(1, int(args.draft_min_chars)),
            max_utterance_ms=max(1000, int(args.max_utterance_ms)),
            show_drafts=bool(args.show_drafts),
            early_finish_min_ms=max(400, int(args.early_finish_min_ms)),
            early_finish_confidence=max(0.0, min(1.0, float(args.early_finish_confidence))),
            discard_confidence=max(0.0, min(1.0, float(args.discard_confidence))),
            max_run_seconds=args.max_run_seconds,
        )

    print(
        "Noise gate: "
        f"open at {args.gate_dbfs:.1f} dBFS | "
        f"attack {args.gate_attack_ms} ms | "
        f"release {args.gate_release_ms} ms | "
        f"min speech {args.gate_min_ms} ms | "
        f"max segment {args.gate_max_ms} ms | "
        f"frame {args.gate_frame_ms} ms"
    )

    frame_count = frame_count_from_ms(sample_rate, args.gate_frame_ms)
    attack_frames = max(1, math.ceil(args.gate_attack_ms / args.gate_frame_ms))
    release_frames = max(1, math.ceil(args.gate_release_ms / args.gate_frame_ms))
    min_frames = max(1, math.ceil(args.gate_min_ms / args.gate_frame_ms))
    max_frames = max(1, math.ceil(args.gate_max_ms / args.gate_frame_ms))
    preroll_frames = max(1, math.ceil(args.gate_preroll_ms / args.gate_frame_ms))

    preroll = deque(maxlen=preroll_frames)
    segment_frames: list[bytes] = []
    gate_open = False
    above_count = 0
    below_count = 0
    voiced_frames = 0
    peak_dbfs = -120.0
    segment_index = 0

    print("Listening. Press Ctrl+C to stop.")
    started_at = time.perf_counter()
    audio_queue: queue.Queue[tuple[bytes, str | None]] = queue.Queue()

    def on_audio(indata, frames, stream_time, status) -> None:
        del frames, stream_time
        status_text = str(status).strip() if status else None
        audio_queue.put((bytes(indata), status_text))

    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_count,
            device=device_index,
            channels=1,
            dtype="int16",
            callback=on_audio,
        ):
            while True:
                if args.max_run_seconds is not None and (time.perf_counter() - started_at) >= args.max_run_seconds:
                    print(f"Reached max run time of {args.max_run_seconds:.1f}s. Stopping.")
                    return 0
                frame, status_text = audio_queue.get()
                if status_text:
                    print(f"[warn] {status_text}")
                level = pcm16le_dbfs(frame)
                preroll.append(frame)
                peak_dbfs = max(peak_dbfs, level)

                if level >= args.gate_dbfs:
                    above_count += 1
                    below_count = 0
                else:
                    below_count += 1
                    if not gate_open:
                        above_count = 0

                if not gate_open and above_count >= attack_frames:
                    gate_open = True
                    segment_frames = list(preroll)
                    voiced_frames = 0
                    peak_dbfs = level
                    print(f"[gate open] level={level:.1f} dBFS")

                if gate_open:
                    segment_frames.append(frame)
                    if level >= args.gate_dbfs:
                        voiced_frames += 1

                    force_close = len(segment_frames) >= max_frames
                    should_close = below_count >= release_frames or force_close
                    if should_close:
                        total_ms = len(segment_frames) * args.gate_frame_ms
                        if voiced_frames >= min_frames:
                            segment_index += 1
                            pcm = b"".join(segment_frames)
                            print(
                                f"[gate close] segment {segment_index} | "
                                f"{total_ms} ms captured | peak {peak_dbfs:.1f} dBFS"
                            )
                            started = time.perf_counter()
                            text, confidence = transcribe_pcm16(
                                runtime_kind=runtime_kind,
                                runtime=runtime,
                                pcm=pcm,
                                sample_rate=sample_rate,
                                language=args.language,
                                task=args.task,
                            )
                            elapsed = time.perf_counter() - started
                            confidence_label = "n/a" if confidence is None else f"{confidence:.2f}"
                            print(f"[transcribe {elapsed:.2f}s | conf {confidence_label}] {text}")
                        else:
                            print(
                                f"[discarded] segment too weak or short "
                                f"({total_ms} ms total, {voiced_frames * args.gate_frame_ms} ms above threshold, "
                                f"peak {peak_dbfs:.1f} dBFS)"
                            )
                        gate_open = False
                        above_count = 0
                        below_count = 0
                        voiced_frames = 0
                        peak_dbfs = -120.0
                        segment_frames = []
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
