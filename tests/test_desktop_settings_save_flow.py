from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop_app" / "renderer_client" / "src" / "desktop"


def test_settings_footer_saves_every_dirty_section_with_visible_feedback():
    panel = (DESKTOP / "DesktopSetupPanel.tsx").read_text(encoding="utf-8")

    assert "const persistDirtySections = async () =>" in panel
    assert "if (editedValueKeysRef.current.size > 0)" in panel
    assert "if (memoryDirty)" in panel
    assert "if (sharedSettingsDirty)" in panel
    assert "onPress={() => void saveAllChanges()}" in panel
    assert "Save Changes" in panel
    assert "Local runtime settings saved and applied." in panel
    assert 'accessibilityLiveRegion="polite"' in panel
    assert "disabled={!settingsDirty || saveBusy}" in panel


def test_local_settings_live_apply_uses_fresh_setup_credentials():
    actions = (DESKTOP / "DesktopAppShellActions.ts").read_text(encoding="utf-8")

    assert "const runtimeApiBaseUrl = setupPayload.apiBaseUrl || bootstrap?.apiBaseUrl" in actions
    assert "const runtimeAccessToken = setupPayload.accessToken || bootstrap?.accessToken" in actions
    assert "configureAgent(\n            runtimeApiBaseUrl,\n            runtimeAccessToken" in actions
    assert "configureHeadlessRuntime(runtimeApiBaseUrl, runtimeAccessToken" in actions


def test_local_setting_toggles_expose_switch_state_and_help():
    section = (DESKTOP / "DesktopSetupSharedSettingsSection.tsx").read_text(encoding="utf-8")

    assert 'accessibilityRole="switch"' in section
    assert "accessibilityState={{ checked: value }}" in section
    assert 'title="Verbose feed"' in section
    assert "Show detailed tool and runtime activity in chat." in section
    assert 'accessibilityLiveRegion="polite"' in section
