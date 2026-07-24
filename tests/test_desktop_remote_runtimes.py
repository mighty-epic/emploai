from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_surface_is_derived_from_local_fleet_without_account_gate():
    machine_panel = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    shell_view = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopAppShellView.tsx").read_text(encoding="utf-8")
    helper = (ROOT / "desktop_app/renderer_client/src/desktop/desktopRemoteRuntimes.ts").read_text(encoding="utf-8")
    snapshot_helper = (ROOT / "desktop_app/renderer_client/src/desktop/desktopFleetSnapshot.ts").read_text(encoding="utf-8")
    workspace = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetWorkspace.tsx").read_text(encoding="utf-8")

    assert "remoteRuntimesFromFleetSnapshot(snapshot)" in machine_panel
    assert "Only computers directly below this one appear here" in machine_panel
    assert "label: 'Remote'" not in shell_view
    assert "worker.machine_desktop_id" in helper
    assert "fleetDirectChildDesktopIds(fleet)" in helper
    assert "const connected = desktop" in helper
    assert "machine.hostLabel" in machine_panel
    assert "permission.source" in snapshot_helper
    assert "paired_desktop" in snapshot_helper
    assert "remoteAuthStatus" not in snapshot_helper
    assert "Connected computers could not be read" in workspace
    assert "Reconnect Fleet" in workspace
    assert "DesktopFleetManagerConnectionPanel" in workspace
    assert "name: isManager" not in helper
