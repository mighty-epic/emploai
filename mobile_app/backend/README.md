# EmploAI Mobile App Backend

This backend now serves two overlapping roles:
- the **local desktop app backend** that the Windows desktop shell talks to
- the **remote control-plane backend** that mobile and desktop can both reach through a VPS

## Current responsibilities

- `/api/app/health`
- legacy local pairing compatibility endpoints
- remote account auth and device pairing endpoints
- session list/create/detail endpoints
- job list/detail/action endpoints
- `WS /ws/app/chat`
- `WS /ws/app/voice`
- `WS /ws/remote/mobile`
- `WS /ws/remote/desktop`
- desktop runtime bootstrap and attach flow
- remote desktop outbound bridge support
- local voice runtime status reporting
- optional voice pack installation/removal for desktop releases

## Voice path

The supported desktop voice flow is:

```text
renderer microphone capture -> /ws/app/voice -> VoiceDraftState -> shared session/chat flow
```

English and Hebrew both use that same path. The active local engine is selected from runtime config:

- `english_local`
- `hebrew_local`
- `none`

## Voice packs

Voice packs are managed by:

- `mobile_app/backend/voice_pack_manager.py`

The desktop release can:
- install/remove packs from the desktop setup panel
- keep voice entirely optional on a fresh install

Pack ids:

- `english_local`
- `hebrew_local`

## Hebrew runtime

The approved local Hebrew runtime is the fine-tuned Whisper small path implemented in:

- `mobile_app/backend/hebrew_transformers_runtime.py`

This replaced the older heavier Hebrew route for desktop local use. The runtime is designed to match the successful terminal validation path documented in:

- `docs/hebrew_live_voice_path.md`

## Release integration

Desktop release/backend glue lives in:

- `deploy/windows/release_backend.py`
- `deploy/windows/release_runtime.py`

Those modules handle:

- runtime home/bootstrap
- setup state
- voice pack preferences
- install/remove actions for managed voice packs

## Current architecture note

The primary mobile direction is the **public remote control plane**, not “phone talks directly to a manually entered backend URL on the same network.”

The current target architecture is:
- VPS control plane for auth, pairing, shared sync state, and realtime fan-out
- paired desktop remains the execution machine

Anything still labeled local pairing should be treated as compatibility support for desktop/mobile development, not the product-default onboarding path.

See:
- [REMOTE_CONTROL_PLANE.md](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/mobile_app/docs/REMOTE_CONTROL_PLANE.md)
- [REMOTE_CONTROL_README.md](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/deploy/vps/linux/REMOTE_CONTROL_README.md)
