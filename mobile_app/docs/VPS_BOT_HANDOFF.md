# VPS Bot Handoff

This file defines the backend work that belongs on the VPS side.

## Ownership Boundary
- The VPS bot owns everything under `mobile_app/backend`.
- The phone app owns everything under `mobile_app/client`.
- Shared runtime changes are allowed only when they are needed to support the app contract and do not break Telegram.

## Product Direction
- The mobile app is a direct client for the VPS-hosted EmploAI backend.
- Telegram remains available, but it is not the required gateway for mobile use.
- The app should work from any phone that can reach the VPS over HTTPS and WebSocket.

## What The VPS Bot Must Build Or Preserve
- Keep the app backend launchable from the existing runtime when `channels.app.enabled` is true.
- Preserve the Telegram path while making the app a first-class client.
- Keep auth, chat execution, voice STT, screenshots, and live screen feed on the VPS.
- Do not require text-to-speech for v1 acceptance. TTS is optional.

## Required REST Contract

### Health and device state
- `GET /api/app/health`
  - Returns at least:
    - `ok: boolean`
    - `steering_beta_enabled: boolean`
- `GET /api/app/me`
  - Bearer auth required
  - Returns at least:
    - `user_id`
    - `current_session_id`
    - `current_model`
    - `current_variant`
    - `device_id`
    - `device_name`
    - `device_platform`

### Pairing and auth
- `POST /api/app/pair/start`
  - Used by trusted devices or server-side tooling to mint short-lived pairing tokens
  - Must be protected by either:
    - an existing trusted device token, or
    - `X-App-Pair-Secret` backed by `EMPLO_APP_PAIRING_SECRET`
- `POST /api/app/pair/complete`
  - Request body:
    - `pairing_token`
    - `device_name`
    - `device_platform`
  - Response body:
    - `access_token`
    - `device_id`
    - optional metadata about the trusted device
- `GET /api/app/devices`
  - Bearer auth required
  - Lists trusted devices
- `POST /api/app/devices/{device_id}/revoke`
  - Bearer auth required

### Sessions and jobs
- `GET /api/app/sessions`
- `POST /api/app/sessions`
- `GET /api/app/sessions/{session_id}`
- `GET /api/app/jobs`
- `POST /api/app/jobs`
- `GET /api/app/jobs/{job_id}`
- `POST /api/app/jobs/{job_id}/run`
- `POST /api/app/jobs/{job_id}/enable`
- `POST /api/app/jobs/{job_id}/disable`
- `DELETE /api/app/jobs/{job_id}`

### Files and capture
- `POST /api/app/upload`
  - Multipart upload
  - Bearer auth required
  - Accepts optional `session_id`
- `GET /api/app/screenshot/current`
  - Bearer auth required
  - Returns:
    - `image_base64`
    - `mime_type`
    - `width`
    - `height`
    - `backend`

## Required Realtime Contract

### Chat
- `WS /ws/app/chat?token=...&session_id=...`
- Incoming message shape:
  - `text`
  - optional `session_id`
  - optional `interrupt_policy`

### Voice
- `WS /ws/app/voice?token=...&session_id=...`
- Incoming client events:
  - `voice_start`
  - `voice_chunk`
    - `sequence`
    - `mime_type`
    - `audio_base64`
    - optional `session_id`
  - `voice_commit`
    - optional `session_id`
    - optional `interrupt_policy`
  - `voice_cancel`

### Screen feed
- `WS /ws/app/screen?token=...&fps=...&max_width=...&quality=...`

## Required Server Event Types
- `assistant_delta`
- `assistant_final`
- `tool_event`
- `status`
- `warning`
- `error`
- `voice_partial`
- `voice_final`
- `voice_state`
- `screen_frame`
- `screen_state`

## Event Payload Expectations

### Chat
- `assistant_delta.payload.delta`
- `assistant_final.payload.text`
- `tool_event.payload`
- `status.payload.message`
- `warning.payload.message`
- `error.payload.message`

### Voice
- `voice_partial.payload.text`
- `voice_final.payload.text`
- `voice_state.payload.state`

### Screen
- `screen_frame.payload.image_base64`
- `screen_frame.payload.mime_type`
- `screen_frame.payload.width`
- `screen_frame.payload.height`
- `screen_frame.payload.backend`
- `screen_state.payload.state`

## Steering Beta
- Keep beta steering behind `channels.app.steering_beta` and `EMPLO_APP_STEERING_BETA_ENABLED`.
- Supported app policies:
  - `none`
  - `steer_now`
  - `after_tool`
- Standard behavior must remain unchanged when the beta flag is off.

## Voice Expectations
- Use chunked low-latency speech-to-text on the VPS.
- Emit partial transcript updates while the user is speaking.
- Finalize promptly when the user presses stop or the server detects an end boundary.
- Do not require record-full-clip then upload for primary use.
- TTS is not required for the app handoff and should not block shipment.

## Deployment Requirements
- The backend must run on the VPS behind TLS.
- REST must be reachable from a phone over `https://`.
- WebSocket must be reachable from a phone over `wss://`.
- Reverse proxy must pass WebSocket upgrades correctly.
- The app backend should bind according to `config.json`:
  - `channels.app.enabled`
  - `channels.app.host`
  - `channels.app.port`

## Environment Requirements
- `OPENAI_API_KEY`
- `EMPLO_APP_PAIRING_SECRET`
- Optional voice tuning envs if STT needs them
- Any existing model/provider envs already required by the main agent runtime

## Non-Negotiable Compatibility Rule
- Do not change request or event shapes without updating the phone app.
- If the server contract must change, update this file first and coordinate the client change in the same cycle.

## Acceptance Checklist
- A physical Android phone can reach the VPS URL over HTTPS.
- The phone can complete pairing with a short-lived token.
- The phone can open chat and receive streamed assistant text.
- The phone can speak, see partial transcript updates, and send the finalized transcript into the agent.
- The phone can refresh a screenshot and open the live screen feed.
- The phone can upload attachments.
- Sessions and jobs endpoints work with the saved bearer token.
