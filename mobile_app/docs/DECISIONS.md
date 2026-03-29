# EmploAI App Decisions

## Confirmed product decisions
- Scope: personal app; each person would connect only to their own EmploAI instance.
- Platform priority: Android first.
- Connectivity target: remote access early, connecting to EmploAI on the VPS.
- Push notifications: not required for v1, but architecture must leave room for them.
- Must-have v1 features:
  - live chat
  - streamed tool logs
  - jobs/scheduler interface
  - file upload
  - voice input
  - session history
- Session relationship: app should share the same underlying sessions/history as Telegram, while handling channel-format mismatch cleanly.
- Pairing/auth UX: QR code preferred, but it must still be secure.
- App naming direction: "EmploAI App" or similar descriptive name.

## Architectural implications
- The app backend should be treated as a second delivery channel, not a second agent core.
- Shared sessions mean the backend must add channel metadata rather than splitting history stores.
- Telegram and app rendering should diverge at presentation time, not storage time.
- Remote access early means HTTPS, token-based auth, secure WebSocket auth, and VPS-friendly deployment need to be first-class from the start.
- QR pairing should issue a short-lived signed pairing token, not embed a long-lived secret directly.
- Voice input must feel live and low-latency, not like delayed file upload followed by blocking transcription.
- The voice path should support partial/interim transcription while the user is still speaking, then finalize and send on pause or explicit send.
- Future conversational interruption and continuation should be planned into the event model even if not fully implemented in v1.

## Recommended naming/package defaults
- App display name: `EmploAI App`
- Android package: `com.emploai.app`
- Expo/EAS slug suggestion: `emploai-app`

## Session compatibility model
Use one shared session store per user, but store message metadata with fields like:
- `channel`: `telegram` or `app`
- `source_format`: `telegram_text`, `app_text`, `app_voice_transcript`, `app_file_upload`
- `display_hints`: optional per-channel rendering hints

This allows:
- Telegram-created sessions to appear in the app
- app-created sessions to appear in Telegram
- channel-specific UI treatment without forking the underlying session model

## Telegram/app mismatch handling
When opening an app-created session in Telegram:
- show the shared text history normally
- represent non-Telegram-native items as summarized placeholders where needed
  - voice input => transcript plus marker that it came from voice
  - file uploads => file summary/attachment marker
  - verbose tool logs => summarized status messages rather than mobile UI cards

When opening a Telegram-created session in the app:
- render normal text history directly
- show Telegram-origin messages with channel metadata when helpful, but do not alter the underlying session

## Security direction for QR pairing
Recommended pairing flow:
1. backend generates a short-lived pairing session and nonce
2. QR encodes a one-time HTTPS URL or signed pairing token
3. mobile app scans and exchanges it for a device-bound auth token
4. backend stores trusted device metadata
5. long-lived token is stored securely on device

Minimum security rules:
- pairing tokens expire quickly
- pairing tokens are single-use
- device token is revocable
- WebSocket auth uses the same device token
- no permanent root secret inside the QR code
