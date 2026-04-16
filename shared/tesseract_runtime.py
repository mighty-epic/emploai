from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TESSERACT_BUNDLE_ENV = "EMPLOAI_TESSERACT_BUNDLE"
TESSERACT_ROOT_ENV = "EMPLOAI_TESSERACT_ROOT"
TESSERACT_MISSING_MESSAGE = (
    "OCR is unavailable because the Tesseract OCR engine was not found. "
    "If you installed EmploAI via the Windows MSI/EXE, reinstall or repair the app "
    "to restore the bundled OCR files. You can also install Tesseract manually and restart EmploAI."
)


@dataclass(frozen=True)
class TesseractRuntime:
    root: Path | None
    executable: Path | None
    tessdata: Path | None
    source: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_candidates(extra_roots: Sequence[Path | str] | None = None) -> Iterable[tuple[str, Path]]:
    seen: set[str] = set()

    def add(label: str, candidate: Path | str | None) -> Iterable[tuple[str, Path]]:
        if candidate is None:
            return ()
        try:
            path = Path(candidate).expanduser().resolve()
        except Exception:
            return ()
        key = str(path).lower()
        if key in seen:
            return ()
        seen.add(key)
        return ((label, path),)

    if extra_roots:
        for candidate in extra_roots:
            yield from add("explicit", candidate)

    yield from add("env-root", os.getenv(TESSERACT_ROOT_ENV))
    yield from add("env-bundle", os.getenv(TESSERACT_BUNDLE_ENV))

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield from add("frozen-bundle", Path(meipass) / "vendor" / "tesseract")

    yield from add("exe-bundle", Path(sys.executable).resolve().parent / "vendor" / "tesseract")
    yield from add("repo-vendor", _project_root() / "deploy" / "windows" / "vendor" / "tesseract")

    which_tesseract = shutil.which("tesseract")
    if which_tesseract:
        yield from add("system-path", Path(which_tesseract).resolve().parent)

    if os.name == "nt":
        yield from add("program-files", Path(r"C:\Program Files\Tesseract-OCR"))
        yield from add("program-files-x86", Path(r"C:\Program Files (x86)\Tesseract-OCR"))


def resolve_tesseract_runtime(extra_roots: Sequence[Path | str] | None = None) -> TesseractRuntime:
    executable_name = "tesseract.exe" if os.name == "nt" else "tesseract"

    for source, root in _iter_candidates(extra_roots=extra_roots):
        executable = root / executable_name
        if not executable.exists():
            continue
        tessdata = root / "tessdata"
        return TesseractRuntime(
            root=root,
            executable=executable,
            tessdata=tessdata if tessdata.exists() else None,
            source=source,
        )

    return TesseractRuntime(root=None, executable=None, tessdata=None, source="missing")


def configure_pytesseract_runtime(pytesseract_module, extra_roots: Sequence[Path | str] | None = None) -> TesseractRuntime:
    runtime = resolve_tesseract_runtime(extra_roots=extra_roots)
    if runtime.executable is None:
        return runtime

    pytesseract_module.pytesseract.tesseract_cmd = str(runtime.executable)
    if runtime.tessdata is not None:
        os.environ["TESSDATA_PREFIX"] = str(runtime.tessdata)
    return runtime


def is_tesseract_not_found_error(exc: Exception, pytesseract_module=None) -> bool:
    if pytesseract_module is not None:
        missing_error = getattr(pytesseract_module, "TesseractNotFoundError", None)
        if missing_error is not None and isinstance(exc, missing_error):
            return True

    text = str(exc).lower()
    return "not installed or it's not in your path" in text or "tesseractnotfounderror" in text


def normalize_tesseract_error(exc: Exception, pytesseract_module=None) -> str:
    if is_tesseract_not_found_error(exc, pytesseract_module=pytesseract_module):
        return TESSERACT_MISSING_MESSAGE
    return str(exc)
