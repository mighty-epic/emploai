# Fleet System Details

## Purpose

This document defines how the fleet-scale EmploAI system should work in practice.

[main_vision.md](main_vision.md) describes the north star: EmploAI as an AI employee operating system where one human manager can control many worker instances. This document turns that vision into a decision-complete product spec for V1 behavior: roles, enrollment, task routing, concurrency, access, dashboard behavior, reports, and failure handling.

It is not an API, database, websocket, or migration spec. Engineering should use it to design those systems without inventing product behavior.

## V1 Object Model

One account owns one fleet in V1.

The fleet contains:

- `Instance`: one installed EmploAI app/runtime identity.
- `Machine`: a physical computer, VPS, or remote desktop environment that can host one or more instances/runtimes.
- `Manager`: the primary human control surface for the fleet.
- `Worker`: an execution unit that receives delegated tasks.
- `Group`: a manager-defined collection of workers.
- `Task`: a unit of work assigned to a worker.
- `Queue`: the per-worker ordered list of pending tasks.
- `Report`: the strict structured result produced by a worker task.
- `Chat`: a cloud-known conversation/session identity that can be reopened across manager, worker, mobile, Telegram, and future fleet surfaces.
- `Workspace`: a stable cloud identity for a project/folder, separate from any one machine's absolute filesystem path.
- `Workspace binding`: a machine-local path mapping for a workspace, such as this machine's current absolute folder path.
- `Grant`: permission for a worker or group to use a connector, credential, tool pack, file area, or app capability.
- `Lock`: a runtime claim over a scarce resource such as a workspace writer, browser profile, or interactive desktop.
- `Audit event`: a durable record of important fleet actions.

V1 has one primary manager per account/fleet. Future versions may add subordinate managers and company/org accounts.

Role changes require an unlink/reset flow. A manager can become a worker, or a worker can become a manager, only after clearing or migrating stale queues, cached grants, role permissions, active tasks, and local identity state. A role toggle must not silently preserve permissions from the previous role.

## Roles

### Manager

A manager is the human-facing control surface for the fleet.

The manager app has:

- `Chat`: direct conversation with the manager's own local agent.
- `Jarvis`: voice-first local agent mode.
- `Fleet` / `Other Computers`: the dashboard for workers and subordinate managers.

`Chat` and `Jarvis` remain first-class modes. Fleet mode must not replace or degrade the existing chat and voice surfaces.

On a manager instance, the Chat tab contains only the manager's own chat. It does not become a worker list, a fleet transcript, or a mixed feed. When the manager is solo, this chat behaves like the current normal chat surface with the default tool packs enabled.

The manager can assign tasks manually or ask the manager agent to delegate work. The manager agent can choose workers, monitor progress, redirect tasks, and compile results when the human asks for orchestration.

Managerial orchestration tools are enabled only once the manager has at least one worker or subordinate manager in the fleet. Before that, a manager behaves like a normal solo EmploAI instance with the default local agent tools.

The manager's default fleet tool surface should be orchestration and verification, not the full worker computer-control surface.

### Worker

A worker is an execution unit.

A worker can be:

- A local logical runtime on the same machine as a manager.
- A separate physical computer.
- A VPS or remote desktop environment.

A solo worker can keep normal multi-chat behavior. A managed worker can only run one active task at a time, whether that task came from the local UI, Jarvis, Telegram, mobile, or a manager.

Workers execute locally, report progress, ask for help when blocked, and return structured reports. Workers should feel like assigned employees, not separate user accounts.

## Startup Role Selection

On login or startup, an EmploAI instance chooses a role:

- `Manager`: used for the primary human-controlled computer.
- `Worker`: used for a machine or runtime that will execute delegated work.

Choosing `Manager` enables the Fleet tab. Choosing `Worker` keeps the simpler Chat/Jarvis interface.

If a manager has no workers below it and no manager above it, it may keep existing multi-chat behavior. If that manager gains workers below it or becomes subordinate to another manager in the future, it follows hierarchy concurrency rules.

## Worker Creation, Enrollment, And Identity

Workers should be easy to create without requiring one email address per worker.

V1 worker creation supports two paths:

- Local workers: a manager creates local logical workers immediately on the manager machine.
- Remote workers: a manager creates a one-time enrollment code for another computer or VPS.

Remote worker enrollment uses the one-time code only. The worker does not need an email/password login. The code should be short-lived, single-use, and bound to the manager's account/fleet.

Installer or setup tokens may be added for bulk VPS creation, but the V1 product behavior is the same: the token enrolls a worker into the manager's fleet without creating a separate user account.

Worker names are sequential and editable:

- Default names: `Worker-001`, `Worker-002`, `Worker-003`.
- Manager can rename workers.
- Optional group prefixes such as `Research-001` can come later.

The account owns the worker identity. Managers can rename, reset, delete, classify, and group workers from the Fleet dashboard.

Deleting or resetting a worker should revoke its fleet identity and optionally wipe local worker state: sessions, task queue, local tokens, cached grants, and worker-specific data.

## Cloud Persistence And Workspace Reconnection

The cloud should persist every manager, worker, machine, group, chat, task, queue, report, grant, lock summary, and audit event needed to reconstruct the fleet view after reconnect.

The cloud should also persist every chat's folder/workspace association, but it must not treat absolute filesystem paths as portable truth.

The correct model is:

- `chat_id` is stable across surfaces.
- `workspace_id` is stable across surfaces.
- `machine_id` identifies the computer/VPS/runtime host.
- `worker_id` or `manager_id` identifies who owns or is currently using the chat.
- Absolute paths are stored as machine-local workspace bindings.

Example:

- Cloud workspace: `workspace_id=wrk_123`, label `Client Reports`.
- Manager computer binding: `C:\Users\A\Documents\Client Reports`.
- Worker VPS binding: `/home/emplo/workspaces/client-reports`.
- New laptop binding: not known yet.

When a chat is opened on a machine that does not have a valid binding for that workspace, the app should not break and should not silently guess the path. It should show the chat history and mark the workspace as needing reconnection. The user or manager can then map the cloud workspace to a local folder on that machine.

Workspace reconnection should support:

- picking a new local folder for a known cloud workspace.
- remembering that machine's binding for future reconnects.
- showing chats as read-only or limited until the needed workspace binding exists.
- preserving chat history, reports, artifacts, and queue metadata even when the local path is missing.
- warning before running file-writing tasks if the workspace binding is missing or points somewhere unexpected.

This gives every surface better control over chats without making the system fragile when a user moves to a new computer, changes drive names, syncs a repo to a different path, or recreates a VPS.

## Fleet Dashboard UX

The Fleet tab exists only for manager instances.

The Fleet UI has two main regions:

- A compact manager chat in a second left sidebar.
- An adaptive, scrollable worker gallery in the main window.

The compact manager chat in Fleet mode is the same manager chat as the Chat tab, adapted to the Fleet layout. It should preserve the same conversation identity, message history, steering behavior, and normal assistant behavior. The difference is layout and available fleet context, not a separate manager personality or duplicate chat.

The manager sidebar has tabs at the top:

- `Manager` is open by default.
- Clicking worker cards opens compact worker chat tabs beside the Manager tab.
- These tabs keep the worker conversation available without leaving the Fleet gallery.

The main worker gallery adapts to screen width:

- 2 to 5 columns depending on available width.
- No large always-on video preview grid by default.
- Cards and rows should be compact; outputs, status, and tool summaries should be thinner than the normal chat UI.

Each worker card shows:

- Worker name.
- Worker status.
- Current task.
- Queue count or short queue preview.
- Compact latest input.
- Compact latest output.
- Compact recent tool-call/evidence summary.
- Latest structured report status when available.

Remote workers show low-rate screenshot previews under the status area while the card is visible and the worker is active. Previews pause when the card is offscreen or the worker is idle to save bandwidth.

Local workers show a placeholder preview. Clicking it opens that worker chat tab, where the manager can talk directly to the worker.

Clicking any worker card opens a compact worker chat tab in the manager sidebar while keeping the gallery visible.

Manager chat supports two routing styles:

- Broad natural language: the human asks the manager agent to plan and delegate a project.
- Explicit targeting: the human can mention workers such as `@Worker-003` or select worker cards/groups before sending.

Bulk or group dispatch requires confirmation with target list and queue estimate.

## Task Assignment And Queues

When the manager sends work to a worker, that work becomes a task assigned to that worker.

Queues are per-worker:

- Default order is FIFO.
- The manager can manually reorder queued tasks.
- Busy workers queue new tasks by default.
- Local user tasks and manager-assigned tasks share the same active-task lock for that worker.

Task states are:

- `queued`
- `running`
- `paused`
- `blocked`
- `needs_review`
- `completed`
- `failed`
- `stopped`
- `canceled`

If a worker is idle, it starts the next queued task. If the worker is already running, new tasks wait in that worker's queue.

Redirecting a running worker pauses the current flow, injects the new direction, and records that the task was redirected. It should preserve useful context rather than destroying the task unless the manager explicitly stops it.

If a worker is blocked, it pauses and asks the manager for help with an exact blocker. It should not silently abandon the task or start the next queued task unless the manager tells it to.

If a worker goes offline, the manager dashboard marks it offline/stale and preserves its queue and running-task state. The manager can reassign or cancel queued/running tasks. If the worker reconnects, it resumes or reconciles with the preserved task state.

## Worker Reports And Manager Index

A worker's final output is no longer just a final chat message. It is a strict structured report.

Required report fields:

- `status`: completed, blocked, stopped, failed, needs_review, or canceled.
- `summary`: what the worker did.
- `evidence`: links to artifacts, files, screenshots, screen summaries, command outputs, or other proof.
- `artifacts`: produced files, links, screenshots, or deliverables.
- `blockers`: what prevented completion, if anything.
- `confidence`: how certain the worker is that the task is done correctly.
- `next_suggested_action`: what the manager or another worker should do next.

The worker model should produce this report by contract. The runtime should validate required fields and repair or create a fallback report if the worker final is missing required structure.

Reports feed a realtime manager-readable index.

The manager index stores:

- Worker name and identity.
- Worker status and current task.
- Worker queue state.
- Latest task finish report.
- Historical completed task reports.
- Task metadata.
- Artifact metadata.
- Searchable summaries.

The manager agent queries this index on demand to avoid context bloat. The full fleet history should not be injected into every manager turn.

Search targets are workers, tasks, and reports. Full transcripts and raw tool logs remain available on demand but are not the default RAG/search corpus.

## Manager Tools And Verification

The manager default tool surface should be lean.

Default manager tools should focus on:

- Listing workers and groups.
- Inspecting worker status.
- Assigning worker or group tasks.
- Reading queues.
- Reordering queues.
- Pausing, resuming, stopping, redirecting, or reassigning tasks.
- Searching worker/task/report index.
- Inspecting reports and artifacts.
- Checking recent screenshots or screen summaries.
- Opening worker transcript/tool timeline on demand.

Workers keep the computer-control tools needed to execute tasks: browser, desktop, files, shell, connectors, credentials, and other assigned capabilities.

The manager should be able to verify physically whether a worker did the work. V1 verification includes worker reports, artifacts, produced files, recent screenshots or screen summaries, and task evidence. Live control of a worker screen is not required for V1, but optional live viewing may exist where already supported.

## Temporary Tool Grants

Any manager or worker can request temporary tool packs when it needs capabilities outside its current tool surface.

Tool pack requests include:

- requesting agent
- current task
- requested tool pack
- reason
- risk level if known
- requested turn count

Manager approval is required by default. The manager can approve, deny, or reduce duration.

Temporary grants expire automatically. Default maximum duration is 10 model/tool turns.

Temporary tool grants should be audited and visible in the task timeline. When the grant expires, the tool pack is removed from the agent's available tools.

## Planners

Every agent should have a planner for consistency.

Worker planners focus on completing the assigned task, verifying completion, avoiding repeated failed methods, and asking for help when blocked.

The manager planner has a different system prompt. It focuses on decomposition, assignment, verification, retries, worker coordination, queue management, and final synthesis across worker reports.

## Multi-Chat And Resource Conflict Rules

The current multi-chat capability remains valuable, but hierarchy changes when it is safe to use.

Rules:

- A solo manager or solo worker can keep existing multi-chat behavior.
- Once an instance has a manager above it or workers below it, it can only have one active run at a time.
- If a managed worker is already running, local users cannot start another run in a different chat without queueing or stopping the current task.
- The UI should explain the active task and offer to queue the new request or stop the current task when allowed.
- No two active chats in the same workspace can both have file write capability.
- Only one active interactive worker per machine may use screen, mouse, keyboard, live browser profile, or app control at a time.
- Busy workers queue new manager-assigned tasks by default.

These rules prevent workers from corrupting shared files, fighting over the same browser, or typing into the wrong window.

## Same-Machine Worker Isolation

Same-machine workers are allowed in V1, but only in a limited, isolated form.

By default, same-machine workers should have:

- Separate workspace unless explicitly shared.
- Separate browser profile unless explicitly shared.
- Separate session state.
- Separate task queue.
- Separate logs and artifacts where practical.
- Tool locks for file writes and interactive desktop control.

If isolation is not possible for a resource, the system should serialize access or block unsafe parallel runs.

Same-machine workers should not be presented as fully parallel desktop employees unless their interactive resources are genuinely isolated.

## Credentials, Connectors, And Permission Grants

Credentials and connectors live in the account vault.

The manager grants access to specific workers or groups. A worker should only receive the credentials, connectors, files, apps, and tools needed for its assignment.

Roles can guide behavior and default connector bundles, but roles are not the core access decider. The core access decider is the explicit grants attached to a worker or group.

Models must never see raw passwords, OAuth tokens, API keys, recovery codes, or session tokens. Workers can use brokered credentials and connectors, but the secrets remain hidden from model context, transcripts, logs, artifacts, Telegram, and mobile sync.

Credential and connector use should be auditable without exposing secret values.

## Delegation Modes

The manager agent supports three delegation modes.

### Ask For Review

The manager agent drafts a delegation plan and waits for human approval before assigning tasks to workers.

### Proceed Safely

This is the default mode.

The manager agent can delegate normal tasks to authorized workers, queue work, monitor progress, and compile results. It asks for confirmation before broad dispatch, high-risk actions, unusual scope expansion, or actions that may affect external users, money, credentials, public posting, deletion, or sensitive data.

### Full Permissions

The manager agent can dispatch authorized workers freely and operate the fleet with minimal interruption.

This mode still respects hard permission limits, tool safety, credential grants, user-defined restrictions, and legal/safety boundaries. It does not allow the manager agent or workers to access secrets they were not granted.

## Remote Transport

Remote worker communication should extend the existing cloud control plane.

V1 should not introduce a separate transport for remote workers. The cloud control plane should evolve from mobile-to-one-desktop routing into fleet routing:

- worker registry
- worker presence
- manager presence
- task dispatch
- queue updates
- status events
- report events
- screenshot or screen-summary updates
- audit events

Execution remains local to the worker. Identity, routing, shared state, and realtime fan-out live in the control plane.

## Audit Logging

V1 requires fleet action auditing.

Audit events should cover:

- worker enrollment
- worker deletion/reset
- worker rename/group changes
- grant creation/removal
- task assignment
- task pause/resume/stop/redirect/reassign
- queue reorder
- temporary tool grant request/approval/denial/expiry
- credential or connector use
- worker report completion

Audit logs should avoid raw secret values and should be useful for manager review and debugging.

## V1 Acceptance Scenario

The core V1 acceptance scenario:

1. A user signs in on one manager computer.
2. The user chooses Manager mode.
3. The manager creates one local logical worker.
4. The manager creates a one-time enrollment code.
5. A second computer or VPS enrolls as a remote worker using that code, without worker email/password login.
6. The Fleet dashboard shows both workers with names, statuses, queues, and latest activity.
7. The manager manually assigns a task to one worker.
8. The manager asks the manager agent to delegate a broader task, and the manager agent assigns work to an appropriate worker.
9. A busy worker queues a second task.
10. A worker produces a strict structured report.
11. The manager index updates in realtime with worker status, queue state, report, and artifact metadata.
12. The manager verifies the result through report evidence, artifacts, and recent screenshot/screen summary.
13. A remote worker disconnects; the dashboard marks it offline and preserves queue/running state.
14. The manager reassigns or cancels work, or the worker reconnects and reconciles state.
15. Lock rules prevent file-write conflicts and interactive desktop conflicts.

If this scenario works, V1 has proven the manager/worker system rather than just a visual dashboard.

## End-State Direction

The end-state system is a company-scale AI employee platform.

In that state:

- A company account can control hundreds or thousands of workers.
- Managers can organize workers into departments and teams.
- Top-level managers can manage subordinate managers.
- Worker roles can include default behavior, connector bundles, and specialized tool policies.
- The manager agent can decompose large goals, assign work, monitor execution, recover from blockers, and synthesize final outcomes.
- Mobile, Telegram, and Jarvis can all act as command surfaces for the same fleet.

The core idea stays the same: execution remains local to the worker, identity and routing live in the control plane, and the manager surface coordinates the workforce.
