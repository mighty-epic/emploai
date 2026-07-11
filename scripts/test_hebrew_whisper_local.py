import argparse
import os
from pathlib import Path
import sys
import time
import wave

import numpy as np
from scipy.signal import resample_poly

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.bundled_python_runtime import configure_bundled_python_dependencies


configure_bundled_python_dependencies(REPO_ROOT)

import torch
from transformers import WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperTokenizerFast

from hebrew_whisper_live_terminal import (
    DEFAULT_CT2_COMPUTE_TYPE,
    DEFAULT_CT2_QUANTIZATION,
    DEFAULT_RUNTIME,
    default_ct2_model_dir,
    load_faster_whisper_model,
)

APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
DEFAULT_MODEL_DIR = Path(
    os.getenv(
        APP_STT_HEBREW_MODEL_DIR_ENV,
        str(Path.home() / "Documents" / "Models" / "hebrew-whisper-small-continue-public-v1-runtime-ready"),
    )
)


def load_wav_mono_16k(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sample_width != 2:
        raise ValueError(f"Expected 16-bit PCM WAV, got sample width {sample_width}: {path}")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000:
        audio = resample_poly(audio, up=16000, down=sample_rate).astype(np.float32)
    return audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Hebrew Whisper inference on a WAV file.")
    parser.add_argument(
        "--model-dir",
        default=str(DEFAULT_MODEL_DIR),
        help="Path to the saved Whisper model directory.",
    )
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
        help="CTranslate2 compute type for faster-whisper.",
    )
    parser.add_argument(
        "--ct2-quantization",
        default=DEFAULT_CT2_QUANTIZATION,
        help="Quantization used when converting the HF model to CT2.",
    )
    parser.add_argument("--force-ct2-convert", action="store_true", help="Rebuild the CT2 model before running faster-whisper.")
    parser.add_argument("--audio-path", required=True, help="Path to a 16 kHz WAV file.")
    parser.add_argument("--language", default="hebrew", help="Whisper language setting.")
    parser.add_argument("--task", default="transcribe", help="Whisper generation task.")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    audio_path = Path(args.audio_path)

    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    audio = load_wav_mono_16k(audio_path)
    runtime_kind = (args.runtime or DEFAULT_RUNTIME).strip().lower()

    load_started = time.perf_counter()
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
        load_elapsed = time.perf_counter() - load_started
        infer_started = time.perf_counter()
        segments, _info = runtime.model.transcribe(
            audio,
            language="he",
            task=args.task,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
            word_timestamps=False,
            suppress_blank=False,
        )
        infer_elapsed = time.perf_counter() - infer_started
        text = " ".join((segment.text or "").strip() for segment in segments if (segment.text or "").strip())
    else:
        device = "cpu"
        feature_extractor = WhisperFeatureExtractor.from_pretrained(model_dir)
        tokenizer = WhisperTokenizerFast.from_pretrained(model_dir)
        model = WhisperForConditionalGeneration.from_pretrained(model_dir)
        model.generation_config.suppress_tokens = None
        model.generation_config.begin_suppress_tokens = None
        model.config.suppress_tokens = None
        model.config.begin_suppress_tokens = None
        model.to(device)
        model.eval()
        load_elapsed = time.perf_counter() - load_started

        infer_started = time.perf_counter()
        inputs = feature_extractor(audio, sampling_rate=16000, return_tensors="pt", return_attention_mask=True)
        input_features = inputs["input_features"].to(device)
        attention_mask = inputs.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to(device)

        with torch.no_grad():
            predicted_ids = model.generate(
                input_features,
                attention_mask=attention_mask,
                language=args.language,
                task=args.task,
            )

        text = tokenizer.batch_decode(
            predicted_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        infer_elapsed = time.perf_counter() - infer_started

    print(f"MODEL: {model_dir}")
    print(f"RUNTIME: {runtime_kind}")
    if runtime_kind == "faster-whisper":
        print(f"CT2_MODEL: {ct2_model_dir}")
    print(f"AUDIO: {audio_path}")
    print(f"LOAD_SECONDS: {load_elapsed:.2f}")
    print(f"INFER_SECONDS: {infer_elapsed:.2f}")
    print("TEXT:")
    print(text)


if __name__ == "__main__":
    main()
