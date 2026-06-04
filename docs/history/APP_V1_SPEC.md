# EmploAI App v1 Spec

## Goal
Deliver a phone app for EmploAI that connects to the VPS-hosted agent, preserves the working Telegram channel, and adds a richer mobile-native interface.

## v1 scope
### Required
- live chat with streamed assistant output
- streamed tool logs/status feed
- session list and session history
- jobs/scheduler list and management view
- file upload
- voice input
- secure QR-based pairing
- remote connectivity to VPS-hosted backend

### Deferred but planned
- push notifications
- iOS-first polish
- app-store packaging details

## Channel model
- `telegram` remains the current working channel
- `app` is a new additive delivery channel
- both channels should hit the same underlying agent/session runtime where possible

## Shared-session behavior
Sessions are shared across Telegram and app.

### Storage recommendation
Persist shared messages with metadata:
- `channel`
- `source_format`
- `attachments`
- `display_hints`

### Rendering rule
Storage stays normalized; each client renders the same underlying history differently.

## Primary app screens
1. Pair/Login
2. Chat
3. Sessions
4. Jobs
5. Settings

## Chat screen requirements
- streaming assistant text
- visible tool execution timeline
- file picker/upload
- live voice capture with interim transcript display while speaking
- transcript finalization on pause and/or explicit send
- reconnect handling for long-running tasks

## Sessions screen requirements
- list shared sessions from the existing session store
- indicate origin when useful: Telegram/app
- allow opening any existing shared session
- allow creating a new session

## Jobs screen requirements
- list scheduled jobs
- show enabled/disabled status
- inspect one job
- enable/disable/delete job
- run job now
- create job later in v1.1 if needed, but API should be ready for it

## Settings requirements
- backend URL
- device status
- model/mode summary
- future push-notification registration area
- origin-label preferences for shared Telegram/app history rendering

## Backend API shape
### REST
- `POST /api/app/pair/start`
- `POST /api/app/pair/complete`
- `GET /api/app/me`
- `GET /api/app/sessions`
- `POST /api/app/sessions`
- `GET /api/app/sessions/{session_id}`
- `GET /api/app/jobs`
- `GET /api/app/jobs/{job_id}`
- `POST /api/app/jobs/{job_id}/run`
- `POST /api/app/jobs/{job_id}/enable`
- `POST /api/app/jobs/{job_id}/disable`
- `DELETE /api/app/jobs/{job_id}`
- `POST /api/app/upload`

### Realtime
- `WS /ws/app/chat?session_id=...`
- `WS /ws/app/voice?session_id=...`

## Event model
The app needs structured event streaming, not just final text.

Recommended event types:
- `session_snapshot`
- `assistant_delta`
- `assistant_final`
- `tool_started`
- `tool_finished`
- `tool_error`
- `job_update`
- `voice_partial`
- `voice_final`
- `voice_state`
- `warning`
- `error`

## Deployment requirements
- backend runs on VPS behind HTTPS
- reverse proxy for REST + WebSocket
- token auth for REST and WS
- CORS restricted to app origins/dev environments
- initial runtime should be launchable from `telegram_agent.py` when the app channel flag is enabled
- prefer lightweight always-on embedded startup over first-version lazy demand detection

## EAS/Expo requirements
- Expo Router
- TypeScript
- Android-first configuration
- EAS build profiles: development, preview, production
- package/app ids prepared for future store release

## Open implementation concern
The current runtime is Telegram-shaped in places. Before full app wiring, create a bridge that:
- loads the shared session
- appends a message with channel metadata
- emits structured progress callbacks
- writes the final assistant response back into the shared session

## Voice architecture direction
The voice path should not be designed as "record full clip -> upload -> wait -> transcribe" for primary chat use.

Recommended v1.0 direction:
- app streams microphone audio in small chunks over WebSocket
- backend runs streaming STT and emits interim transcript updates immediately
- app shows live partial transcript as the user speaks
- on pause or explicit send, backend finalizes the utterance
- finalized transcript is then sent into the same chat/session pipeline as text input

This preserves the low-latency feel the user wants while keeping the actual STT engine on the VPS.

## Future conversational control
Not required for first scaffold, but architecture should leave room for:
- queued outgoing user turns
- interruption while the assistant is responding
- cancellation/replacement of active response generation
- continuation after interruption using the newly finalized user turn
