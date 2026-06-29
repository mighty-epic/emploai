from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mobile_app.backend.voice_pack_manager import (
    DEFAULT_KOKORO_TTS_MODEL_FILENAME,
    DEFAULT_KOKORO_TTS_VOICES_FILENAME,
    TTS_MODELS_DIRNAME,
    TTS_SITE_PACKAGES_DIRNAME,
    VOICE_PACK_MANIFEST_FILENAME,
)


DEFAULT_PACK_DIR = Path.home() / "Documents" / "Models" / "kokoro-onnx-emploai-desktop-pack"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the runtime-ready Kokoro ONNX speech pack to a Hugging Face model repo."
    )
    parser.add_argument("--repo-id", required=True, help="Destination Hugging Face repo id, for example org/model-name.")
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR), help="Local runtime-ready Kokoro pack directory.")
    parser.add_argument("--private", action="store_true", help="Create the repo as private instead of public.")
    parser.add_argument("--revision", default="main", help="Target branch or revision.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from huggingface_hub import HfApi, create_repo
    except Exception as exc:  # pragma: no cover
        raise SystemExit("huggingface_hub is required. Install it with `pip install huggingface_hub`.") from exc

    pack_dir = Path(args.pack_dir).expanduser().resolve()
    if not pack_dir.exists():
        raise SystemExit(f"Pack directory not found: {pack_dir}")

    required_paths = (
        pack_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_MODEL_FILENAME,
        pack_dir / TTS_MODELS_DIRNAME / DEFAULT_KOKORO_TTS_VOICES_FILENAME,
        pack_dir / TTS_SITE_PACKAGES_DIRNAME / "kokoro_onnx",
        pack_dir / VOICE_PACK_MANIFEST_FILENAME,
    )
    missing = [str(path.relative_to(pack_dir)) for path in required_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Pack directory is missing required runtime files: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="emploai-kokoro-pack-publish-") as temp_dir:
        staging_dir = Path(temp_dir) / "pack"
        shutil.copytree(pack_dir, staging_dir)

        manifest_path = staging_dir / VOICE_PACK_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise SystemExit(f"Invalid pack manifest: {manifest_path}")
        manifest["repo_id"] = args.repo_id
        manifest["revision"] = args.revision
        manifest["source_kind"] = "huggingface_repo"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        create_repo(
            repo_id=args.repo_id,
            repo_type="model",
            private=bool(args.private),
            exist_ok=True,
        )

        api = HfApi()
        upload_large_folder = getattr(api, "upload_large_folder", None)
        if callable(upload_large_folder):
            upload_large_folder(
                folder_path=str(staging_dir),
                repo_id=args.repo_id,
                repo_type="model",
                revision=args.revision,
                private=bool(args.private),
                print_report=True,
                print_report_every=60,
            )
        else:
            api.upload_folder(
                folder_path=str(staging_dir),
                repo_id=args.repo_id,
                repo_type="model",
                revision=args.revision,
                commit_message="Publish runtime-ready Kokoro TTS pack",
            )

    print(f"Published Kokoro TTS pack to https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
