from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional


_DLL_DIRECTORY_HANDLES: list[Any] = []


def bundled_python_dependencies(repo_root: Optional[Path] = None) -> Path:
    """Return the optional Python dependency bundle used by packaged desktop builds."""

    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    return root / "desktop_app" / "backend" / "_internal"


def configure_bundled_python_dependencies(
    repo_root: Optional[Path] = None,
) -> Optional[Path]:
    """Expose packaged Python dependencies when the optional bundle is present.

    Source checkouts don't contain ``desktop_app/backend/_internal``. Importing a
    voice module must still work there, so missing bundles are deliberately a
    no-op. Windows DLL directory handles are retained for the process lifetime.
    """

    dependency_dir = bundled_python_dependencies(repo_root)
    if not dependency_dir.is_dir():
        return None

    dependency_path = str(dependency_dir)
    if dependency_path not in sys.path:
        sys.path.insert(0, dependency_path)

    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(dependency_path))
        except OSError:
            # A present bundle can still lack a native dependency on a developer
            # machine. Let the eventual dependency import report the useful error.
            pass
    return dependency_dir
