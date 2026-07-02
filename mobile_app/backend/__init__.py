"""Compatibility shim for the old ``mobile_app.backend`` package path.

The local desktop backend now lives in :mod:`app_backend`. This package keeps
older imports and ``python -m mobile_app.backend.<module>`` commands working
while code migrates to the neutral package name.
"""

from __future__ import annotations

from importlib import import_module

_backend = import_module("app_backend")

__path__ = list(getattr(_backend, "__path__", []))
__all__ = list(getattr(_backend, "__all__", []))


def __getattr__(name: str):
    return getattr(_backend, name)


def create_app(*args, **kwargs):
    return _backend.create_app(*args, **kwargs)


def start_embedded_app_server_if_enabled(*args, **kwargs):
    return _backend.start_embedded_app_server_if_enabled(*args, **kwargs)
