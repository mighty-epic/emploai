# Legacy Kraitos App Runtime Notes

Status: archived. These notes describe the preserved mobile/VPS runtime path,
not the current standalone desktop startup path. Current desktop startup is
documented in [../../README.md](../../README.md).

## Archived runtime decisions
- Android package id: `app.kraitos.mobile`.
- App display name: `Kraitos`.
- Release API base URL: `https://api.kraitos.app`.
- Mobile v1 is text-first in `remote_cloud` mode.
- Mobile voice capture is intentionally disabled in remote-cloud mode for v1.
- The desktop app owns actual execution on the user's machine.
- The public control plane owns account auth, pairing, shared mirrored state,
  fleet metadata, and realtime fan-out.
- The desktop connects outward to the control plane through the remote desktop
  bridge instead of requiring the phone to reach a LAN-local backend.

## File/media path
The mobile client supports three intake paths:
- camera capture
- gallery/media selection
- document picking

The backend normalizes uploads into chat/session artifacts so mobile, desktop,
and Telegram-era surfaces can represent the same underlying content.

## Voice path
Current v1 behavior:
- Mobile remote-cloud voice is disabled by design.
- Desktop voice uses the Electron renderer microphone path:
  `renderer getUserMedia -> /ws/app/voice -> local backend voice runtime`.
- Managed voice input/output packs are installed and selected from the desktop
  app, not bundled into the mobile APK.

Future mobile voice work should preserve the same chat/session contract, but it
is not part of the current remote-cloud v1 behavior.

## Runtime/deployment direction
Archived public mobile deployment:
- FastAPI control plane runs on the VPS behind HTTPS/WSS.
- Desktop signs into the same account and keeps a persistent outbound websocket.
- Mobile signs into the account, completes pairing, and sends actions through
  the control plane to the paired desktop.

Current local/legacy compatibility:
- Local app APIs, Telegram runtime paths, and direct backend modes still exist
  for development and backward compatibility.
- They are not the primary mobile product architecture.
