# Work In Progress Tracker

> **All agents MUST check this file before starting any work.**
> 
> **All agents MUST add an entry here before modifying any files.**

---

## Active Work

<!-- Agents: Add your entries below this line -->

## [DONE] Task: Update CLI model list and contexts
- **Started**: 2026-01-22 23:26
- **Completed**: 2026-01-22 23:27
- **Files**:
  - cli/tui_app.py
  - WORK_IN_PROGRESS.md
- **Status**: Completed
- **Notes**: Update model contexts; remove Claude 3.x; add Claude Haiku 4.5; set default to Claude Haiku 4.5.

## [DONE] Task: Fix model picker + context max update
- **Started**: 2026-01-22 18:37
- **Completed**: 2026-01-22 18:41
- **Files**:
  - cli/tui_app.py
  - WORK_IN_PROGRESS.md
- **Status**: Completed
- **Notes**: Update model picker to select on click and refresh context size in status bar.


## [ACTIVE] Task: Critical Dual-Agent Optimization & isolated Testing
- **Started**: 2026-01-19 10:45
- **Files**:
  - dual_test/*
  - agent/dual_agent/memory_agent.py
  - agent/dual_agent/executor_agent.py
- **Status**: In Progress (Testing Phase)
- **Notes**: Moving work to a dedicated `dual_test` environment to iterate on the Dual-Agent logic without TUI overhead. 
  - **Model Upgrades**: Integrated Gemini 3 Pro (1M context) and Grok-2 (2M context) for the Memory Agent.
  - **Action-Masking Fix**: Resolved issue where observations would hide successful actions, causing loops.
  - **Loop Prevention**: Refined system prompts to force alternative approaches when an observation fails.
  - **Context Persistence**: Adjusted pruning logic to keep 80% of history for high-context models.
  - **Tool Restoration**: Synchronized full Selenium, OCR, and Desktop tools in the testing sandbox.

## [DONE] Task: make task details selectable and autoscroll
- **Started**: 2026-01-18 23:40
- **Completed**: 2026-01-18 23:42
- **Files**:
  - cli/tui_app.py
  - WORK_IN_PROGRESS.md
- **Status**: Completed
- **Notes**: Enable selection auto-copy and drag autoscroll in task details dropdown.

## [DONE] Task: Fix streaming line breaks
- **Started**: 2026-01-18 21:50
- **Completed**: 2026-01-18 21:55
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Ensure assistant stream starts on its own line after user message.


## [DONE] Task: Fix log order and Escape key behavior
- **Started**: 2026-01-18 21:15
- **Completed**: 2026-01-18 21:40
- **Files**:
  - cli/tui_app.py
  - cli/dual_agent.py
- **Status**: Completed
- **Notes**: Fixed a major UX bug where clicking the log would cause out-of-order log entries (now always appends to end). Also refined the Escape key logic so it immediately reverts to regular chat mode (double-tap to interrupt) once a dual-agent task is cancelled.

## [DONE] Task: Add streaming for default chat
- **Started**: 2026-01-18 21:20
- **Completed**: 2026-01-18 21:35
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Stream token-by-token for non-slash chat across all models.

## [DONE] Task: Fix "no running event loop" and "hidden dropdown" in dual-agent tasks
- **Started**: 2026-01-18 20:45
- **Completed**: 2026-01-18 21:10
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Resolved a subtle deadlock/race condition where background threads were interacting with Textual widgets directly. Improved the asyncio environment using `asyncio.run()` and switched to CSS classes for toggling the agent log visibility.

## [DONE] Task: Show context window stats near model
- **Started**: 2026-01-18 23:15
- **Completed**: 2026-01-18 23:15
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Added token count and context percentage to the status line near model.


## [DONE] Task: Add collapsible Detailed Agent Log
- **Started**: 2026-01-18 20:55
- **Completed**: 2026-01-18 21:05
- **Files**:
  - cli/tui_app.py
  - cli/dual_agent.py
- **Status**: Completed
- **Notes**: Implemented a `Collapsible` widget named "Agent Execution Details" hosting full thoughts and tool calls. Main log remains clean with high-level summaries.

## [DONE] Task: Keep input focused for log selection
- **Started**: 2026-01-18 20:50
- **Completed**: 2026-01-18 20:55
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Refocus input after log mouse-up to keep typing while preserving selection/copy.

## [DONE] Task: Remove /agent command
- **Started**: 2026-01-18 20:46
- **Completed**: 2026-01-18 20:47
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Removed deprecated /agent command as dual-agent functionality is now handled by /task.

## [DONE] Task: Tweak dual-agent prompt + browser start
- **Started**: 2026-01-18 20:15
- **Completed**: 2026-01-18 20:30
- **Files**:
  - agent/dual_agent/memory_agent.py
  - agent/dual_agent/executor_agent.py
- **Status**: Completed
- **Notes**: Reduce observation loops; auto-start Selenium Chrome on navigate.

## [DONE] Task: Fix CLI model routing
- **Started**: 2026-01-18 19:12
- **Completed**: 2026-01-18 19:30
- **Files**:
  - cli/tui_app.py
- **Status**: Completed
- **Notes**: Route Anthropic models via Anthropic client; use max_completion_tokens for gpt-5.

---

## Completed Work

<!-- USER will move completed entries here or clear them -->
