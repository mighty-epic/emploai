from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs(*, creationflags: int = 0) -> dict[str, Any]:
    """Keep background command-line helpers from flashing a console on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": int(creationflags) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        "startupinfo": startupinfo,
    }
