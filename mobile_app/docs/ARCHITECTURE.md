# EmploAI Mobile App Architecture

## Goal
Add a standalone mobile app experience for EmploAI without removing or breaking the current Telegram path.

## Non-negotiable constraints
- Telegram remains intact.
- New app support is additive only.
- Runtime behavior should be switchable by flag, not by replacing existing paths.
- The mobile app lives in its own top-level folder: `mobile_app/`.

## Recommended direction
Build a new app channel alongside Telegram:
- **Client:** Expo / React Native app using EAS
- **Backend transport:** FastAPI service with HTTP + WebSocket endpoints
- **Shared agent core:** reuse existing session, unified-agent, memory, tools, scheduler infrastructure where practical
- **Channel flag:** `telegram` for current flow, `app` for the new mobile flow

## Why this architecture fits the current repo
The repo already has:
- Python backend logic
- session and memory abstractions in `shared/`
- live config in `shared/live_config.py`
- agent/session runtime in `telegram_bot/telegram_session_state.py`
- FastAPI/WebSocket dependencies already present in `requirements.txt`

So the clean expansion path is:
1. keep Telegram as one delivery channel
2. add a new app channel backend
3. let both channels call into shared runtime/state layers

## Proposed channel model
Introduce a simple channel concept:
- `telegram` = existing bot path
- `app` = new mobile app path

Recommended config shape:
```json
{
  "channels": {
    "telegram": {
      "enabled": true
    },
    "app": {
      "enabled": false,
      "host": "0.0.0.0",
      "port": 8787,
      "auth_mode": "token",
      "push_notifications": false
    }
  }
}
```

This is additive and avoids touching current Telegram behavior except for reading a flag later.

## Recommended backend split
Create a new Python package for app support, separate from `telegram_bot/`:
- `mobile_app/backend/` for app transport/backend code
- `mobile_app/client/` for Expo app

Suggested backend modules:
- `mobile_app/backend/app_server.py` — FastAPI app entry point
- `mobile_app/backend/routes/auth.py` — login/device registration
- `mobile_app/backend/routes/chat.py` — REST chat/session endpoints
- `mobile_app/backend/routes/jobs.py` — scheduled jobs/status endpoints
- `mobile_app/backend/ws.py` — WebSocket streaming endpoint
- `mobile_app/backend/session_bridge.py` — adapter between mobile channel and shared runtime
- `mobile_app/backend/models.py` — pydantic models
- `mobile_app/backend/push.py` — Expo push integration later

## Recommended mobile app split
Suggested Expo structure:
- `mobile_app/client/app/` — Expo Router screens
- `mobile_app/client/src/api/` — backend client
- `mobile_app/client/src/state/` — auth/session/chat state
- `mobile_app/client/src/components/` — UI
- `mobile_app/client/src/types/` — TS types

## Core app features for v1
1. authentication / trusted-device pairing
2. chat with the agent
3. streamed assistant responses
4. tool-run status feed
5. session list/history
6. job list / scheduler visibility
7. settings page for model/mode/channel info

## Backend integration strategy
Do **not** fork the agent logic.
Instead, extract/reuse the reusable parts now buried in Telegram session handling.

### Current reusable pieces
- `shared/live_config.py`
- `shared/session_types.py`
- memory/context infrastructure in `shared/`
- tool execution path in `cli/agent_tools/`
- unified prompt/tool architecture in current chat flow

### Current Telegram-coupled pieces that should be wrapped, not replaced
- `telegram_bot/telegram_chat_flow.py`
- `telegram_bot/telegram_message_handlers.py`
- `telegram_bot/telegram_session_state.py`

## Best additive refactor path
Short version:
1. create a channel-agnostic runtime layer
2. keep Telegram calling it
3. let the new app call it too

That runtime layer should eventually own:
- session creation/loading
- chat message append
- run_tool_loop orchestration
- verbose tool event streaming
- scheduled job execution dispatch

## Flag strategy
Use config/env flags, additive only.

Recommended flags:
- `channels.telegram.enabled=true`
- `channels.app.enabled=false`
- `APP_BACKEND_HOST=0.0.0.0`
- `APP_BACKEND_PORT=8787`
- `APP_AUTH_SECRET=...`
- `EXPO_PROJECT_ID=...`

## EAS / Expo setup requirements
The mobile client will need:
- `package.json`
- `app.json` or `app.config.ts`
- `eas.json`
- Expo Router setup
- bundle identifier / android package name
- EAS project initialization
- push notification project id if notifications are enabled

## Build/deploy notes
For EAS builds, you will need later:
- Expo account logged in locally
- `eas.json` profiles (`development`, `preview`, `production`)
- Android package name
- iOS bundle identifier
- app icon/splash assets
- EAS credentials setup

## Networking recommendation
For early development:
- mobile app talks to local FastAPI server over LAN or tunnel

For production:
- deploy the FastAPI backend behind HTTPS
- app uses secure token auth
- WebSocket endpoint uses the same auth token

## Recommended auth for v1
Use token-based auth first.
Avoid full social auth initially.

Suggested v1 auth options:
- one trusted user account
- long-lived app token generated from backend env/config
- optional device registration endpoint

## Push notifications
Do not make push notifications a blocker for v1.
Ship without them first if needed.
Then add:
- Expo push token registration endpoint
- backend sender utility
- scheduler-triggered notifications for completed jobs/messages

## Main technical work required
1. **Channel abstraction**
   - add channel-aware config
   - add app-specific runtime path
2. **Backend service**
   - FastAPI app with REST + WebSocket
3. **Session/runtime adapter**
   - bridge mobile requests into the existing agent runtime
4. **Expo app**
   - chat UI, auth, session list, settings
5. **Streaming/progress model**
   - forward tool logs/status to the app in real time
6. **Optional push layer**
   - Expo notifications after core chat works

## What should not be changed right now
- Telegram commands
- Telegram handlers
- Telegram bot startup path
- current cron-to-Telegram delivery behavior

Those can remain exactly as-is while the app path is built in parallel.

## Suggested implementation phases
### Phase 1
- create `mobile_app/`
- add architecture docs
- add app channel config defaults
- add backend skeleton
- add Expo client skeleton

### Phase 2
- make a minimal mobile chat round-trip work
- app sends message
- backend runs agent
- app receives reply

### Phase 3
- stream tool events
- show sessions/history/jobs
- add auth hardening

### Phase 4
- add push notifications
- EAS production builds
- app store packaging if wanted

## Recommendation summary
The cleanest path is:
- keep Telegram as channel A
- add a new app channel B
- create a new `mobile_app/` root
- use FastAPI + WebSocket backend
- use Expo + EAS client
- extract shared runtime gradually behind a channel flag
