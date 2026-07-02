# Jarvis Voice Mode Plan

## Product Goal

Jarvis mode is a no-chat desktop operating mode for EmploAI. The user should be able to walk around the room, speak to the computer, and have the agent perform work through the same desktop runtime, tools, planner, and verification behavior used by chat mode.

The UI should not feel like chat with a microphone attached. It should feel like a voice-first control surface:

- top-level mode switch: Chat / Jarvis
- no visible transcript or composer in Jarvis mode
- always-on microphone unless muted
- central voice circle with live waveform activity
- assistant responses and progress updates spoken through TTS
- optional status drawer for tool/activity visibility, hidden by default
- visible computer actions remain the main evidence that work is happening

Jarvis mode initially supports the English local voice path only. Hebrew can remain supported in normal voice/chat mode until the Jarvis latency, echo, and TTS path are proven.

## Current Code Facts

The feature should build on existing app voice infrastructure instead of creating a separate agent:

- `app_backend/app_server.py` exposes `WS /ws/app/voice`.
- `VoiceClientEvent` already supports `voice_start`, `voice_chunk`, `voice_pause`, `voice_resume`, `voice_commit`, and `voice_cancel`.
- `app_backend/voice_runtime.py` contains `VoiceDraftState`, local STT routing, English/Hebrew voice pack status, and `synthesize_assistant_audio`.
- `DesktopConversationView.tsx` already has microphone capture, always-on VAD/gating, voice chunk streaming, and `assistant_audio` playback.
- `run_app_chat_turn` already sends finalized voice transcripts through the same agent/session path using `source_format="app_voice_transcript"`.
- `shared/channel_runtime.py` already emits `assistant_delta`, `tool_use`, `status`, `task_board`, and related events through `event_sink`.

The current TTS path is not enough for Jarvis mode:

- it is final-response oriented
- it uses the OpenAI audio API when available
- it does not produce spoken progress updates during tool execution
- it does not have a local packaged TTS voice pack

## UX Requirements

### Chat / Jarvis Mode Switch

Add a segmented control at the top of the desktop conversation surface:

- Chat: current transcript/composer/tool UI.
- Jarvis: no transcript, no text input, no visible tool calls by default.

Switching to Jarvis mode should:

- require a ready English voice input path
- start or arm always-on capture
- show a mute control prominently
- keep the current agent session active internally
- keep sync/history internal, but avoid rendering text transcript in the main surface

Switching back to Chat should:

- stop or suspend Jarvis always-on capture unless the user explicitly keeps it enabled
- restore the normal chat transcript and composer
- leave the underlying session history intact

### Jarvis Visual Surface

The main surface should include:

- central circle/orb
- waveform around the circle driven by live mic amplitude while listening
- waveform or ring animation driven by assistant audio playback while speaking
- small non-text or minimal-label state indicators for listening, thinking, speaking, muted, and error
- mute button
- optional tool/status drawer button

The default Jarvis screen should not show:

- user transcript text
- assistant final text
- raw tool calls
- reasoning/thinking text
- a chat composer

### Optional Tool Status Drawer

The user can open a compact status drawer when they want visibility.

The drawer can show:

- current high-level activity
- recent spoken progress updates
- current active app/window if available
- warnings/errors
- optional technical tool timeline for diagnostics

This drawer is not the primary UX. It is a trust and debugging layer.

## Voice Input Requirements

Jarvis mode should reuse the desktop always-on capture path, but with Jarvis defaults:

- always-on enabled automatically when Jarvis mode starts
- `auto_send=true`
- English local STT only for the first implementation
- no transcript inserted into the visible composer
- VAD/gate tuned for room speech, not only close-mic push-to-talk
- microphone permission/device errors must produce spoken and visible recovery prompts

Warmup matters. On app startup, if English voice is installed and Jarvis is available:

- initialize voice runtime status early
- resolve English pack paths early
- warm the STT model enough that the first utterance is not slow
- expose warmup status through `/api/app/voice/status`

## TTS Requirements

Jarvis mode needs TTS for two separate streams:

1. Progress narration while the agent is working.
2. Final spoken response when the agent has something useful to report.

The preferred engine is local and packaged like the English/Hebrew voice packs. If a local engine is too heavy or not responsive enough after benchmarking, keep the existing API TTS as a fallback path, not as the desired default.

### TTS Runtime Shape

Add a backend TTS adapter layer rather than wiring a model directly into the websocket handler:

- `app_backend/tts_runtime.py` or a clearly separated TTS section in `voice_runtime.py`
- engine interface: `synthesize(text, voice, speed, priority) -> audio payload`
- status interface: `get_tts_runtime_status()`
- warmup interface: `preload_tts_engine()`
- cancellation/queue control for interruptions

The websocket event payload can continue to use the existing `assistant_audio` event shape:

- `audio_base64`
- `mime_type`
- `format`
- `voice`
- `model`
- `text`
- add optional `kind`: `progress`, `final`, `warning`
- add optional `sequence_id`

### Local TTS Voice Pack

Add an English TTS pack alongside STT packs:

- pack id: `english_tts_local`
- managed install location under runtime home voice packs
- manifest with model files, checksum, engine, license, sample rate, expected output format
- setup panel/install flow support
- MSI selection or first-run setup support after the local engine is chosen

The first local engine should be chosen by benchmark, not by guess. The benchmark should measure:

- package size
- cold start time
- warm synthesis latency for 5 short progress phrases
- final answer synthesis latency for 50, 150, and 500 words
- CPU load during simultaneous STT and TTS
- naturalness at low latency
- Windows packaged runtime compatibility

Candidate local engines should be evaluated as adapters. The product should not depend on a specific local engine until the benchmark proves it.

### Snappiness Requirements

Target behavior:

- first spoken progress update starts quickly after the first meaningful action
- short progress phrases synthesize from a warm engine fast enough to feel conversational
- common phrases can be pre-generated or cached
- long final answers are chunked into sentences/clauses so playback can begin before the whole response is synthesized
- TTS playback can be cancelled when the user interrupts

Common progress phrases worth caching:

- "Opening that now."
- "I'm checking the page."
- "I'm gathering the latest items."
- "I'm creating the file."
- "I'm verifying it opened."
- "I hit an issue, trying another route."

## Spoken Progress Design

Jarvis must not wait until the final answer to speak. It should narrate general actions while the agent is working, without reading every low-level tool call.

Example target behavior:

User asks: "Open Chrome, go to Gmail, gather my latest five emails, summarize them, and open the summary for me."

Jarvis should speak progress like:

- "Opening Gmail."
- "Gathering the latest five emails."
- "Summarizing them into a list."
- "Opening the summary for you."

It should not speak every click, keypress, DOM query, screenshot, or retry unless that retry changes the user-facing plan.

### Recommended Architecture

Use a `JarvisNarrationCoordinator` on the backend.

Inputs:

- `status` events
- `tool_use` events from `shared/channel_runtime.py`
- `task_board` updates
- assistant final text
- warnings/errors

Outputs:

- `assistant_audio` events with `kind="progress"` or `kind="final"`
- optional `jarvis_activity` events for the hidden status drawer

The coordinator should:

- group low-level tool events into user-facing action phases
- rate-limit spoken updates
- dedupe repeated updates
- prioritize warnings and blockers
- skip narration while the assistant is already speaking unless the new update is higher priority
- avoid leaking sensitive content unless the user asked for it aloud

### Model-Authored Progress

There are two possible ways to make progress narration more intentional:

1. Deterministic narration from tool categories.
2. Model-authored narration hints attached to key actions.

The best first implementation is hybrid:

- deterministic fallback always exists
- optional model-authored `spoken_update` can be added only to key high-level tools or internal action events
- do not add a required narration parameter to every tool schema

Adding a required `user_message` or `spoken_update` parameter to every tool would increase schema bloat, tool-call friction, and failure surface. Instead:

- add optional `spoken_update` to key high-level tool families only if needed
- key families: browser navigation/search, file creation/write/open, `run_command`, app/window focus, and final verification actions
- if absent, the coordinator derives narration from tool name, arguments, result, and task board state
- if present, the coordinator validates and shortens it before TTS

This keeps the agent adaptive while still letting it say what it is doing.

### Tool Grouping Rules

Initial grouping rules:

- browser navigation/search/read actions -> "Opening/checking/gathering from [site/page]"
- file write/create/open actions -> "Creating/opening/verifying the file"
- command execution -> "Running the command" or a more specific safe summary from args
- screen/window actions -> "Switching to [app/window]" or "Checking the screen"
- repeated failed actions -> "That route did not work, trying another way"
- task board focus changes -> speak the new phase
- final verified success -> speak the concise result
- real blockers -> speak the blocker and what is needed from the user

Do not narrate:

- every click
- every keypress
- raw filesystem paths unless useful
- secrets/tokens
- full email/message content unless the user requested it
- speculative claims before verification

## Turn-Taking and Echo Control

Jarvis is always listening, but it must not transcribe its own voice as user input.

Minimum behavior:

- enable browser/Electron audio constraints where available: echo cancellation, noise suppression, auto gain control
- mark internal state as `speaking` while TTS plays
- do not auto-commit speech detected during assistant playback unless barge-in is enabled
- support TTS cancellation when the user intentionally interrupts
- drain or discard mic frames captured during TTS playback

Later behavior:

- barge-in mode where loud/clear user speech cancels current TTS and starts a new utterance
- selectable sensitivity for room use
- device selection for mic and speaker

## Backend Implementation Phases

### Phase 1: Mode Plumbing

- Add desktop UI state for `conversationMode: "chat" | "jarvis"`.
- Persist the preferred mode locally.
- Keep agent sessions identical across modes.
- Hide transcript/composer/tool timeline in Jarvis mode.
- Reuse existing voice websocket connection.

### Phase 2: Jarvis Voice Input

- Start always-on capture when entering Jarvis mode.
- Force Jarvis capture to `auto_send=true`.
- Avoid placing transcripts into the composer.
- Keep voice transcripts in session history internally as `app_voice_transcript`.
- Add mute/unmute control.
- Add visible privacy/listening indicator.
- Add recovery states for missing mic permission, missing English voice pack, and voice socket errors.

### Phase 3: TTS Adapter and Local Pack

- Extract current OpenAI TTS path behind a TTS adapter.
- Add TTS runtime status to app dependency status.
- Add warmup endpoint or extend `/api/app/voice/warmup`.
- Benchmark local TTS candidates.
- Add `english_tts_local` managed pack once an engine is chosen.
- Keep API TTS fallback behind settings/env, but prefer local when installed.

### Phase 4: Spoken Progress Pipeline

- Add `JarvisNarrationCoordinator`.
- Feed it `tool_use`, `status`, `task_board`, warnings, errors, and final assistant text.
- Emit progress `assistant_audio` events during the run.
- Add hidden `jarvis_activity` events for the optional status drawer.
- Add dedupe/rate limits.
- Add optional `spoken_update` only to key tool families if deterministic narration is not good enough.

### Phase 5: Final Answer Behavior

- In Jarvis mode, final assistant text should be spoken, not rendered as a chat bubble.
- Long final answers should be chunked.
- If the result is mostly visible on the computer, the spoken final can be short.
- If the task requires reporting information, the spoken final should contain the useful summary.

### Phase 6: Echo, Interruptions, and Reliability

- Suppress STT commits while TTS is speaking.
- Add TTS cancellation on mute, mode switch, stop, and user interruption.
- Ensure always-on capture resumes after speaking.
- Add watchdog recovery for stuck voice states.
- Prevent queued stale utterances from firing after mode switches.

### Phase 7: Settings and Installer

- Add Jarvis availability checks to setup/settings.
- Add English TTS pack install/remove/status UI.
- Add startup warmup preference.
- Add mic/speaker device selection when practical.
- Add TTS speed/voice selection after the first engine is stable.
- Ensure MSI/runtime isolation includes TTS pack state under the beta runtime home.

## Frontend Implementation Phases

### Jarvis Shell

- Add top segmented control.
- Add central voice circle.
- Add live mic waveform.
- Add assistant-speaking waveform.
- Add mute button.
- Add stop button or reuse existing run stop affordance.
- Add hidden activity drawer.

### Event Handling

- Handle `assistant_audio.kind`.
- Keep `progress` audio out of chat transcript.
- In Jarvis mode, suppress visible `assistant_delta`, `assistant_final`, and `voice_final` rendering.
- Still update internal session state and sidebar metadata.
- Show errors/recovery prompts visually even without text transcript.

### Activity Drawer

- Show last few high-level progress updates.
- Show current voice state.
- Show active run state.
- Show technical timeline only behind a diagnostic toggle.

## Verification Plan

Automated tests:

- TTS adapter returns the expected audio payload shape.
- TTS disabled path returns no audio without breaking voice turns.
- Jarvis mode does not render voice transcript/final assistant text in the main transcript.
- `voice_commit` in Jarvis mode still reaches `run_app_chat_turn`.
- narration coordinator groups tool events into bounded progress updates.
- repeated tool events do not produce repeated spoken lines.
- warnings/errors become priority spoken updates.
- assistant playback state suppresses always-on auto-commit.

Manual smoke tests:

- enter Jarvis mode and say "open Chrome"
- ask for a browser navigation task and confirm progress narration speaks before final answer
- ask for a file creation/opening task and confirm narration changes phases
- interrupt while assistant is speaking
- mute and confirm no speech is sent
- switch back to Chat and confirm normal transcript/composer returns
- restart app and confirm English STT/TTS warmup is ready enough for first use

Latency checks:

- app startup to voice ready
- Jarvis mode entry to listening
- end of user speech to agent turn start
- first tool event to first spoken progress audio
- final text to first final-audio playback

## Open Decisions

- Which local English TTS engine meets size, license, quality, and latency requirements.
- Whether the first beta should ship API TTS fallback only while local TTS is benchmarked.
- Whether Jarvis should support barge-in in the first version or only after echo suppression is stable.
- Whether `spoken_update` should be added to selected tool schemas or kept entirely coordinator-derived for v1.
- Whether Jarvis mode should be per-session state, global app state, or a local UI-only preference.

## Recommended First Build Slice

The first useful slice should be:

1. Add Chat/Jarvis mode switch and Jarvis shell.
2. Reuse English always-on STT with auto-send and no visible transcript.
3. Use the existing `assistant_audio` event for final spoken responses.
4. Add a simple narration coordinator that speaks deterministic progress updates from `tool_use` and `status` events.
5. Keep OpenAI TTS as fallback while benchmarking local TTS.
6. Add local TTS pack only after benchmark proof.

This gives a working Jarvis UX quickly while keeping the deeper local TTS packaging decision evidence-based.
