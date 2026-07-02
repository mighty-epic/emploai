"""Compatibility shim for the old ``bot_core`` package name."""

from importlib import import_module

_support = import_module("runtime_support")
__path__ = list(getattr(_support, "__path__", []))
__all__ = list(getattr(_support, "__all__", []))


def __getattr__(name: str):
    return getattr(_support, name)
