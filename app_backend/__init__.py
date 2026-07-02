from __future__ import annotations


def create_app(*args, **kwargs):
    from .app_server import create_app as _create_app

    return _create_app(*args, **kwargs)


def start_embedded_app_server_if_enabled(*args, **kwargs):
    from .app_server import start_embedded_app_server_if_enabled as _start_embedded_app_server_if_enabled

    return _start_embedded_app_server_if_enabled(*args, **kwargs)


__all__ = ["create_app", "start_embedded_app_server_if_enabled"]
