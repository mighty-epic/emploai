from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from desktop_runtime.config import load_runtime_config, save_runtime_config


def manager_mode_enabled(config: Mapping[str, Any]) -> bool:
    fleet = config.get("fleet") if isinstance(config.get("fleet"), dict) else {}
    return bool(fleet.get("manager_enabled", False))


def manager_bind_ready(config: Mapping[str, Any]) -> bool:
    channels = config.get("channels") if isinstance(config.get("channels"), dict) else {}
    desktop = channels.get("desktop") if isinstance(channels.get("desktop"), dict) else {}
    host = str(desktop.get("host") or "").strip().lower()
    return host in {"::", "[::]"}


def _runtime_bind_ready(runtime: Mapping[str, Any]) -> bool:
    if "bind_host" not in runtime:
        # Compatibility for callers that only know whether a runtime is up.
        return True
    host = str(runtime.get("bind_host") or "").strip().lower().strip("[]")
    return host == "::"


def enable_manager_mode(home: Path) -> bool:
    config = load_runtime_config(home)
    if manager_mode_enabled(config):
        return False
    fleet = dict(config.get("fleet") or {})
    fleet["manager_enabled"] = True
    config["fleet"] = fleet
    save_runtime_config(home, config)
    return True


def reconcile_manager_connection_config(home: Path, *, enable: bool = False) -> dict[str, bool]:
    config = load_runtime_config(home)
    marker_changed = False
    configured_manager = manager_mode_enabled(config) or manager_bind_ready(config)
    if (enable or configured_manager) and not manager_mode_enabled(config):
        fleet = dict(config.get("fleet") or {})
        fleet["manager_enabled"] = True
        config["fleet"] = fleet
        marker_changed = True
    if not manager_mode_enabled(config):
        if marker_changed:
            save_runtime_config(home, config)
        return {"enabled": False, "marker_changed": marker_changed, "bind_changed": False}

    channels = config.get("channels") if isinstance(config.get("channels"), dict) else {}
    next_channels = dict(channels)
    desktop = dict(next_channels.get("desktop") or {})
    app = dict(next_channels.get("app") or {})
    bind_changed = False
    if str(desktop.get("host") or "").strip() not in {"::", "[::]"}:
        desktop["host"] = "::"
        bind_changed = True
    if str(app.get("host") or "").strip() not in {"::", "[::]"}:
        app["host"] = "::"
        bind_changed = True
    next_channels["desktop"] = desktop
    next_channels["app"] = app
    config["channels"] = next_channels
    if marker_changed or bind_changed:
        save_runtime_config(home, config)
    return {"enabled": True, "marker_changed": marker_changed, "bind_changed": bind_changed}


def manager_connection_status(
    home: Path,
    *,
    yggdrasil: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    config = load_runtime_config(home)
    bind_ready = manager_bind_ready(config)
    enabled = manager_mode_enabled(config) or bind_ready
    transport_ready = bool(yggdrasil.get("available")) and bool(yggdrasil.get("running")) and bool(yggdrasil.get("address"))
    runtime_ready = bool(runtime.get("ok"))
    runtime_bind_ready = _runtime_bind_ready(runtime)
    live_bind_ready = bind_ready and (not runtime_ready or runtime_bind_ready)
    ready = transport_ready and live_bind_ready and runtime_ready
    if ready:
        state = "online"
        detail = "Paired computers can reach this manager over Yggdrasil."
    elif not bool(yggdrasil.get("available")):
        state = "unavailable"
        detail = "Yggdrasil is not installed on this computer."
    elif not bool(yggdrasil.get("running")):
        state = "offline"
        detail = "The Yggdrasil service is stopped."
    elif not bind_ready:
        state = "needs_repair"
        detail = "The manager backend is restricted to this computer and needs its Fleet binding repaired."
    elif runtime_ready and not runtime_bind_ready:
        state = "needs_repair"
        detail = "The manager backend is running on this computer only and must restart on its Fleet binding."
    else:
        state = "starting" if str(runtime.get("state") or "") == "starting" else "offline"
        detail = str(runtime.get("detail") or "The manager backend is not running.")
    return {
        "enabled": enabled,
        "ready": ready,
        "state": state,
        "detail": detail,
        "address": str(yggdrasil.get("address") or "").strip() or None,
        "transport_ready": transport_ready,
        "bind_ready": live_bind_ready,
        "configured_bind_ready": bind_ready,
        "runtime_bind_ready": runtime_bind_ready,
        "runtime_ready": runtime_ready,
        "persistent": enabled and bind_ready,
    }
