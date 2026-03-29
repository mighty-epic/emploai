# EmploAI App Runtime Notes

## Newly confirmed decisions
- Android package id is confirmed as `com.emploai.app`.
- Voice input is required in v1.
- For voice transcription, optimize for responsiveness, but prefer VPS-side handling in v1 if it is significantly easier and more reliable to ship.
- File intake in v1 should support:
  - camera capture
  - gallery/media selection
  - document picking
- Telegram should visibly label app-originated sessions/content when shown in Telegram UX.
- Operational preference: running `telegram_agent.py` should remain the main entrypoint for the whole EmploAI runtime.

## Recommended implementation decisions
### Voice path
Updated requirement:
- voice input must feel immediate and live
- user should see transcription appear while speaking
- final send should happen on pause or explicit send, not only after a fully uploaded recording is processed

Recommended v1 path:
- capture microphone audio in the app continuously while press-to-talk or live-mic mode is active
- stream audio frames to the VPS over a dedicated WebSocket
- run streaming STT on the VPS
- emit partial transcript events back to the app in real time
- finalize the current utterance on pause or send
- inject the finalized transcript into the shared session as the actual user message

Why this is now the best fit:
- preserves the fast "phone-call-like" experience you want
- keeps heavy STT infra centralized on the VPS
- avoids having to ship and tune an on-device Android STT stack immediately
- supports future interruption/queueing semantics more naturally than batch-upload transcription

Future upgrade path:
- optionally add on-device interim STT later if we want even lower perceived latency
- keep the same chat/session contract so the app can use local or VPS streaming STT behind the same UI

### File/media path
The app client should support three entry paths:
- take photo with camera
- pick image/video from gallery where allowed
- pick general documents/files

The backend should normalize uploads into a shared attachment model so Telegram and app can both represent them.

### Telegram labeling behavior
When Telegram displays app-originated content, show a visible origin label such as:
- `[App]`
- `from app`
- `voice from app`
- `file uploaded from app`

Exact wording can be finalized later, but origin labeling is required.

### Runtime/deployment direction
Recommended v1 operational model:
- keep a single primary launch path via `telegram_agent.py`
- if `channels.app.enabled` is true, start a lightweight embedded FastAPI/uvicorn service alongside the Telegram runtime
- do not implement on-demand lazy boot first

Why:
- much simpler and more reliable than demand-detection startup
- avoids missed wakeups, race conditions, and pairing failures
- app backend idle cost should be small if implemented as a lightweight HTTP/WS service
- can be refactored later if actual resource usage proves meaningful

## Important warning on lazy-start idea
Starting the app backend only when an external detector notices app usage sounds attractive, but creates problems:
- the phone cannot contact a backend that is not already listening
- QR pairing and websocket reconnects become more fragile
- wake-on-demand usually requires another always-on component anyway

So for v1, the practical version of `telegram_agent.py runs everything` is:
- Telegram runtime starts as now
- app backend also starts only when the app flag is enabled
- both remain additive
