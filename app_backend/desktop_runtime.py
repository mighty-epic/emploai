"""Compatibility wrapper for the old ``app_backend.desktop_runtime`` module.

The local app API server helper now lives in ``app_backend.local_runtime_server``.
This wrapper keeps old imports and ``python -m app_backend.desktop_runtime``
commands working while active code uses the clearer module name.
"""

from __future__ import annotations

from app_backend.local_runtime_server import *  # noqa: F401,F403
from app_backend.local_runtime_server import main as _main


if __name__ == "__main__":
    raise SystemExit(_main())
