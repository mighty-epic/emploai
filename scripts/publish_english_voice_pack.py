from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path


DEFAULT_PACK_DIR = Path.home() / "Documents" / "Models" / "english-whisper-cpp-desktop-pack"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the runtime-ready English whisper.cpp voice pack to a public Hugging Face model repo."
    )
    parser.add_argument("--repo-id", required=True, help="Destination Hugging Face repo id, for example org/model-name")
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR), help="Local runtime-ready English pack directory to upload.")
    parser.add_argument("--private", action="store_true", help="Create the repo as private instead of public.")
    parser.add_argument("--revision", default="main", help="Target branch or revision.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from huggingface_hub import HfApi, create_repo
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "huggingface_hub is required. Install it with `pip install huggingface_hub`."
        ) from exc

    pack_dir = Path(args.pack_dir).expanduser().resolve()
    if not pack_dir.exists():
        raise SystemExit(f"Pack directory not found: {pack_dir}")

    required_paths = (
        pack_dir / "runtime" / "Release" / "whisper-cli.exe",
        pack_dir / "models" / "ggml-base.en-q5_1.bin",
        pack_dir / "models" / "ggml-tiny.en.bin",
        pack_dir / "pack_manifest.json",
    )
    missing = [str(path.relative_to(pack_dir)) for path in required_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Pack directory is missing required runtime files: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="emploai-english-pack-publish-") as temp_dir:
        staging_dir = Path(temp_dir) / "pack"
        shutil.copytree(pack_dir, staging_dir)

        manifest_path = staging_dir / "pack_manifest.json"
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
        api.upload_folder(
            folder_path=str(staging_dir),
            repo_id=args.repo_id,
            repo_type="model",
            revision=args.revision,
            commit_message="Publish runtime-ready English voice pack",
        )

    print(f"Published English voice pack to https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
