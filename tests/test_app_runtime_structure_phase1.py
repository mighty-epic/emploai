from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from cli.models.session import Session
from cli.session_manager import SessionManager
from app_backend import app_server, runtime, session_bridge
from shared.task_board import create_task_board
from shared.tool_packs import default_enabled_tool_packs
from telegram_bot.telegram_session_state import TelegramSession


def test_mobile_surfaces_expose_chat_fleet_and_jarvis_navigation():
    root = Path(__file__).resolve().parents[1]
    chat_screen = (root / "mobile_app/client/src/screens/ChatScreen.tsx").read_text(encoding="utf-8")
    chat_screen_view = (root / "mobile_app/client/src/screens/ChatScreenView.tsx").read_text(encoding="utf-8")
    chat_screen_realtime = (root / "mobile_app/client/src/screens/ChatScreenRealtime.ts").read_text(encoding="utf-8")
    chat_screen_attachments = (root / "mobile_app/client/src/screens/ChatScreenAttachments.ts").read_text(encoding="utf-8")
    chat_screen_helpers = (root / "mobile_app/client/src/screens/ChatScreen.helpers.ts").read_text(encoding="utf-8")
    chat_screen_styles = (root / "mobile_app/client/src/screens/ChatScreen.styles.ts").read_text(encoding="utf-8")
    chat_surface = "\n".join([
        chat_screen,
        chat_screen_view,
        chat_screen_realtime,
        chat_screen_attachments,
        chat_screen_helpers,
        chat_screen_styles,
    ])
    fleet_screen = (root / "mobile_app/client/src/screens/FleetScreen.tsx").read_text(encoding="utf-8")
    agent_screen = (root / "mobile_app/client/src/screens/AgentScreen.tsx").read_text(encoding="utf-8")
    drawer = (root / "mobile_app/client/src/components/AppDrawer.tsx").read_text(encoding="utf-8")
    chat_web_route = (root / "desktop_app/renderer_client/app/chat.tsx").read_text(encoding="utf-8")
    fleet_web_route = (root / "desktop_app/renderer_client/app/fleet.tsx").read_text(encoding="utf-8")
    agent_web_route = (root / "desktop_app/renderer_client/app/agent.tsx").read_text(encoding="utf-8")
    app_api = (root / "mobile_app/client/src/lib/appApi.ts").read_text(encoding="utf-8")
    desktop_bridge = (root / "desktop_app/renderer_client/src/lib/desktopBridge.ts").read_text(encoding="utf-8")
    desktop_web_route = (root / "desktop_app/renderer_client/app/desktop.tsx").read_text(encoding="utf-8")
    index_web_route = (root / "desktop_app/renderer_client/app/index.tsx").read_text(encoding="utf-8")
    settings_route = (root / "desktop_app/renderer_client/app/settings.tsx").read_text(encoding="utf-8")
    cron_route = (root / "desktop_app/renderer_client/app/cron.tsx").read_text(encoding="utf-8")
    desktop_shell = (root / "desktop_app/renderer_client/src/desktop/DesktopAppShell.tsx").read_text(encoding="utf-8")
    desktop_shell_view = (root / "desktop_app/renderer_client/src/desktop/DesktopAppShellView.tsx").read_text(encoding="utf-8")
    desktop_shell_surface = "\n".join([desktop_shell, desktop_shell_view])
    desktop_conversation = (
        root / "desktop_app/renderer_client/src/desktop/DesktopConversationView.tsx"
    ).read_text(encoding="utf-8")
    desktop_conversation_sidebar = (
        root / "desktop_app/renderer_client/src/desktop/DesktopConversationSidebarDock.tsx"
    ).read_text(encoding="utf-8")
    desktop_conversation_render = (
        root / "desktop_app/renderer_client/src/desktop/DesktopConversationRender.tsx"
    ).read_text(encoding="utf-8")
    desktop_conversation_overlays = (
        root / "desktop_app/renderer_client/src/desktop/DesktopConversationOverlays.tsx"
    ).read_text(encoding="utf-8")
    desktop_conversation_realtime = (
        root / "desktop_app/renderer_client/src/desktop/DesktopConversationRealtime.ts"
    ).read_text(encoding="utf-8")
    desktop_conversation_controller_parts = [
        (
            root / f"desktop_app/renderer_client/src/desktop/{name}"
        ).read_text(encoding="utf-8")
        for name in [
            "DesktopConversationController.ts",
            "DesktopConversationDerivedValues.tsx",
            "DesktopConversationDerivedTail.tsx",
            "DesktopConversationFleetActions.ts",
            "DesktopConversationFleetEffects.ts",
            "DesktopConversationSessionControls.ts",
            "DesktopConversationSyncControls.ts",
            "DesktopConversationVoiceControls.ts",
        ]
    ]
    desktop_conversation_surface = "\n".join([
        desktop_conversation,
        desktop_conversation_sidebar,
        desktop_conversation_render,
        desktop_conversation_overlays,
        desktop_conversation_realtime,
        *desktop_conversation_controller_parts,
    ])
    desktop_commands = (root / "desktop_app/renderer_client/src/desktop/desktopCommands.ts").read_text(encoding="utf-8")

    assert "Chat selected" in chat_surface
    assert "Open Fleet" in chat_surface
    assert "Open Agent" in chat_surface
    assert "router.push('/agent'" in chat_surface
    assert "config.accountToken || config.accessToken" in chat_surface
    assert "chatConnected" in chat_surface
    assert "chatBlocked" in chat_surface
    assert "requireChatConnection" in chat_surface
    assert "connectionMode === 'remote_cloud' && !pairedDesktopId" in chat_surface
    assert "pair this phone with a desktop first" in chat_surface
    assert "if (!configLoaded || !chatConnected) return" in chat_surface
    assert "const setupMissing = configLoaded && !chatConnected" in chat_surface
    assert "const sendDisabled = chatBlocked || !input.trim()" in chat_surface
    assert "disabled={sendDisabled}" in chat_surface
    assert "sendButtonDisabled" in chat_surface
    assert "const closeFailedChatSocket = (ws: WebSocket)" in chat_surface
    assert "pendingMessagesRef.current.unshift(next)" in chat_surface
    assert "queued chat send failed; retrying" in chat_surface
    assert "options?: { appendLocal?: boolean; sessionId?: string | null }" in chat_surface
    assert "queuePendingMessage(trimmed, { appendLocal: false, sessionId: materializedSessionId })" in chat_surface
    assert "workspace?: string | string[]" in chat_surface
    assert "const requestedWorkspace = normalizeRouteWorkspace(params.workspace)" in chat_surface
    assert "const [draftSessionWorkspace, setDraftSessionWorkspace]" in chat_surface
    assert "blankChatRequestedRef.current = true" in chat_surface
    assert "workspace: draftSessionWorkspace || undefined" in chat_surface
    assert "const suppressAutoSessionLoad = blankChatRequestedRef.current && !requestedSessionId" in chat_surface
    assert "data.type === 'session_snapshot' || data.type === 'session_sync'" in chat_surface
    assert "Ready in ${draftSessionWorkspace}" in chat_surface
    assert "const CHAT_NO_ACTIVE_SESSION_STATUS" in chat_surface
    assert "const hasActiveChatSession = Boolean(sessionId)" in chat_surface
    assert "const agentControlsDisabled = chatBlocked || !hasActiveChatSession" in chat_surface
    assert "const subAgentSpawnDisabled = agentControlsDisabled || !subAgentPrompt.trim()" in chat_surface
    assert "const ensureChatActiveSession = () =>" in chat_surface
    assert "setStatus(CHAT_NO_ACTIVE_SESSION_STATUS)" in chat_surface
    assert "if (!ensureChatActiveSession()) return" in chat_surface
    assert "disabled={subAgentSpawnDisabled}" in chat_surface
    assert "const uploadSessionId = await ensureSessionForSend()" in chat_surface
    assert "form.append('session_id', uploadSessionId)" in chat_surface
    assert "uploadChatAttachment(kind" in chat_screen

    assert "Open Chat" in fleet_screen
    assert "Fleet selected" in fleet_screen
    assert "Open Agent" in fleet_screen
    assert "router.push('/agent'" in fleet_screen
    assert "Connect Fleet" in fleet_screen
    assert "fleetSetupMissing" in fleet_screen
    assert "reconcileRemoteAccountConfig(loadedConfig)" in fleet_screen
    assert "config.accountToken || config.accessToken" in fleet_screen
    assert "connectionMode === 'remote_cloud' && !pairedDesktopId" in fleet_screen
    assert "Pair this phone with a desktop before Fleet" in fleet_screen
    assert "loading || !configLoaded || !fleetConnected" in fleet_screen
    assert "Open Pair from Fleet" in fleet_screen
    assert "Open Settings from Fleet" in fleet_screen
    assert "Fleet not connected" in fleet_screen
    assert "actionDisabled" in fleet_screen
    assert "onCreateSession={(workspace)" in fleet_screen
    assert "params: { newSession: '1', workspace }" in fleet_screen
    assert "function selectedChatIdForWorker(" in fleet_screen
    assert "const targetSessionId = selectedChatIdForWorker(worker, identities, snapshot?.selected_chat_by_identity)" in fleet_screen
    assert "target_session_id: targetSessionId" in fleet_screen
    assert "target_mode: 'auto'" in fleet_screen
    assert "target_session_id: options?.target_session_id || null" in app_api
    assert "target_mode: options?.target_mode || 'auto'" in app_api

    assert "Open Chat" in agent_screen
    assert "Open Fleet" in agent_screen
    assert "Agent selected" in agent_screen
    assert 'title="Agent controls"' in agent_screen
    assert "Agent availability" in agent_screen
    assert "Open Chat from Agent" in agent_screen
    assert "Open Fleet from Agent" in agent_screen
    assert "ensureAgentConnection" in agent_screen
    assert "reconcileRemoteAccountConfig(loadedConfig)" in agent_screen
    assert "config.accountToken || config.accessToken" in agent_screen
    assert "Connect agent: sign in and pair this phone first" in agent_screen
    assert "Connect agent: pair this phone with a desktop first" in agent_screen
    assert "connectionMode === 'remote_cloud' && !pairedDesktopId" in agent_screen
    assert "agentConnected" in agent_screen
    assert "const AGENT_NO_ACTIVE_SESSION_STATUS" in agent_screen
    assert "Open or select a chat before starting an agent task." in agent_screen
    assert "setStatus(AGENT_NO_ACTIVE_SESSION_STATUS)" in agent_screen
    assert "if (!ensureAgentConnection()) return" in agent_screen
    assert "ensureAgentActiveSession" in agent_screen
    assert "disabledControlsGroup" in agent_screen
    assert "fetchSubAgents" in agent_screen
    assert "spawnSubAgent" in agent_screen
    assert "activeSection === 'tasks'" in agent_screen
    assert "Start Agent task" in agent_screen
    assert "Refresh Agent tasks" in agent_screen
    assert "const agentTaskStartDisabled = !agentConnected || !overview?.session_id || !subAgentPrompt.trim()" in agent_screen
    assert "const agentTaskRefreshDisabled = !agentConnected || !overview?.session_id" in agent_screen
    assert "disabled={agentTaskStartDisabled}" in agent_screen
    assert "disabled={agentTaskRefreshDisabled}" in agent_screen
    assert "fetchSubAgents(apiBaseUrl, token, nextOverview.session_id).catch(() => null)" in agent_screen
    assert "fetchSidebarState(apiBaseUrl, token).catch(() => null)" in agent_screen
    assert "updateSidebarState(apiBaseUrl, token, nextState)" in agent_screen
    assert "const deleteConversation = async (sessionId: string)" in agent_screen
    assert "deleteSession(apiBaseUrl, token, sessionId)" in agent_screen
    assert "sidebarState={sidebarState}" in agent_screen
    assert "onCreateSession={(workspace)" in agent_screen
    assert "params: { newSession: '1', workspace }" in agent_screen
    assert "onSelectSession={(sessionId)" in agent_screen
    assert "router.push({ pathname: '/chat', params: { sessionId } })" in agent_screen
    assert "onDeleteSession={(sessionId)" in agent_screen
    assert "onSidebarStateChange={(nextState)" in agent_screen

    for label, route in [("Chat", "/chat"), ("Fleet", "/fleet"), ("Agent", "/agent")]:
        assert f">{label}</Text>" in drawer
        assert f"navigate('{route}')" in drawer

    assert "Jarvis Voice State" in desktop_conversation_surface
    assert ">Jarvis</Text>" in desktop_conversation_surface
    assert "Hide Jarvis" in desktop_conversation_surface
    assert "initialSurfaceMode?: ConversationSurfaceMode" in desktop_conversation_surface
    assert "useState<ConversationSurfaceMode>(initialSurfaceMode)" in desktop_conversation_surface
    assert "setConversationMode(initialSurfaceMode)" in desktop_conversation_surface
    assert "const DESKTOP_NO_ACTIVE_SESSION_STATUS" in desktop_conversation_surface
    assert "const requireActiveDesktopSession = () =>" in desktop_conversation_surface
    assert "setStatus(DESKTOP_NO_ACTIVE_SESSION_STATUS)" in desktop_conversation_surface
    assert "const activeSessionId = requireActiveDesktopSession()" in desktop_conversation_surface
    assert "controlAgentRun(apiBaseUrl, token, action, activeSessionId)" in desktop_conversation_surface
    assert "const fleetSelectedChatIdForWorker = (worker: DesktopFleetWorker)" in desktop_conversation_surface
    assert "target_session_id: targetSessionId" in desktop_conversation_surface
    assert "const hasActiveFleetTask = fleetWorkers.some((worker: any) => Boolean(fleetTaskForWorker(worker)))" in desktop_conversation_surface
    assert "disabled={fleetLoading || !hasActiveFleetTask}" in desktop_conversation_surface
    assert "targetSessionId: options?.targetSessionId || null" in desktop_bridge
    assert "targetMode: options?.targetMode || 'auto'" in desktop_bridge
    assert "const DESKTOP_NO_ACTIVE_SESSION_STATUS = 'Open or select a chat before using agent commands.'" in desktop_commands
    assert "const SESSION_REQUIRED_COMMANDS = new Set([" in desktop_commands
    assert "SESSION_REQUIRED_COMMANDS.has(command.name) && !sessionId" in desktop_commands
    assert "status: 'select a chat'" in desktop_commands

    assert "tab: 'chat'" in chat_web_route
    assert "tab: 'fleet'" in fleet_web_route
    assert "tab: 'jarvis'" in agent_web_route
    assert "<DesktopAppShell />" in desktop_web_route
    assert "<DesktopAppShell />" in index_web_route
    assert "params: { setup: '1' }" in settings_route
    assert "DesktopAutomationsScreen" in cron_route
    assert "normalizeDesktopTab" in desktop_shell_surface
    assert "normalized === 'fleet'" in desktop_shell_surface
    assert "normalized === 'jarvis' || normalized === 'agent'" in desktop_shell_surface
    assert "setActiveTab(requestedDesktopMode)" in desktop_shell_surface
    assert "initialSurfaceMode={requestedSurfaceMode}" in desktop_shell_surface
    assert "hydratedBootstrap = await loadDesktopBootstrap({ force: true }).catch(() => null)" in desktop_shell_surface
    assert "!hydratedBootstrap.setupState?.required" in desktop_shell_surface
    assert "await beginStartup({ forceBootstrap: true, attachTimeoutSeconds: STARTUP_INITIAL_TIMEOUT_SECONDS })" in desktop_shell_surface


def test_mobile_account_pairing_flow_routes_into_shared_surfaces():
    root = Path(__file__).resolve().parents[1]
    auth_screen = (root / "mobile_app/client/app/auth.tsx").read_text(encoding="utf-8")
    pair_screen = (root / "mobile_app/client/app/pair.tsx").read_text(encoding="utf-8")
    settings_screen = (root / "mobile_app/client/app/settings.tsx").read_text(encoding="utf-8")
    cron_screen = (root / "mobile_app/client/src/screens/CronScreen.tsx").read_text(encoding="utf-8")
    app_config = (root / "mobile_app/client/lib/appConfig.ts").read_text(encoding="utf-8")
    account_session = (root / "mobile_app/client/lib/accountSession.ts").read_text(encoding="utf-8")

    assert "const pairedDesktopId = result.mobile?.paired_desktop_id || ''" in auth_screen
    assert "accountToken: sessionToken" in auth_screen
    assert "connectionMode: 'remote_cloud'" in auth_screen
    assert "router.replace(pairedDesktopId ? '/chat' : '/pair')" in auth_screen
    assert "getOrCreateMobileDeviceKey" in auth_screen
    assert "remoteStartGoogleAuth" in auth_screen

    assert "reconcileRemoteAccountConfig(await loadAppConfig())" in pair_screen
    assert "router.replace('/auth')" in pair_screen
    assert "fetchRemoteDesktops(config.apiBaseUrl, accountToken)" in pair_screen
    assert "remoteCompletePairing(apiBaseUrl, token, cleanToken)" in pair_screen
    assert "pairedDesktopId: result.desktop.desktop_id" in pair_screen
    assert "router.replace('/chat')" in pair_screen
    assert "Chat and sidebar state are synced." in pair_screen

    assert "reconcileRemoteAccountConfig(await loadAppConfig())" in settings_screen
    assert "router.replace('/auth')" in settings_screen
    assert "signed in, not paired" in settings_screen
    assert "clearRemoteAccountConfig()" in settings_screen
    assert "applySharedSettingsDraftToProfile" in settings_screen
    assert "profileToSharedSettingsDraft" in settings_screen
    assert "validateSharedSettingsDraft" in settings_screen
    assert "configureHeadlessRuntime(apiBaseUrl, token, { enabled: profileDraft.sleepModeEnabled })" in settings_screen
    assert "customSystemPromptAppend" in settings_screen
    assert "memoryPromptContextEnabled" in settings_screen
    assert '<Link href="/pair" style={styles.link}>Open pairing</Link>' in settings_screen
    assert '<Link href="/chat" style={styles.backLink}>Back to chat</Link>' in settings_screen

    assert "reconcileRemoteAccountConfig(loadedConfig)" in cron_screen
    assert "config.accountToken || config.accessToken" in cron_screen
    assert "connectionMode === 'remote_cloud' && !pairedDesktopId" in cron_screen
    assert "Connect automations: pair this phone with a desktop first" in cron_screen
    assert "if (!automationsConnected)" in cron_screen

    assert "if (config.connectionMode === 'remote_cloud')" in app_config
    assert "return 'missing_pairing' as const" in app_config
    assert "volatileAppConfig = accountTokenIsEphemeral ? normalized : null" in app_config

    assert "fetchRemoteAccountProfile(config.apiBaseUrl, token)" in account_session
    assert "pairedDesktopId" in account_session
    assert "return { config: await clearRemoteAccountConfig(), profile: null, changed: true }" in account_session


def test_resolve_pairing_user_id_prefers_pairing_creator(monkeypatch):
    class DummyStore:
        def get_pairing(self, pairing_id: str):
            assert pairing_id == "pair-1"
            return {"created_by": "user:77"}

    monkeypatch.setattr(app_server, "_get_auth_store", lambda: DummyStore())
    monkeypatch.setattr(app_server, "_default_user_id", lambda: 11)

    assert app_server._resolve_pairing_user_id("pair-1") == 77


def test_resolve_pairing_user_id_falls_back_to_default(monkeypatch):
    class DummyStore:
        def get_pairing(self, pairing_id: str):
            assert pairing_id == "pair-2"
            return {"created_by": "service:bootstrap"}

    monkeypatch.setattr(app_server, "_get_auth_store", lambda: DummyStore())
    monkeypatch.setattr(app_server, "_default_user_id", lambda: 11)

    assert app_server._resolve_pairing_user_id("pair-2") == 11


def test_app_default_user_id_ignores_allowed_user_ids(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "8562474049")

    assert app_server._default_user_id() == app_server.DEFAULT_APP_USER_ID


def test_jarvis_spoken_response_formatter_removes_markdown_lists():
    text = """
    Here is what I see:
    - Chrome is open on Gmail.
    - There is a login prompt.
    1. The inbox is not visible yet.
    """

    formatted = runtime._format_jarvis_spoken_response(text)

    assert "-" not in formatted
    assert "1." not in formatted
    assert "\n" not in formatted
    assert formatted == "Here is what I see. Chrome is open on Gmail. There is a login prompt. The inbox is not visible yet"


def test_jarvis_voice_contract_marks_surface_as_spoken_hands_free():
    content = runtime._jarvis_voice_response_contract()["content"].lower()

    assert "hands-free voice conversation" in content
    assert "spoken aloud" in content
    assert "same tools" in content
    assert "do not use markdown" in content


def test_jarvis_spoken_confirmation_helpers():
    assert app_server._jarvis_confirmation_intent("yes, proceed") is True
    assert app_server._jarvis_confirmation_intent("no cancel that") is False
    assert app_server._jarvis_confirmation_intent("I was asking a different question with many words") is None

    prompt = app_server._jarvis_confirmation_prompt(
        "fleet_stop_all",
        {
            "confirmation_required": True,
            "action": "stop all workers",
            "summary": "This stops every active worker task.",
            "risk": "bulk_stop",
            "confirmation_id": "confirm-123",
        },
    )
    assert prompt is not None
    assert prompt["confirmation_id"] == "confirm-123"
    assert "stop all workers" in prompt["spoken_prompt"]
    assert prompt["risk"] == "bulk_stop"


def test_jarvis_voice_websocket_surfaces_tool_confirmation(monkeypatch):
    run_calls: list[dict[str, object]] = []

    class DummyVoiceDraft:
        revision = 0
        state = "idle"
        cancel_empty_pending_before_final = True

        def reset(self):
            self.state = "idle"

        def register_task(self, _task):
            return None

        async def wait_for_pending(self, timeout=None):
            return None

        def transcript(self):
            return "Stop all workers"

        async def final_transcript(self, fast=False):
            return "Stop all workers"

        def cancel_pending(self):
            return None

    runtime_obj = SimpleNamespace(
        verbose_mode=True,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-jarvis"),
    )

    class DummyBridge:
        def load_runtime_session(self, session_id: str):
            assert session_id == "sess-jarvis"
            return runtime_obj

    async def fake_run_app_chat_turn_lazy(runtime_obj_arg, **kwargs):
        run_calls.append({"runtime": runtime_obj_arg, **kwargs})
        await kwargs["log_callback"](
            {
                "type": "tool_use",
                "tool_name": "fleet_stop_all",
                "tool_args": {},
                "tool_result": {
                    "confirmation_required": True,
                    "action": "stop all workers",
                    "summary": "This stops every active worker task.",
                    "risk": "bulk_stop",
                    "confirmation_id": "confirm-jarvis",
                },
                "duration_ms": 1.0,
            }
        )
        return {
            "ok": True,
            "busy": False,
            "steering": False,
            "session_id": "sess-jarvis",
            "assistant_text": "Please confirm yes or no.",
            "duration_seconds": 0.1,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 7})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_new_voice_draft_state", lambda: DummyVoiceDraft())
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", fake_run_app_chat_turn_lazy)
    monkeypatch.setattr(app_server, "_synthesize_assistant_audio_sync", lambda _text: None)
    monkeypatch.setattr(app_server, "_jarvis_voice_turn_is_task_like", lambda _text: False)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        "/ws/app/voice?token=test-token&session_id=sess-jarvis&surface_mode=jarvis&client_id=jarvis-client"
    ) as websocket:
        websocket.send_json(
            {
                "type": "voice_start",
                "session_id": "sess-jarvis",
                "surface_mode": "jarvis",
                "utterance_id": "utt-1",
            }
        )
        websocket.send_json(
            {
                "type": "voice_commit",
                "session_id": "sess-jarvis",
                "surface_mode": "jarvis",
                "utterance_id": "utt-1",
                "interrupt_policy": "none",
            }
        )

        confirmation_event = None
        for _ in range(12):
            event = websocket.receive_json()
            if event.get("type") == "voice_confirmation_required":
                confirmation_event = event
                break

    assert confirmation_event is not None
    assert confirmation_event["session_id"] == "sess-jarvis"
    assert confirmation_event["payload"]["confirmation_id"] == "confirm-jarvis"
    assert "stop all workers" in confirmation_event["payload"]["spoken_prompt"]
    assert run_calls[0]["runtime"] is runtime_obj
    assert run_calls[0]["user_message"] == "Stop all workers"
    assert run_calls[0]["source_format"] == "app_voice_transcript"
    assert run_calls[0]["surface_mode"] == "jarvis"
    assert run_calls[0]["source_client_id"] == "jarvis-client"


def test_telegram_allowed_user_ids_accepts_multi_and_legacy_values(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, bad, 222, 111")
    monkeypatch.setenv("ALLOWED_USER_ID", "333")

    assert app_server._telegram_allowed_user_ids() == [111, 222, 333]


@pytest.mark.asyncio
async def test_notify_sleep_mode_enabled_sends_notice_from_each_bot(monkeypatch):
    sent: list[dict[str, object]] = []

    class DummyBot:
        def __init__(self, token: str):
            self.token = token

        async def send_message(self, *, chat_id: int, text: str):
            sent.append({"token": self.token, "chat_id": chat_id, "text": text})

    class DummyTelegramBots:
        def list_configs(self):
            return [
                {"id": "bot-a", "label": "Primary", "bot_token": "token-a", "is_default": True},
                {"id": "bot-b", "label": "Backup", "bot_token": "token-b", "is_default": False},
            ]

        def get_sleep_session_by_bot(self):
            return {"bot-a": "sess-a"}

    class DummyBridge:
        orchestrator = SimpleNamespace(telegram_bots=DummyTelegramBots())

        def get_session(self, session_id: str):
            assert session_id == "sess-a"
            return SimpleNamespace(id=session_id, name="Sleep Chat")

    monkeypatch.setattr(app_server, "Bot", DummyBot)
    monkeypatch.setattr(app_server, "_telegram_allowed_user_ids", lambda: [111, 222])

    await app_server._notify_sleep_mode_enabled(DummyBridge())

    assert len(sent) == 4
    assert {(item["token"], item["chat_id"]) for item in sent} == {
        ("token-a", 111),
        ("token-a", 222),
        ("token-b", 111),
        ("token-b", 222),
    }
    primary_notice = next(item["text"] for item in sent if item["token"] == "token-a")
    backup_notice = next(item["text"] for item in sent if item["token"] == "token-b")
    assert "EmploAI sleep mode is now active." in str(primary_notice)
    assert "Sleep Chat (sess-a)" in str(primary_notice)
    assert "No sleep chat is assigned for this bot" in str(backup_notice)


@pytest.mark.asyncio
async def test_send_realtime_event_treats_closed_socket_send_as_disconnect():
    class ClosedSocket:
        client_state = object()
        application_state = object()

        async def send_json(self, _payload):
            raise RuntimeError('Cannot call "send" once a close message has been sent.')

    lock = asyncio.Lock()
    event = app_server.RealtimeServerEvent(type="status", payload={"message": "ok"})

    with pytest.raises(app_server.WebSocketDisconnect):
        await app_server._send_realtime_event(ClosedSocket(), lock, event)


def test_context_usage_counts_prompt_envelope_and_tool_schemas(tmp_path: Path):
    runtime = SimpleNamespace(
        current_model="gpt-5.4-mini",
        current_variant="standard",
        chat_history=[{"role": "user", "content": "Inspect the README file"}],
        enabled_tool_packs=["workspace_read"],
        _active_tool_packs_for_current_run=[],
        workspace=tmp_path,
        system_info="OS: Windows\nActive Windows: Codex",
        context_loader=None,
        live_config={},
        session_context=None,
        memory_manager=None,
        skill_registry=None,
        active_skills=[],
        pending_files=[],
        last_user_message="Inspect the README file",
        task_history=[],
        active_task_id=None,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-context"),
        user_id=None,
        last_context_compaction=None,
        context_manager=None,
    )

    usage = app_server._context_usage(runtime)

    assert usage["system_prompt_tokens"] > 0
    assert usage["injected_context_tokens"] > 0
    assert usage["chat_history_tokens"] > 0
    assert usage["tool_schema_tokens"] > 0
    assert usage["tool_schema_count"] > 0
    assert usage["message_count"] == usage["prompt_message_count"]
    assert usage["estimated_tokens"] > usage["chat_history_tokens"]


def test_stop_runtime_execution_interrupts_and_kills_background_commands():
    killed = []
    stopped_agents = []

    class DummyAgent:
        current_task = object()

        def stop(self):
            stopped_agents.append("agent")

    class DummyToolExecutor:
        def kill_all_background_commands(self):
            killed.append("commands")
            return {
                "killed_count": 2,
                "killed": [{"command_id": "one"}, {"command_id": "two"}],
                "errors": [],
            }

    class DummySpawnTool:
        def stop_all_tasks(self):
            return 1

    runtime_obj = SimpleNamespace(
        is_processing=True,
        should_interrupt=False,
        interrupt_message="queued steering",
        interrupt_queue=["queued steering"],
        deferred_interrupt_queue=["later"],
        current_turn_allowed_tool_names={"run_command"},
        current_turn_allowed_tool_definitions=[{"name": "run_command"}],
        unified_agent=DummyAgent(),
        refined_agent=None,
        single_agent=None,
        tool_executor=DummyToolExecutor(),
        spawn_tool=DummySpawnTool(),
    )

    summary = app_server._stop_runtime_execution(runtime_obj)

    assert runtime_obj.should_interrupt is True
    assert runtime_obj.interrupt_message is None
    assert runtime_obj.interrupt_queue == []
    assert runtime_obj.deferred_interrupt_queue == []
    assert runtime_obj.is_processing is False
    assert runtime_obj.current_turn_allowed_tool_names is None
    assert runtime_obj.current_turn_allowed_tool_definitions == []
    assert stopped_agents == ["agent"]
    assert killed == ["commands"]
    assert summary["was_processing"] is True
    assert summary["background_commands"]["killed_count"] == 2
    assert summary["subagents_stopped"] == 1


def test_app_chat_send_allows_active_steering_before_orchestrator_lease(monkeypatch):
    prepare_calls: list[str] = []
    run_calls: list[dict] = []

    class DummyOrchestrator:
        async def prepare_turn(self, session_id: str, **_kwargs):
            prepare_calls.append(session_id)
            return SimpleNamespace(busy=True, error="should not be reached")

        async def complete_turn(self, _lease):
            raise AssertionError("steering bypass should not complete an unused lease")

    runtime_obj = SimpleNamespace(
        is_processing=True,
        session=SimpleNamespace(id="sess-steer"),
    )
    bridge = SimpleNamespace(orchestrator=DummyOrchestrator())

    async def fake_run_app_chat_turn_lazy(runtime, **kwargs):
        run_calls.append({"runtime": runtime, **kwargs})
        return {
            "ok": True,
            "busy": False,
            "steering": True,
            "session_id": "sess-steer",
            "assistant_text": "",
            "steering_status": "armed",
        }

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: bridge)
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", fake_run_app_chat_turn_lazy)

    response = TestClient(app_server.create_app()).post(
        "/api/app/chat/send",
        json={
            "session_id": "sess-steer",
            "text": "actually use the docs tab",
            "interrupt_policy": "steer_now",
            "source_client_id": "phone-client-1",
        },
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["steering"] is True
    assert prepare_calls == []
    assert run_calls == [
        {
            "runtime": runtime_obj,
            "user_message": "actually use the docs tab",
            "source_format": "app_text",
            "interrupt_policy": "steer_now",
            "source_client_id": "phone-client-1",
        }
    ]


def test_app_chat_websocket_runs_local_turn_with_client_metadata(monkeypatch, tmp_path):
    prepare_calls: list[str] = []
    complete_calls: list[object] = []
    run_calls: list[dict] = []

    class DummyOrchestrator:
        async def prepare_turn(self, session_id: str, **_kwargs):
            prepare_calls.append(session_id)
            return SimpleNamespace(busy=False, session_id=session_id)

        async def complete_turn(self, lease):
            complete_calls.append(lease)

    runtime_obj = SimpleNamespace(
        is_processing=False,
        verbose_mode=False,
        session=SimpleNamespace(id="sess-ws"),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-ws"),
    )

    class DummyBridge:
        orchestrator = DummyOrchestrator()

        def build_session_sync_payload(self, session_id: str):
            return {
                "session": {"id": session_id, "messages": []},
                "sessions": [{"id": session_id, "name": "Socket Chat"}],
            }

        def session_file_path(self, session_id: str):
            return tmp_path / f"{session_id}.json"

        def session_index_path(self):
            return tmp_path / "index.json"

        def get_current_session(self):
            return runtime_obj.session

    async def fake_run_app_chat_turn_lazy(runtime_arg, **kwargs):
        run_calls.append({"runtime": runtime_arg, **kwargs})
        await kwargs["log_callback"]({"type": "assistant_delta", "delta": "Working"})
        await kwargs["log_callback"]({"type": "status", "message": "checking"})
        return {
            "ok": True,
            "busy": False,
            "steering": False,
            "session_id": "sess-ws",
            "assistant_text": "Done from socket",
            "duration_seconds": 0.12,
            "input_tokens": 3,
            "output_tokens": 4,
            "total_tokens": 7,
        }

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", fake_run_app_chat_turn_lazy)

    client = TestClient(app_server.create_app())
    with client.websocket_connect("/ws/app/chat?token=test&session_id=sess-ws&client_id=phone-client-1") as websocket:
        initial_types = []
        for _ in range(3):
            message = websocket.receive_json()
            initial_types.append(message.get("type"))
            if message.get("type") == "session_sync":
                break

        websocket.send_json(
            {
                "text": "Run this from the chat socket",
                "session_id": "sess-ws",
                "source_format": "app_text",
                "interrupt_policy": "after_tool",
            }
        )
        seen_events = []
        for _ in range(6):
            message = websocket.receive_json()
            seen_events.append(message)
            if message.get("type") == "assistant_final":
                break

    assert "session_snapshot" in initial_types
    assert "session_sync" in initial_types
    assert [event.get("type") for event in seen_events[:3]] == ["assistant_delta", "status", "assistant_final"]
    assert seen_events[-1]["payload"]["text"] == "Done from socket"
    assert prepare_calls == ["sess-ws"]
    assert len(complete_calls) == 1
    assert run_calls[0]["runtime"] is runtime_obj
    assert run_calls[0]["user_message"] == "Run this from the chat socket"
    assert run_calls[0]["source_format"] == "app_text"
    assert run_calls[0]["interrupt_policy"] == "after_tool"
    assert run_calls[0]["source_client_id"] == "phone-client-1"


def test_app_chat_websocket_explicit_session_ignores_external_current_session_change(monkeypatch, tmp_path):
    runtime_obj = SimpleNamespace(
        is_processing=False,
        verbose_mode=False,
        session=SimpleNamespace(id="sess-pinned"),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-pinned"),
    )

    class DummyBridge:
        orchestrator = SimpleNamespace()

        def build_session_sync_payload(self, session_id: str):
            return {"session": {"id": session_id, "messages": []}, "sessions": []}

        def session_file_path(self, session_id: str):
            return tmp_path / f"{session_id}.json"

        def session_index_path(self):
            return tmp_path / "index.json"

        def get_current_session(self):
            return SimpleNamespace(id="sess-other")

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, session_id: runtime_obj)

    client = TestClient(app_server.create_app())
    with client.websocket_connect("/ws/app/chat?token=test&session_id=sess-pinned&client_id=phone-client-1") as websocket:
        for _ in range(3):
            if websocket.receive_json().get("type") == "session_sync":
                break

        app_server.get_channel_sync_hub().publish(
            user_id=9,
            event={
                "type": "current_session_changed",
                "session_id": "sess-other",
                "payload": {"current_session_id": "sess-other"},
            },
        )
        app_server.get_channel_sync_hub().publish(
            user_id=9,
            event={
                "type": "session_config",
                "session_id": "sess-pinned",
                "payload": {"setting": "pinned_config"},
            },
        )
        next_event = websocket.receive_json()

    assert next_event["type"] == "session_sync"
    assert next_event["session_id"] == "sess-pinned"
    assert next_event["payload"]["reason"] == "pinned_config"
    assert next_event["payload"]["session"]["id"] == "sess-pinned"


def test_app_chat_websocket_runtime_error_surfaces_without_closing_socket(monkeypatch, tmp_path):
    complete_calls: list[object] = []

    class DummyOrchestrator:
        async def prepare_turn(self, session_id: str, **_kwargs):
            return SimpleNamespace(busy=False, session_id=session_id)

        async def complete_turn(self, lease):
            complete_calls.append(lease)

    runtime_obj = SimpleNamespace(
        is_processing=False,
        verbose_mode=False,
        session=SimpleNamespace(id="sess-error"),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-error"),
    )

    class DummyBridge:
        orchestrator = DummyOrchestrator()

        def build_session_sync_payload(self, session_id: str):
            return {"session": {"id": session_id, "messages": []}, "sessions": []}

        def session_file_path(self, session_id: str):
            return tmp_path / f"{session_id}.json"

        def session_index_path(self):
            return tmp_path / "index.json"

        def get_current_session(self):
            return runtime_obj.session

    async def failing_run_app_chat_turn_lazy(_runtime_arg, **_kwargs):
        raise RuntimeError("No API key configured for provider: openai")

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", failing_run_app_chat_turn_lazy)

    client = TestClient(app_server.create_app())
    with client.websocket_connect("/ws/app/chat?token=test&session_id=sess-error&client_id=phone-client-1") as websocket:
        for _ in range(3):
            if websocket.receive_json().get("type") == "session_sync":
                break

        websocket.send_json({"text": "hello", "session_id": "sess-error"})
        error_event = websocket.receive_json()

        websocket.send_json({"text": "", "session_id": "sess-error"})
        warning_event = websocket.receive_json()

    assert error_event["type"] == "error"
    assert error_event["payload"] == {
        "message": "Provider authentication, quota, or permission error. No API key configured for provider: openai",
        "code": "provider_auth_or_quota_error",
        "retryable": False,
    }
    assert warning_event["type"] == "warning"
    assert warning_event["session_id"] == "sess-error"
    assert warning_event["payload"]["message"] == "Empty message ignored"
    assert len(complete_calls) == 1


def test_app_chat_websocket_provider_error_is_normalized_and_retryable(monkeypatch, tmp_path):
    class RateLimitedProviderError(Exception):
        status_code = 429

    class DummyOrchestrator:
        async def prepare_turn(self, session_id: str, **_kwargs):
            return SimpleNamespace(busy=False, session_id=session_id)

        async def complete_turn(self, _lease):
            return None

    runtime_obj = SimpleNamespace(
        is_processing=False,
        verbose_mode=False,
        session=SimpleNamespace(id="sess-provider-error"),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-provider-error"),
    )

    class DummyBridge:
        orchestrator = DummyOrchestrator()

        def build_session_sync_payload(self, session_id: str):
            return {"session": {"id": session_id, "messages": []}, "sessions": []}

        def session_file_path(self, session_id: str):
            return tmp_path / f"{session_id}.json"

        def session_index_path(self):
            return tmp_path / "index.json"

        def get_current_session(self):
            return runtime_obj.session

    async def failing_run_app_chat_turn_lazy(_runtime_arg, **_kwargs):
        raise RateLimitedProviderError("rate limit exceeded")

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", failing_run_app_chat_turn_lazy)

    client = TestClient(app_server.create_app())
    with client.websocket_connect("/ws/app/chat?token=test&session_id=sess-provider-error&client_id=phone-client-1") as websocket:
        for _ in range(3):
            if websocket.receive_json().get("type") == "session_sync":
                break

        websocket.send_json({"text": "hello", "session_id": "sess-provider-error"})
        error_event = websocket.receive_json()

        websocket.send_json({"text": "", "session_id": "sess-provider-error"})
        warning_event = websocket.receive_json()

    assert error_event["type"] == "error"
    assert error_event["payload"] == {
        "message": "Provider authentication, quota, or permission error. rate limit exceeded",
        "code": "provider_auth_or_quota_error",
        "retryable": True,
        "provider_status_code": 429,
    }
    assert warning_event["type"] == "warning"
    assert warning_event["session_id"] == "sess-provider-error"
    assert warning_event["payload"]["message"] == "Empty message ignored"


def test_app_chat_websocket_rejects_missing_provider_key_before_run(monkeypatch, tmp_path):
    class DummyOrchestrator:
        async def prepare_turn(self, *_args, **_kwargs):
            raise AssertionError("turn lease should not start without a provider API key")

        async def complete_turn(self, _lease):
            raise AssertionError("turn lease should not complete without a provider API key")

    runtime_obj = SimpleNamespace(
        is_processing=False,
        verbose_mode=False,
        session=SimpleNamespace(id="sess-no-key"),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-no-key"),
        get_enabled_providers=lambda: set(),
    )

    class DummyBridge:
        orchestrator = DummyOrchestrator()

        def build_session_sync_payload(self, session_id: str):
            return {"session": {"id": session_id, "messages": []}, "sessions": []}

        def session_file_path(self, session_id: str):
            return tmp_path / f"{session_id}.json"

        def session_index_path(self):
            return tmp_path / "index.json"

        def get_current_session(self):
            return runtime_obj.session

    async def unexpected_run_app_chat_turn_lazy(_runtime_arg, **_kwargs):
        raise AssertionError("chat turn should not run without a provider API key")

    monkeypatch.setattr(app_server, "_resolve_ws_token", lambda _token: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: DummyBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", unexpected_run_app_chat_turn_lazy)

    client = TestClient(app_server.create_app())
    with client.websocket_connect("/ws/app/chat?token=test&session_id=sess-no-key&client_id=phone-client-1") as websocket:
        for _ in range(3):
            if websocket.receive_json().get("type") == "session_sync":
                break

        websocket.send_json({"text": "hello", "session_id": "sess-no-key"})
        warning_event = websocket.receive_json()

    assert warning_event["type"] == "warning"
    assert warning_event["payload"] == {
        "message": "You have not set an API key yet. Add an API key in Setup before sending a message.",
        "code": "missing_provider_api_key",
        "retryable": False,
    }


def test_app_chat_send_runtime_error_returns_conflict(monkeypatch):
    complete_calls: list[object] = []

    class DummyOrchestrator:
        async def prepare_turn(self, session_id: str, **_kwargs):
            return SimpleNamespace(busy=False, session_id=session_id)

        async def complete_turn(self, lease):
            complete_calls.append(lease)

    runtime_obj = SimpleNamespace(
        is_processing=False,
        session=SimpleNamespace(id="sess-http-error"),
    )
    bridge = SimpleNamespace(orchestrator=DummyOrchestrator())

    async def failing_run_app_chat_turn_lazy(_runtime, **_kwargs):
        raise RuntimeError("No API key configured for provider: openai")

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: bridge)
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", failing_run_app_chat_turn_lazy)

    response = TestClient(app_server.create_app()).post(
        "/api/app/chat/send",
        json={"session_id": "sess-http-error", "text": "hello"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Provider authentication, quota, or permission error. No API key configured for provider: openai"
    assert len(complete_calls) == 1


def test_app_chat_send_rejects_missing_provider_key_before_run(monkeypatch):
    class DummyOrchestrator:
        async def prepare_turn(self, *_args, **_kwargs):
            raise AssertionError("turn lease should not start without a provider API key")

        async def complete_turn(self, _lease):
            raise AssertionError("turn lease should not complete without a provider API key")

    runtime_obj = SimpleNamespace(
        is_processing=False,
        session=SimpleNamespace(id="sess-http-no-key"),
        get_enabled_providers=lambda: set(),
    )
    bridge = SimpleNamespace(orchestrator=DummyOrchestrator())

    async def unexpected_run_app_chat_turn_lazy(_runtime, **_kwargs):
        raise AssertionError("chat turn should not run without a provider API key")

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: bridge)
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id: runtime_obj)
    monkeypatch.setattr(app_server, "_run_app_chat_turn_lazy", unexpected_run_app_chat_turn_lazy)

    response = TestClient(app_server.create_app()).post(
        "/api/app/chat/send",
        json={"session_id": "sess-http-no-key", "text": "hello"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You have not set an API key yet. Add an API key in Setup before sending a message."


def test_agent_mutating_routes_require_explicit_session(monkeypatch):
    load_calls: list[str | None] = []

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: SimpleNamespace())

    def fail_load(_bridge, session_id=None):
        load_calls.append(session_id)
        raise AssertionError("mutating agent route should reject missing session before loading runtime")

    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", fail_load)

    client = TestClient(app_server.create_app())
    cases = [
        ("post", "/api/app/agent/configure", {"model": "gpt-5.4-mini"}),
        ("post", "/api/app/agent/config", {"key": "agent.test", "value": "on"}),
        ("post", "/api/app/agent/memory/note", {"note": "remember this"}),
        ("post", "/api/app/agent/files/clear", None),
        ("post", "/api/app/agent/forget-last", None),
        ("post", "/api/app/agent/reset", None),
        ("post", "/api/app/agent/compact", None),
        ("post", "/api/app/agent/skills/activate", {"name": "mobile-developer", "active": True}),
        ("post", "/api/app/agent/subagents", {"prompt": "check the release notes", "headless": True, "max_turns": 30}),
        ("post", "/api/app/agent/task-board/arm", {"armed": True}),
        ("post", "/api/app/agent/task-board/reassess", None),
        ("post", "/api/app/agent/control/pause", None),
        ("post", "/api/app/agent/control/stop", None),
        ("post", "/api/app/agent/control/restart", None),
    ]

    for method, path, payload in cases:
        response = getattr(client, method)(
            path,
            json=payload if payload is not None else None,
            headers={"Authorization": "Bearer test"},
        )
        assert response.status_code == 400, path
        assert response.json()["detail"] == "Open or select a chat before using agent controls."

    assert load_calls == []


def test_agent_subagent_spawn_uses_explicit_session(monkeypatch):
    load_calls: list[str | None] = []
    spawn_calls: list[dict[str, object]] = []

    class DummySpawnTool:
        async def spawn(self, **kwargs):
            spawn_calls.append(kwargs)
            return "subagent-1"

    runtime_obj = SimpleNamespace(spawn_tool=DummySpawnTool())

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 9})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: SimpleNamespace())
    monkeypatch.setattr(app_server, "_ensure_background_runtime", lambda _runtime: None)

    def load_runtime(_bridge, session_id=None):
        load_calls.append(session_id)
        return runtime_obj

    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", load_runtime)

    response = TestClient(app_server.create_app()).post(
        "/api/app/agent/subagents?session_id=sess-explicit",
        json={"prompt": "check the release notes", "headless": True, "max_turns": 30},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Sub-agent subagent-1 started"
    assert load_calls == ["sess-explicit"]
    assert spawn_calls == [
        {
            "prompt": "check the release notes",
            "headless": True,
            "max_turns": 30,
            "announce_on_complete": False,
        }
    ]


def test_remote_agent_control_requires_explicit_session_before_dispatch(monkeypatch):
    dispatch_calls: list[dict[str, object]] = []

    async def fail_dispatch(*args, **kwargs):
        dispatch_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("remote control should not dispatch without an explicit session")

    monkeypatch.setattr(
        app_server,
        "_resolve_token",
        lambda _authorization: {"auth_kind": "remote_session", "actor_kind": "mobile", "user_id": 9},
    )
    monkeypatch.setattr(app_server, "_remote_dispatch_command", fail_dispatch)

    response = TestClient(app_server.create_app()).post(
        "/api/app/agent/control/stop",
        headers={"Authorization": "Bearer remote-test"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Open or select a chat before using agent controls."
    assert dispatch_calls == []


def test_telegram_session_defaults_use_openai_pair_when_openai_key_is_available(monkeypatch):
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = object.__new__(TelegramSession)
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_model": "auto",
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )

    assert TelegramSession._configured_default_model(runtime) == "gpt-5.4-mini"
    assert TelegramSession._configured_default_planner_model(runtime, "gpt-5.4-mini") == "gpt-5.4-mini"


def test_telegram_session_defaults_use_anthropic_pair_when_only_anthropic_key_is_available(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    runtime = object.__new__(TelegramSession)
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_model": "auto",
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )

    assert TelegramSession._configured_default_model(runtime) == "claude-sonnet-4.5"
    assert TelegramSession._configured_default_planner_model(runtime, "claude-sonnet-4.5") == "claude-haiku-4.5"


def test_telegram_session_defaults_use_nvidia_pair_when_only_nvidia_key_is_available(monkeypatch):
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "PLANNER_MODEL",
        "AGENT_DEFAULT_PLANNER_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    runtime = object.__new__(TelegramSession)
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_model": "auto",
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )

    assert TelegramSession._configured_default_model(runtime) == "mistralai/ministral-14b-instruct-2512"
    assert (
        TelegramSession._configured_default_planner_model(runtime, "mistralai/ministral-14b-instruct-2512")
        == "mistralai/ministral-14b-instruct-2512"
    )


def test_telegram_session_automatic_planner_follows_current_model_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)
    runtime = object.__new__(TelegramSession)
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )

    assert TelegramSession._configured_default_planner_model(runtime, "claude-sonnet-4.5") == "claude-haiku-4.5"


def test_supported_planner_models_include_openai_responses_models():
    runtime = object.__new__(TelegramSession)
    runtime.current_model = "gpt-5.4-mini"
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )
    runtime.openai_client = object()
    runtime.anthropic_client = None
    runtime.google_client = None
    runtime.gemini_openai_client = None
    runtime.xai_client = None
    runtime.deepseek_client = None
    runtime.openrouter_client = None
    runtime.nvidia_client = None

    assert TelegramSession.get_supported_planner_models(runtime, ["gpt-5", "gpt-5.4-mini"]) == [
        "gpt-5.4-mini",
        "gpt-5",
    ]


def test_telegram_session_unavailable_model_fallback_prefers_provider_default(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)

    runtime = object.__new__(TelegramSession)
    runtime.current_model = "gpt-5.4-mini"
    runtime.current_variant = "standard"
    runtime.planner_model = None
    runtime.default_planner_model = None
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_model": "auto",
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )
    runtime.openai_client = None
    runtime.anthropic_client = object()
    runtime.google_client = None
    runtime.gemini_openai_client = None
    runtime.xai_client = None
    runtime.deepseek_client = None
    runtime.openrouter_client = None
    runtime.nvidia_client = None

    changed = TelegramSession.ensure_current_model_available(
        runtime,
        ["gpt-5", "gpt-5.4-mini", "claude-sonnet-4.5", "claude-haiku-4.5"],
    )

    assert changed is True
    assert runtime.current_model == "claude-sonnet-4.5"
    assert runtime.default_planner_model == "claude-haiku-4.5"


def test_telegram_session_known_default_planner_realigns_to_current_model_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)

    runtime = object.__new__(TelegramSession)
    runtime.current_model = "claude-sonnet-4.5"
    runtime.planner_model = "gpt-5.4-mini"
    runtime.default_planner_model = "gpt-5.4-mini"
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )
    runtime.openai_client = object()
    runtime.anthropic_client = object()
    runtime.google_client = None
    runtime.gemini_openai_client = None
    runtime.xai_client = None
    runtime.deepseek_client = None
    runtime.openrouter_client = None
    runtime.nvidia_client = None

    changed = TelegramSession.ensure_planner_model_available(
        runtime,
        ["gpt-5.4-mini", "claude-sonnet-4.5", "claude-haiku-4.5"],
    )

    assert changed is True
    assert runtime.planner_model is None
    assert runtime.default_planner_model == "claude-haiku-4.5"


def test_telegram_session_old_registry_first_planner_pin_resets_to_automatic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("AGENT_DEFAULT_PLANNER_MODEL", raising=False)

    runtime = object.__new__(TelegramSession)
    runtime.current_model = "gpt-5.4-mini"
    runtime.planner_model = "gpt-5"
    runtime.default_planner_model = "gpt-5"
    runtime.config_manager = SimpleNamespace(get_api_key=lambda _provider: None)
    runtime.live_config = SimpleNamespace(
        get=lambda path, default="": {
            "agent.default_planner_model": "auto",
        }.get(path, default)
    )
    runtime.openai_client = object()
    runtime.anthropic_client = None
    runtime.google_client = None
    runtime.gemini_openai_client = None
    runtime.xai_client = None
    runtime.deepseek_client = None
    runtime.openrouter_client = None
    runtime.nvidia_client = None

    changed = TelegramSession.ensure_planner_model_available(
        runtime,
        ["gpt-5", "gpt-5.4-mini"],
    )

    assert changed is True
    assert runtime.planner_model is None
    assert runtime.default_planner_model == "gpt-5.4-mini"


def test_app_session_bridge_uses_shared_telegram_runtime(monkeypatch, tmp_path: Path):
    captured = {}
    runtime = object()

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path

    def fake_get_session(user_id: int, *, workspace: Path | None = None, create_new_session: bool = True):
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["create_new_session"] = create_new_session
        return runtime

    monkeypatch.setattr(session_bridge, "SessionManager", DummySessionManager)
    monkeypatch.setattr(session_bridge, "get_session", fake_get_session)

    bridge = session_bridge.AppSessionBridge(user_id=5, workspace=tmp_path)

    assert bridge.get_or_create_runtime_session() is runtime
    assert captured == {
        "user_id": 5,
        "workspace": tmp_path,
        "create_new_session": False,
    }


def test_app_session_bridge_create_session_during_busy_runtime_uses_disk_detail(monkeypatch, tmp_path: Path):
    created = Session(
        id="busy1234",
        name="Busy",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path),
        model="gpt-5.2",
        variant="standard",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.set_calls: list[str] = []
            self.create_calls: list[dict] = []

        def create_session(self, **kwargs):
            self.create_calls.append(kwargs)
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, set_current: bool = False):
            assert session_id == created.id
            assert set_current is False
            return created

    load_calls: list[str] = []
    save_calls: list[bool] = []
    runtime = SimpleNamespace(
        is_processing=True,
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        save_session=lambda: save_calls.append(True),
        session_manager=SimpleNamespace(get_current_session_id=lambda: "current"),
        workspace=tmp_path,
        current_model="gpt-5.2",
        current_variant="standard",
        planner_model=None,
        default_planner_model="gpt-5.2",
        enabled_tool_packs=["workspace_read"],
        telegram_bot_config_id=None,
        headless_eligible=False,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)

    result = bridge.create_session("Busy")

    assert result is created
    assert len(manager.create_calls) == 1
    assert manager.set_calls == ["busy1234"]
    assert save_calls == [True]
    assert load_calls == []


def test_app_session_bridge_prunes_old_empty_sessions(monkeypatch, tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    old_empty = manager.create_session(name="Empty", workspace=tmp_path, model="gpt-5.4-mini")
    old_timestamp = (datetime.now() - timedelta(minutes=5)).isoformat()
    old_empty.account_user_id = 9
    old_empty.created_at = old_timestamp
    old_empty.updated_at = old_timestamp
    manager._save_session(old_empty)
    manager._update_index(old_empty)

    populated = manager.create_session(name="Real", workspace=tmp_path, model="gpt-5.4-mini")
    populated.chat_history = [{"role": "user", "content": "keep me"}]
    manager.save_session(populated)
    manager.set_current_session(old_empty.id)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    summaries = bridge.list_session_summaries()

    assert [summary.id for summary in summaries] == [populated.id]
    assert not (manager.sessions_dir / f"{old_empty.id}.json").exists()
    assert manager.get_current_session_id() == populated.id


def test_app_session_bridge_keeps_recent_empty_session_during_creation_grace(monkeypatch, tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    recent_empty = manager.create_session(name="Recent", workspace=tmp_path, model="gpt-5.4-mini")

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    summaries = bridge.list_session_summaries()

    assert [summary.id for summary in summaries] == [recent_empty.id]
    assert (manager.sessions_dir / f"{recent_empty.id}.json").exists()


def test_app_session_bridge_keeps_old_session_with_artifacts(monkeypatch, tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    artifact_session = manager.create_session(name="Artifact", workspace=tmp_path, model="gpt-5.4-mini")
    old_timestamp = (datetime.now() - timedelta(minutes=5)).isoformat()
    artifact_session.created_at = old_timestamp
    artifact_session.updated_at = old_timestamp
    manager._save_session(artifact_session)
    manager._update_index(artifact_session)

    user_root = tmp_path / "user-state"
    artifact_index = user_root / "artifacts" / "chats" / artifact_session.id / "index.json"
    artifact_index.parent.mkdir(parents=True)
    artifact_index.write_text(
        json.dumps({"items": [{"artifact_id": "a1", "created_at": old_timestamp}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_state_root", lambda _user_id: user_root)
    monkeypatch.setattr(session_bridge, "user_sessions", {})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    summaries = bridge.list_session_summaries()

    assert [summary.id for summary in summaries] == [artifact_session.id]
    assert (manager.sessions_dir / f"{artifact_session.id}.json").exists()


def test_app_session_bridge_create_session_inherits_runtime_defaults(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12345",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def get_current_session_id(self):
            return None

        def list_sessions(self):
            return []

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model="gpt-4o-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": runtime.workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-4o-mini",
        "agent_mode": "auto",
        "enabled_tool_packs": default_enabled_tool_packs(),
        "security_permission_mode": "standard",
        "telegram_bot_config_id": None,
        "headless_eligible": False,
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_create_session_without_live_runtime_uses_provider_default(monkeypatch, tmp_path: Path):
    created = Session(
        id="new-provider-default",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4-mini",
        variant="standard",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def get_current_session_id(self):
            return None

        def list_sessions(self):
            return []

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    manager = DummySessionManager(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": tmp_path,
        "model": "gpt-5.4-mini",
        "variant": "standard",
        "planner_model": "gpt-5.4-mini",
        "agent_mode": "auto",
        "enabled_tool_packs": default_enabled_tool_packs(),
        "security_permission_mode": "standard",
        "telegram_bot_config_id": None,
        "headless_eligible": False,
    }
    assert manager.set_calls == [created.id]


def test_session_model_normalizes_runtime_home_workspace_to_default_workspace(monkeypatch, tmp_path: Path):
    runtime_home = (tmp_path / "runtime-home").resolve()
    runtime_home.mkdir()
    default_workspace = (tmp_path / "Documents" / "EmploAI").resolve()
    default_workspace.mkdir(parents=True)

    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))
    monkeypatch.setenv("DEFAULT_WORKSPACE", str(default_workspace))

    session = Session.from_dict(
        {
            "id": "sess-legacy",
            "name": "Legacy",
            "created_at": "2026-05-25T00:00:00",
            "updated_at": "2026-05-25T00:00:00",
            "workspace": str(runtime_home),
            "chat_history": [],
        }
    )

    assert session.workspace == str(default_workspace)
    assert session.to_summary().workspace == str(default_workspace)


def test_session_workspace_id_and_binding_status_are_persisted_and_backfilled(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = SessionManager(base_path=tmp_path / "state")

    created = manager.create_session(name="Workspace", workspace=workspace, model="gpt-5.4-mini")
    assert created.workspace_id
    assert created.workspace_binding_status == "active"

    loaded = manager.load_session(created.id, set_current=False)
    assert loaded.workspace_id == created.workspace_id
    assert loaded.workspace_binding_status == "active"
    assert loaded.to_summary().workspace_id == created.workspace_id

    legacy = Session.from_dict(
        {
            "id": "legacy-workspace",
            "name": "Legacy Workspace",
            "created_at": "2026-06-23T00:00:00",
            "workspace": str(workspace),
        }
    )
    assert legacy.workspace_id
    assert legacy.workspace_binding_status == "active"


def test_app_session_bridge_prefers_newer_disk_session_over_stale_runtime(monkeypatch, tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    created = manager.create_session(
        name="Shared",
        workspace=tmp_path,
        model="gpt-5.2",
        variant="standard",
        agent_mode="auto",
    )
    created.chat_history = [
        {
            "role": "user",
            "content": "hello from app",
            "timestamp": "2026-05-25T00:00:00",
            "channel": "app",
        }
    ]
    manager.save_session(created)

    disk_session = manager.load_session(created.id, set_current=False)
    disk_session.chat_history.append(
        {
            "role": "user",
            "content": "hello from telegram",
            "timestamp": "2026-05-25T00:01:00",
            "channel": "telegram",
        }
    )
    manager.save_session(disk_session)

    stale_runtime_session = Session(
        id=created.id,
        name="Shared",
        created_at=created.created_at,
        updated_at="2026-05-25T00:00:30",
        workspace=str(tmp_path),
        model="gpt-5.2",
        variant="standard",
        agent_mode="auto",
        chat_history=[created.chat_history[0]],
    )

    load_calls: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        session=stale_runtime_session,
        session_manager=manager,
    )

    def load_session_by_id(session_id: str) -> None:
        load_calls.append(session_id)
        runtime.session = manager.load_session(session_id, set_current=False)

    runtime.load_session_by_id = load_session_by_id

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {5: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=5, workspace=tmp_path)
    resolved = bridge.get_session(created.id)

    assert load_calls == [created.id]
    assert [item["content"] for item in resolved.chat_history] == [
        "hello from app",
        "hello from telegram",
    ]


def test_telegram_session_initial_session_prefers_default_workspace_over_runtime_home(monkeypatch, tmp_path: Path):
    runtime_home = (tmp_path / "runtime-home").resolve()
    runtime_home.mkdir()
    default_workspace = (tmp_path / "Documents" / "Primary").resolve()
    default_workspace.mkdir(parents=True)

    created_workspaces: list[Path] = []

    class DummySessionManager:
        def get_current_session_id(self):
            return None

        def create_session(self, **kwargs):
            created_workspaces.append(kwargs["workspace"])
            return Session(
                id="sess-init",
                name="Session 12:00",
                created_at="2026-05-25T12:00:00",
                updated_at="2026-05-25T12:00:00",
                workspace=str(kwargs["workspace"]),
                model=kwargs["model"],
                variant=kwargs["variant"],
                agent_mode=kwargs["agent_mode"],
                planner_model=kwargs["planner_model"],
            )

        def set_current_session(self, _session_id: str):
            return None

    runtime = object.__new__(TelegramSession)
    runtime.session_manager = DummySessionManager()
    runtime.create_new_session_on_init = False
    runtime.workspace = runtime_home
    runtime.current_model = "gpt-5.2"
    runtime.current_variant = "standard"
    runtime.planner_model = None
    runtime.default_planner_model = None
    runtime.shared_current_session_id = None
    runtime.load_session_by_id = lambda _session_id: None
    runtime._resolve_shared_current_session_id = lambda: None

    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))
    monkeypatch.setenv("DEFAULT_WORKSPACE", str(default_workspace))

    TelegramSession._initialize_runtime_session(runtime)

    assert created_workspaces == [default_workspace]


def test_app_session_bridge_create_session_uses_explicit_workspace_override(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12347",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    explicit_workspace = (tmp_path / "chosen-workspace").resolve()
    explicit_workspace.mkdir()
    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model="gpt-4o-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh", workspace=explicit_workspace)

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": explicit_workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-4o-mini",
        "agent_mode": "auto",
        "enabled_tool_packs": default_enabled_tool_packs(),
        "security_permission_mode": "standard",
        "telegram_bot_config_id": None,
        "headless_eligible": False,
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_create_session_uses_runtime_default_planner_when_session_is_automatic(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12346",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model=None,
        default_planner_model="gpt-5.4-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": runtime.workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-5.4-mini",
        "agent_mode": "auto",
        "enabled_tool_packs": default_enabled_tool_packs(),
        "security_permission_mode": "standard",
        "telegram_bot_config_id": None,
        "headless_eligible": False,
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_create_session_prefers_configured_workspace_over_runtime_home(monkeypatch, tmp_path: Path):
    created = Session(
        id="new-home-fallback",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def save_session(self, session):
            return None

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    runtime_home = (tmp_path / "runtime-home").resolve()
    runtime_home.mkdir()
    default_workspace = (tmp_path / "Documents" / "EmploAI").resolve()
    default_workspace.mkdir(parents=True)

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=runtime_home,
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model=None,
        default_planner_model=None,
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))
    monkeypatch.setenv("DEFAULT_WORKSPACE", str(default_workspace))
    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=runtime_home)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": default_workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": None,
        "agent_mode": "auto",
        "enabled_tool_packs": default_enabled_tool_packs(),
        "security_permission_mode": "standard",
        "telegram_bot_config_id": None,
        "headless_eligible": False,
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_activate_session_persists_runtime_before_switch(monkeypatch, tmp_path: Path):
    existing = Session(
        id="sess4321",
        name="Existing",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path),
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.set_calls: list[str] = []

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == existing.id
            return existing

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=existing,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {42: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=42, workspace=tmp_path)
    result = bridge.activate_session(existing.id)

    assert result is existing
    assert saved == ["saved"]
    assert manager.set_calls == [existing.id]
    assert load_calls == [existing.id]


def test_load_session_by_id_rejects_switch_during_active_task():
    class DummySessionManager:
        def __init__(self):
            self.load_calls: list[str] = []

        def get_current_session_id(self):
            return "current"

        def load_session(self, session_id: str):
            self.load_calls.append(session_id)
            raise AssertionError("load_session should not run while the task is active")

    runtime = object.__new__(TelegramSession)
    runtime.session_manager = DummySessionManager()
    runtime.is_processing = True
    runtime.tool_executor = None
    runtime.single_agent = None
    runtime.refined_agent = None
    runtime.unified_agent = None

    TelegramSession.load_session_by_id(runtime, "current")
    assert runtime.session_manager.load_calls == []

    with pytest.raises(RuntimeError, match="Cannot switch sessions"):
        TelegramSession.load_session_by_id(runtime, "other")


def test_load_session_by_id_updates_tool_executor_workspace_path(tmp_path: Path):
    new_workspace = tmp_path / "workspace"
    new_workspace.mkdir()

    loaded_session = Session(
        id="sess1234",
        name="Loaded",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(new_workspace),
        model="gpt-test",
        variant="thinking",
        agent_mode="auto",
        chat_history=[{"role": "user", "content": "hello"}],
        active_skills=["skill-a"],
    )

    class DummySessionManager:
        def get_current_session_id(self):
            return "old"

        def load_session(self, session_id: str):
            assert session_id == "sess1234"
            return loaded_session

    runtime = object.__new__(TelegramSession)
    runtime.session_manager = DummySessionManager()
    runtime.is_processing = False
    runtime.workspace = tmp_path / "old"
    runtime.active_skills = []
    runtime.skill_registry = None
    runtime.tool_executor = SimpleNamespace(
        workspace_path=runtime.workspace,
        single_agent=None,
        skill_registry=None,
        active_skills=[],
    )
    runtime.single_agent = None
    runtime.refined_agent = None
    runtime.unified_agent = None

    TelegramSession.load_session_by_id(runtime, "sess1234")

    assert runtime.workspace == new_workspace.resolve()
    assert runtime.tool_executor.workspace_path == new_workspace.resolve()
    assert runtime.current_model == "gpt-test"
    assert runtime.current_variant == "thinking"
    assert runtime.active_skills == ["skill-a"]


def test_set_workspace_refreshes_workspace_scoped_runtime_managers(monkeypatch, tmp_path: Path):
    import shared.heartbeat as heartbeat_module

    old_workspace = (tmp_path / "old").resolve()
    new_workspace = (tmp_path / "new").resolve()
    old_workspace.mkdir()
    new_workspace.mkdir()

    memory_calls: list[Path] = []
    context_calls: list[Path] = []

    class DummyLiveConfig:
        def __init__(self, path: Path):
            self.path = path
            self.imported = False

        def import_from_env(self):
            self.imported = True

    class DummyHeartbeat:
        def __init__(self, workspace: Path, *, enabled: bool = False):
            self.workspace = workspace
            self.enabled = enabled
            self.interval_seconds = 900
            self.announcement_callback = "announce"
            self.agent_callback = "agent"
            self.stop_calls = 0
            self.start_calls = 0

        def stop(self):
            self.stop_calls += 1

        def start(self):
            self.start_calls += 1

    new_heartbeat_instances: list[DummyHeartbeat] = []

    def fake_get_memory_manager(path: Path):
        memory_calls.append(path)
        return f"memory:{path}"

    def fake_get_context_loader(path: Path):
        context_calls.append(path)
        return f"context:{path}"

    def fake_get_heartbeat_manager(*, workspace: Path, interval_seconds: int, announcement_callback, agent_callback):
        heartbeat = DummyHeartbeat(workspace, enabled=False)
        heartbeat.interval_seconds = interval_seconds
        heartbeat.announcement_callback = announcement_callback
        heartbeat.agent_callback = agent_callback
        new_heartbeat_instances.append(heartbeat)
        return heartbeat

    monkeypatch.setattr("telegram_bot.telegram_session_state.get_memory_manager", fake_get_memory_manager)
    monkeypatch.setattr("telegram_bot.telegram_session_state.get_context_loader", fake_get_context_loader)
    monkeypatch.setattr("telegram_bot.telegram_session_state.LiveConfig", DummyLiveConfig)
    monkeypatch.setattr(heartbeat_module, "get_heartbeat_manager", fake_get_heartbeat_manager)

    runtime = object.__new__(TelegramSession)
    runtime.workspace = old_workspace
    runtime.is_processing = False
    runtime.memory_manager = None
    runtime.context_loader = None
    runtime.live_config = None
    runtime.skill_registry = "skills"
    runtime.active_skills = ["skill-a"]
    runtime.single_agent = "single-agent"
    runtime.tool_executor = SimpleNamespace(
        workspace_path=old_workspace,
        single_agent=None,
        skill_registry=None,
        active_skills=[],
    )
    runtime.heartbeat_manager = DummyHeartbeat(old_workspace, enabled=True)
    runtime.unified_agent = SimpleNamespace(workspace=old_workspace)

    resolved = TelegramSession.set_workspace(runtime, new_workspace)

    assert resolved == new_workspace
    assert runtime.workspace == new_workspace
    assert memory_calls == [new_workspace]
    assert context_calls == [new_workspace]
    assert runtime.memory_manager == f"memory:{new_workspace}"
    assert runtime.context_loader == f"context:{new_workspace}"
    assert isinstance(runtime.live_config, DummyLiveConfig)
    assert runtime.live_config.path == new_workspace / "config.json"
    assert runtime.live_config.imported is True
    assert runtime.tool_executor.workspace_path == new_workspace
    assert runtime.tool_executor.single_agent == "single-agent"
    assert runtime.tool_executor.skill_registry == "skills"
    assert runtime.tool_executor.active_skills == ["skill-a"]
    assert runtime.unified_agent.workspace == new_workspace
    assert len(new_heartbeat_instances) == 1
    assert new_heartbeat_instances[0].workspace == new_workspace
    assert new_heartbeat_instances[0].start_calls == 1


def test_session_manager_load_session_can_skip_current_pointer_update(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    first = manager.create_session(name="First", workspace=tmp_path, model="gpt-5.2")
    second = manager.create_session(name="Second", workspace=tmp_path, model="gpt-5.4")
    manager.set_current_session(first.id)

    loaded = manager.load_session(second.id, set_current=False)

    assert loaded.id == second.id
    assert manager.get_current_session_id() == first.id


def test_app_session_bridge_list_sessions_does_not_switch_current_session(tmp_path: Path, monkeypatch):
    manager = SessionManager(base_path=tmp_path)
    current = manager.create_session(name="Current", workspace=tmp_path, model="gpt-5.4")
    manager.set_current_session(current.id)
    manager.create_session(name="Older", workspace=tmp_path, model="claude-haiku-4.5")
    manager.set_current_session(current.id)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)

    bridge = session_bridge.AppSessionBridge(user_id=101, workspace=tmp_path)
    sessions = bridge.list_sessions()

    assert {session.id for session in sessions} == {summary.id for summary in manager.list_sessions()}
    assert manager.get_current_session_id() == current.id


def test_session_round_trips_event_timeline():
    session = Session(
        id="sess1",
        name="Timeline",
        created_at="2026-05-08T10:00:00",
        updated_at="2026-05-08T10:00:00",
        workspace="C:/tmp",
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
        event_timeline=[
            {
                "id": "evt1",
                "kind": "command",
                "title": "Command · /verbose on",
                "content": "Verbose tool logging enabled.",
                "tone": "accent",
                "timestamp": "2026-05-08T10:00:01",
                "channel": "app",
                "source_format": "app_system",
                "metadata": {"command": "/verbose on"},
            }
        ],
    )

    restored = Session.from_dict(session.to_dict())

    assert restored.event_timeline == session.event_timeline


def test_telegram_session_save_and_load_round_trips_event_timeline(monkeypatch, tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Timeline", workspace=tmp_path, model="gpt-5.4")
    manager.set_current_session(session.id)
    event_timeline = [
        {
            "id": "evt-live",
            "kind": "tool",
            "title": "Tool · run_command",
            "content": "run_command(command='npm test')",
            "tone": "neutral",
        }
    ]

    runtime = TelegramSession.__new__(TelegramSession)
    runtime.session_manager = manager
    runtime.chat_history = [{"role": "user", "content": "run tests"}]
    runtime.event_timeline = list(event_timeline)
    runtime.workspace = tmp_path
    runtime.current_model = "gpt-5.4"
    runtime.current_variant = "standard"
    runtime.agent_mode = "auto"
    runtime.planner_model = "gpt-5.4-mini"
    runtime.default_planner_model = "gpt-5.4-mini"
    runtime.enabled_tool_packs = ["workspace_read", "workspace_write"]
    runtime.telegram_bot_config_id = None
    runtime.headless_eligible = False
    runtime.task_history = []
    runtime.active_task_id = None
    runtime.task_board_armed_next_turn = False
    runtime.active_skills = []
    runtime.last_context_compaction = None

    runtime.save_session()

    persisted = manager.load_session(session.id, set_current=False)
    assert persisted.event_timeline == event_timeline

    monkeypatch.setattr(
        TelegramSession,
        "set_workspace",
        lambda self, workspace, rebuild_tool_executor=False: setattr(self, "workspace", Path(workspace)) or self.workspace,
    )
    restored_runtime = TelegramSession.__new__(TelegramSession)
    restored_runtime.session_manager = manager
    restored_runtime.is_processing = False
    restored_runtime.workspace = tmp_path
    restored_runtime.default_planner_model = "gpt-5.4-mini"

    restored_runtime.load_session_by_id(session.id, set_current=False)

    assert restored_runtime.event_timeline == event_timeline


def test_sync_event_to_realtime_event_maps_timeline_event():
    event = {
        "type": "timeline_event",
        "session_id": "sess1",
        "payload": {
            "event": {
                "id": "evt1",
                "kind": "tool",
                "title": "Tool · click",
                "content": "click(x: 100, y: 200)",
            }
        },
    }

    realtime = app_server._sync_event_to_realtime_event(
        event,
        active_session_id="sess1",
        client_id=None,
        verbose_mode=False,
    )

    assert realtime is not None
    assert realtime.type == "timeline_event"
    assert realtime.payload == event["payload"]


def test_app_session_bridge_append_timeline_event_persists(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Timeline", workspace=tmp_path, model="gpt-5.4")

    bridge = session_bridge.AppSessionBridge(user_id=7, workspace=tmp_path)
    bridge.session_manager = manager

    event = bridge.append_timeline_event(
        session_id=session.id,
        kind="command",
        title="Command · /verbose on",
        content="Verbose tool logging enabled.",
        tone="accent",
        channel="app",
        source_format="app_system",
        metadata={"command": "/verbose on"},
    )

    reloaded = manager.load_session(session.id, set_current=False)

    assert event["kind"] == "command"
    assert len(reloaded.event_timeline) == 1
    assert reloaded.event_timeline[0]["title"] == "Command · /verbose on"


def test_app_session_bridge_detailed_session_view_includes_task_board(tmp_path: Path, monkeypatch):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Tasked", workspace=tmp_path, model="gpt-5.4")
    create_task_board(session, user_message="Open Spotify and play a song")
    manager.save_session(session)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)

    bridge = session_bridge.AppSessionBridge(user_id=55, workspace=tmp_path)
    loaded = bridge.get_session(session.id)
    detail = bridge.detailed_session_view(loaded)

    assert detail["task_board"] is None
    assert len(detail["completed_task_boards"]) == 1
    assert detail["completed_task_boards"][0]["main_goal"] == "Open Spotify and play a song"
    assert detail["completed_task_boards"][0]["status"] == "interrupted"
