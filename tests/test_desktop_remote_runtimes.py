from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_surface_is_derived_from_local_fleet_without_account_gate():
    shell = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopAppShell.tsx").read_text(encoding="utf-8")
    helper = (ROOT / "desktop_app/renderer_client/src/desktop/desktopRemoteRuntimes.ts").read_text(encoding="utf-8")

    assert "remoteRuntimesFromFleetSnapshot(fleet)" in shell
    assert "if (!remoteAuthStatus?.signedIn)" not in shell[shell.index("const [remoteRuntimes") : shell.index("const effectiveRuntimeStatus")]
    assert "worker.machine_desktop_id" in helper
    assert "desktopId === managerDesktopId" in helper
