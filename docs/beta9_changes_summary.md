# Beta 9 Changes Summary

Updated: 2026-04-29

This file summarizes the main changes made so far while preparing beta 9. It is focused on the shared runtime path so the same behavior carries into both local testing and the packaged MSI build.

## Desktop App And Build

- The desktop app is treated as an Electron shell around the existing web client and Python backend.
- The Windows build flow packages the renderer and backend together so the MSI matches the local app behavior as closely as possible.
- The Windows release README was updated to reflect the current desktop packaging flow.
- The packaged backend/runtime startup path was hardened so the MSI build is less likely to fail on repeated launches or locked files.

## Voice Path

- The duplicate Electron-side voice path was removed.
- The working renderer-side voice flow remains the active one: browser microphone capture plus the backend websocket voice channel.
- This keeps the desktop app and the packaged MSI on the same voice implementation.

## Context Compaction

- A shared context compaction system was added in `cli/agent_tools/context_manager.py`.
- The trigger threshold is 40 percent of the model context window.
- When provider-native token counting is available, it is used first.
- When provider-native counting is not available, the system falls back to a rough estimate so compaction still happens.
- The retention rule preserves the last 5 user messages and the last 20 agent messages, including tool calls.
- Context older than that tail is summarized into a compact block.
- The summary block is capped at 2000 tokens, including its wrapper text.
- Compaction now runs in the shared runtime, so Telegram and the desktop app behave the same way.

## Manual Compaction Command

- `/compact` was added for Telegram.
- `/compact` was also wired into the desktop app command surface.
- Both channels use the same backend compaction helper.
- Manual compaction is executed under the session lock so it is atomic and does not race a live turn.

## Context Status Display

- The desktop app now shows a visible context status mark in the context window area.
- The status reflects `OK`, `Needs Compact`, or `Compacted`.
- Telegram `/context` now reports the same compaction state and last compaction details.

## Session State And Persistence

- `last_context_compaction` was added to session persistence so the last compaction result can be shown later.
- Compaction metadata is sanitized before saving so the session file does not store the full rewritten history inside the compaction record.
- The `message_id_map` is rebuilt after compaction so Telegram edit and reply tracking stays valid.

## API And UI Wiring

- The backend app API now exposes a manual compact action.
- The desktop client types were updated so the UI can read the new context usage and compaction state.
- The Telegram command handlers and the desktop command handlers both point at the same shared runtime behavior.

## Token Counting

- `tiktoken` was added as a dependency for better token counting where it applies.
- OpenAI, xAI, and DeepSeek families use tokenizer-based counting when available.
- Anthropic and Google families use provider token-count APIs when available.
- If no provider tokenizer/API is available, the system falls back to a rough estimate rather than blocking compaction.

## Intentional Non-Changes

- The `Other Computers` tab was intentionally left as a placeholder.
- No attempt was made to redesign that surface while working on the beta 9 runtime fixes.

## Verification

- The changed Python files were compiled successfully with `py_compile`.
- The targeted diff checks on the touched files were clean aside from existing line-ending warnings in the working tree.
- The context compaction path was checked to ensure the old 600-token local fallback and full-history compaction payloads were removed.
