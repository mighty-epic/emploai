"""Compatibility shim for the old ``single_agent`` package name.

The active source now lives in ``local_agent_runtime``. Keeping this package
path lets older imports such as ``single_agent.agent`` keep working while new
code migrates to ``local_agent_runtime.agent``.
"""

from importlib import import_module

_runtime = import_module("local_agent_runtime")
__path__ = list(getattr(_runtime, "__path__", []))
__all__ = list(getattr(_runtime, "__all__", []))


def __getattr__(name: str):
    return getattr(_runtime, name)
