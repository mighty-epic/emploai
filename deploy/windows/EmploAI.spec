# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]


def collect_tree(src: Path, prefix: str):
    datas = []
    if not src.exists():
        return datas
    for file_path in src.rglob("*"):
        if not file_path.is_file():
            continue
        relative_parent = file_path.relative_to(src).parent.as_posix()
        destination = prefix if relative_parent == "." else f"{prefix}/{relative_parent}"
        datas.append((str(file_path), destination))
    return datas


hiddenimports = []
for package_name in ("telegram_bot", "single_agent", "shared", "bot_core", "cli", "mobile_app.backend"):
    hiddenimports += collect_submodules(package_name)


datas = [
    (str(project_root / ".env.example"), "."),
    (str(project_root / "config.json"), "."),
    (str(project_root / "deploy" / "windows" / "release_info.json"), "deploy/windows"),
]
datas += collect_tree(project_root / "browser_extension", "browser_extension")
datas += collect_tree(project_root / "skills", "skills")
datas += collect_tree(project_root / ".agents", ".agents")

tesseract_bundle = os.environ.get("EMPLOAI_TESSERACT_BUNDLE", "").strip()
if tesseract_bundle:
    datas += collect_tree(Path(tesseract_bundle), "vendor/tesseract")


a = Analysis(
    [str(project_root / "deploy" / "windows" / "release_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EmploAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    onefile=True,
)
