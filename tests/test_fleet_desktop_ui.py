from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_on_demand_workers_render_as_ready_between_tasks():
    helper = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "desktopFleetWorkerState.ts"
    ).read_text(encoding="utf-8")
    fleet = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationDerivedTail.tsx"
    ).read_text(encoding="utf-8")
    jarvis = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationJarvisStage.tsx"
    ).read_text(encoding="utf-8")

    assert "kind === 'local' && !activeTask" in helper
    assert "status === 'offline' || status === 'stale'" in helper
    assert "fleetWorkerStatusLabel(worker, task)" in fleet
    assert "workers.filter(isFleetWorkerAvailable)" in jarvis


def test_fleet_chat_panel_hides_a_transcript_until_it_matches_the_selected_identity():
    fleet = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationDerivedTail.tsx"
    ).read_text(encoding="utf-8")

    assert "sessionBelongsToFleetIdentity(scope.activeSession, activeFleetIdentity)" in fleet
    assert "fleetManagerSessionMatchesIdentity ? transcriptEntries.slice(-10) : []" in fleet
    assert "fleetManagerSessionMatchesIdentity ? assistantDraft : ''" in fleet
    assert "fleetManagerSessionMatchesIdentity && shouldShowThinkingIndicator" in fleet


def test_fleet_workspace_switches_to_worker_only_controls_for_worker_identity():
    derived = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationDerivedTail.tsx"
    ).read_text(encoding="utf-8")
    worker_workspace = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopFleetWorkerWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert "const fleetWorkerMode = activeFleetIdentity?.role === 'worker'" in derived
    assert "fleetWorkerMode && activeFleetIdentity && fleetSnapshot" in derived
    assert "!fleetWorkerMode ? (" in derived
    assert "<DesktopFleetWorkerWorkspace" in derived
    assert "This worker cannot delegate or manage connected computers" in derived
    assert "Switch to Manager Console" in worker_workspace
    assert "Connected-computer controls are unavailable in Worker view" in worker_workspace
    assert "DesktopFleetMachinesPanel" not in worker_workspace
    assert "Update and restart" not in worker_workspace


def test_manager_tool_pack_menu_keeps_core_but_allows_optional_packs():
    derived = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationDerivedTail.tsx"
    ).read_text(encoding="utf-8")
    controls = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationVoiceControls.ts"
    ).read_text(encoding="utf-8")

    assert "const managerProfileSelected = activeToolProfileRole === 'manager'" in derived
    assert "Manager Core stays enabled. Optional packs let this manager act directly" in derived
    assert "disabled={toolPackMutationInFlight === pack.id}" in derived
    assert "Manager tools are fixed" not in controls


def test_connected_manager_tools_have_a_compact_permissioned_editor():
    machines = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetComputerSettingsPage.tsx").read_text(encoding="utf-8")
    manager_tools = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetManagerTools.tsx").read_text(encoding="utf-8")
    access = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetConnectionAccess.tsx").read_text(encoding="utf-8")

    assert "Open settings for ${machine.name}" in machines
    assert "<DesktopFleetManagerTools" in settings
    assert "setDesktopFleetManagerToolPacksOnComputer" in settings
    assert "From this computer" in settings
    assert "Tools on {machine.name}" in settings
    assert "Configure manager tools" in access
    assert "Manager Core" in manager_tools
    assert "Remote configuration blocked" in manager_tools
    assert "Save tools" in manager_tools


def test_connected_computer_settings_are_a_dedicated_fleet_page():
    setup = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopSetupPanel.tsx").read_text(encoding="utf-8")
    machines = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    workspace = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetWorkspace.tsx").read_text(encoding="utf-8")
    tail = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopConversationDerivedTail.tsx").read_text(encoding="utf-8")

    assert "This Computer’s Manager" in setup
    assert "Child Computer Managers" not in setup
    assert "fleet_children" not in setup
    assert "onOpenComputerSettings(machine.id)" in machines
    assert "<DesktopFleetComputerSettingsPage" in workspace
    assert "onOpenComputerSettings={setSettingsDesktopId}" in workspace
    assert "fleet_children" not in tail


def test_fleet_activity_summaries_auto_open_and_collapse_without_stretched_cards():
    activity = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetComputerActivity.tsx").read_text(encoding="utf-8")
    requests = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetRequestsPanel.tsx").read_text(encoding="utf-8")
    disclosure = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "useFleetAutoDisclosure.ts").read_text(encoding="utf-8")
    machines = (ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")

    assert "30 * 60 * 1000" in disclosure
    assert "setExpanded(true)" in disclosure
    assert "useFleetAutoDisclosure" in activity
    assert "useFleetAutoDisclosure" in requests
    assert "alignItems: 'flex-start'" in machines
    assert "signalRow:" in machines
    assert "workRow:" in machines
    assert "<DesktopFleetReportsPanel" in machines
    assert "detailColumns:" not in machines
    assert "drawerColumns:" not in machines


def test_fleet_identity_snapshots_cannot_roll_selection_back():
    snapshot_policy = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "desktopFleetSnapshot.ts"
    ).read_text(encoding="utf-8")
    actions = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationFleetActions.ts"
    ).read_text(encoding="utf-8")
    realtime = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationRealtime.ts"
    ).read_text(encoding="utf-8")

    assert "fleetIdentitySelectionVersion(incoming) < fleetIdentitySelectionVersion(current)" in snapshot_policy
    assert "applyFleetIdentitySelection" in actions
    assert "requestId !== fleetSnapshotRequestRef.current" in actions
    assert "preferNewerFleetIdentitySnapshot(current, snapshot)" in actions
    assert "preferNewerFleetIdentitySnapshot(current, normalizedSnapshot)" in realtime


def test_cold_desktop_startup_resolves_manager_before_loading_a_chat():
    shell = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopAppShellView.tsx"
    ).read_text(encoding="utf-8")
    actions = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationFleetActions.ts"
    ).read_text(encoding="utf-8")
    sync = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopConversationSyncControls.ts"
    ).read_text(encoding="utf-8")

    assert "initialSessionId={requestedSessionId || undefined}" in shell
    assert "'desktop_startup'" in actions
    assert "String(identity.role || '').toLowerCase() === 'manager'" in actions
    assert "if (!apiBaseUrl || !token || !fleetSnapshot) return;" in sync
    assert "initialSessionId || selectedIdentityChatId || null" in sync


def test_session_opening_remembers_a_chat_without_changing_identity():
    session_routes = (ROOT / "app_backend" / "app_server_routes_sessions.py").read_text(encoding="utf-8")

    assert ".set_active_fleet_identity(" not in session_routes
    assert ".set_active_chat_for_fleet_identity(" in session_routes
    assert 'event_type="fleet_identity_chat_selected"' in session_routes


def test_live_preview_stops_automatic_retries_when_windows_display_is_unavailable():
    preview = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopFleetLivePreview.tsx"
    ).read_text(encoding="utf-8")
    scheduler = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "desktopFleetPreviewScheduler.ts"
    ).read_text(encoding="utf-8")
    connection = (
        ROOT
        / "desktop_app"
        / "renderer_client"
        / "src"
        / "desktop"
        / "DesktopFleetConnectionPanel.tsx"
    ).read_text(encoding="utf-8")
    shell = (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8")

    assert "result.capture_capability?.available === false" in scheduler
    assert "automaticCaptureBlocked.add(desktopId)" in scheduler
    assert "options.automatic && automaticCaptureBlocked.has(desktopId)" in scheduler
    assert "Screen unavailable" in preview
    assert "DISPLAY UNAVAILABLE" in preview
    assert "BACKGROUND HOST READY" in connection
    assert "stopLocalRuntime({ preserveFleetHost: true })" in shell
    assert "stopLocalRuntime();" in shell
