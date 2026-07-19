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
