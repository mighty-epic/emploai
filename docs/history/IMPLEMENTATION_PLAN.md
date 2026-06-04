# EmploAI App Channel Implementation Plan

## Objective
Add a new app delivery channel while preserving the current Telegram system unchanged.

## Proposed folder layout
```text
mobile_app/
  docs/
    ARCHITECTURE.md
    IMPLEMENTATION_PLAN.md
    OPEN_QUESTIONS.md
  backend/
    __init__.py
    README.md
  client/
    README.md
```

## Concrete plan

### 1. Config and flags
Add additive config only:
- `channels.telegram.enabled`
- `channels.app.enabled`
- `channels.app.host`
- `channels.app.port`
- `channels.app.auth_mode`
- `channels.app.push_notifications`

This should be implemented in shared config, not in Telegram-only code.

### 2. App backend package
Create a new package separate from Telegram code.

Responsibilities:
- authenticate app client
- create/load sessions
- accept user messages
- stream agent output and tool events
- expose jobs/session/settings endpoints

### 3. Channel-agnostic runtime bridge
The current chat logic is Telegram-centric. To support the app cleanly, add a bridge layer that takes:
- channel type
- user identity
- message text
- callback hooks for status/progress/output

The bridge should call the existing tool-loop logic under the hood.

### 4. Expo client
Initial screens:
- Pair/Login
- Chat
- Sessions
- Jobs
- Settings

### 5. EAS setup
Prepare for:
- `eas.json`
- `app.config.ts`
- app ids
- build profiles
- Expo project ID

## Suggested backend API v1
### REST
- `POST /api/app/auth/pair`
- `GET /api/app/me`
- `GET /api/app/sessions`
- `POST /api/app/sessions`
- `GET /api/app/jobs`

### WebSocket
- `WS /ws/chat?session_id=...`

Message envelope example:
```json
{
  "type": "user_message",
  "session_id": "abc123",
  "text": "Summarize today’s markets"
}
```

Server event example:
```json
{
  "type": "tool_event",
  "name": "web_search",
  "status": "running",
  "detail": "Searching for market news"
}
```

## Recommended technical decisions
- Backend language: Python, same repo
- Backend framework: FastAPI
- Real-time transport: WebSocket
- Mobile client: Expo + React Native + TypeScript
- Routing: Expo Router
- State: lightweight local state first
- Auth: token/device pairing first

## Lowest-risk path
1. create docs + folder structure
2. add flags
3. scaffold backend/client
4. wire one happy-path chat flow
5. iterate

## Existing code most likely to be reused
- `cli/agent_tools/loop.py`
- `telegram_bot/telegram_unified_agent.py`
- `shared/live_config.py`
- `shared/session_types.py`
- reusable pieces from `telegram_bot/telegram_session_state.py`

## Existing code that should remain untouched for now
- Telegram command registration
- Telegram message handlers
- current Telegram startup path

## Verification target for phase 1
Phase 1 is complete when:
- `mobile_app/` exists
- architecture docs exist
- additive app-channel config exists
- no Telegram behavior is removed or disabled
