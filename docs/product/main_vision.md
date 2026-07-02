# Main Vision: Fleet-Scale EmploAI

## North Star

EmploAI is not only a personal desktop agent. The larger vision is an AI employee operating system: one human manager can control a fleet of EmploAI workers across many computers, VPSs, and safe same-machine runtimes.

The product should let a company install EmploAI on a large number of machines, designate one or more manager instances, and use those managers to direct many worker agents. Each worker acts like an employee with access to its assigned computer, tools, files, applications, credentials, connectors, and workspace. The manager can assign tasks, monitor progress, redirect work, and gather results without manually operating every machine.

This is the reason the desktop app originally had space for `This Computer` and `Other Computers`. The third surface should evolve into a real fleet dashboard where the manager can control many EmploAI instances, not merely a paired phone or a single remote desktop.

## Existing Foundation

The current EmploAI system already contains the pieces needed to move toward this vision:

- The desktop runtime owns real execution: local tools, files, browser control, screen vision, OCR, shell commands, and app control.
- The cloud login and remote control plane already provide identity, device records, pairing, shared state, websocket routing, and desktop presence.
- Mobile and Telegram already act as remote control surfaces that can send tasks into a desktop runtime.
- The desktop UI already contains a disabled `Other Computers` concept, which should become the fleet view.
- The multi-agent work already points toward multiple logical agents operating from one environment.

This document supersedes the older framing where EmploAI was only a personal app connected to one user's own desktop. That use case still matters, but it becomes the smallest version of the larger product: one manager, one worker, one machine.

## Roles

### Manager

A manager instance is the human-facing control surface for the fleet.

The manager desktop should have:

- `Chat`: the normal direct conversation with the manager's own local agent.
- `Jarvis`: the voice-first local agent mode.
- `Fleet` / `Other Computers`: the dashboard for controlling worker and subordinate manager instances.

A manager can prompt one worker, multiple selected workers, or an entire group such as Research, Sales, Support, Engineering, Operations, or Admin. The manager's own agent should also be able to delegate work, monitor workers, redirect tasks, and compile results for the human manager.

### Worker

A worker instance is an execution unit.

A worker should have only the local work surfaces it needs, primarily `Chat` and `Jarvis`. It receives delegated work, executes on its assigned computer or runtime, asks for help only when blocked, and reports progress and final results back to its manager.

Workers are not subordinate chatbots. They are local agents with real computer access, scoped tools, scoped credentials, and assigned responsibilities.

### Hierarchy

The hierarchy should always preserve authority:

- A manager can control a worker.
- A manager can control another manager when a larger fleet needs multiple layers.
- A worker can never control a manager.

This supports small teams and large organizations without changing the basic model. A single manager may control a few workers, or a top-level manager may coordinate multiple department managers that each coordinate their own workers.

## Fleet Enrollment

The fleet must not require one email account per worker. A company or user should be able to create many workers under one account.

Enrollment should be easy enough for a manager to create workers on new computers, VPSs, or safe same-machine runtimes. A likely flow is:

- The manager creates a short-lived worker enrollment code or installer token.
- A new EmploAI instance starts in setup and chooses `Worker`.
- The worker enters the enrollment code or receives the token from the installer.
- The control plane registers the worker under the manager's account.
- The worker receives an automatic identity such as `Worker-001`, `Worker-002`, or `Research-003`.

Managers should be able to rename, reset, delete, classify, and group workers. Worker identity should be operational, not bureaucratic: easy to create, easy to replace, and easy to understand from the dashboard.

## Worker Units

A worker can be:

- A separate physical computer.
- A VPS or remote desktop environment.
- A logical worker runtime on the same machine as a manager or other workers, as long as capabilities do not conflict.

One machine may contain:

- One manager and no workers.
- One manager and many logical workers.
- Zero managers and one or more workers.

Same-machine workers are useful when tasks do not compete for the same interactive desktop, browser profile, workspace, local files, or credentials. If workers need the same scarce resource, the system should isolate them or prevent unsafe parallel use.

## Manager Experience

The manager's third tab should become a fleet dashboard.

The dashboard should show:

- All workers and subordinate managers attached to the account.
- Groups and departments.
- Online, offline, idle, working, blocked, and failed states.
- Current task per worker.
- Recent transcript and tool timeline.
- Produced artifacts and files.
- Optional live screen view for a worker when the manager needs to inspect or intervene.

The manager should be able to:

- Send a prompt to one worker.
- Send the same prompt to multiple workers.
- Assign a task to a group.
- Ask the manager agent to split a larger task across workers.
- Pause, stop, reset, or reassign worker tasks.
- Review worker reports and combine them into a final result.
- Move workers between groups or roles.

The worker should operate independently once assigned work. It should not require constant approval for normal progress. It should report status, ask for help when blocked, and escalate sensitive actions according to its role permissions.

## Access And Security

Fleet control requires stronger access boundaries than a personal desktop agent.

Access should be role-scoped by worker or group:

- A research worker may have browser, files, and read-only document access.
- A support worker may have inbox and customer communication access.
- An engineering worker may have repository, terminal, and issue tracker access.
- An operations worker may have scheduling, reporting, and dashboard access.

Workers should only receive the connectors, credentials, files, applications, and tools needed for their assigned job. Company-wide credentials should not automatically become available to every worker.

Credentials and connectors should remain brokered. A worker can use an authorized capability, but the model should not see raw passwords, OAuth tokens, API keys, recovery codes, or session tokens. Secrets should be usable by the agent, not readable by the agent.

The manager dashboard should provide observability without creating unnecessary leakage. The default view should show status, current task, transcript/tool timeline, and artifacts. Live screen viewing should be available when needed, but it should be treated as a supervision feature.

## Product Ambition

The goal is scalable AI labor coordination.

EmploAI should let a manager control an army of local agents that perform everyday computer work like employees: reading information, creating files, using web apps, managing communication, running workflows, coordinating tasks, and reporting outcomes.

Remote control is only the transport layer. The real product is the ability to create, organize, supervise, and direct many AI workers across many computers from one manager surface.

In the smallest case, EmploAI is one person controlling one local agent. In the larger case, EmploAI is a company-scale manager platform where one human can direct hundreds or thousands of workers without needing one login, one email, or one manual setup flow per worker.

## Non-Goals For This Vision Document

This document does not define exact APIs, database schemas, migrations, or implementation tickets.

It also does not turn EmploAI into a generic connector marketplace. Connectors and saved credentials matter only because they let workers perform real employee tasks on approved surfaces.

The implementation should continue to build on the existing EmploAI architecture: desktop execution, cloud identity and routing, mobile and Telegram as control surfaces, and the unified agent runtime as the worker brain.
