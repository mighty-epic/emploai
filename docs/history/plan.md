# Desktop-First Voice App Plan

## Summary
- Build a real `Windows-first` desktop app using an `Electron` shell around the existing React/Expo web-capable client, not a browser-only wrapper.
- Keep one shared session system across `Telegram`, `mobile app`, and `desktop app`; the desktop app auto-opens the last active session and creates a new one only if no session exists.
- Treat voice as the primary input path and text as a secondary fallback control; do not build a new voice engine, only integrate the existing desktop-oriented voice engine/runtime already present in `app_backend`.
- The desktop app has two top-level tabs from day one:
  - `This Computer`: fully functional in v1, same core behavior as the mobile app chat/control surface, but with no pairing flow and no local screen preview.
  - `Other Computers`: visible in v1 as a non-functional control shell with placeholder states and preview regions, ready for future VPS/remote-agent work.
- First implementation task should mirror this exact plan into repo-root `plan.md` as the canonical handoff document for other agents.

## Key Changes
- Add a new `desktop shell` package for Electron main/preload/runtime lifecycle, while keeping renderer reuse centered on the existing `mobile_app/client` code and shared API/state modules.
- Refactor the current mobile client into `shared renderer logic + platform adapters`:
  - mobile adapters keep pairing, backend URL entry, secure-store behavior, and mobile capture/voice wiring.
  - desktop adapters remove pairing/backend URL setup, use local bootstrap, and expose desktop runtime status.
- Desktop window model is a single main window with two tabs:
  - `This Computer` uses the current chat/session/cron/agent-control model, keeps all complex controls visible or reachable, and removes the phone-specific pairing/setup gate.
  - `Other Computers` shows remote-agent cards, preview panes, connection/status placeholders, and empty states only; no remote runtime implementation is included in v1.
- Local runtime model is `hybrid attach/launch`:
  - on startup, the Electron main process looks for a compatible local backend/runtime.
  - if found, it attaches.
  - if not found, it launches the local backend/runtime and waits for readiness.
  - the renderer never spawns backend processes directly.
- Desktop auth/bootstrap replaces pairing, not session logic:
  - no device pairing screens, no trusted-device exchange, no backend URL input.
  - Electron main/preload bootstraps the renderer into the local app-channel API with a desktop-local auth/context handshake.
  - the renderer then uses the same app REST/WebSocket contracts for sessions, chat, cron, controls, and voice event display.
- Voice integration reuses the existing voice-engine/runtime pieces as an adapter layer:
  - keep the existing `voice_state`, `voice_partial`, `voice_final`, and `error` interaction model for the renderer.
  - finalized transcripts go through the same shared chat turn/session path as the mobile app.
  - partial transcripts stay UI-only draft state and are not stored as session history.
  - assistant voice output is explicitly out of scope for v1.
- Local-tab UI behavior:
  - no screen preview on `This Computer`.
  - always show current mic/voice state, runtime status, current session, live transcript draft, assistant messages, and run/tool activity.
  - keep advanced controls accessible: sessions, run control, cron, memory, config, skills, subagents, heartbeat, and future expansion points.
- Remote-tab UI behavior:
  - reserve card/list/detail layout for future remote runtimes.
  - each future runtime gets a preview area, connection state, and control affordances.
  - in v1, render this as a visible but disabled/planned interface with explicit “not connected yet” messaging.
- Distribution path:
  - desktop app is part of the main Windows product direction, not a separate long-term product.
  - initial implementation can land as a working desktop app + local runtime integration first, then fold into the MSI/distributed Windows packaging path once stable.

## Public Interfaces / Contracts
- Add desktop config flags alongside existing channel flags:
  - `channels.desktop.enabled`
  - `channels.desktop.host`
  - `channels.desktop.port`
  - `channels.desktop.auto_start`
  - `channels.desktop.attach_timeout_seconds`
- Add an Electron preload contract as the renderer’s only desktop-native surface:
  - `bootstrap()` returns local API base URL, desktop auth context/token, current session id, and runtime mode.
  - `getRuntimeStatus()` returns attach/launch/readiness/degraded state.
  - `onRuntimeEvent()` streams backend lifecycle and desktop-shell status updates.
- Keep the existing app-channel transport as the renderer’s main backend contract:
  - existing session/chat/control REST endpoints stay the primary API.
  - existing chat and voice websocket event model stays the renderer event contract.
- Add frontend-only desktop view models for the second tab:
  - `DesktopMode = "local" | "remote"`
  - `RemoteRuntimeSummary` for future remote cards
  - `RemotePreviewState` for future remote preview panes
- Keep `TelegramSession` / shared session store as the source of truth; no desktop-only session namespace is introduced.

## Test Plan
- Startup:
  - desktop app attaches to an already-running compatible local runtime and opens the last active shared session.
  - desktop app launches the local runtime when none is running, then opens the last active session.
  - if no prior session exists, desktop app creates one cleanly and marks it current.
- Session sharing:
  - messages sent from desktop appear in the same shared session visible to Telegram/mobile.
  - switching sessions in desktop uses the same current-session semantics and respects active-run guards.
- UI gating:
  - no pairing UI, backend URL UI, or trusted-device flow is reachable in desktop mode.
  - `This Computer` tab has no screen preview surface.
  - `Other Computers` tab is visible with placeholder preview/status cards and no broken actions.
- Voice integration:
  - desktop voice adapter drives the existing voice-state model in the UI.
  - partial transcript updates render continuously.
  - final transcript is committed once and stored as a normal shared session message.
  - backend/voice failures surface as UI state and diagnostics without crashing the window.
- Controls:
  - pause/stop/restart, cron views, memory/config/skills/subagents, and heartbeat controls all work from the desktop renderer on the local tab.
  - text fallback still works even though voice is primary.
- Packaging smoke target:
  - Windows desktop build launches successfully and can attach/launch local runtime in a packaged environment before MSI integration is considered complete.

## Assumptions And Defaults
- `Electron` is the chosen shell because the repo already has a React/Expo client with `react-native-web`, and there is no existing desktop shell to extend.
- `Windows-first` is the v1 delivery target because the current distributed product and installer path are Windows-centric.
- `Hybrid attach/launch` is the runtime ownership model.
- `This Computer` is the only functional tab in v1; `Other Computers` is intentionally UI-only scaffolding.
- Voice input is in scope; assistant voice output is not.
- No new STT/TTS engine should be invented; only the existing desktop voice-engine/runtime work should be integrated.
- The desktop renderer should preserve the mobile app’s advanced control breadth rather than launching as a simplified consumer UI.
