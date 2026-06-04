# Desktop App Status And Feature Direction

## Purpose

This document explains:

- what was implemented for the new desktop-first app path
- how the current desktop app works
- which parts of the requested feature set are already in place
- which requested features are planned but not fully implemented yet
- how the desktop app fits into the larger Windows product direction

This is meant to be the practical handoff/status file for anyone continuing desktop app work.

## Product Direction You Asked For

The requested desktop feature set is not "just a web wrapper." The intended product is:

- a real Windows desktop app
- using the same shared session system already used by Telegram and the mobile app
- opening the last active shared session automatically
- using voice as the default input path
- keeping text as a secondary fallback input path
- avoiding all phone-style pairing logic in desktop mode
- acting as both:
  - the local interface for the agent running on the same computer
  - the future hub for controlling other agent instances on VPSs / servers / remote machines

The requested desktop structure is:

- `This Computer`
  - functional in v1
  - same core behavior as the mobile app chat/control flow
  - no pairing flow
  - no local screen preview
- `Other Computers`
  - visible from day one
  - intended as the future hub for remote runtimes
  - should eventually show previews and controls for agents running on other machines
  - in v1 it is intentionally a placeholder shell, not a finished remote-control system

You also asked for the desktop app to preserve advanced control breadth, not become a simplified chat-only UI. That means the desktop app needs to remain a place where deeper agent/runtime controls can live.

## Core Decisions That Were Implemented

### 1. Real desktop shell

The desktop path now uses an `Electron` shell rather than a browser-only wrapper.

Files:

- [desktop_app/package.json](desktop_app/package.json)
- [desktop_app/main.js](desktop_app/main.js)
- [desktop_app/preload.js](desktop_app/preload.js)

Why:

- the repo already had a React/Expo client that can render on web
- Electron lets the existing renderer be reused
- Electron gives a clean preload bridge for desktop-native bootstrap/runtime/voice wiring
- this matches the Windows-first product direction better than treating desktop as a browser tab

### 2. Shared-session model was preserved

The desktop app does not create a separate desktop-only session namespace.

It uses the same session system already shared between:

- Telegram
- the mobile app
- the new desktop app

Relevant files:

- [mobile_app/backend/session_bridge.py](mobile_app/backend/session_bridge.py)
- [mobile_app/backend/app_server.py](mobile_app/backend/app_server.py)
- [mobile_app/client/src/lib/appApi.ts](mobile_app/client/src/lib/appApi.ts)

Implemented behavior:

- desktop bootstrap loads the last current shared session if one exists
- if no session exists, one is created
- desktop session switching updates the canonical current session
- desktop messages go into the same session history visible to other channels

### 3. Pairing was removed from desktop mode

Desktop mode does not use:

- device pairing UI
- backend URL entry UI
- trusted-device pairing flow

Instead, Electron bootstraps the renderer directly into the local app channel.

Relevant files:

- [mobile_app/client/lib/appConfig.ts](mobile_app/client/lib/appConfig.ts)
- [mobile_app/client/src/lib/desktopBridge.ts](mobile_app/client/src/lib/desktopBridge.ts)
- [mobile_app/client/src/components/AppDrawer.tsx](mobile_app/client/src/components/AppDrawer.tsx)
- [mobile_app/client/app/pair.web.tsx](mobile_app/client/app/pair.web.tsx)
- [mobile_app/client/app/settings.web.tsx](mobile_app/client/app/settings.web.tsx)

### 4. Runtime ownership moved to Electron main, not the renderer

The renderer does not spawn backend processes directly.

Electron main now:

- checks whether a compatible local runtime is already running
- attaches if it exists
- launches it if it does not
- waits for readiness
- hands the renderer the local API/token/session bootstrap data

Relevant files:

- [mobile_app/backend/desktop_runtime.py](mobile_app/backend/desktop_runtime.py)
- [desktop_app/main.js](desktop_app/main.js)
- [desktop_app/preload.js](desktop_app/preload.js)

### 5. Voice was treated as primary input, text as fallback

The desktop UI was built around voice-first interaction, while still keeping a text composer for fallback.

Important constraint:

- no new voice engine was invented
- the desktop shell integrates existing voice runtime pieces already present in `mobile_app/backend`

Current integration path:

- the Electron renderer captures microphone audio with Web Audio / `getUserMedia`
- the renderer streams voice events to the backend over `/ws/app/voice`
- the backend voice runtime handles local Whisper transcription
- partial transcript events update the desktop draft UI
- final transcript events are sent into the same shared chat/session path as normal chat messages
- there is intentionally no separate Electron IPC voice bridge; the websocket path is the single supported desktop voice path

Relevant files:

- [desktop_app/main.js](desktop_app/main.js)
- [mobile_app/backend/whisper_cpp_live.py](mobile_app/backend/whisper_cpp_live.py)
- [mobile_app/backend/standalone_voice_engine.py](mobile_app/backend/standalone_voice_engine.py)
- [mobile_app/client/src/desktop/DesktopConversationView.tsx](mobile_app/client/src/desktop/DesktopConversationView.tsx)

### 6. The two-tab desktop model now exists

The desktop renderer now has:

- `This Computer`
- `Other Computers`

Relevant files:

- [mobile_app/client/app/desktop.web.tsx](mobile_app/client/app/desktop.web.tsx)
- [mobile_app/client/src/desktop/DesktopAppShell.tsx](mobile_app/client/src/desktop/DesktopAppShell.tsx)
- [mobile_app/client/src/desktop/models.ts](mobile_app/client/src/desktop/models.ts)

## What Is Implemented Right Now

### Desktop bootstrap / runtime

Implemented:

- desktop config flags in app config
- desktop-local token bootstrap
- attach-or-launch runtime behavior
- readiness/status reporting
- shared-session bootstrap

Relevant files:

- [config.json](config.json)
- [shared/live_config.py](shared/live_config.py)
- [mobile_app/backend/auth_store.py](mobile_app/backend/auth_store.py)
- [mobile_app/backend/desktop_runtime.py](mobile_app/backend/desktop_runtime.py)

Added desktop config keys:

- `channels.desktop.enabled`
- `channels.desktop.host`
- `channels.desktop.port`
- `channels.desktop.auto_start`
- `channels.desktop.attach_timeout_seconds`

### Desktop renderer shell

Implemented:

- desktop route
- desktop home redirect for web
- local tab UI
- remote placeholder tab UI
- desktop-only chat surface
- shared session rail
- runtime / voice state display
- run / tool activity display

Relevant files:

- [mobile_app/client/app/index.web.tsx](mobile_app/client/app/index.web.tsx)
- [mobile_app/client/app/chat.web.tsx](mobile_app/client/app/chat.web.tsx)
- [mobile_app/client/app/desktop.web.tsx](mobile_app/client/app/desktop.web.tsx)
- [mobile_app/client/src/desktop/DesktopAppShell.tsx](mobile_app/client/src/desktop/DesktopAppShell.tsx)
- [mobile_app/client/src/desktop/DesktopConversationView.tsx](mobile_app/client/src/desktop/DesktopConversationView.tsx)
- [mobile_app/client/src/desktop/models.ts](mobile_app/client/src/desktop/models.ts)

### Shared current-session switching

Implemented:

- backend session activation endpoint
- client session activation helper
- shared current-session updates when switching sessions in desktop

Relevant files:

- [mobile_app/backend/session_bridge.py](mobile_app/backend/session_bridge.py)
- [mobile_app/backend/app_server.py](mobile_app/backend/app_server.py)
- [mobile_app/client/src/lib/appApi.ts](mobile_app/client/src/lib/appApi.ts)

### Voice event routing into shared chat

Implemented:

- renderer voice capture sends `voice_start`, `voice_chunk`, `voice_commit`, and `voice_cancel` through `/ws/app/voice`
- backend voice websocket emits `voice_state`, `voice_partial`, `voice_final`, and `error`
- partial transcript stays UI-only
- final transcript goes through the same chat path as other user input
- chat websocket now accepts `source_format`, including voice transcript sends from the desktop client

Relevant files:

- [config.json](config.json)
- [shared/live_config.py](shared/live_config.py)
- [desktop_app/main.js](desktop_app/main.js)
- [mobile_app/backend/app_server.py](mobile_app/backend/app_server.py)
- [mobile_app/client/src/desktop/DesktopConversationView.tsx](mobile_app/client/src/desktop/DesktopConversationView.tsx)

### Desktop UI gating

Implemented:

- no desktop pairing flow
- no desktop backend URL setup flow
- no local screen preview in `This Computer`
- `Other Computers` visible but clearly placeholder

Relevant files:

- [mobile_app/client/src/components/AppDrawer.tsx](mobile_app/client/src/components/AppDrawer.tsx)
- [mobile_app/client/app/pair.web.tsx](mobile_app/client/app/pair.web.tsx)
- [mobile_app/client/app/settings.web.tsx](mobile_app/client/app/settings.web.tsx)
- [mobile_app/client/src/desktop/DesktopConversationView.tsx](mobile_app/client/src/desktop/DesktopConversationView.tsx)

### Plan mirroring / handoff

Implemented:

- the accepted desktop-first plan was mirrored into repo-root [plan.md](plan.md)

## How The Desktop App Behaves Right Now

### This Computer tab

Current behavior:

- boots into the local runtime
- opens the last shared session
- creates a shared session if none exists
- shows live voice state
- shows live transcript draft
- sends finalized voice transcript through the shared chat path
- keeps text fallback available
- shows assistant messages and streaming text
- shows run/tool activity
- provides quick access to Cron and Agent controls
- deliberately does not show local screen preview

### Other Computers tab

Current behavior:

- visible in the desktop shell
- contains placeholder remote-runtime cards
- contains placeholder preview regions
- explicitly communicates that remote runtime support is planned, not connected yet

This matches the intent that the desktop app should already be shaped like a future multi-machine hub even before the remote backend exists.

## Requested Features That Are Part Of The Direction But Not Fully Implemented Yet

This section is important because these items were part of the requested feature set, but they are not all complete in the current code.

### 1. The full remote hub for VPS / server / other-computer agents

Requested behavior:

- the desktop app should not only control the local machine
- it should also become the control hub for other agent instances on other machines
- each remote runtime should eventually have:
  - identity
  - connection status
  - preview area
  - control surface
  - session / runtime context

Current status:

- UI placeholder exists
- actual remote runtime transport, preview streaming, runtime registration, and remote control logic do not exist yet

What still needs to be built:

- remote runtime discovery / registration model
- remote status transport
- remote preview transport
- remote action transport
- remote runtime auth model
- remote session-selection semantics per runtime

### 2. Assistant voice output / TTS

Requested direction:

- voice input is primary now
- assistant voice output should eventually exist too
- no new TTS stack should be invented if an existing voice/runtime path already exists or is being built by another agent

Current status:

- desktop v1 is voice-input-first only
- desktop UI and architecture assume future assistant voice output can be added later
- desktop does not yet play assistant voice responses as part of the Electron experience

Important guidance:

- future TTS should be integrated as an extension of the existing runtime/voice event flow
- it should not become a separate, unrelated desktop-only voice subsystem

### 3. The desktop app as the main advanced control surface

Requested direction:

- desktop should carry the more complex controls
- later it should expose deeper parameters such as:
  - which tools the model can use
  - heartbeat tuning
  - manual cron management
  - other runtime/model parameters

Current status:

- desktop already links into the existing Cron and Agent control surfaces
- the deeper desktop-native control set is not fully redesigned into the new desktop shell yet

Future work should bring more of the Telegram-style controls directly into the desktop-native interface.

### 4. Windows MSI / distributed packaging integration

Requested direction:

- the desktop app is part of the main Windows product path
- not a separate long-term side product

Current status:

- desktop app implementation exists
- desktop runtime bootstrap exists
- the Windows build script now exports the renderer, builds the backend helper, packages Electron, and wraps that app into the MSI
- packaged parity still needs to be verified on every release because local development uses source Python while the MSI uses `EmploAIBackend.exe`

## Important Product Rules To Preserve

These are the rules that should stay true as further desktop work continues.

### Shared session rules

- do not create a desktop-only local session namespace
- local desktop must stay on the existing shared session system used by Telegram/mobile
- desktop should continue to open the last active shared session by default

### Voice rules

- voice is the primary input mode
- text is fallback, not the main product identity
- no new voice engine should be invented if the existing runtime pieces or the other agent's voice work can be integrated
- partial transcripts should remain draft/UI state
- only final transcript should enter session history

### Screen preview rules

- do not add local screen preview to `This Computer`
- screen preview belongs to the remote-control case
- `Other Computers` is where preview surfaces belong

### Desktop-mode gating rules

- no phone-style pairing flow
- no backend URL manual setup flow
- no trusted-device pairing UX in desktop mode

### Advanced-control rules

- desktop should remain the place where deeper agent controls can live
- future desktop work should not collapse into a consumer-only chat window

## Current File-Level Summary

The main desktop-related additions / updates are:

- [plan.md](plan.md)
- [config.json](config.json)
- [shared/live_config.py](shared/live_config.py)
- [.gitignore](.gitignore)
- [desktop_app/package.json](desktop_app/package.json)
- [desktop_app/main.js](desktop_app/main.js)
- [desktop_app/preload.js](desktop_app/preload.js)
- [mobile_app/backend/desktop_runtime.py](mobile_app/backend/desktop_runtime.py)
- [mobile_app/backend/auth_store.py](mobile_app/backend/auth_store.py)
- [mobile_app/backend/session_bridge.py](mobile_app/backend/session_bridge.py)
- [mobile_app/backend/app_server.py](mobile_app/backend/app_server.py)
- [mobile_app/client/package.json](mobile_app/client/package.json)
- [mobile_app/client/lib/appConfig.ts](mobile_app/client/lib/appConfig.ts)
- [mobile_app/client/src/lib/desktopBridge.ts](mobile_app/client/src/lib/desktopBridge.ts)
- [mobile_app/client/src/lib/appApi.ts](mobile_app/client/src/lib/appApi.ts)
- [mobile_app/client/src/components/AppDrawer.tsx](mobile_app/client/src/components/AppDrawer.tsx)
- [mobile_app/client/app/index.web.tsx](mobile_app/client/app/index.web.tsx)
- [mobile_app/client/app/chat.web.tsx](mobile_app/client/app/chat.web.tsx)
- [mobile_app/client/app/desktop.web.tsx](mobile_app/client/app/desktop.web.tsx)
- [mobile_app/client/app/pair.web.tsx](mobile_app/client/app/pair.web.tsx)
- [mobile_app/client/app/settings.web.tsx](mobile_app/client/app/settings.web.tsx)
- [mobile_app/client/src/desktop/DesktopAppShell.tsx](mobile_app/client/src/desktop/DesktopAppShell.tsx)
- [mobile_app/client/src/desktop/DesktopConversationView.tsx](mobile_app/client/src/desktop/DesktopConversationView.tsx)
- [mobile_app/client/src/desktop/models.ts](mobile_app/client/src/desktop/models.ts)

## Verification Already Performed

Verified:

- TypeScript renderer typecheck passed with:
  - `npm --prefix mobile_app/client run typecheck`
- desktop runtime status helper worked
- desktop runtime bootstrap worked
- local runtime launched successfully through bootstrap
- bootstrap returned:
  - local API URL
  - desktop access token
  - current shared session id
  - launched/attached runtime status

## Recommended Next Steps

The next logical phases are:

1. Verify MSI parity against local development before each release, especially runtime startup speed, `/ws/app/voice`, and agent stability.
2. Build the real remote-runtime hub backend for `Other Computers`.
3. Add assistant voice output / TTS using the existing runtime/voice path rather than inventing a separate stack.
4. Promote deeper controls into the desktop-native shell:
   - tool access control
   - heartbeat controls
   - cron editing
   - more runtime/model configuration

## Canonical Planning Docs

Current planning / handoff docs for this effort:

- [plan.md](plan.md)
- [desktop_app_status.md](desktop_app_status.md)
