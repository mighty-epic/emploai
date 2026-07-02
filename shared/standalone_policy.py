from __future__ import annotations

import os


STANDALONE_DESKTOP_ENV = "EMPLOAI_STANDALONE_DESKTOP"
CLOUD_BACKEND_ENABLED_ENV = "EMPLOAI_CLOUD_BACKEND_ENABLED"
MOBILE_CONNECTION_ENABLED_ENV = "EMPLOAI_MOBILE_CONNECTION_ENABLED"

_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_FALSY = {"0", "false", "no", "off", "disabled"}


def _env_flag(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return None


def cloud_backend_enabled() -> bool:
    explicit_cloud = _env_flag(CLOUD_BACKEND_ENABLED_ENV)
    if explicit_cloud is not None:
        return explicit_cloud
    explicit_standalone = _env_flag(STANDALONE_DESKTOP_ENV)
    if explicit_standalone is not None:
        return not explicit_standalone
    return False


def mobile_connection_enabled() -> bool:
    explicit_mobile = _env_flag(MOBILE_CONNECTION_ENABLED_ENV)
    if explicit_mobile is not None:
        return explicit_mobile
    return cloud_backend_enabled()


def standalone_desktop_enabled() -> bool:
    explicit_standalone = _env_flag(STANDALONE_DESKTOP_ENV)
    if explicit_standalone is not None:
        return explicit_standalone
    return not cloud_backend_enabled()
