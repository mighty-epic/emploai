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
