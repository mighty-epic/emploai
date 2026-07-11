from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_startup_phase_and_account_requests_are_synchronously_guarded():
    shell = (
        ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopAppShell.tsx"
    ).read_text(encoding="utf-8")

    assert "startupPhaseRef.current = nextPhase;\n    setStartupPhase(nextPhase);" in shell
    assert "startupRequests.invalidate();" in shell
    assert "accountHydrationRequests.invalidate();" in shell
    assert "const requestIsCurrent = () => startupRequests.isCurrent(requestId);" in shell
    assert "if (requestIsCurrent()) {\n        startupFlowInFlightRef.current = false;" in shell


def test_forced_bootstrap_is_forwarded_and_waits_for_a_fresh_main_process_result():
    bridge = (
        ROOT / "desktop_app" / "renderer_client" / "src" / "lib" / "desktopBridge.ts"
    ).read_text(encoding="utf-8")
    main = (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8")

    assert "force: Boolean(options?.force)" in bridge
    assert "if (!options?.force)" in main
    assert "await pendingBootstrap;" in main
    assert "if (bootstrapRuntimePromise === currentBootstrap)" in main

    bootstrap_handler = main.split("ipcMain.handle('emploai:bootstrap'", 1)[1].split(");", 1)[0]
    assert "bootstrapCache = null;" not in bootstrap_handler
    assert "mergeBootstrapCache(bootstrapCache, nextPayload, options)" in main
    assert "updateBootstrapCaches(payload, { preserveConnectedSession: false })" in main
    assert ").then(normalizeDesktopBootstrapRuntimeStatus)" in bridge


def test_ready_desktop_keeps_monitoring_runtime_liveness_and_drops_stale_process_state():
    shell = (
        ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopAppShell.tsx"
    ).read_text(encoding="utf-8")
    render = (
        ROOT / "desktop_app" / "renderer_client" / "src" / "desktop" / "DesktopConversationRender.tsx"
    ).read_text(encoding="utf-8")

    assert "const RUNTIME_OFFLINE_CONFIRMATIONS = 2;" in shell
    assert "startupPhase !== 'ready' || setupBlocksRuntime" in shell
    assert "const status = await loadDesktopRuntimeStatus();" in shell
    assert "if (status.runtimeProcessDetected)" in shell
    assert "payload = normalizeDesktopBootstrapRuntimeStatus(payload);" in shell
    assert "runtimeOfflinePollsRef.current < RUNTIME_OFFLINE_CONFIRMATIONS" in shell
    assert "runtimeProcessDetected: false" in shell
    assert "const effectiveRuntimeStatus = runtimeStatus || bootstrap?.runtimeStatus || null;" in shell
    assert "effectiveRuntimeStatus?.ok && (" in shell
    assert "Checking local runtime status..." not in shell
    assert "accessibilityLiveRegion=\"polite\"" in render
    assert "{shortStatusText(status)}" in render
