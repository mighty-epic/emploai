# MEMORY.md - Long-Term Memory

## User Preferences

*(Add user preferences here)*

## Key Events

*(Important events and decisions)*

## Lessons Learned

- The refined agent path in `single_agent/refined_agent.py` is not the authoritative live Telegram auto-mode tool exposure path and should not be treated as authoritative for live tool exposure.
- Live Telegram auto-mode tool exposure currently flows through `telegram_bot/telegram_chat_flow.py`, `telegram_bot/telegram_unified_agent.py`, `cli/agent_tools/executor.py`, and merged tool schemas from `get_auto_mode_extra_tools()` plus `single_agent.agent.AGENT_TOOLS`.
- Cron-triggered job execution is now being phased onto the live unified tool-loop path via `telegram_bot/cron_runner.py` and `telegram_bot/telegram_session_state.py`; `single_agent/refined_agent.py` may still be used by older spawned background paths but should no longer be the target path for cron work.

## Context

- Telegram bot startup entry file: `telegram_bot/telegram_agent.py`, which starts the bot and hands off to `telegram_bot/telegram_app.py`.
- Telegram bot architecture: startup/app wiring in `telegram_bot/telegram_agent.py` and `telegram_bot/telegram_app.py`; Telegram update/message handling in `telegram_bot/telegram_handlers.py`; live chat execution flow in `telegram_bot/telegram_chat_flow.py`; live prompt/tool exposure in `telegram_bot/telegram_unified_agent.py`; session state, spawn tool wiring, and cron scheduler wiring in `telegram_bot/telegram_session_state.py`.
- For future runtime/tool exposure debugging, check these live-path files first: `telegram_bot/telegram_chat_flow.py`, `telegram_bot/telegram_unified_agent.py`, `cli/agent_tools/executor.py`, `cli/agent_tools/definitions.py`, and `telegram_bot/telegram_session_state.py`.

- Dedicated agent Gmail account identifier: `emplo2146@gmail.com`.
- Dedicated agent Gmail password provided by user for in-session use only; do not expose it in normal responses.
- Browser extension setup steps that worked: close Selenium browser, open regular Chrome, go to Chrome extensions page, enable Developer mode, use Load unpacked on `/opt/emploai/browser_extension`, confirm `EmploAI Native Bridge 1.0` appears, optionally pin it to the toolbar, then user enables the bridge and the agent verifies by switching to extension mode and successfully creating a real Chrome task tab.
- Live cron delivery wiring lives in `telegram_bot/telegram_session_state.py` via async `announcement_callback` + async `spawn_callback`; scheduler announcements and spawned cron task completions are intended to message the user back in the same Telegram chat.
- User timezone for scheduled daily jobs is GMT+2; cron daily-at-time scheduling should be computed with a +2 hour offset rather than server local time.
- GitHub username provided by user: `mighty-epic`.
- GitHub token was provided by user for in-session use only; do not expose it in normal responses or store the raw token in long-term memory.
- When pushing my code changes for this project, push to the `mighty-epic/emploai` repository on branch `emplo-chnages`, not to any other repository unless the user explicitly says otherwise.
- From now on, after making code changes for this project, push them to the `mighty-epic/emploai` repository on branch `emplo-chnages` by default unless the user explicitly says not to.
- Preferred update workflow for this project: trace the live path end-to-end before patching; prefer the live Telegram/unified path over older refined-only paths; make careful minimal code changes; verify with syntax checks and targeted runtime/tool tests; restart the bot/runtime when code-path changes require reload; then re-test with a small controlled case before re-enabling real jobs/features.
- For cron/scheduler fixes specifically: inspect `telegram_bot/telegram_session_state.py`, `telegram_bot/cron_runner.py`, `telegram_bot/telegram_unified_agent.py`, and `single_agent/cron_scheduler.py`; verify both job state (`list_scheduled_jobs`) and real Telegram user-visible behavior; if a job loops/spams, disable/remove active jobs first to reach a safe state, then patch root cause, restart, run one tiny test job, and only then recreate real recurring jobs.
