from __future__ import annotations

import json
import subprocess
from pathlib import Path

from desktop_runtime import backend
from app_backend.remote_control_store import RemoteControlPlaneStore
from shared.fleet_connection import write_fleet_connection


ROOT = Path(__file__).resolve().parents[1]


def test_yggdrasil_enrollment_adds_computer_without_creating_worker_or_identity(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Build worker",
        metadata={"transport": "yggdrasil"},
    )
    completed = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Worker PC",
        device_platform="windows",
        device_key="worker-key",
    )

    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])
    desktop_ids = {item["desktop_id"] for item in snapshot["desktops"]}

    assert completed["worker"] is None
    assert completed["desktop"]["desktop_id"] in desktop_ids
    assert snapshot["workers"] == []
    assert all(item.get("desktop_id") != completed["desktop"]["desktop_id"] for item in snapshot["identities"])


def test_computer_pairing_is_durable_and_rotates_session_without_creating_worker(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )

    def pair_again():
        enrollment = store.create_worker_enrollment(
            user_id=0,
            desktop_id=manager["desktop_id"],
            display_name="Durable worker",
            metadata={"transport": "yggdrasil"},
        )
        return store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name="Worker PC",
            device_platform="windows",
            device_key="stable-worker-key",
        )

    first = pair_again()
    second = pair_again()

    assert first["expires_at"] == 0
    assert second["expires_at"] == 0
    assert first["worker"] is None
    assert second["worker"] is None
    assert first["desktop"]["desktop_id"] == second["desktop"]["desktop_id"]
    assert first["session_token"] != second["session_token"]
    assert store.resolve_session_token(first["session_token"]) is None
    assert store.resolve_session_token(second["session_token"])["desktop_id"] == second["desktop"]["desktop_id"]

    assert store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])["workers"] == []


def test_yggdrasil_status_exposes_connection_without_session_token(tmp_path: Path, monkeypatch):
    write_fleet_connection(
        home=tmp_path,
        payload={
            "apiBaseUrl": "http://[200::abcd]:8787",
            "managerUrl": "http://[200::abcd]:8787",
            "sessionToken": "secret-worker-session",
            "desktop": {"desktop_id": "dsk_worker", "device_name": "Worker PC"},
            "worker": {"worker_id": "wrk_worker", "display_name": "Build worker"},
            "transport": {
                "kind": "yggdrasil",
                "managerYggdrasilIp": "200::abcd",
                "pairedAt": 1234,
            },
        },
    )
    monkeypatch.setattr(backend, "_runtime_paths", lambda: (ROOT, tmp_path, tmp_path / ".env"))
    monkeypatch.setattr(
        "shared.fleet_yggdrasil.yggdrasil_status",
        lambda _home: {"available": True, "running": True, "address": "200::beef"},
    )
    monkeypatch.setattr(
        backend,
        "_read_remote_control_status_record",
        lambda _home: {"state": "connected", "detail": "Worker relay connected."},
    )

    status = backend._fleet_yggdrasil_status()

    assert status["connection"] == {
        "configured": True,
        "role": "paired",
        "managerUrl": "http://[200::abcd]:8787",
        "managerYggdrasilIp": "200::abcd",
        "pairedAt": 1234,
        "desktopId": "dsk_worker",
        "desktopName": "Worker PC",
        "workerId": "wrk_worker",
        "workerName": "Build worker",
        "relayState": "connected",
        "relayDetail": "Worker relay connected.",
        "permissions": {
            "delegate_manager": True,
            "delegate_workers": True,
            "create_workers": False,
        },
        "pendingRequest": None,
        "lastDecision": None,
        "updatedAt": None,
    }
    serialized = json.dumps(status)
    assert "secret-worker-session" not in serialized
    assert "sessionToken" not in serialized


def test_desktop_yggdrasil_bridge_accepts_only_complete_pairing_tokens(tmp_path: Path):
    service_path = ROOT / "desktop_app" / "fleet_yggdrasil_services.js"
    script = r"""
const { createFleetYggdrasilServices } = require(process.argv[1]);
const calls = [];
const services = createFleetYggdrasilServices({
  runBackendJson: async (args, options) => { calls.push({ args, options }); return { ok: true }; },
});
(async () => {
  let rejected = false;
  try { await services.join({ pairingToken: 'fw_inner_token', deviceName: 'Worker' }); }
  catch (error) { rejected = String(error.message || error).includes('complete EmploAI Yggdrasil Fleet pairing code'); }
  if (!rejected || calls.length !== 0) process.exit(2);
  await services.createPairing({ displayName: 'Worker One', expiresInSeconds: 1800 });
  await services.join({ pairingToken: 'emploai-yggdrasil-v1.abc', deviceName: 'Worker One' });
  if (calls[0].args[0] !== 'yggdrasil-bootstrap') process.exit(3);
  if (calls[1].args[0] !== 'fleet-yggdrasil-pair') process.exit(4);
  if (!calls[1].args.includes('--configure-manager-bind')) process.exit(5);
  if (calls[2].args[0] !== 'yggdrasil-bootstrap') process.exit(6);
  if (calls[3].args[0] !== 'fleet-yggdrasil-join') process.exit(7);
})().catch(() => process.exit(8));
"""
    result = subprocess.run(
        ["node", "-e", script, str(service_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_desktop_has_one_fleet_surface_and_redirects_legacy_remote_links():
    shell = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopAppShell.tsx").read_text(encoding="utf-8")
    shell_view = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopAppShellView.tsx").read_text(encoding="utf-8")
    fleet_panel = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetConnectionPanel.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopSetupPanel.tsx").read_text(encoding="utf-8")
    preload = (ROOT / "desktop_app" / "preload.js").read_text(encoding="utf-8")

    header_tabs = shell_view.split("const CONVERSATION_HEADER_TABS", 1)[1].split("] as const", 1)[0]
    assert "label: 'Fleet'" in header_tabs
    assert "label: 'Remote'" not in header_tabs
    assert "return { mode: 'local', surface: 'fleet' };" in shell
    assert "nextUrl.searchParams.set('tab', 'fleet')" in shell_view
    assert "Connect computers with Yggdrasil" in fleet_panel
    assert "No EmploAI account" in fleet_panel
    assert "joinDesktopFleetYggdrasil" in fleet_panel
    assert "Create & Copy Connection Code" in fleet_panel
    assert "completed pairings reconnect after restarts" in fleet_panel
    assert "It does not copy" in fleet_panel or "stay local" in fleet_panel
    assert "yggdrasilCreatePairing" in preload
    assert "yggdrasilJoin" in preload
    assert "SETTINGS_TABS.filter((tab) => tab.key !== 'remote')" in settings
