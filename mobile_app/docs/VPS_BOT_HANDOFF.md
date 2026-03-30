# VPS Bot Handoff

This file is the working brief for the bot that owns the VPS side of the mobile app rollout.

## Goal
- Make the VPS fully ready to serve the EmploAI mobile app as a real client.
- Keep Telegram working.
- Do not make the mobile app depend on Telegram as a gateway.
- Do not block on text-to-speech. TTS is optional for v1.

## Ownership Boundary
- The VPS bot owns everything under `mobile_app/backend`.
- The VPS bot may update shared runtime code only when needed to support the app contract without breaking Telegram.
- The phone app owns everything under `mobile_app/client`.
- Do not change the mobile app UI/build flow unless a contract break makes coordination unavoidable.

## Build Ownership
- The mobile app binary should be built from the local machine, not on the VPS.
- Preferred flow: trigger `eas build` from the local machine in `mobile_app/client`.
- The VPS exists to host the backend API, realtime websockets, auth, voice processing, and screen capture.
- The VPS bot should not spend time trying to package the Expo app for installation.

## What The VPS Bot Must Finish

### 1. Backend runtime
- Ensure the app backend starts when `channels.app.enabled` is true.
- Keep embedded startup compatible with the existing agent runtime.
- Do not regress Telegram behavior.

### 2. Deployment and reachability
- Make the app backend reachable from a physical phone over `https://`.
- Make chat, voice, and screen websockets reachable over `wss://`.
- Configure the reverse proxy so websocket upgrades work correctly.
- Ensure the VPS process survives restart and comes back cleanly.
- Provide the final public base URL the app should use.

### 3. Auth and pairing
- Keep persistent trusted-device pairing.
- Keep `POST /api/app/pair/start` protected by either:
  - a trusted device token, or
  - `X-App-Pair-Secret` backed by `EMPLO_APP_PAIRING_SECRET`
- Keep `POST /api/app/pair/complete` working for first-device bootstrap.
- Make sure pairing survives VPS restarts.
- Provide one reliable first-device bootstrap path:
  - either a documented server-side command to mint a pairing token, or
  - a protected API flow that can be triggered manually

### 4. App-facing product surface
- Chat must stream assistant text.
- Voice must support chunked low-latency STT with partial transcript updates.
- Screen capture must support both one-shot screenshot fetch and live frame feed.
- Uploads must work with bearer auth and optional session binding.
- Sessions and jobs endpoints must work from the app with the saved device token.

### 5. Validation
- Smoke test every required endpoint and websocket path from the VPS side.
- Validate that the server contract still matches this document.
- If anything in the contract changes, update this file before shipping the change.

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
    - `expires_in_seconds`
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
- TTS is not required for this handoff and should not block shipment.

## Required VPS Configuration
- `channels.app.enabled` must be set to `true` in `config.json` on the VPS when testing the app.
- The backend should bind according to:
  - `channels.app.host`
  - `channels.app.port`
- Required env:
  - `OPENAI_API_KEY`
  - `EMPLO_APP_PAIRING_SECRET`
- Optional env:
  - any voice/STT tuning envs already supported by the backend

## First Device Pairing Runbook
The VPS bot should be able to take the user from "app installed" to "phone paired" without making the user guess the server steps.

### Step 1. Enable and restart the app backend
- Set `channels.app.enabled` to `true` on the VPS.
- Restart the main agent process so the embedded app backend starts.
- Confirm the backend is listening on the configured host/port.

### Step 2. Verify the public app URL
- Confirm the final public base URL that the phone should use.
- Verify:
  - `GET https://YOUR_HOST/api/app/health`
- The health response should show at least:
  - `ok: true`
  - `enabled: true`
  - `pairing_bootstrap_enabled: true`

### Step 3. Mint one first-device pairing token
- Use `POST /api/app/pair/start` with the header:
  - `X-App-Pair-Secret: <EMPLO_APP_PAIRING_SECRET>`
- Minimal JSON body:
  - `{"device_name":"My Phone"}`
- The VPS bot should return the resulting `pairing_token` to the user.
- Pairing tokens are short-lived, so mint the token close to when the user will paste it into the app.

### Step 4. Tell the user exactly what to enter in the app
- `Backend URL`: the public HTTPS base URL
- `Pairing token`: the minted short-lived token
- `Device name`: any label the user wants

### Step 5. Post-pair verification
- After the user completes pairing in the app, the VPS bot should be ready to verify:
  - `GET /api/app/me`
  - `GET /api/app/sessions`
  - websocket reachability for:
    - `/ws/app/chat`
    - `/ws/app/voice`
    - `/ws/app/screen`

### PowerShell example
```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://YOUR_HOST/api/app/pair/start" `
  -Headers @{ "X-App-Pair-Secret" = "YOUR_PAIRING_SECRET" } `
  -ContentType "application/json" `
  -Body '{"device_name":"My Phone"}'
```

### curl example
```bash
curl -X POST "https://YOUR_HOST/api/app/pair/start" \
  -H "Content-Type: application/json" \
  -H "X-App-Pair-Secret: YOUR_PAIRING_SECRET" \
  -d '{"device_name":"My Phone"}'
```

## What The VPS Bot Should Hand Back To The User
When the VPS bot is done with pairing setup, it should reply with only the useful facts:
- the final public backend URL
- whether `/api/app/health` is healthy
- one fresh `pairing_token`
- whether websocket routes are confirmed reachable
- any blocker that still prevents the phone from pairing

## Deployment Deliverables From The VPS Bot
- The final public app backend URL.
- Confirmation that HTTPS works.
- Confirmation that WSS works for:
  - `/ws/app/chat`
  - `/ws/app/voice`
  - `/ws/app/screen`
- Confirmation that a first-device pairing token can be created.
- Confirmation that the app backend survives restart.
- A short smoke-test report covering:
  - health
  - pairing
  - chat
  - voice partials
  - screenshot
  - live screen feed
  - sessions
  - jobs

## Non-Negotiable Compatibility Rule
- Do not change request or event shapes without updating the phone app.
- If the server contract must change, update this file first and coordinate the client change in the same cycle.

## Definition Of Done
- A physical Android phone can reach the VPS URL over HTTPS.
- The phone can complete pairing with a short-lived token.
- The phone can open chat and receive streamed assistant text.
- The phone can speak, see partial transcript updates, and send the finalized transcript into the agent.
- The phone can refresh a screenshot and open the live screen feed.
- The phone can upload attachments.
- Sessions and jobs endpoints work with the saved bearer token.
- Telegram still works after the app channel is enabled.
