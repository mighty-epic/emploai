# Legacy Mobile Remote Architecture

Status: preserved design, not the current product path. EmploAI now starts as a
local-first desktop app with no account, VPS, cloud backend, or mobile pairing
enabled by default. Use [../../README.md](../../README.md) and
[../../docs/repository_map.md](../../docs/repository_map.md) for current
startup and folder guidance.

## Archived remote product direction
This file records the earlier plan where the mobile app was a **public remote
companion** to the desktop app, not a same-LAN client that talks directly to a
user-entered desktop backend URL.

The product target is:
- desktop and mobile authenticate against a **public HTTPS/WSS control plane**
- the control plane owns **identity, pairing, shared sync state, and realtime fan-out**
- the paired desktop owns **execution on that machine**: tools, files, screen/vision, cron, and agent runs
- mobile and desktop stay in **live sync** for folders/projects, chats, timeline/tool events, task state, running state, and current-session selection
- mobile v1 is **text-first** and intentionally excludes mobile voice paths

## Roles

### VPS control plane
Owns:
- user accounts and login
- desktop/mobile device registration
- short-lived pairing tokens
- paired-desktop tracking
- mirrored shared state for mobile/desktop sync
- realtime websocket fan-out

### Desktop
Owns:
- agent execution
- file system access
- browser and desktop control
- `describe_screen` and `ocr_screen`
- cron execution for that machine
- publishing snapshots and realtime sync events to the VPS

### Mobile
Owns:
- account sign-in
- pairing to one of the user's desktops
- realtime display of the shared state
- sending turns and control actions through the control plane

## Realtime model
The control plane is the shared state authority for anything both clients should currently display:
- current session id
- session summaries
- mirrored transcript/timeline state
- task-board and run presence
- folder/project metadata
- desktop online/offline state

The desktop remains the authority for the actual execution results. The control plane mirrors those results so mobile and desktop stay aligned after reconnects and network changes.

## Transport
- HTTPS REST for auth, pairing, and shared-state fetches
- WSS for desktop and mobile realtime channels
- desktop keeps a persistent outbound control-plane connection
- mobile subscribes to the same per-user realtime stream

Related legacy deployment notes live in:
- [LEGACY_REMOTE_CONTROL_PLANE.md](LEGACY_REMOTE_CONTROL_PLANE.md)
- [../../deploy/legacy_vps/linux/REMOTE_CONTROL_README.md](../../deploy/legacy_vps/linux/REMOTE_CONTROL_README.md)

## Desktop parity requirement
The mobile app is not meant to be a reduced Telegram-like shell. It should be a responsive adaptation of the desktop experience with the same behavior for:
- folder/project navigation
- chat/session switching
- transcript and verbose tool timeline visibility
- task-board visibility
- running/stop state
- scheduler visibility and management

## Compatibility and legacy notes
The older ideas below are no longer the primary architecture and should only be treated as compatibility or development paths:
- manually entering a backend URL into the phone app
- local trusted-device pairing as the main product onboarding
- using Telegram mirroring as the behavioral benchmark for mobile parity

Legacy docs that discuss those paths should be treated as history, not implementation guidance.

## Archived implementation status
The disabled remote/mobile path still has code in the repo:
- remote control-plane store and APIs
- mobile cloud sign-in and pairing flow
- desktop outbound bridge for the control plane
- Ubuntu 22 VPS deployment assets for the control plane

Still intentionally lighter than the final product UX:
- desktop renderer polish for account/pairing setup
- production hosting and account hardening beyond the repo-level scaffolding
