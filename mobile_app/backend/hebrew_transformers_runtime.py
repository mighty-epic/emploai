from __future__ import annotations

import io
import re
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from transformers.utils import logging as hf_logging

from mobile_app.backend.voice_pack_manager import get_hebrew_pack_status, hebrew_pack_runtime_dir
from mobile_app.backend.whisper_cpp_runtime import recommended_thread_count


WHISPER_SAMPLE_RATE = 16000
DEFAULT_LANGUAGE = "hebrew"
DEFAULT_TASK = "transcribe"
DEFAULT_MAX_NEW_TOKENS = 48

_MODEL_CACHE: dict[str, tuple[Any, Any, Any]] = {}


hf_logging.set_verbosity_error()


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
    if len(words) >= 6:
        single_word_peak = repeated_ngram_count(words, 1)
        if single_word_peak >= 4:
            return True
    if len(words) < 12:
        return False
    unique_ratio = len(set(words)) / float(len(words))
    if len(words) >= 24 and unique_ratio < 0.45:
        return True
    for n in (2, 3, 4):
        if repeated_ngram_count(words, n) >= 4:
            return True
    return False


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


def _wav_bytes_to_float32_audio(data: bytes, *, target_rate: int = WHISPER_SAMPLE_RATE) -> np.ndarray:
    sample_rate, frames = _read_pcm16_mono_wav(data)
    resampled_frames = _resample_pcm16_mono(frames, source_rate=sample_rate, target_rate=target_rate)
    pcm = np.frombuffer(resampled_frames, dtype=np.int16).astype(np.float32)
    if pcm.size == 0:
        return np.zeros((0,), dtype=np.float32)
    return pcm / 32768.0


def _model_cache_key(model_dir: Path) -> str:
    return str(model_dir.resolve())


def _load_model_bundle() -> tuple[Any, Any, Any]:
    status = get_hebrew_pack_status()
    if not status.get("installed"):
        issues = status.get("issues") or ["Hebrew voice pack is not installed."]
        raise RuntimeError(str(issues[0]))

    model_dir = hebrew_pack_runtime_dir()
    cache_key = _model_cache_key(model_dir)
    cached = _MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        from transformers import WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperTokenizerFast
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "The local Hebrew voice runtime requires the Transformers Whisper stack to be installed."
        ) from exc

    torch.set_num_threads(max(1, recommended_thread_count()))
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
    _MODEL_CACHE[cache_key] = (feature_extractor, tokenizer, model)
    return feature_extractor, tokenizer, model


def clear_model_cache() -> None:
    _MODEL_CACHE.clear()


def transcribe_wav_bytes(
    data: bytes,
    *,
    initial_prompt: Optional[str],
    language: str = DEFAULT_LANGUAGE,
    task: str = DEFAULT_TASK,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> tuple[str, float | None]:
    feature_extractor, tokenizer, model = _load_model_bundle()
    audio = _wav_bytes_to_float32_audio(data, target_rate=WHISPER_SAMPLE_RATE)
    inputs = feature_extractor(
        audio,
        sampling_rate=WHISPER_SAMPLE_RATE,
        return_tensors="pt",
        return_attention_mask=True,
    )

    generate_kwargs: dict[str, object] = {
        "attention_mask": inputs.get("attention_mask"),
        "language": language,
        "task": task,
        "max_new_tokens": max(8, int(max_new_tokens)),
        "return_dict_in_generate": True,
        "output_scores": True,
    }
    if initial_prompt:
        try:
            prompt_ids = tokenizer.get_prompt_ids(initial_prompt)
        except Exception:
            prompt_ids = None
        if prompt_ids:
            generate_kwargs["prompt_ids"] = torch.tensor([prompt_ids], dtype=torch.long)

    with torch.inference_mode():
        outputs = model.generate(
            inputs["input_features"],
            **generate_kwargs,
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

    text = tokenizer.batch_decode(
        predicted_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()
    return normalize_transcript_text(text), confidence
