from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_backend.voice_pack_manager import (
    DEFAULT_KYUTAI_TTS_LANGUAGE,
    DEFAULT_KYUTAI_TTS_PACK_ENGINE,
    DEFAULT_KYUTAI_TTS_PACK_ID,
    DEFAULT_KYUTAI_TTS_VOICE_FILENAME,
    TTS_SITE_PACKAGES_DIRNAME,
    TTS_VOICES_DIRNAME,
    VOICE_PACK_MANIFEST_FILENAME,
)


DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Models" / "kyutai-pocket-tts-emploai-clone-pack"


def default_site_packages_dir() -> Path:
    temp_dir = Path(os.getenv("TEMP", str(Path.home()))).expanduser()
    return temp_dir / "emploai-pocket-tts-bench" / ".venv" / "Lib" / "site-packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a runtime-ready Kyutai/Pocket speech pack with an EmploAI voice clone."
    )
    parser.add_argument("--site-packages", default=str(default_site_packages_dir()), help="site-packages folder containing pocket_tts and dependencies.")
    parser.add_argument("--voice-file", default="", help="Existing Pocket voice-state .safetensors file to package.")
    parser.add_argument("--audio-prompt", default="", help="Authorized voice prompt audio to export into jarvis.safetensors.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to use when exporting --audio-prompt.")
    parser.add_argument("--language", default=DEFAULT_KYUTAI_TTS_LANGUAGE, help="Pocket TTS language/config for voice export.")
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


def export_voice_state(*, python_executable: str, site_packages: Path, audio_prompt: Path, output_path: Path, language: str) -> None:
    env = dict(os.environ)
    existing_python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(site_packages) if not existing_python_path else str(site_packages) + os.pathsep + existing_python_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        python_executable,
        "-m",
        "pocket_tts",
        "export-voice",
        str(audio_prompt),
        str(output_path),
        "--language",
        str(language),
    ]
    subprocess.run(command, check=True, env=env)


def main() -> int:
    args = parse_args()
    site_packages_dir = Path(args.site_packages).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    packaged_voice_path = output_dir / TTS_VOICES_DIRNAME / DEFAULT_KYUTAI_TTS_VOICE_FILENAME

    if not (site_packages_dir / "pocket_tts").exists():
        raise SystemExit(f"Pocket TTS site-packages folder is missing pocket_tts: {site_packages_dir}")

    if output_dir.exists() and bool(args.force):
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not bool(args.force):
        raise SystemExit(f"Output directory already exists and is not empty: {output_dir}. Use --force to overwrite.")

    voice_file = Path(args.voice_file).expanduser().resolve() if str(args.voice_file or "").strip() else None
    audio_prompt = Path(args.audio_prompt).expanduser().resolve() if str(args.audio_prompt or "").strip() else None

    if voice_file is not None and audio_prompt is not None:
        raise SystemExit("Use either --voice-file or --audio-prompt, not both.")
    if voice_file is None and audio_prompt is None:
        raise SystemExit("Kyutai pack preparation requires --voice-file or --audio-prompt.")

    if voice_file is not None:
        if not voice_file.exists():
            raise SystemExit(f"Voice state file does not exist: {voice_file}")
        if voice_file.suffix.lower() != ".safetensors":
            raise SystemExit(f"Voice state must be a .safetensors file: {voice_file}")
        packaged_voice_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(voice_file, packaged_voice_path)
    elif audio_prompt is not None:
        if not audio_prompt.exists():
            raise SystemExit(f"Audio prompt does not exist: {audio_prompt}")
        export_voice_state(
            python_executable=str(args.python),
            site_packages=site_packages_dir,
            audio_prompt=audio_prompt,
            output_path=packaged_voice_path,
            language=str(args.language or DEFAULT_KYUTAI_TTS_LANGUAGE),
        )

    shutil.copytree(
        site_packages_dir,
        output_dir / TTS_SITE_PACKAGES_DIRNAME,
        dirs_exist_ok=True,
        ignore=ignore_transient_files,
    )

    manifest = {
        "pack_id": DEFAULT_KYUTAI_TTS_PACK_ID,
        "engine": DEFAULT_KYUTAI_TTS_PACK_ENGINE,
        "repo_id": str(args.repo_id or ""),
        "revision": str(args.revision or "main"),
        "voice_filename": DEFAULT_KYUTAI_TTS_VOICE_FILENAME,
        "language": str(args.language or DEFAULT_KYUTAI_TTS_LANGUAGE),
        "source_kind": "prepared_local_runtime",
        "model_weight_note": "Pocket TTS may still resolve Kyutai model weights from its configured Hugging Face source on first use.",
    }
    (output_dir / VOICE_PACK_MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Prepared Kyutai TTS pack at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
