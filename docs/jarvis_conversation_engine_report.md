# Jarvis Conversation Engine Report

Date: 2026-06-08

## Scope

This report compares the conversational design of the three Jarvis-style sibling repositories under `powerful-project-collection` and the current EmploAI desktop/app agent backend. It is intentionally code-first. READMEs and docs were treated as secondary because they may be outdated.

Repos found:

| Repo | Main conversational style | Primary files inspected |
| --- | --- | --- |
| `Jarvis-v2.0` | Deterministic voice command router | `Jarvis (Male Version).py`, `Jarvia (Female Version).py`, `README.md` |
| `Jarvis-MT67` | Gemini Live native-audio assistant | `main.py`, `core/prompt.txt`, `memory/memory_manager.py`, `jarvis_telegram_patch.py` |
| `Mark-XL` | Local LLM voice/text assistant with tool calls | `main.py`, `core/llm_client.py`, `core/stt.py`, `core/tts.py`, `core/prompt.txt`, `memory/memory_manager.py` |
| `emploai` | Multi-chat desktop/app agent runtime with persistent sessions, tool packs, planner verifier, and websocket sync | `mobile_app/backend/app_server.py`, `mobile_app/backend/runtime.py`, `mobile_app/backend/session_bridge.py`, `shared/channel_runtime.py`, `shared/multi_chat_orchestrator.py`, `cli/agent_tools/loop.py`, `telegram_bot/telegram_session_state.py`, `telegram_bot/telegram_unified_agent.py`, `desktop_app/renderer_client/src/desktop/DesktopConversationView.tsx` |

## Executive Summary

The three Jarvis repos represent three different generations of assistant architecture:

- `Jarvis-v2.0` is not a model-driven conversation engine. It is a speech recognizer feeding a large `if/elif` command menu. It can feel conversational because it speaks, asks simple follow-up questions, and routes natural phrases, but it has no transcript, planner, memory, or tool-call loop.
- `Jarvis-MT67` is a realtime voice assistant around Gemini Live. Gemini owns the active conversation context inside a live audio session. The app streams mic audio in, streams audio out, and executes Gemini function calls. It has long-term memory injection, but no local persisted chat transcript.
- `Mark-XL` is the most direct Jarvis-style local agent. It keeps an in-memory OpenAI-style message list, builds a system prompt with long-term memory and current time, streams text from Ollama or an OpenAI-compatible local server, speaks sentence fragments as they arrive, and runs tools in loop rounds.
- `EmploAI` is a much heavier agent runtime. Its conversation engine is not a single script. It is a desktop websocket surface, a per-user session bridge, a multi-chat orchestrator, a disk-backed session model, a shared turn runtime, and a provider-neutral tool loop. It supports multi-chat persistence, tool-pack availability locks, artifacts, task boards, streaming UI events, voice mode, and final-answer verification.

In short: the Jarvis repos optimize for voice-assistant immediacy. EmploAI optimizes for durable, multi-session autonomous work.

## Architecture Evolution

| Layer | Jarvis-v2.0 | Jarvis-MT67 | Mark-XL | EmploAI |
| --- | --- | --- | --- | --- |
| Model | None | Gemini Live | Ollama/OpenAI-compatible local LLM | Configurable providers through unified tool loop |
| Input | Microphone via `speech_recognition` | Realtime mic PCM, UI text, Telegram bridge, clap commands | Whisper/Vosk mic plus UI text queue | Desktop chat websocket, voice websocket, Telegram, scheduled jobs |
| Output | `pyttsx3` speech | Gemini native audio playback | TTS queue via EdgeTTS/Kokoro/ElevenLabs | Chat transcript, voice TTS, timeline, artifacts, task board |
| Conversation state | Current recognized string only | Gemini Live session state | In-memory `_conversation` list, clipped to recent history | Persistent `Session.chat_history` plus `event_timeline`, artifacts, task state |
| Memory | None | JSON long-term memory injected into system prompt | JSON long-term memory injected into system prompt | Memory manager plus workspace context, skills, session history, task board, artifacts |
| Tools | Hard-coded Python branches | Gemini function calls | OpenAI/Ollama-style tool calls | Tool packs, provider-normalized schemas, executor, artifacts, planner guard |
| Multi-chat | No | No | No | Yes, per-session workers plus lock-limited shared resources |

## Jarvis-v2.0

### Conversational Shape

`Jarvis-v2.0` is a traditional voice-command assistant. The male and female scripts are nearly the same. They initialize a SAPI5 `pyttsx3` voice, greet the user, ask for a name, then enter an infinite command loop:

1. Listen to the microphone.
2. Send the audio to Google's speech recognizer.
3. Lowercase the recognized text.
4. Match substrings against a long `if/elif` chain.
5. Execute the corresponding Python side effect.
6. Speak a short response.

There is no LLM, no model memory, no planner, and no message history. The assistant feels conversational because some commands contain nested prompts, for example asking which city to use for weather or what note text to write.

### Input And Output

Input is synchronous microphone capture through `speech_recognition.Recognizer.listen()`. Recognition uses `recognize_google(..., language='en-in')`, so it depends on Google's web recognizer.

Output is synchronous local TTS:

- `engine.say(audio)`
- `engine.runAndWait()`

This design is simple, but every conversation step blocks while listening, recognizing, executing, or speaking.

### Tooling Model

The "tools" are not abstracted as model-callable functions. They are hard-coded branches such as:

- open websites and apps
- read Wikipedia summaries
- report time/date/weather
- send email
- take screenshots
- open camera
- read news
- search Google
- empty recycle bin
- run OCR, QR, video, and YouTube workflows

The routing is brittle because broad substring checks can collide. For example, any command containing a short greeting token can match accidentally.

### State And Persistence

There is no persistent transcript and no durable long-term memory. The only conversation state is local variables in the current process and any files created by specific commands.

### Reliability Notes

- The male script contains unresolved merge conflict markers near the top, so that file is likely not runnable as-is.
- Many actions depend on hard-coded Windows paths and local installed programs.
- There is no concept of task completion evidence. If an action branch runs, the assistant usually assumes success.
- There is no multi-chat or session isolation problem because there is only one blocking loop.

## Jarvis-MT67

### Conversational Shape

`Jarvis-MT67` is a Gemini Live native-audio assistant. The local app manages audio devices, queues, tool execution, memory injection, and UI/Telegram bridges, while Gemini Live owns the active conversational context inside a live session.

The central class is `JarvisLive` in `main.py`.

### Input Flow

The main input path is realtime audio:

1. `_listen_audio()` opens a `sounddevice` raw input stream.
2. The microphone callback receives PCM chunks.
3. If the assistant is not muted and not currently speaking, chunks are placed into `out_queue`.
4. `_send_realtime()` reads queue messages and sends them to Gemini Live via `session.send_realtime_input(...)`.

Other input paths share the same Live session:

- UI text commands call `send_client_content(..., turn_complete=True)`.
- `TelegramBridge` polls a local JSON inbox and forwards incoming text as a completed client-content turn.
- Clap detection toggles mute or sends canned text commands.

### Output Flow

`_receive_audio()` consumes Gemini Live responses:

- `response.data` is assistant audio and goes into `audio_in_queue`.
- `_play_audio()` streams the raw audio to a `sounddevice.RawOutputStream`.
- server-side input and output transcription events are logged for UI/debug visibility.
- `response.tool_call.function_calls` are executed locally and returned as Gemini function responses.

The speaking flag blocks mic audio forwarding while assistant audio is playing, which reduces feedback loops.

### Prompt And Memory

`_build_config()` builds the Gemini Live config. It combines:

- current date/time
- formatted long-term memory
- `core/prompt.txt`
- Gemini function declarations
- input and output transcription
- audio response modality
- voice config
- session resumption

The memory manager stores structured JSON in `memory/long_term.json`, grouped into categories such as identity, preferences, projects, relationships, wishes, and notes.

### Tooling Model

Gemini function declarations expose desktop, browser, file, web, messaging, memory, and agent-like actions. The Live receive loop detects tool calls and dispatches `_execute_tool(fc)` through `asyncio.run_in_executor()` so tool execution does not freeze the audio receive loop.

The `save_memory` tool is treated as a silent memory write. Some tools, such as `screen_process`, are kicked off in the background and Gemini is told the vision module will respond directly.

### State And Persistence

The conversation context is primarily Gemini Live session state. Local persistent state is long-term memory, config, and logs. There is no durable local chat transcript equivalent to EmploAI's `Session.chat_history`.

### Reliability Notes

- Reconnects rebuild config and start another Live session. Session resumption may help, but the local app is not the source of truth for conversation history.
- The Telegram bridge is one-way from a conversation perspective: it forwards text into the Live session, but the outbox response is a generic acknowledgement rather than the actual model reply.
- Tool recovery is shallow. Errors become function responses or spoken failures; there is no independent final verifier.
- This design is excellent for low-latency voice presence, but weaker for inspectable, persisted, multi-session work.

## Mark-XL

### Conversational Shape

`Mark-XL` is the closest sibling to a local Jarvis agent. It uses local STT, local or compatible LLM serving, local/remote TTS options, an OpenAI-style message history, and a tool-call loop.

The central class is `JarvisLocal` in `main.py`.

### Input Flow

Mark-XL has both voice and text input:

- Whisper path: microphone audio is gated by `_VADBuffer`, then transcribed by `WhisperSTT`.
- Vosk path: microphone audio is streamed to a `VoskSTT` recognizer.
- UI text path: `_on_text_command()` pushes text into `_text_queue`; `_text_command_loop()` sends it to `_process_message(text)`.

Both voice and text converge on the same `_process_message()` turn loop.

### Output Flow

The LLM stream yields sentence-level events. Each complete sentence is passed to `speak()` immediately, allowing TTS to overlap with model generation instead of waiting for the final answer. This is a strong voice-assistant design choice: perceived response latency is much lower.

TTS backends include EdgeTTS, Kokoro, and ElevenLabs. A worker queue handles speech playback.

### Prompt And Memory

`_build_system_prompt()` loads:

- static persona and behavior rules from `core/prompt.txt`
- formatted long-term memory from `memory/long_term.json`
- current date/time

The code orders the static prompt first, memory second, and dynamic time last. That is useful for Ollama prompt/KV caching because the largest stable prefix stays stable between turns.

The memory manager is compact and practical:

- JSON-backed storage
- categories for identity, preferences, projects, relationships, wishes, and notes
- value length limits
- total memory prompt budget
- older entries trimmed by update time

### Turn Loop

`_process_message(user_text)` does the real conversation work:

1. Append the user message to `_conversation`.
2. Clip recent history to `MAX_HISTORY = 10`.
3. Build messages as system prompt plus conversation.
4. Call `call_llm_stream(messages, OLLAMA_TOOLS)`.
5. Speak streamed sentence events.
6. On `"done"`, inspect final content and tool calls.
7. If no tools were called, append the assistant answer.
8. If tools were called, append the assistant tool-call message, execute tools, append tool results, and either answer directly or allow another LLM round.

Tool rounds are capped by `MAX_TOOL_ROUNDS = 6`.

### LLM Client

`core/llm_client.py` supports:

- Ollama `/api/chat`
- OpenAI-compatible `/v1/chat/completions`, such as LM Studio, Jan, LocalAI, llama.cpp, or vLLM

It normalizes OpenAI-style streaming tool-call fragments into the local shape expected by the main turn loop.

On Windows, it can auto-start Ollama with hidden-window process flags.

### Tooling Model

Tools are declared in `main.py`, originally in a Gemini-like structure and converted to Ollama/OpenAI-compatible definitions. Tool categories include apps, web search, weather, messaging, reminders, browser control, screen processing, file control, coding helpers, dev agents, memory, and shutdown.

Mark-XL has several pragmatic paths:

- `save_memory` is silent.
- Pure memory saves with assistant verbal content can be executed without another model round.
- Some tools return direct results that are spoken directly.
- More complex tools such as `web_search`, `screen_process`, and `agent_task` trigger another model round with tool output in context.

### State And Persistence

The active transcript is `_conversation`, an in-memory list. Long-term memory is persisted, but full chat history is not persisted as a session transcript.

### Reliability Notes

- Strong for a single local voice assistant.
- Sentence-level streaming TTS is worth borrowing.
- The tool loop is much simpler than EmploAI's and has no final-answer verifier.
- Directly speaking tool results can be fast, but it can bypass model synthesis for multi-step tasks.
- There is no multi-chat, session isolation, lock management, or persistent verbose timeline.

## Current EmploAI Conversation Engine

### Conversational Shape

EmploAI's main conversation engine is the desktop app plus agent backend. It is not a single Jarvis loop; it is a layered runtime:

1. The desktop app opens `/ws/app/chat` or `/ws/app/voice`.
2. `mobile_app/backend/app_server.py` authenticates the websocket and resolves the session.
3. `AppSessionBridge` loads disk-backed session details and exposes session summaries/details to the UI.
4. `UserMultiChatOrchestrator` leases a per-session worker and enforces shared-resource locks.
5. `mobile_app/backend/runtime.py` converts the app turn into the shared runtime format.
6. `shared/channel_runtime.py` appends the user message, builds prompt context, emits live events, persists timeline rows, captures artifacts, and calls the tool loop.
7. `cli/agent_tools/loop.py` streams the model, executes provider-normalized tool calls, and asks the final-quality guard whether a candidate final can be shown.
8. Results are persisted back into `Session.chat_history`, published through channel sync, and reflected in the frontend.

### Session State

The persistent session model is `cli/models/session.py::Session`. It stores:

- `chat_history`
- `event_timeline`
- `task_history`
- `active_task_id`
- `task_board_armed_next_turn`
- `active_skills`
- model, variant, planner model, workspace, tool packs, bot config, and headless eligibility

`telegram_bot/telegram_session_state.py::TelegramSession` mirrors this state at runtime. Save/load copies both `chat_history` and `event_timeline` between the live runtime object and the disk-backed `Session` object.

`mobile_app/backend/session_bridge.py` exposes session detail to the frontend as:

- `messages`
- `timeline_events`
- task board state
- artifact metadata
- live run state
- enabled and available tool packs
- lock status

This means the chat transcript and verbose tool/log timeline are meant to survive navigation and reloads.

### Multi-Chat Runtime

The orchestrator in `shared/multi_chat_orchestrator.py` is the key difference from the Jarvis repos.

It maintains:

- a worker per `session_id`
- a running worker map
- `max_concurrent_chats`, defaulting to 4
- an interactive desktop owner
- workspace-write owners by workspace
- headless-mode constraints

`prepare_turn(session_id)` prevents two overlapping turns in the same chat, but allows different chats to run concurrently until the concurrency cap is hit. Shared resources are lock-limited:

- `interactive_desktop` can be reserved by one chat
- `workspace_write` can be reserved by one chat per workspace

The frontend and session bridge can activate or create chats while a runtime is processing. If the live runtime is busy, activation returns the disk session instead of loading it into the busy runtime.

### Prompt Construction

`telegram_bot/telegram_unified_agent.py::build_unified_system_prompt()` builds the main system prompt from:

- active task board prompt
- browser runtime prompt when browser or interactive desktop tools are active
- desktop runtime prompt when interactive desktop tools are active
- workspace path context
- current time
- scheduler prompt when scheduler tools are active
- active tool-pack prompt
- unified agent core prompt
- workspace context from the context loader
- memory context
- skill index and loaded skill context

`mobile_app/backend/runtime.py` also adds turn-specific system messages:

- task execution contract
- screen observation contract
- conversational style guard for non-task-like turns
- Jarvis voice response contract for app voice transcripts in Jarvis surface mode
- kickstart prelude for early task-like turns

This makes EmploAI's conversation behavior strongly dependent on the active tool packs and the current surface.

### Tool Loop

`cli/agent_tools/loop.py::run_tool_loop()` is provider-neutral. It supports Anthropic, Google, OpenAI chat completions, and OpenAI Responses-style APIs through a common loop:

1. Ensure the effective system prompt is in message zero.
2. Inject fresh runtime context before each model turn.
3. Stream assistant text and reasoning.
4. Accumulate tool-call chunks.
5. Validate requested tool names against the provider inventory.
6. Execute tools through `tool_executor.execute(name, args)`.
7. Summarize tool results back into model messages.
8. Track a compact `tool_trace` for final verification.
9. Continue until the model returns no tool calls and the final guard allows the answer.

`shared/channel_runtime.py` wraps this loop with higher-level desktop behavior:

- verbose log and tool events are appended to `session.event_timeline`
- command outputs, screenshots, browser observations, OCR, and file snapshots can become chat artifacts
- task board updates are generated from user turns and tool results
- assistant deltas are streamed to the frontend
- final assistant messages are persisted to `chat_history`
- status events publish `running` and `idle`

### Planner And Auto-Continuation

EmploAI has a final-answer verifier path that the Jarvis repos do not have.

When the final quality guard is enabled, `run_tool_loop()` buffers assistant stream events before exposing them. If the model tries to final-answer without tool calls, the loop asks `judge_final_candidate`. The desktop runtime wires that callback to `shared/channel_runtime.py::_planner_final_verdict()`.

The verifier:

- preserves the original task objective when the latest user message is only "continue", "keep going", or similar
- sends the original request, candidate final, and recent tool trace to the planner model
- requires tool evidence rather than trusting the candidate final
- is stricter for coding, build, install, run, launch, website, desktop-app, server, and test tasks
- treats missing dependencies, installer failures, missing PATH, launch failures, and "if you want I can continue" style answers as retry signals when safe routes remain
- emits a hidden continuation instruction when it chooses retry

`cli/agent_tools/loop.py::_max_auto_continues_for_request()` raises the auto-continue budget to at least 5 for coding-like requests, while generic requests use the configured default.

The continuation is hidden from the user: the previous candidate final is discarded, the model receives a runtime instruction to continue the original task, and it must use a materially useful tool action before final-answering again.

### Frontend Event Handling

`desktop_app/renderer_client/src/desktop/DesktopConversationView.tsx` treats `event.session_id` as the routing key for live events.

For the selected chat, it applies:

- user messages
- assistant deltas
- assistant finals
- thinking text
- tool events
- timeline events
- artifacts
- task board state
- run state

For non-selected chats, it refreshes sidebar/session metadata instead of appending transcript or timeline rows to the visible chat. On session sync, timeline events are normalized or merged so live websocket rows and persisted rows should not duplicate.

This is a major difference from the Jarvis repos: the visible conversation is a projection of persisted per-session state plus selected-session live events, not just whatever the current process happens to be saying.

### Voice/Jarvis Mode Inside EmploAI

EmploAI's voice/Jarvis surface is not a separate assistant brain. It feeds app voice transcripts into the same `run_app_chat_turn()` path and adds a voice response contract. The final answer is transformed to be short, natural speech, and markdown/list formatting is stripped for TTS.

This is the right architectural direction if the goal is a Jarvis-feeling desktop assistant without forking the conversation engine.

### Reliability Notes

Strengths:

- persistent sessions and timelines
- multi-chat workers
- tool-pack-aware prompts
- shared-resource locks
- artifact capture
- task board context
- final-answer verification and hidden continuation
- same engine for chat, voice, Telegram, and scheduled work

Risks:

- The stack is complex. UI, bridge, orchestrator, runtime, session persistence, and tool loop all have to agree on `session_id`.
- The runtime historically shares lineage with Telegram session state, so desktop behavior depends on a class named `TelegramSession`.
- The planner guard depends on model availability and configuration. If unavailable, the loop can fall back to allowing finals.
- Verbose logs require both backend persistence and frontend selected-session routing. If either side loses the session key or timeline merge, tool rows can appear in the wrong chat or disappear after navigation.

## Design Lessons For EmploAI

Useful ideas from `Jarvis-v2.0`:

- Deterministic command shortcuts can be useful for common local actions where a full model turn is unnecessary.
- A voice assistant should have crisp acknowledgement phrases for frequent commands.

Useful ideas from `Jarvis-MT67`:

- Native full-duplex audio feels more alive than turn-based voice.
- Server-side input/output transcription is valuable for debugging voice behavior.
- Speaking-state suppression of mic input is important to avoid feedback loops.

Useful ideas from `Mark-XL`:

- Sentence-level streaming TTS is excellent for perceived latency.
- Local STT/TTS fallback makes a Jarvis mode more private and resilient.
- The memory formatter is simple and effective.
- Static-prompt-first ordering is useful for local model cache behavior.

What EmploAI already does better:

- durable per-chat transcript
- durable verbose tool/log timeline
- multi-chat execution
- resource locks for desktop and workspace tools
- artifact capture and replay
- final-answer verification
- tool-pack-aware UI/runtime behavior

## Recommended Direction

If EmploAI is going to absorb "Jarvis" behavior, it should keep EmploAI's conversation engine as canonical and add Jarvis behavior as a surface layer:

- Voice input should become another source format into `run_app_chat_turn()`.
- Voice output should use the existing final answer after the shared tool loop and planner verifier approve it.
- Local STT/TTS from Mark-XL can be borrowed, especially sentence-level speech streaming, but should not create a separate memory or tool loop.
- Native realtime audio ideas from Jarvis-MT67 are useful, but session state should remain EmploAI's disk-backed `Session`.
- Deterministic shortcuts from Jarvis-v2.0 can be implemented as optional pre-model fast paths, but should write through the same session/timeline system when user-visible.

The important invariant is: one conversation engine, many surfaces. Chat, voice, Telegram, and scheduled jobs should all converge on the same session, tool, artifact, timeline, and planner machinery.

## Concrete Watchpoints

- Keep `event.session_id` authoritative in every live UI event.
- Do not let thinking state, assistant drafts, or verbose tool rows be global desktop state.
- Preserve `event_timeline` on every session save/load path.
- Treat `available_tool_packs` as runtime availability, not saved configuration.
- Keep command execution hidden by default unless the user explicitly asks to watch or interact with a terminal.
- Keep the planner final verifier strict for build/run/create-app tasks, especially when the candidate final says setup failed but safe routes remain.
- Avoid adding a second Jarvis memory store unless it is explicitly bridged into EmploAI's memory/context system.
