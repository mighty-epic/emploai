from pathlib import Path

from app_backend import voice_pack_manager


def _write_english_pack(root: Path) -> None:
    runtime_dir = root / "runtime" / "Release"
    models_dir = root / "models"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "whisper-cli.exe").write_text("cli", encoding="utf-8")
    (runtime_dir / "ggml.dll").write_text("dll", encoding="utf-8")
    (models_dir / "ggml-base.en-q5_1.bin").write_text("model", encoding="utf-8")
    (models_dir / "ggml-tiny.en.bin").write_text("draft", encoding="utf-8")


def _write_hebrew_pack(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for filename in voice_pack_manager.HEBREW_REQUIRED_MODEL_FILES:
        (root / filename).write_text(filename, encoding="utf-8")


def _write_kokoro_tts_pack(root: Path) -> None:
    models_dir = root / "models"
    site_packages_dir = root / "site-packages" / "kokoro_onnx"
    models_dir.mkdir(parents=True, exist_ok=True)
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "kokoro-v1.0.onnx").write_text("onnx", encoding="utf-8")
    (models_dir / "voices-emploai-v1.0.bin").write_text("voices", encoding="utf-8")
    (site_packages_dir / "__init__.py").write_text("", encoding="utf-8")


def test_packaged_release_ignores_local_english_override(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"
    override_dir = tmp_path / "override-english"
    _write_english_pack(override_dir)

    monkeypatch.setattr(voice_pack_manager, "runtime_root", lambda: runtime_home)
    monkeypatch.setattr(voice_pack_manager.sys, "frozen", True, raising=False)
    monkeypatch.delenv(voice_pack_manager.ALLOW_DEV_VOICE_PACK_SOURCES_ENV, raising=False)
    monkeypatch.setenv(voice_pack_manager.APP_STT_ENGLISH_PACK_DIR_ENV, str(override_dir))
    monkeypatch.setenv(voice_pack_manager.APP_STT_ENGLISH_PACK_REPO_ENV, "mighty1234/emploai-english-voice-pack")

    status = voice_pack_manager.get_english_pack_status()

    assert status["installed"] is False
    assert Path(status["model_dir"]).resolve() == (
        runtime_home / "voice_packs" / "english_local" / "models"
    ).resolve()


def test_packaged_release_ignores_local_hebrew_override(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"
    override_dir = tmp_path / "override-hebrew"
    _write_hebrew_pack(override_dir)

    monkeypatch.setattr(voice_pack_manager, "runtime_root", lambda: runtime_home)
    monkeypatch.setattr(voice_pack_manager.sys, "frozen", True, raising=False)
    monkeypatch.delenv(voice_pack_manager.ALLOW_DEV_VOICE_PACK_SOURCES_ENV, raising=False)
    monkeypatch.setenv(voice_pack_manager.APP_STT_HEBREW_MODEL_DIR_ENV, str(override_dir))

    status = voice_pack_manager.get_hebrew_pack_status()

    assert status["installed"] is False
    assert Path(status["model_dir"]).resolve() == (
        runtime_home / "voice_packs" / "hebrew_local" / "model"
    ).resolve()


def test_install_english_voice_pack_reports_progress(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"

    monkeypatch.setattr(voice_pack_manager, "runtime_root", lambda: runtime_home)
    monkeypatch.setattr(voice_pack_manager.sys, "frozen", False, raising=False)
    monkeypatch.delenv(voice_pack_manager.ALLOW_DEV_VOICE_PACK_SOURCES_ENV, raising=False)
    monkeypatch.delenv(voice_pack_manager.APP_STT_ENGLISH_PACK_DIR_ENV, raising=False)
    monkeypatch.delenv(voice_pack_manager.ENGLISH_PACK_SOURCE_DIR_ENV, raising=False)
    monkeypatch.delenv(voice_pack_manager.ENGLISH_PACK_ARCHIVE_URL_ENV, raising=False)
    monkeypatch.setenv(voice_pack_manager.APP_STT_ENGLISH_PACK_REPO_ENV, "mighty1234/emploai-english-voice-pack")

    def _fake_snapshot_download(*, local_dir: str, tqdm_class=None, **_kwargs):
        target_root = Path(local_dir)
        _write_english_pack(target_root)
        if tqdm_class is not None:
            progress = tqdm_class(total=100, unit="B", unit_scale=True, disable=True)
            progress.update(100)
            progress.close()
        return str(target_root)

    monkeypatch.setattr(voice_pack_manager, "snapshot_download", _fake_snapshot_download)

    events: list[dict[str, object]] = []
    status = voice_pack_manager.install_english_voice_pack(progress_callback=events.append)

    assert status["installed"] is True
    assert status["available"] is True
    assert status["manifest_verified"] is True
    assert events[0]["state"] == "starting"
    assert any(event["state"] == "downloading" for event in events)
    assert any(event["state"] == "verifying" for event in events)
    assert events[-1]["state"] == "ready"


def test_install_kokoro_tts_voice_pack_from_local_source(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"
    source_dir = tmp_path / "kokoro-source"
    _write_kokoro_tts_pack(source_dir)

    monkeypatch.setattr(voice_pack_manager, "runtime_root", lambda: runtime_home)
    monkeypatch.setattr(voice_pack_manager.sys, "frozen", False, raising=False)
    monkeypatch.delenv(voice_pack_manager.ALLOW_DEV_VOICE_PACK_SOURCES_ENV, raising=False)
    monkeypatch.delenv(voice_pack_manager.APP_TTS_KOKORO_PACK_DIR_ENV, raising=False)
    monkeypatch.delenv(voice_pack_manager.KOKORO_TTS_PACK_ARCHIVE_URL_ENV, raising=False)
    monkeypatch.setenv(voice_pack_manager.KOKORO_TTS_PACK_SOURCE_DIR_ENV, str(source_dir))
    monkeypatch.setenv(voice_pack_manager.APP_TTS_KOKORO_PACK_REPO_ENV, "mighty1234/emploai-kokoro-tts-pack")

    events: list[dict[str, object]] = []
    status = voice_pack_manager.install_voice_pack("kokoro_tts", progress_callback=events.append)

    assert status["installed"] is True
    assert status["available"] is True
    assert status["manifest_verified"] is True
    assert Path(status["model_dir"]).resolve() == (runtime_home / "voice_packs" / "kokoro_tts").resolve()
    assert status["manifest"]["pack_id"] == voice_pack_manager.DEFAULT_KOKORO_TTS_PACK_ID
    assert events[0]["state"] == "starting"
    assert any(event["phase"] == "copy" for event in events)
    assert events[-1]["state"] == "ready"
