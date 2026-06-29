"""Create a local Kokoro voices bundle with an added blended voice alias.

Kokoro ONNX does not clone a voice from a WAV prompt at inference time. Its
voices file is an NPZ-style bundle of named style tensors. This script copies an
existing voices bundle and adds a new voice by blending existing compatible
voices. The original bundle is left untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


DEFAULT_BLEND = "am_echo=0.45,am_onyx=0.35,am_michael=0.20"


def parse_blend(raw: str) -> list[tuple[str, float]]:
    entries: list[tuple[str, float]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Blend entry must be name=weight, got {item!r}")
        name, weight_text = item.split("=", 1)
        name = name.strip()
        weight = float(weight_text.strip())
        if not name:
            raise ValueError("Blend voice name cannot be empty.")
        if weight < 0:
            raise ValueError("Blend weights must be non-negative.")
        entries.append((name, weight))
    if not entries:
        raise ValueError("At least one blend entry is required.")
    total = sum(weight for _, weight in entries)
    if total <= 0:
        raise ValueError("Blend weights must sum above zero.")
    return [(name, weight / total) for name, weight in entries]


def default_voices_path() -> Path:
    local_app_data = Path.home() / "AppData" / "Local"
    return local_app_data / "EmploAI" / "tts_runtimes" / "kokoro_onnx" / "models" / "voices-v1.0.bin"


def default_output_path() -> Path:
    local_app_data = Path.home() / "AppData" / "Local"
    return local_app_data / "EmploAI" / "tts_runtimes" / "kokoro_onnx" / "models" / "voices-emploai-v1.0.bin"


def write_npz_exact_path(path: Path, payload: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.savez_compressed(handle, **payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a blended voice alias to a Kokoro voices bundle.")
    parser.add_argument("--source", type=Path, default=default_voices_path(), help="source Kokoro voices file")
    parser.add_argument("--output", type=Path, default=default_output_path(), help="output voices file")
    parser.add_argument("--name", default="jarvis", help="new voice alias name")
    parser.add_argument("--blend", default=DEFAULT_BLEND, help="comma-separated voice=weight entries")
    parser.add_argument("--force", action="store_true", help="overwrite an existing alias in the output")
    args = parser.parse_args()

    source = args.source.expanduser()
    output = args.output.expanduser()
    alias_name = str(args.name or "").strip()
    if not alias_name:
        raise SystemExit("Voice alias name cannot be empty.")
    if not source.exists():
        raise SystemExit(f"Source voices file does not exist: {source}")

    voices = np.load(str(source))
    payload = {name: np.asarray(voices[name], dtype=np.float32) for name in voices.keys()}
    if alias_name in payload and not args.force:
        raise SystemExit(f"Voice alias {alias_name!r} already exists. Use --force to replace it.")

    blend = parse_blend(args.blend)
    missing = [name for name, _ in blend if name not in payload]
    if missing:
        available = ", ".join(sorted(payload.keys()))
        raise SystemExit(f"Missing blend voices: {', '.join(missing)}. Available: {available}")

    shape = payload[blend[0][0]].shape
    blended = np.zeros(shape, dtype=np.float32)
    for name, weight in blend:
        voice = payload[name]
        if voice.shape != shape:
            raise SystemExit(f"Voice {name!r} has shape {voice.shape}, expected {shape}.")
        blended += voice.astype(np.float32) * np.float32(weight)

    payload[alias_name] = blended.astype(np.float32)
    write_npz_exact_path(output, payload)
    print(f"Created {output}")
    print(f"Added voice {alias_name!r} from {args.blend}")
    print(f"Voice count: {len(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
