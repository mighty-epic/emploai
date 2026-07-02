# Multi-Chat Concurrency, Tool Packs, Telegram Routing, and Headless Mode

## Purpose
This document records the architectural and product changes that were made in response to the user's multi-chat concurrency direction:

- allow several EmploAI agents to work at the same time across different chats
- prevent conflicting tool usage when multiple agents are active
- preserve shared truth between desktop and Telegram
- make cron global in the app while still routing Telegram output correctly
- support headless or sleep-mode operation
- keep the task board or bulletin board working independently per chat

This file is a history and handoff document. It is meant to explain what changed, why it changed, and what decisions were settled afterward.

## Source Direction
The original direction was:

- multiple chats should be able to run at the same time
- interactive tools cannot safely be used by multiple chats at once
- tool availability should be packaged into tool groups or packs
- each pack should come with system-prompt guidance so the agent behaves professionally within that tool set
- Telegram and desktop should stay in sync
- outgoing app messages mirrored to Telegram should identify which app chat they came from
- cron should not behave like normal chat history
- the system should support a headless or sleep mode
- chats should be assignable to different Telegram bots

## Final Clarified Decisions
After follow-up discussion, these decisions were explicitly settled:

- Headless mode should allow `one sleep chat per bot`
- File mutation safety should remain `workspace-level write locking`, not per-file locking
- Cron should be `global in the app`, but `bot-routed in Telegram` according to the chat that created the cron job

These clarifications override the earlier rougher wording where needed.

## What Was Implemented

### 1. Per-user multi-chat orchestrator
The runtime no longer treats the current session as the only runnable session.

Instead, a per-user orchestration layer now manages:

- many worker runtimes keyed by `session_id`
- shared session storage
- a global run-slot manager
- a global interactive lock
- workspace-level write locks
- headless or sleep-mode eligibility and bot-specific sleep mappings

This means many chats can exist, and up to the configured concurrency limit can be active at the same time.

### 2. Concurrent run limit
A default maximum of `4` active running chats was added at the runtime level.

This is runtime-enforced, not just a UI hint. A fifth chat cannot start if the four run slots are already occupied.

### 3. Interactive-tool exclusivity
Only one running chat may hold the `interactive_desktop` pack at a time.

That lock protects tool families that can conflict globally, including:

- screen reading tied to the live desktop
- OCR or vision tied to the visible machine state
- desktop clicking and typing
- window control
- browser-extension-backed interactive behavior

When one chat is already using the interactive pack:

- that running owner keeps the lock until its current run ends
- other chats see the conflicting pack as unavailable or greyed out

### 4. Workspace-level write locking
Write safety was implemented at the workspace level.

That means:

- only one running chat per normalized workspace may hold workspace-write capability
- chats in different workspaces may write concurrently
- chats in the same workspace may still run read-only packs concurrently

This was chosen instead of per-file locking to avoid complex race conditions around shell commands, generators, package managers, and multi-file mutations.

### 5. Tool packs
Manual per-chat tool-pack selection was added.

The initial pack set is:

- `interactive_desktop`
- `browser_isolated`
- `workspace_write`
- `workspace_read`
- `web_research`
- `scheduler`
- `app_runtime`

These packs now affect two things:

- which tools a chat is actually allowed to use
- which pack-specific instruction fragments are included in that chat's system prompt

This gives each agent a more professional, tool-aware operating context instead of one broad undifferentiated tool surface.

### 6. Pack-aware prompt construction
Tool packs are not only visual toggles.

Each pack contributes instruction fragments so the running agent is guided as if it were operating with that specific professional tool set. This aligns with the original request that any agent should behave competently within the tools it has been given.

### 7. Task boards remain per chat
The runtime-owned task board or bulletin-board system continues to work independently per chat.

There is no shared board across chats. Each worker session keeps its own:

- active task state
- reassessment state
- completion state
- history

This preserves long-task management without cross-chat contamination.

## Telegram and Desktop Sync Changes

### 8. Shared session truth remains the core rule
The implementation preserves the requirement that desktop and Telegram share the same underlying truth for:

- sessions
- current session selection
- messages
- task boards
- workspace changes
- run state

UI-only state remains local to the desktop app, such as:

- sidebar order or pins
- popover visibility
- search popup state
- local layout preferences

### 9. App-originated Telegram mirroring includes chat identity
Outgoing app messages mirrored to Telegram now include the app chat title so the user can tell which app chat produced the message.

This satisfies the requirement that Telegram should not receive ambiguous cross-chat output.

### 10. Multiple Telegram bots per app instance
Support was added for a default Telegram bot plus additional bot configurations.

Each chat now stores a `telegram_bot_config_id`, allowing different chats to route through different Telegram bots.

This allows:

- several app chats on one default bot
- different app chats on different bots
- future chat reassignment between bots

### 11. Inbound Telegram routing for shared bots
When one Telegram bot is assigned to multiple app chats, inbound messages are routed to the chat that most recently emitted on that bot.

When that routing changes the active chat:

- the desktop app updates focus to that chat
- shared current-session sync is updated with it

This was the implemented multi-chat routing strategy for shared-bot operation.

## Cron Changes

### 12. Cron became global in the app
Cron scheduling and cron output were separated from ordinary session chat history.

The app now treats cron as a global surface instead of making cron behave like normal conversation turns in a single session.

### 13. Cron is still attributed to its source chat
Each cron job now stores origin metadata including:

- `origin_session_id`
- `origin_workspace`
- `origin_telegram_bot_config_id`
- originating model and tool-pack context

This preserves the connection between a cron job and the chat that created it.

### 14. Telegram cron output is bot-routed by origin chat
Even though cron is global in the app UI, Telegram output follows the originating chat's bot assignment.

So:

- the app has one global cron center or feed
- Telegram delivery goes to the bot assigned to the chat that created the cron job

That matches the later clarified requirement.

## Headless or Sleep Mode Changes

### 15. Headless mode support was added at the orchestration layer
The runtime now has headless or sleep-mode state and enforcement logic.

Headless mode is designed for situations where the desktop UI is not the active control surface and Telegram remains the primary live interface.

### 16. One sleep chat per bot
The final clarified rule is:

- one designated sleep chat per Telegram bot

This allows controlled background operation while still preventing uncontrolled multi-chat execution in sleep-oriented use.

### 17. Interactive behavior is restricted in headless mode
Only the designated sleep chat for the default bot may retain interactive pack access in headless mode.

Sleep chats belonging to additional bots are treated as non-interactive in headless mode.

This keeps the most dangerous machine-bound tool surface tightly controlled when the desktop UI is not active.

## Desktop UX and Settings Changes

### 18. Running indicators in the sidebar
The desktop sidebar now shows which chats are actively running.

This gives the user visibility into concurrent execution instead of hiding it.

### 19. Tools menu next to model controls
A dedicated `Tools` menu was added next to the model controls.

This lets the user:

- inspect enabled packs
- toggle packs per chat
- see why a pack is disabled or locked by another running chat

### 20. Chat settings for bot and sleep configuration
Per-chat settings now expose:

- assigned Telegram bot
- headless eligibility
- designated sleep-chat status for the relevant bot

### 21. Settings for Telegram bot management and concurrency
The app settings surface was extended to support:

- Telegram bot config management
- default bot assignment
- concurrent chat limits
- headless-mode configuration

## Data Model and API Changes

### 22. Session metadata was extended
Session summary and detail models were expanded to include:

- run state
- running status
- enabled tool packs
- available tool packs
- lock status
- assigned Telegram bot
- headless eligibility

### 23. New runtime and bot management APIs were added
New app/backend routes and actions were added for:

- tool-pack updates
- chat bot assignment
- headless eligibility
- orchestrator status
- runtime headless configuration
- Telegram bot CRUD operations

## Representative Files
The main implementation touched these areas:

- `shared/multi_chat_orchestrator.py`
- `shared/tool_packs.py`
- `shared/telegram_bot_config_store.py`
- `shared/cron_feed_store.py`
- `cli/models/session.py`
- `app_backend/session_bridge.py`
- `app_backend/app_server.py`
- `app_backend/runtime.py`
- `app_backend/cron_runtime.py`
- `telegram_bot/telegram_session_state.py`
- `telegram_bot/telegram_unified_agent.py`
- `telegram_bot/telegram_message_handlers.py`
- `telegram_bot/telegram_app.py`
- `telegram_bot/telegram_agent.py`
- `local_agent_runtime/cron_scheduler.py` (formerly `single_agent/cron_scheduler.py`)
- `desktop_app/renderer_client/src/desktop/DesktopConversationView.tsx`
- `desktop_app/renderer_client/src/desktop/DesktopSetupPanel.tsx`
- `desktop_app/renderer_client/src/desktop/DesktopAppShell.tsx`
- `mobile_app/client/src/screens/CronScreen.tsx`

## What This Work Intentionally Did Not Do
This change set did not attempt to make everything fully symmetrical in desktop UX and Telegram UX.

The core requirement was shared state truth, not identical presentation.

It also intentionally kept write safety at the workspace level rather than attempting per-file locking, because per-file locking would introduce a much higher risk of subtle race bugs around shell-based mutations.

## Result
This work moved EmploAI from a single-runnable-chat model toward a real multi-chat orchestration model with:

- controlled concurrency
- controlled interactive-tool ownership
- workspace-safe writing
- per-chat task boards
- bot-aware Telegram routing
- global cron with bot-based Telegram delivery
- headless or sleep-mode controls
- explicit tool-pack selection and pack-aware prompting

In short, the system now has the architectural base needed for several EmploAI chats to operate at once without collapsing shared state, machine control, or Telegram routing into ambiguity.
