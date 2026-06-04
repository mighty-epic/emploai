from pathlib import Path

from mobile_app.backend import voice_pack_manager


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
