# Remote Control Plane

## Purpose
This document describes the public mobile architecture for EmploAI.

The mobile app is a remote companion to the desktop app:
- the **VPS control plane** is authoritative for identity, pairing, shared sync state, and realtime fan-out
- the **desktop** is authoritative for execution on that computer

## Roles

### VPS control plane
Owns:
- account registration and login
- desktop/mobile device records
- short-lived pairing tokens
- shared session and project metadata
- current-session tracking
- mirrored timeline/tool/run/task-board state
- desktop presence and heartbeat status

### Desktop
Owns:
- local tool execution
- file reads/writes
- browser and desktop control
- `describe_screen` / `ocr_screen`
- cron execution for that machine
- agent turns for that paired computer

The desktop connects outward to the VPS using a persistent websocket and publishes shared state snapshots plus realtime sync events.

### Mobile
Owns:
- account login
- pairing to one of the user's desktops
- realtime display of shared state
- sending turns to the paired desktop through the control plane

Mobile v1 is text-first and does not expose mobile voice capture.

## Pairing flow
1. Desktop signs into the control plane as `actor_kind=desktop`.
2. Mobile signs into the same account as `actor_kind=mobile`.
3. Desktop requests a short-lived pairing token.
4. Mobile completes pairing with that token.
5. The control plane records the `paired_desktop_id` for that mobile device.

## Realtime channels

### Desktop websocket
`/ws/remote/desktop`

Desktop sends:
- `heartbeat`
- `state_snapshot`
- `sync_event`
- `status`

Desktop receives:
- `create_session`
- `activate_session`
- `chat_send`
- `pause_run`
- `stop_run`
- `restart_runtime`

### Mobile websocket
`/ws/remote/mobile`

Mobile receives shared realtime events such as:
- session sync
- user messages
- assistant deltas/finals
- tool/timeline events
- task-board events
- status/warning/error updates

## Shared-state model
The control plane mirrors the following per user:
- desktops and desktop connection state
- current paired desktop
- current session id
- session summaries
- current session detail snapshot
- jobs/task summaries
- project groups derived from workspaces
- sync version for reconnect polling

Desktop remains the source of truth for execution results, but the control plane becomes the source of truth for what mobile and desktop should both currently display.

## Environment variables for desktop bridge
The desktop-side remote bridge currently uses:
- `EMPLOAI_REMOTE_CONTROL_BASE_URL`
- `EMPLOAI_REMOTE_CONTROL_EMAIL`
- `EMPLOAI_REMOTE_CONTROL_PASSWORD`
- `EMPLOAI_REMOTE_DESKTOP_NAME`
- `EMPLOAI_REMOTE_DESKTOP_KEY`

The bridge entrypoint is:
- `python -m mobile_app.backend.desktop_runtime remote-control`

## Current limitations
- The backend and mobile client support the public remote control plane.
- Desktop-side renderer UX for account login and QR/token creation is still thinner than the mobile-side onboarding path.
- Mobile voice remains intentionally disabled in remote-cloud mode for v1.
