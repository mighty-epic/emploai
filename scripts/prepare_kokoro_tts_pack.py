from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_backend.voice_pack_manager import (
    DEFAULT_KOKORO_TTS_MODEL_FILENAME,
    DEFAULT_KOKORO_TTS_PACK_ENGINE,
    DEFAULT_KOKORO_TTS_PACK_ID,
    DEFAULT_KOKORO_TTS_VOICE,
    DEFAULT_KOKORO_TTS_VOICES_FILENAME,
    FALLBACK_KOKORO_TTS_VOICES_FILENAME,
    TTS_MODELS_DIRNAME,
    TTS_SITE_PACKAGES_DIRNAME,
    VOICE_PACK_MANIFEST_FILENAME,
)


DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Models" / "kokoro-onnx-emploai-desktop-pack"


def default_source_dir() -> Path:
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home()))).expanduser()
    return local_app_data / "EmploAI" / "tts_runtimes" / "kokoro_onnx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a runtime-ready Kokoro ONNX speech pack for Hugging Face publication."
    )
    parser.add_argument("--source-dir", default=str(default_source_dir()), help="Local Kokoro runtime directory.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Destination runtime-ready pack directory.")
    parser.add_argument("--repo-id", default="", help="Optional repo id to stamp into pack_manifest.json.")
    parser.add_argument("--revision", default="main", help="Revision to stamp into pack_manifest.json.")
    parser.add_argument("--force", action="store_true", help="Overwrite the output directory.")
    return parser.parse_args()


def ignore_transient_files(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        lower = name.lower()
        if lower == "__pycache__" or lower.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    model_path = source_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_MODEL_FILENAME
    custom_voices_path = source_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_VOICES_FILENAME
    fallback_voices_path = source_dir / TTS_MODELS_DIRNAME / FALLBACK_KOKORO_TTS_VOICES_FILENAME
    site_packages_dir = source_dir / TTS_SITE_PACKAGES_DIRNAME

    missing: list[str] = []
    if not model_path.exists():
        missing.append(str(model_path))
    if not custom_voices_path.exists() and not fallback_voices_path.exists():
        missing.append(str(custom_voices_path))
    if not (site_packages_dir / "kokoro_onnx").exists():
        missing.append(str(site_packages_dir / "kokoro_onnx"))
    if missing:
        raise SystemExit("Kokoro source is missing required runtime files:\n- " + "\n- ".join(missing))

    if output_dir.exists() and bool(args.force):
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not bool(args.force):
        raise SystemExit(f"Output directory already exists and is not empty: {output_dir}. Use --force to overwrite.")

    copy_file(model_path, output_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_MODEL_FILENAME)
    if custom_voices_path.exists():
        copy_file(custom_voices_path, output_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_VOICES_FILENAME)
    if fallback_voices_path.exists():
        copy_file(fallback_voices_path, output_dir / TTS_MODELS_DIRNAME / FALLBACK_KOKORO_TTS_VOICES_FILENAME)

    shutil.copytree(
        site_packages_dir,
        output_dir / TTS_SITE_PACKAGES_DIRNAME,
        dirs_exist_ok=True,
        ignore=ignore_transient_files,
    )

    manifest = {
        "pack_id": DEFAULT_KOKORO_TTS_PACK_ID,
        "engine": DEFAULT_KOKORO_TTS_PACK_ENGINE,
        "repo_id": str(args.repo_id or ""),
        "revision": str(args.revision or "main"),
        "model_filename": DEFAULT_KOKORO_TTS_MODEL_FILENAME,
        "voices_filename": DEFAULT_KOKORO_TTS_VOICES_FILENAME,
        "default_voice": DEFAULT_KOKORO_TTS_VOICE,
        "source_kind": "prepared_local_runtime",
    }
    (output_dir / VOICE_PACK_MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Prepared Kokoro TTS pack at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
