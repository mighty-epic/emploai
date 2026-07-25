# Fleet System Details

> This document preserves the current Fleet execution behavior and implementation baseline. The authoritative destination contract is [emploai_company_operating_system_and_fleet_ux_spec.md](emploai_company_operating_system_and_fleet_ux_spec.md), which controls product behavior and supersedes this file's Fleet-dashboard UX where they differ.

## Purpose

This document defines how EmploAI's Fleet execution infrastructure should work in practice.

[main_vision.md](main_vision.md) describes the north star. [company_system_details.md](company_system_details.md) defines the locked company operating layer and contains the canonical shared glossary. Locking it does not authorize application implementation. This document defines the underlying V1 execution behavior: computers, identities, pairing, task routing, concurrency, access, reports, and failure handling.

It is not an API, database, websocket, or migration spec. Engineering should use it to design those systems without inventing product behavior.

Fleet and Company are separate layers. Fleet answers where work executes, who owns an identity, which route reaches it, and what that route permits. Company answers why work exists, which manager is responsible, and whether an objective was accepted. Company organization must not replace or mirror the computer topology.

## V1 Object Model

V1 has no hosted user, company, or fleet account. A fleet is the local hierarchy formed by explicit parent-child computer pairings.

The fleet contains:

- `Computer`: a physical computer, VPS, or remote desktop environment running one EmploAI installation and owning its local state.
- `Manager`: the one mandatory orchestration identity on a computer.
- `Default Worker`: the mandatory protected execution identity owned by that computer's manager.
- `Worker`: an optional additional execution identity owned by that computer's manager.
- `Parent pairing`: the one optional authenticated relationship placing a computer beneath another computer's manager.
- `Child computer`: a directly paired computer whose manager and published workers are visible to its parent.
- `Fleet group`: a manager-local routing primitive for a collection of directly addressable workers. It is not a second user-facing organization model, does not change identity ownership, and may serve as compatibility data or an implementation detail beneath a company department.
- `Task`: a unit of work assigned to a worker.
- `Queue`: the per-worker ordered list of pending tasks.
- `Report`: the strict structured result produced by a worker task.
- `Chat`: a locally persisted conversation/session owned by one manager or worker identity.
- `Workspace`: a stable logical project/folder identity in the local fleet, separate from any one machine's absolute filesystem path.
- `Workspace binding`: a machine-local path mapping for a workspace, such as this machine's current absolute folder path.
- `Grant`: permission for a worker or group to use a connector, credential, tool pack, file area, or app capability.
- `Lock`: a runtime claim over a scarce resource such as a workspace writer, browser profile, or interactive desktop.
- `Audit event`: a durable record of important fleet actions.

Every computer has exactly one protected active manager and begins with one deletable default worker. A computer may have one parent, may have many direct children, and may be both a child and a parent. There is no global server that owns or flattens the hierarchy.

Manager and worker authority is structural rather than a startup toggle. The local manager cannot be deleted or converted into a worker. Default and additional workers are removable and configurable; no worker can be converted into a manager.

## Why There Is No Cloud Login Or Account

EmploAI deliberately avoids a hosted login and account system. The fleet controls real computers and can touch private files, applications, connectors, and credentials. A central EmploAI account would create an unnecessary dependency and a high-value copy of company topology, activity, and access metadata.

The accountless model means:

- Local EmploAI remains usable when the internet or any EmploAI-operated service is unavailable.
- Each computer is authoritative for its identities, sessions, memory, workspaces, tools, secrets, queues, reports, and detailed history.
- Pair credentials are generated during explicit computer pairing and stored only on the paired computers.
- Yggdrasil supplies encrypted network transport, while EmploAI pair authentication and role permissions authorize application requests.
- Parents receive only the published directory and operational information needed to manage direct children; they do not receive a silent copy of the child's full local state.
- Removing a pairing revokes that parent-child route without requiring an external identity provider or account recovery flow.

Mobile, Telegram, and future command surfaces attach to a chosen local installation. They are optional interfaces, not the authority that owns the fleet or company.

## Roles

### Manager

A manager is the human-facing control surface for the fleet.

The manager app has:

- `Chat`: direct conversation with the manager's own local agent.
- `Jarvis`: voice-first local agent mode.
- `Company`: objectives, workforce, attention, and a `Computers` page containing Fleet infrastructure for local workers and direct child computers.

`Chat` and `Jarvis` remain first-class modes. Company must not replace or degrade the existing chat and voice surfaces.

When the local manager identity is selected, Chat contains only that manager's chat. It does not become a worker list, a fleet transcript, or a mixed feed. Selecting a local worker opens that worker's direct chat with its own execution profile.

The manager can assign tasks manually or ask the manager agent to delegate work. The manager agent can choose workers, monitor progress, redirect tasks, and compile results when the human asks for orchestration.

The manager always has its role-locked managerial tools because its default worker always exists. Its default tool surface is orchestration, memory, automations, and verification. The user may explicitly enable compatible execution tool packs on a manager when direct execution is useful; this never removes its managerial authority or gives a worker managerial tools.

### Worker

A worker is an execution unit.

A worker can be:

- The default worker on its manager's computer, when one exists.
- An additional specialized worker on that same computer.
- A worker published upward from a directly paired child computer.

A physical computer or VPS is never itself a worker. It is a complete EmploAI node with its own manager and workers.

A worker always belongs to its local manager. A worker can have persistent direct chats, while delegated tasks receive isolated task sessions. A worker can only run one interactive or otherwise resource-conflicting task at a time, whether that task came from the local UI, Jarvis, Telegram, mobile, its local manager, or a parent manager.

Workers execute locally, report progress, ask for help when blocked, and return structured reports. Workers should feel like assigned employees, not separate user accounts.

## Per-Computer Startup Baseline

Startup does not ask the user to choose whether the installation is a manager or worker machine. An idempotent local reconciler ensures the same baseline on every computer:

```text
Computer
├─ Manager
├─ Default Worker
├─ Optional additional workers
└─ Direct child computers
```

The manager is the default Chat identity and the only protected identity. The default worker is created initially, remains deletable, and receives the standard execution profile. An explicit deletion is persisted and startup must not silently recreate it; creating another worker may establish a new default. Repeated startup or reconnect must never duplicate identities and must not start model inference merely to establish the baseline.

Chat and Jarvis select local identities only. Company is the operating surface; its `Computers` page owns local hierarchy management and remote child computers. Pairing the computer to a parent publishes its visible local manager and workers upward but does not replace or demote its local manager.

## Parent-Child Computer Structure

A computer may have at most one direct parent and any number of direct children:

```text
Top-level computer
├─ Local manager
├─ Local workers
└─ Direct child computer
   ├─ Child manager
   ├─ Child workers
   └─ Direct grandchild computer
```

The parent manager has two distinct ways to use a child:

- Delegate execution to the child's published default worker or another explicitly selected published worker.
- Delegate coordination to the child manager, allowing that manager to choose among its own local workers or children.

Every delegation carries an explicit `local` or `child` scope plus its destination computer and identity. Scope is request data, not a hidden global mode. An unqualified local action routes to the local default worker. Naming a child computer routes execution to that child's default worker. Asking to coordinate a child routes to its manager. An explicit identity selection overrides automatic selection.

A parent sees direct children only. It does not import grandchildren into its own worker list or bypass the child manager. Work for a grandchild is sent to the direct child manager, which applies its local routing, queue, capability, and safety rules.

Company-scale visibility does not weaken this boundary. A child manager may publish aggregate objective progress, capacity, blockers, risks, and accepted results upward, but the parent still routes control and requests for detail through that child manager.

The child publishes only the minimum directory needed upstream: computer label, identity label, role, status, default marker, visibility, and capability tags. Chats, absolute paths, provider state, credentials, secret values, and raw tool payloads remain local unless a specific delegated task returns approved evidence or artifacts.

Connection permissions determine whether a parent may delegate to the manager, use existing workers, request new workers, configure child manager tool packs, start EmploAI, or manage updates. Changing these permissions changes what the parent can request; it does not grant a worker manager authority. Removing the pairing removes the route while leaving both computers' local managers, workers, chats, and files intact.

## Worker Creation, Enrollment, And Identity

Workers should be easy to create because they are local identities, not users.

V1 worker creation supports two paths:

- Local workers: a manager creates local logical workers immediately on the manager machine.
- Remote capacity: a manager pairs another computer or VPS as a child; that child already owns its manager and default worker.

Computer pairing uses a short-lived, single-use code. It authenticates one explicit parent-child relationship and exchanges persistent pair credentials directly between those installations. It does not create an email/password identity, hosted membership, or remotely owned worker.

Installer or setup tokens may be added for bulk VPS creation, but their role is still to automate direct computer pairing, never to create an account.

Worker names are sequential and editable:

- Default names: `Worker-001`, `Worker-002`, `Worker-003`.
- Manager can rename workers.
- Optional descriptive prefixes may come from a worker profile or company department without changing the worker's stable identity.

The source computer owns each worker identity. Its local operator can rename, reset, delete, classify, and group any worker, including the default worker. A parent can act only through the permissions granted by the child and can never delete the child's protected manager.

Deleting or resetting a worker should revoke its fleet identity and optionally wipe local worker state: sessions, task queue, local tokens, cached grants, and worker-specific data.

## Local Persistence And Workspace Reconnection

Each source computer persists its own manager, workers, chats, tasks, queues, reports, grants, locks, audit events, and workspace bindings. A parent persists only its pairing record and the direct-child summaries, assignments, reports, and evidence needed to reconstruct its Computers view after reconnect.

No parent or shared service should treat an absolute filesystem path from another computer as portable truth.

The correct model is:

- `chat_id` is stable on its source computer and across the local surfaces allowed to open it.
- `workspace_id` is a stable logical identifier exchanged only when a delegated task needs a matching binding.
- `machine_id` identifies the computer/VPS/runtime host.
- `worker_id` or `manager_id` identifies who owns or is currently using the chat.
- Absolute paths are stored as machine-local workspace bindings.

Example:

- Logical workspace: `workspace_id=wrk_123`, label `Client Reports`.
- Manager computer binding: `C:\Users\A\Documents\Client Reports`.
- Worker VPS binding: `/home/emplo/workspaces/client-reports`.
- New laptop binding: not known yet.

When delegated work refers to a workspace that does not have a valid binding on the destination computer, the app should not silently guess a path. It should mark the task as needing a workspace binding so the local user or manager can map the logical workspace to a local folder.

Workspace reconnection should support:

- picking a new local folder for a known logical workspace.
- remembering that machine's binding for future reconnects.
- showing delegated tasks as read-only or blocked until the needed workspace binding exists.
- preserving chat history, reports, artifacts, and queue metadata even when the local path is missing.
- warning before running file-writing tasks if the workspace binding is missing or points somewhere unexpected.

This gives every surface better control over chats without making the system fragile when a user moves to a new computer, changes drive names, syncs a repo to a different path, or recreates a VPS.

## Computers And Fleet UX

The current top-level Fleet destination becomes `Company`. The underlying infrastructure remains available on Company's `Computers` page; this is a navigation change, not removal of Fleet capabilities.

> The whole-company operating model and decision-complete Fleet information architecture, layouts, flows, terminology, state models, accessibility requirements, and edge-case behavior are defined in [emploai_company_operating_system_and_fleet_ux_spec.md](emploai_company_operating_system_and_fleet_ux_spec.md). That document treats Fleet as an expansion of the current implementation and supersedes the UX guidance in this section where the two differ.

`Computers` exists on every desktop because every computer has a manager. Its controls are role-aware:

- A selected manager can inspect the local node, pair computers, refresh connection state, configure permitted child settings, inspect published identities, and route work through direct children.
- A selected worker sees a focused My Work surface elsewhere in Company and cannot inherit pairing, connection, child-settings, delegation, update, or manager-tool controls.
- Reconnects, polling, and navigation cannot change the selected identity or briefly render another role's controls.

The page shows the local computer and direct child computers, not a flattened company org chart. A child card exposes its connection state, manager route, published worker count, pending attention, latest confirmed activity, and a dedicated settings entry. Offline or incompatible state is visible on the card before opening its detail page.

Selecting a computer opens a dedicated page with predictable back navigation. Infrastructure detail includes only the sections relevant to that computer: connection recovery, runtime/update controls, published identities, permission requests, recent execution activity, reports, and optional view-only preview. Empty and inactive sections collapse instead of preserving dead space.

Worker organization and task activity belong to Company's `Workforce` and `Work` pages. Worker summaries remain compact and may show status, current task, queue count, latest milestone, capability tags, and report state. A view-only screenshot is secondary evidence, loads only when visible or explicitly requested, and must not dominate the default layout.

The compact Company manager chat, where present, reuses the same manager chat identity and history as Chat. It is not a second manager personality or duplicate session. Clicking a worker may open that worker's direct chat without replacing the surrounding Company context.

Manager chat supports broad natural-language delegation and explicit targeting. Bulk or department dispatch requires a target-and-queue preview and confirmation. Every dispatch displays its issuing manager, destination computer, manager or worker identity, and resulting queue state.

## Task Assignment And Queues

When the manager sends executable work to a worker, that work becomes a task assigned to that worker. A company objective may link several tasks, but objective ownership and acceptance are defined in [company_system_details.md](company_system_details.md).

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

Interactive or background behavior is derived from the task's requested resources, not from a second worker role. An interactive task claims the relevant desktop, browser, or application lock. Compatible background tasks may overlap only when all workspace, browser, credential, and compute locks allow it.

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

A valid completed report ends worker execution; it does not automatically accept a company objective. The owning manager reviews success criteria and evidence through the Company work lifecycle, then accepts the objective or requests linked rework.

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

- Listing workers and Fleet routing groups.
- Inspecting worker status.
- Assigning worker or routing-group tasks.
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

The current multi-chat capability remains valuable, but resource use determines when it is safe. Interactivity is a task property, not a permanent worker type.

Rules:

- Direct manager and worker chats can remain persistent and independent from delegated task sessions.
- Each identity may run concurrently only when its tools and underlying resources do not conflict.
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

Credentials and connectors live in a local encrypted/brokered store on the computer that uses them. There is no shared account vault.

The local manager grants access to specific local workers or Fleet routing groups. A parent may request that a child use a published capability, but the child manager enforces the request locally. A worker should only receive the credentials, connectors, files, apps, and tools needed for its assignment.

Roles and company departments can guide behavior and default connector bundles, but they are not the core access decider. The core access decider is the explicit grants attached to a worker or Fleet routing group. Company responsibility never creates technical access.

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

Remote communication uses direct authenticated connections between paired computers over Yggdrasil. There is no hosted routing or identity control plane.

Each computer runs a persistent Fleet host independently of the visible Electron window. Parent and child exchange only the messages needed for:

- published manager/worker directory
- computer and identity presence
- task dispatch
- queue updates
- status events
- report events
- screenshot or screen-summary updates
- audit events

Every request carries pair authentication, the intended scope, target computer/identity, and applicable permission checks. Network reachability is not authority by itself. Execution and authoritative state remain on the source computer; parents retain only the operational records needed to supervise work they delegated.

Parents communicate with direct children only. A request for a grandchild is delegated to the intermediary child manager, which decides how to route it beneath itself. This prevents a top-level manager from bypassing a child manager's policy or reaching through the hierarchy with stale assumptions.

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

1. EmploAI starts without a login and reconciles one protected local manager and an initial deletable default worker.
2. The local manager delegates ordinary actionable work to its default worker.
3. The manager creates a short-lived computer pairing code.
4. A second computer or VPS starts with its own manager and default worker, then pairs beneath the first computer using that code.
5. Company > Computers shows the direct child computer, its published manager route, and its published default worker without copying their chats or local files.
6. The parent delegates execution to the child's default worker.
7. The parent delegates coordination to the child manager, which may route work to its own workers or direct children.
8. A busy worker queues a second task.
9. A worker produces a strict structured report in its isolated delegated-task session.
10. The originating manager task card updates in realtime and receives one deduplicated manager synthesis turn.
11. The manager verifies the result through report evidence, artifacts, and recent screenshot/screen summary.
12. A child computer disconnects; its parent card marks it offline and preserves the known queue/running state.
13. Refreshing the Fleet connection repairs transport/host state without creating a new pairing or opening a visible terminal.
14. A third computer pairs beneath the second; the top-level manager reaches it through the second computer's manager rather than seeing it as a direct child.
15. Revoking a pairing removes that parent-child route without affecting either computer's local identities or data.
16. Lock rules prevent file-write conflicts and interactive desktop conflicts.

If this scenario works, V1 has proven the manager/worker execution system rather than just a visual dashboard. Company objectives, departments, review, acceptance, offline continuation, and recovery have their separate acceptance scenarios in [company_system_details.md](company_system_details.md).

## End-State Direction

Fleet's end state is secure execution infrastructure for the company-scale AI employee platform.

In that state:

- A top-level local manager can coordinate hundreds or thousands of workers through a tree of directly paired computers, without a company account.
- Company managers can organize directly addressable workers without changing Fleet ownership or bypassing subordinate managers.
- Top-level managers coordinate subordinate managers and receive aggregate rollups without flattening descendants.
- Worker roles can include default behavior, connector bundles, and specialized tool policies.
- The manager agent can decompose large goals, assign work, monitor execution, recover from blockers, and synthesize final outcomes.
- Mobile, Telegram, and Jarvis can all act as command surfaces for the same fleet.

The core idea stays the same: execution and identity remain local, routing follows authenticated parent-child relationships, and Company coordinates the workforce without turning Fleet into a hosted login or account authority.
