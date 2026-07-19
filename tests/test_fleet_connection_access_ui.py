from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_connection_access_is_a_compact_safe_disclosure():
    machines = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    access = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetConnectionAccess.tsx").read_text(encoding="utf-8")

    assert "<DesktopFleetConnectionAccess" in machines
    assert "Request a permission change" not in machines
    assert "accessibilityState={{ expanded }}" in access
    assert "Connection access" in access
    assert "of {permissionRows.length} allowed" in access
    assert "permissions blocked" in access
    assert "Changes require approval on" in access
    assert "Cancel" in access
    assert "Send request" in access


def test_connection_access_only_submits_a_changed_non_pending_draft():
    access = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetConnectionAccess.tsx").read_text(encoding="utf-8")

    assert "const hasChanges" in access
    assert "requestPending || !hasChanges" in access
    assert "if (submitDisabled) return" in access
    assert "A change is waiting for approval on" in access
    assert "setDraft(copyPermissions(permissions))" in access
