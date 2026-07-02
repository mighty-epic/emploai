"""Compatibility wrapper for the moved desktop runtime config module."""

from importlib import import_module
import sys

_compat_name = __name__
_module = import_module("desktop_runtime.config")
globals().update(_module.__dict__)
sys.modules[_compat_name] = _module
