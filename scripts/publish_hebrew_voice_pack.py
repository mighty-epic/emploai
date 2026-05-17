from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_MODEL_DIR = Path.home() / "Documents" / "Models" / "hebrew-whisper-small-continue-public-v1-runtime-ready"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the runtime-ready Hebrew Whisper pack to a public Hugging Face model repo."
    )
    parser.add_argument("--repo-id", required=True, help="Destination Hugging Face repo id, for example org/model-name")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR), help="Local runtime-ready model directory to upload.")
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

    model_dir = Path(args.model_dir).expanduser().resolve()
    if not model_dir.exists():
        raise SystemExit(f"Model directory not found: {model_dir}")

    required_files = (
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "processor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "merges.txt",
        "vocab.json",
        "normalizer.json",
        "special_tokens_map.json",
        "added_tokens.json",
    )
    missing = [name for name in required_files if not (model_dir / name).exists()]
    if missing:
        raise SystemExit(f"Model directory is missing required runtime files: {', '.join(missing)}")

    create_repo(
        repo_id=args.repo_id,
        repo_type="model",
        private=bool(args.private),
        exist_ok=True,
    )

    api = HfApi()
    api.upload_folder(
        folder_path=str(model_dir),
        repo_id=args.repo_id,
        repo_type="model",
        revision=args.revision,
        commit_message="Publish runtime-ready Hebrew voice pack",
    )

    print(f"Published Hebrew voice pack to https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
