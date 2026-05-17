from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_RELEASE_TAG,
    bundled_ggml_model,
    bundled_whisper_cli,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    models_root,
    runtime_root,
    tools_root,
)
from shared.live_config import get_live_config

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover
    snapshot_download = None


VOICE_ENGINE_ENGLISH = "english_local"
VOICE_ENGINE_HEBREW = "hebrew_local"
VOICE_PACK_IDS = (VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW)

APP_STT_MODEL_ENV = "EMPLO_APP_STT_MODEL"
APP_STT_DRAFT_MODEL_ENV = "EMPLO_APP_STT_DRAFT_MODEL"
APP_STT_BINARY_FLAVOR_ENV = "EMPLO_APP_STT_BINARY_FLAVOR"
APP_STT_HEBREW_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_MODEL_REPO"
APP_STT_HEBREW_MODEL_DIR_ENV = "EMPLO_APP_STT_HEBREW_MODEL_DIR"
HEBREW_PACK_ARCHIVE_URL_ENV = "EMPLOAI_HEBREW_VOICE_PACK_ARCHIVE_URL"
HEBREW_PACK_SOURCE_DIR_ENV = "EMPLOAI_HEBREW_VOICE_PACK_SOURCE_DIR"
HEBREW_PACK_REVISION_ENV = "EMPLOAI_HEBREW_VOICE_PACK_REVISION"

DEFAULT_LOCAL_STT_MODEL = "base.en-q5_1"
DEFAULT_LOCAL_DRAFT_MODEL = "tiny.en"
DEFAULT_HEBREW_MODEL_REPO = "Mighty1234/hebrew-whisper-small-continue-public-v1"

MANAGED_VOICE_PACKS_DIRNAME = "voice_packs"
HEBREW_RUNTIME_DIRNAME = "model"
HEBREW_REQUIRED_MODEL_FILES = (
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "normalizer.json",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)
DEV_HEBREW_SOURCE_DIR_CANDIDATES = (
    Path.home() / "Documents" / "Models" / "hebrew-whisper-small-continue-public-v1-runtime-ready",
    Path.home() / "Documents" / "Models" / "hebrew-whisper-small-real-v2-runtime",
)


def managed_voice_packs_root() -> Path:
    return runtime_root() / MANAGED_VOICE_PACKS_DIRNAME


def _local_model_name() -> str:
    return os.getenv(APP_STT_MODEL_ENV, DEFAULT_LOCAL_STT_MODEL).strip() or DEFAULT_LOCAL_STT_MODEL


def _local_draft_model_name() -> str:
    return os.getenv(APP_STT_DRAFT_MODEL_ENV, DEFAULT_LOCAL_DRAFT_MODEL).strip() or DEFAULT_LOCAL_DRAFT_MODEL


def _local_binary_flavor() -> str:
    return os.getenv(APP_STT_BINARY_FLAVOR_ENV, DEFAULT_BINARY_FLAVOR).strip() or DEFAULT_BINARY_FLAVOR


def _release_asset_name(*, flavor: str) -> str:
    if flavor == "plain":
        return "whisper-bin-x64.zip"
    if flavor == "blas":
        return "whisper-blas-bin-x64.zip"
    if flavor == "cublas-11.8":
        return "whisper-cublas-11.8.0-bin-x64.zip"
    if flavor == "cublas-12.4":
        return "whisper-cublas-12.4.0-bin-x64.zip"
    raise RuntimeError(f"Unsupported whisper.cpp binary flavor: {flavor}")


def _managed_english_binary_dir() -> Path:
    return tools_root() / _release_asset_name(flavor=_local_binary_flavor()).removesuffix(".zip")


def _managed_english_binary_zip() -> Path:
    return tools_root() / _release_asset_name(flavor=_local_binary_flavor())


def _managed_english_cli_path() -> Path:
    return _managed_english_binary_dir() / "Release" / "whisper-cli.exe"


def _english_model_names() -> tuple[str, str]:
    return (_local_model_name(), _local_draft_model_name())


def _managed_english_model_paths() -> list[Path]:
    return [models_root() / f"ggml-{model_name}.bin" for model_name in _english_model_names()]


def _required_hebrew_runtime_dir() -> Path:
    configured = os.getenv(APP_STT_HEBREW_MODEL_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (managed_voice_packs_root() / VOICE_ENGINE_HEBREW / HEBREW_RUNTIME_DIRNAME).resolve()


def _managed_hebrew_runtime_dir() -> Path:
    return (managed_voice_packs_root() / VOICE_ENGINE_HEBREW / HEBREW_RUNTIME_DIRNAME).resolve()


def _hebrew_pack_ready(model_dir: Path) -> bool:
    return all((model_dir / filename).exists() for filename in HEBREW_REQUIRED_MODEL_FILES)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _find_nested_hebrew_runtime_dir(root: Path) -> Path | None:
    if _hebrew_pack_ready(root):
        return root
    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        if _hebrew_pack_ready(candidate):
            return candidate
    return None


def _promote_hebrew_runtime_dir(target_dir: Path) -> Path:
    if _hebrew_pack_ready(target_dir):
        return target_dir
    nested = _find_nested_hebrew_runtime_dir(target_dir)
    if nested is None or nested == target_dir:
        return target_dir

    with tempfile.TemporaryDirectory(prefix="emploai-hebrew-pack-") as temp_dir:
        staging = Path(temp_dir) / "model"
        shutil.copytree(nested, staging)
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, target_dir)
    return target_dir


def _candidate_hebrew_source_dir() -> Path | None:
    configured = os.getenv(HEBREW_PACK_SOURCE_DIR_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if _hebrew_pack_ready(candidate):
            return candidate
    for candidate in DEV_HEBREW_SOURCE_DIR_CANDIDATES:
        resolved = candidate.expanduser().resolve()
        if _hebrew_pack_ready(resolved):
            return resolved
    return None


def hebrew_pack_repo() -> str:
    return os.getenv(APP_STT_HEBREW_MODEL_REPO_ENV, DEFAULT_HEBREW_MODEL_REPO).strip()


def hebrew_pack_runtime_dir() -> Path:
    return _required_hebrew_runtime_dir()


def get_english_pack_status() -> dict[str, Any]:
    managed_cli = _managed_english_cli_path()
    managed_models = _managed_english_model_paths()
    bundled_cli = bundled_whisper_cli(flavor=_local_binary_flavor())
    bundled_models = [bundled_ggml_model(model_name) for model_name in _english_model_names()]

    managed_ready = managed_cli.exists() and all(path.exists() for path in managed_models)
    bundled_ready = bundled_cli is not None and all(path is not None and path.exists() for path in bundled_models)
    installed = managed_ready or bundled_ready
    source = "managed" if managed_ready else "bundled" if bundled_ready else "missing"

    issues: list[str] = []
    if os.name != "nt":
        issues.append("The English voice pack currently expects Windows whisper.cpp binaries.")
    if not installed:
        issues.append("English voice pack assets are not installed yet.")

    return {
        "id": VOICE_ENGINE_ENGLISH,
        "installed": installed,
        "available": installed,
        "managed": managed_ready,
        "removable": managed_ready,
        "source": source,
        "issues": issues,
        "binary_path": str(managed_cli if managed_ready else bundled_cli) if installed else None,
        "model_paths": [str(path) for path in (managed_models if managed_ready else bundled_models if bundled_ready else []) if path],
    }


def get_hebrew_pack_status() -> dict[str, Any]:
    model_dir = hebrew_pack_runtime_dir()
    managed_dir = _managed_hebrew_runtime_dir()
    installed = _hebrew_pack_ready(model_dir)
    managed = installed and model_dir == managed_dir
    source = "managed" if managed else "local_override" if installed else "missing"

    issues: list[str] = []
    if not installed:
        configured_dir = os.getenv(APP_STT_HEBREW_MODEL_DIR_ENV, "").strip()
        if configured_dir:
            issues.append(f"Configured Hebrew voice pack path is missing required files: {model_dir}")
        elif os.getenv(HEBREW_PACK_ARCHIVE_URL_ENV, "").strip():
            issues.append(f"Hebrew voice pack is not installed yet. Expected files under {model_dir}")
        elif hebrew_pack_repo():
            issues.append(f"Hebrew voice pack is not installed yet. Expected files under {model_dir}")
        elif _candidate_hebrew_source_dir() is not None:
            issues.append(f"Hebrew voice pack is available locally but not installed into {managed_dir}")
        else:
            issues.append(
                "Hebrew voice pack is not installed and no public source is configured. "
                f"Set {APP_STT_HEBREW_MODEL_REPO_ENV} to a public model repo or "
                f"{HEBREW_PACK_ARCHIVE_URL_ENV} to a downloadable zip."
            )

    return {
        "id": VOICE_ENGINE_HEBREW,
        "installed": installed,
        "available": installed,
        "managed": managed,
        "removable": managed,
        "source": source,
        "issues": issues,
        "model_dir": str(model_dir),
        "repo_id": hebrew_pack_repo() or None,
    }


def get_voice_pack_status(pack_id: str) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return get_english_pack_status()
    if pack_id == VOICE_ENGINE_HEBREW:
        return get_hebrew_pack_status()
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def install_english_voice_pack(*, force: bool = False) -> dict[str, Any]:
    ensure_prebuilt_whisper_cpp(
        release_tag=DEFAULT_RELEASE_TAG,
        flavor=_local_binary_flavor(),
        force=force,
    )
    for model_name in _english_model_names():
        ensure_ggml_model(model_name, force=force)
    return get_english_pack_status()


def _download_hebrew_pack_archive(archive_url: str, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="emploai-hebrew-download-") as temp_dir:
        archive_path = Path(temp_dir) / "hebrew-pack.zip"
        with urllib.request.urlopen(archive_url) as response, archive_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_root)
        nested_dir = _find_nested_hebrew_runtime_dir(extract_root)
        if nested_dir is None:
            raise RuntimeError(
                f"Downloaded Hebrew voice pack archive did not contain the required runtime files: {archive_url}"
            )
        _copy_tree(nested_dir, target_dir)


def install_hebrew_voice_pack(*, force: bool = False) -> dict[str, Any]:
    target_dir = _managed_hebrew_runtime_dir()
    if _hebrew_pack_ready(target_dir) and not force:
        return get_hebrew_pack_status()

    source_dir = _candidate_hebrew_source_dir()
    archive_url = os.getenv(HEBREW_PACK_ARCHIVE_URL_ENV, "").strip()
    repo_id = hebrew_pack_repo()
    revision = os.getenv(HEBREW_PACK_REVISION_ENV, "").strip() or None

    if source_dir is not None:
        _copy_tree(source_dir, target_dir)
    elif archive_url:
        _download_hebrew_pack_archive(archive_url, target_dir)
    elif repo_id:
        if snapshot_download is None:
            raise RuntimeError("The `huggingface_hub` package is required to download the Hebrew voice pack.")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            revision=revision,
            local_dir_use_symlinks=False,
        )
    else:
        raise RuntimeError(
            "No Hebrew voice pack source is configured. "
            f"Set {APP_STT_HEBREW_MODEL_REPO_ENV} to a public repo, "
            f"{HEBREW_PACK_ARCHIVE_URL_ENV} to a downloadable zip, or "
            f"{HEBREW_PACK_SOURCE_DIR_ENV} to a local runtime-ready folder."
        )

    _promote_hebrew_runtime_dir(target_dir)
    if not _hebrew_pack_ready(target_dir):
        raise RuntimeError(f"Hebrew voice pack installation completed, but required files are still missing in {target_dir}")
    return get_hebrew_pack_status()


def install_voice_pack(pack_id: str, *, force: bool = False) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return install_english_voice_pack(force=force)
    if pack_id == VOICE_ENGINE_HEBREW:
        return install_hebrew_voice_pack(force=force)
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def remove_english_voice_pack() -> dict[str, Any]:
    for path in _managed_english_model_paths():
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        shutil.rmtree(_managed_english_binary_dir(), ignore_errors=True)
    except Exception:
        pass
    try:
        _managed_english_binary_zip().unlink(missing_ok=True)
    except Exception:
        pass
    return get_english_pack_status()


def remove_hebrew_voice_pack() -> dict[str, Any]:
    managed_dir = _managed_hebrew_runtime_dir().parent
    try:
        shutil.rmtree(managed_dir, ignore_errors=True)
    except Exception:
        pass
    return get_hebrew_pack_status()


def remove_voice_pack(pack_id: str) -> dict[str, Any]:
    if pack_id == VOICE_ENGINE_ENGLISH:
        return remove_english_voice_pack()
    if pack_id == VOICE_ENGINE_HEBREW:
        return remove_hebrew_voice_pack()
    raise ValueError(f"Unsupported voice pack: {pack_id}")


def requested_voice_pack_ids(config_path: Path | None = None) -> list[str]:
    config = get_live_config(config_path or (runtime_root() / "config.json"))
    requested: list[str] = []
    if bool(config.get("voice.packs.english_local.requested", True)):
        requested.append(VOICE_ENGINE_ENGLISH)
    if bool(config.get("voice.packs.hebrew_local.requested", False)):
        requested.append(VOICE_ENGINE_HEBREW)
    return requested


def ensure_requested_voice_packs(*, config_path: Path | None = None, force: bool = False) -> dict[str, Any]:
    installed: list[str] = []
    errors: dict[str, str] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for pack_id in requested_voice_pack_ids(config_path=config_path):
        status = get_voice_pack_status(pack_id)
        if status.get("installed") and not force:
            statuses[pack_id] = status
            continue
        try:
            statuses[pack_id] = install_voice_pack(pack_id, force=force)
            installed.append(pack_id)
        except Exception as exc:
            errors[pack_id] = str(exc)
            statuses[pack_id] = get_voice_pack_status(pack_id)

    return {
        "ok": not errors,
        "installed": installed,
        "errors": errors,
        "statuses": statuses,
    }
