from pathlib import Path

from deploy.windows.release_runtime import (
    EXTENSION_GUIDE_FILENAME,
    ensure_runtime_files,
    extension_path,
)


def test_ensure_runtime_files_copies_extension_and_writes_guide(tmp_path: Path):
    source_root = tmp_path / "source"
    browser_extension = source_root / "browser_extension"
    browser_extension.mkdir(parents=True)
    (browser_extension / "manifest.json").write_text("{}", encoding="utf-8")
    (source_root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")

    runtime_home = tmp_path / "runtime"
    ensure_runtime_files(runtime_home, source_root)

    assert (extension_path(runtime_home) / "manifest.json").exists()
    guide = (runtime_home / EXTENSION_GUIDE_FILENAME).read_text(encoding="utf-8")
    assert "chrome://extensions" in guide
    assert str(extension_path(runtime_home)) in guide
