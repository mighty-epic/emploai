from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from mobile_app.backend.voice_pack_manager import (
    DEFAULT_ENGLISH_PACK_ENGINE,
    DEFAULT_ENGLISH_PACK_ID,
    DEFAULT_ENGLISH_PACK_TUNING_PRESET,
    VOICE_PACK_MANIFEST_FILENAME,
)
from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_RELEASE_TAG,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
)


DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Models" / "english-whisper-cpp-desktop-pack"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a runtime-ready English whisper.cpp voice pack for Hugging Face publication."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Destination runtime-ready pack directory.")
    parser.add_argument("--model", default="base.en-q5_1", help="Final English ggml model name.")
    parser.add_argument("--draft-model", default="tiny.en", help="Draft English ggml model name.")
    parser.add_argument("--binary-flavor", default=DEFAULT_BINARY_FLAVOR, help="whisper.cpp binary flavor to package.")
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG, help="whisper.cpp release tag to pull binaries from.")
    parser.add_argument("--force", action="store_true", help="Redownload assets and overwrite the output directory.")
    return parser.parse_args()


def _copy_release_dir(src_release_dir: Path, dst_release_dir: Path) -> None:
    dst_release_dir.mkdir(parents=True, exist_ok=True)
    for src_path in src_release_dir.iterdir():
        if not src_path.is_file():
            continue
        shutil.copy2(src_path, dst_release_dir / src_path.name)


def main() -> int:
    args = parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    runtime_release_dir = output_dir / "runtime" / "Release"
    models_dir = output_dir / "models"

    whisper_cli = ensure_prebuilt_whisper_cpp(
        release_tag=str(args.release_tag),
        flavor=str(args.binary_flavor),
        force=bool(args.force),
    )
    model_path = ensure_ggml_model(str(args.model), force=bool(args.force))
    draft_model_path = ensure_ggml_model(str(args.draft_model), force=bool(args.force))

    if output_dir.exists() and bool(args.force):
        shutil.rmtree(output_dir)
    runtime_release_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    _copy_release_dir(whisper_cli.parent, runtime_release_dir)
    shutil.copy2(model_path, models_dir / model_path.name)
    shutil.copy2(draft_model_path, models_dir / draft_model_path.name)

    manifest = {
        "pack_id": DEFAULT_ENGLISH_PACK_ID,
        "engine": DEFAULT_ENGLISH_PACK_ENGINE,
        "repo_id": "",
        "revision": "main",
        "binary_flavor": str(args.binary_flavor),
        "model_name": str(args.model),
        "draft_model_name": str(args.draft_model),
        "tuning_preset": DEFAULT_ENGLISH_PACK_TUNING_PRESET,
        "source_kind": "prepared_local_runtime",
        "release_tag": str(args.release_tag),
    }
    (output_dir / VOICE_PACK_MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Prepared English voice pack at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
