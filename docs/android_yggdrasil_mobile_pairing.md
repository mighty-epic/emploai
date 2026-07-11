# Android Yggdrasil Mobile Pairing Idea

This is a future design note. The mobile app is currently disconnected from the main product path, but Android can likely support a no-VPS pairing model by bundling a Yggdrasil client inside the app.

## Goal

Let a phone reach the user's desktop from another network without an EmploAI domain, VPS, login system, or developer-owned relay.

## Proposed Shape

- Desktop app ships or downloads a pinned Yggdrasil binary.
- Android app bundles a Yggdrasil runtime through a native module or foreground VPN service.
- First pairing happens locally with a QR code.
- The QR code contains:
  - desktop Yggdrasil public address
  - desktop app pairing public key
  - desktop local API identity
  - optional known Yggdrasil peers
  - one-time pairing token
- After pairing, Android stores the desktop device identity locally.
- Desktop stores the phone identity locally.
- Mobile connects to the desktop over its Yggdrasil IPv6 address.
- App-level auth still uses a local pairing token/session key; Yggdrasil is only transport.

## Android Requirements

- Foreground VPN/service integration so Android keeps the Yggdrasil tunnel alive.
- Clear battery/network status in the app.
- User-controlled disconnect/delete-device controls.
- No cloud fallback by default.
- A local-only pairing reset path on both devices.

## Tradeoffs

- Works without EmploAI infrastructure.
- Does not require user-owned domains.
- NAT traversal is handled by the Yggdrasil mesh when enough public peers are reachable.
- Connection quality depends on public peers or user-provided peers.
- iOS is harder because long-running VPN/background service behavior is more constrained.

## Open Implementation Questions

- Whether to embed an existing Android Yggdrasil client/library or run a packaged binary.
- How to expose Yggdrasil status and logs safely in React Native.
- How to rotate app-level pairing credentials without breaking the device link.
- Whether bundled peer lists are acceptable, or whether users should provide peers manually.
- How to keep the desktop local API bound only to trusted Yggdrasil peers and localhost.
