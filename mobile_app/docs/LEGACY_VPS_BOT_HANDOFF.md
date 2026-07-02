# Legacy VPS Bot Handoff

## Status
This file is now an **archive marker**, not the source of truth for the mobile product contract.

It previously described an older rollout model where:
- the phone targeted the app backend directly
- local trusted-device pairing was the main onboarding path
- the VPS owned more of the voice/screen path than the current product direction

That is no longer the default architecture we should implement against.

## Use these docs instead
- [../../README.md](../../README.md) for the current local-first desktop path
- [../../docs/repository_map.md](../../docs/repository_map.md) for current folder guidance
- [LEGACY_REMOTE_ARCHITECTURE.md](LEGACY_REMOTE_ARCHITECTURE.md) for the archived mobile remote design

## Practical guidance
If you intentionally reconnect the mobile/VPS product path:
1. Treat the **VPS control plane** as the authority for auth, pairing, shared state, and realtime fan-out.
2. Treat the **desktop** as the authority for actual execution on the paired machine.
3. Keep the **mobile app text-first** for v1.
4. Do not revive the old "manual backend URL + trusted-device pairing" flow as the primary architecture.

## Why this file still exists
It remains here only so future developers who discover the old filename are redirected quickly instead of following stale rollout instructions.
