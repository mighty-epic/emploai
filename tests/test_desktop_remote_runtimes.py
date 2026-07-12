from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_surface_is_derived_from_local_fleet_without_account_gate():
    machine_panel = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    shell_view = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopAppShellView.tsx").read_text(encoding="utf-8")
    helper = (ROOT / "desktop_app/renderer_client/src/desktop/desktopRemoteRuntimes.ts").read_text(encoding="utf-8")

    assert "remoteRuntimesFromFleetSnapshot(snapshot)" in machine_panel
    assert "Computers in this Fleet" in machine_panel
    assert "label: 'Remote'" not in shell_view
    assert "worker.machine_desktop_id" in helper
    assert "desktopId === managerDesktopId" in helper
