"""Immutable local-only product policy.

Cloud accounts and the hosted control plane are no longer product modes.  The
functions remain as small compatibility seams for older callers, but no
environment variable can re-enable a hosted backend or mobile pairing.
"""

from __future__ import annotations


def cloud_backend_enabled() -> bool:
    return False


def mobile_connection_enabled() -> bool:
    return False


def standalone_desktop_enabled() -> bool:
    return True
