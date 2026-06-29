# EmploAI

EmploAI is an agentic computer-control system that accepts tasks over Telegram and executes them on a live machine using LLM reasoning, browser automation, desktop input, OCR, persistent memory, and scheduled jobs.

## Why This Exists

Large language models can reason about tasks, but turning that reasoning into reliable action on a real computer is a separate systems problem. EmploAI was built to explore that problem in a practical way:

- give the model a controlled tool surface instead of direct unrestricted execution
- keep the system observable through screenshots, OCR, browser snapshots, and logs
- support long-running remote use on a Linux VPS, not only short local demos
- preserve enough memory and context to continue work across sessions

The result is not a chat bot with a few commands. It is a multi-layer execution system for real computer tasks.

## What The System Does

EmploAI can:

- receive tasks through a Telegram bot
- select from multiple LLM providers, including OpenAI, Anthropic, Gemini, xAI, DeepSeek, NVIDIA NIM, and OpenRouter
- read and edit files inside a workspace
- run shell commands
- search the web and fetch pages headlessly
- automate browser flows through Selenium or a Chrome extension bridge
- fall back to desktop automation with screenshots, OCR, and physical input
- persist long-term notes and recent session logs
- run recurring jobs through a scheduler

## Architecture

```text
User
  -> Telegram bot / companion app / CLI
  -> session runtime
  -> unified agent loop
     -> model adapter (OpenAI / Anthropic / Gemini / others)
     -> tool registry
     -> tool executor
        -> file and shell tools
        -> web tools
        -> browser automation
        -> desktop automation
        -> memory
        -> scheduler
  -> results, screenshots, logs, and follow-up context
```

### Interface Layer

- `telegram_bot/` is the primary operating surface. It handles authorization, command routing, session state, model selection, task execution, and user-facing messaging.
- `mobile_app/backend/` provides a companion backend for app pairing, session access, websocket chat, and job access. In the current codebase, this layer is additive and still being expanded.
- `cli/` contains a local terminal interface built around the same tool-oriented runtime.

### Agent Loop

The core loop lives in `shared/unified_agent.py` and the provider adapters in `shared/agents/`.

At a high level, the loop works like this:

1. Load the selected model configuration and the available tool schemas.
2. Send the current task, conversation history, and system context to the model.
3. If the model returns tool calls, execute them one by one.
4. Feed tool results back into the conversation history.
5. Repeat until the model returns a final response or the task is stopped.

This design keeps the model provider separate from the tool surface. The same task loop can run through different LLM APIs without rewriting the execution layer.

### Tools System

The tool surface is intentionally broad because the system needs to move between different environments during the same task.

Main tool groups:

- workspace tools: read, write, edit, and list files
- execution tools: run shell commands and change working directories
- web tools: search and fetch live pages
- browser tools: navigate, inspect ARIA snapshots, click by ref, type, wait, switch tabs, and capture screenshots
- desktop tools: describe the screen, OCR visible text, click coordinates, type text, press keys, manage windows, and open apps
- system tools: memory retrieval, memory updates, scheduler control, and sub-agent spawning

In the Telegram runtime, these handlers are wired in `telegram_bot/telegram_unified_agent.py`.

### Memory System

The memory layer is intentionally simple and inspectable.

- `MEMORY.md` stores curated long-term notes.
- `memory/YYYY-MM-DD.md` stores daily logs.
- `shared/memory.py` provides retrieval, append, and lightweight keyword search.

This avoids hiding state in an opaque database and makes the system easier to debug. It also fits the project goal: continuity across sessions with a format that is easy to inspect manually.

### Execution Layer

EmploAI does not rely on a single control mechanism. It uses multiple execution paths depending on the environment.

#### Browser Execution

- `single_agent/browser_tool.py` wraps Selenium and builds ARIA-style snapshots so the model can act on stable element references instead of guessing from raw HTML.
- `single_agent/extension_tool.py` adds a websocket bridge to a real Chrome session. This is important when tasks depend on logged-in state or sites that behave differently under automation.

#### Desktop Execution

- `telegram_bot/linux/desktop_tools.py` provides Linux-native screenshot, OCR, input, and window control using tools such as `scrot`, `xdotool`, `wmctrl`, `mss`, Pillow, and Tesseract.
- OCR is used as a fallback when DOM-level browser control is not enough or when the task moves outside the browser.

#### Scheduled Execution

- `single_agent/cron_scheduler.py` persists jobs in `jobs.json`, computes future runs, skips missed backfill on restart, and dispatches scheduled prompts through the same runtime.

## How A Task Flows

Example control flow for a real task:

1. A user sends a request through Telegram.
2. The session runtime loads model choice, workspace context, and recent memory.
3. The model receives the task and the tool schemas.
4. The model chooses an action, such as `browser_navigate`, `read_file`, or `ocr_screen`.
5. The tool executor runs that action and returns structured output.
6. The next turn uses that output to decide whether to continue, recover, or finish.
7. If the task needs recurring follow-up, it can be turned into a scheduled job.

The important point is that observation and action are part of the same loop. The model is not only generating text; it is iterating on evidence from the environment.

## Example Use Cases

- run a remote task from Telegram on a Linux VPS
- inspect a codebase, edit files, and run verification commands
- complete browser workflows that need real navigation and form interaction
- recover from browser limitations by switching to OCR and desktop input
- create recurring jobs such as briefings, monitoring checks, or scheduled research

## Tech Stack

### Core

- Python
- FastAPI
- WebSockets
- Pydantic

### Model Providers

- OpenAI
- Anthropic
- Google Gemini

### Browser And Desktop Control

- Selenium
- Chrome extension bridge over WebSocket
- Tesseract OCR
- Pillow
- `mss`
- `xdotool`
- `wmctrl`

### Interfaces

- Telegram Bot API
- Textual CLI
- companion app backend scaffold

## Repository Structure

```text
telegram_bot/          Primary remote interface and tool execution runtime
shared/                Provider-agnostic agent loop, memory, context, and shared runtime
single_agent/          Browser tools, extension bridge, and scheduler
mobile_app/backend/    Companion app backend and websocket scaffolding
app/                   Earlier FastAPI/web interface
bot_core/              Security, analytics, hooks, and file processing
deploy/vps/linux/      VPS setup for persistent headed Linux execution
tests/                 Unit, integration, and smoke tests
```

## Running The Project

This repository is under active development, so setup is still fairly manual.

### Prerequisites

- Python 3.10+
- Chrome or Chromium
- Tesseract OCR
- Telegram bot token
- API key for at least one model provider

### Basic Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Fill in the environment variables in `.env`, then start the Telegram bot:

```bash
cd telegram_bot
python telegram_agent.py
```

### Linux VPS Deployment

For a persistent remote desktop setup, see:

- `deploy/vps/linux/README.md`

That deployment uses a virtual display, headed Chrome, and Linux-native desktop tooling so the agent can keep operating even when no one is actively watching the session.

## Design Decisions And Challenges

### 1. Browser control needs multiple fallback paths

One control method is not enough. Some tasks work well through Selenium, some require a real logged-in Chrome session, and some only work through desktop-level input. The project therefore keeps all three paths available instead of pretending a single browser driver is always sufficient.

### 2. Observation is as important as action

Blind action loops are brittle. EmploAI uses browser snapshots, screenshots, OCR, and status checks so each next step is based on the current state of the environment rather than assumptions.

### 3. Memory should be inspectable

The system uses markdown files for curated memory and daily logs instead of a hidden storage layer. That makes debugging easier and keeps state portable.

### 4. Long-running operation matters

The Linux deployment is designed around persistent headed execution on a VPS. That is a different engineering problem from a local one-off automation script.

### 5. Remote control requires guardrails

The Telegram layer includes authorization and rate limiting because a remote execution system needs basic operational controls from the start.

## Current Limitations

- setup is still developer-oriented rather than one-command installation
- the companion app backend is present but not yet at feature parity with Telegram
- reliability still depends on the target environment, especially for UI-heavy desktop tasks
- some parts of the repository reflect active experimentation, not only polished production paths

## Future Work

- strengthen test coverage around cross-environment task execution
- improve state recovery after failed UI actions
- reduce duplication between older agent modules and the shared runtime
- expand the companion app path into a fuller control surface
- add stronger telemetry and task-level auditing for long runs

## Notes

This repository is best understood as a systems project: an attempt to connect reasoning, tools, memory, and remote execution into one controllable runtime.
