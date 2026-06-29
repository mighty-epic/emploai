# Kraitos Social Posts

## X Thread: Rename and Positioning

### Post 1

Kraitos is the new name for EmploAI.

Same technical mission: a self-hosted AI operator layer that can run real computer tasks through browser, desktop, terminal, memory, and scheduled jobs.

kraitos.app

### Post 2

The core bet: agentic systems need observable control surfaces.

Kraitos does not just ask a model to "use the computer." It gives the loop structured tools: file operations, shell commands, browser snapshots, OCR, screenshots, and desktop input.

### Post 3

Browser automation is layered.

Kraitos can use Selenium, but it can also connect to a real Chrome session through a WebSocket extension bridge. That matters when tasks depend on active tabs, logged-in state, or sites that behave differently under automation.

### Post 4

When DOM control is not enough, the system can fall back to desktop observation.

Screenshots plus OCR make failures visible. The agent can recover by reading the screen, selecting windows, typing, and clicking through controlled desktop tooling.

### Post 5

The trust model is simple: self-host it, inspect it, constrain it.

Memory is plain Markdown. Logs and screenshots are visible. Authorization is explicit. Kraitos is built for people who want computer-use automation without a black box.

Project page during migration:
https://kraitos.app

## LinkedIn Post

Kraitos is the new public name for EmploAI.

The product direction is sharper now: Kraitos is a self-hosted AI operator layer for real computer tasks.

Most agent demos stop at chat or a clean browser sandbox. Kraitos is built around the messier systems problem: how do you let an LLM-driven loop act on a live machine while keeping the work observable, constrained, and recoverable?

The architecture is intentionally layered:

1. Browser snapshots expose stable element references instead of raw coordinate guessing.
2. A Chrome extension bridge can connect to a real user session when standard automation is too brittle.
3. OCR and screenshot fallback keep the loop grounded when DOM-level control fails.
4. Telegram, desktop, and CLI surfaces route tasks into the same tool-oriented runtime.
5. Memory and logs stay inspectable in plain files.

The brand is moving to Kraitos because the project is no longer just an "AI employee" concept. It is an operator system: browser, terminal, desktop, remote VPS workers, and scheduled workflows under one auditable control plane.

Domain:
https://kraitos.app

Project page during the migration:
https://kraitos.app

#AI #OpenSource #SelfHosted #DevOps #Automation #AgenticAI

## Reddit Draft

### Title

Show r/selfhosted: Kraitos, formerly EmploAI - a self-hosted AI operator layer for browser, desktop, terminal, and Telegram workflows

### Body

Hey everyone,

I am moving the project name from EmploAI to **Kraitos** and wanted to share the architecture with self-hosters and people building computer-use agents.

Kraitos is a self-hosted AI operator layer. It accepts tasks from Telegram, a desktop surface, or a CLI, then runs them on a live machine through a constrained tool loop.

What makes it different from a simple chatbot wrapper:

- Browser actions can use structured snapshots with stable references instead of raw HTML dumps or coordinate guessing.
- A Chrome extension bridge can connect to a real browser session for workflows that depend on logged-in state.
- If browser-level control fails, the system can fall back to screenshots, OCR, keyboard input, mouse input, and window management.
- Memory is plain Markdown, so state is inspectable and editable.
- Remote VPS operation is a first-class path, including Telegram control and scheduled jobs.

The trust boundary is the main design concern. Kraitos controls real machines, so the goal is not unchecked autonomy. The goal is an auditable operator loop where the user owns the runtime, credentials, authorization list, logs, memory, and deployment environment.

The new brand/domain:

https://kraitos.app

The public repo link will be added after it passes verification.

I would especially appreciate feedback on:

- the self-hosting path
- the browser bridge design
- what security docs you would expect before running an agent like this
- what demo would make the control model clearer
