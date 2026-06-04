# EmploAI Voice Streaming Plan

## Requirement
Voice input must feel live: as the user speaks, text should appear almost immediately. Final send should occur on pause or explicit send, not after a slow record-upload-transcribe cycle.

## Chosen direction
For v1, use VPS-side streaming STT rather than batch audio upload.

## Proposed flow
1. User opens chat and holds/taps voice input.
2. App starts microphone capture and streams small audio chunks over `WS /ws/app/voice`.
3. Backend feeds chunks into a streaming STT engine.
4. Backend emits `voice_partial` events continuously.
5. App shows live transcript as editable draft text.
6. When silence/pause threshold is reached or the user presses send:
   - backend emits `voice_final`
   - finalized transcript is committed as the outgoing user message
   - normal chat execution begins on the shared session
7. Assistant response streams back over the chat websocket as usual.

## Why not batch upload
Batch upload would feel laggy and blocky:
- user speaks first
- waits for upload
- waits for transcription
- only then sees text

That does not meet the required interaction feel.

## Interface implications
### Voice websocket input
Client -> backend events:
- `voice_start`
- `voice_chunk`
- `voice_pause`
- `voice_resume`
- `voice_commit`
- `voice_cancel`

### Voice websocket output
Backend -> client events:
- `voice_state`
- `voice_partial`
- `voice_final`
- `error`

## Session behavior
- partial transcript should remain draft UI state only
- only the finalized transcript should be stored in shared session history
- stored finalized message metadata should indicate `source_format=app_voice_transcript`
- Telegram should display this with an origin label such as `[App Voice]`

## Future-ready hooks
The same event model should later support:
- interrupting an active assistant response
- queueing a new user utterance while assistant output is in progress
- replacing or continuing generation after interruption
- optional duplex/near-duplex voice mode

## Implementation note
The STT engine choice should be benchmarked for low-latency streaming on the VPS before locking it in. The protocol should stay engine-agnostic so we can swap providers/models later without changing the mobile UX.
