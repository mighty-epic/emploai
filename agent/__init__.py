"""Compatibility shim for the old generic ``agent`` package name."""

from importlib import import_module

_legacy = import_module("legacy_agent_orchestration")
__path__ = list(getattr(_legacy, "__path__", []))
__all__ = list(getattr(_legacy, "__all__", []))


def __getattr__(name: str):
    return getattr(_legacy, name)
