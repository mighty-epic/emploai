# Accountless Company System Details

> **Specification status: Supporting first-implementation reference.**
>
> The primary product contract is [emploai_company_operating_system_and_fleet_ux_spec.md](emploai_company_operating_system_and_fleet_ux_spec.md). Where the documents differ, that comprehensive specification controls. This file remains useful for the earlier simplified Company/Fleet decisions that do not conflict with it.

## Purpose

This document defines the company operating layer of EmploAI: how one root operator organizes managers and workers around durable objectives, reviews results, handles attention, and continues safely across multiple computers.

The companion documents have narrower responsibilities:

- [main_vision.md](main_vision.md) defines the product north star and non-negotiable principles.
- [fleet_system_details.md](fleet_system_details.md) defines execution infrastructure: computers, identities, pairing, routes, queues, reports, permissions, resource locks, and transport.
- This document defines company organization, work ownership, acceptance, company UX, offline behavior, governance, and recovery.

It is a product-behavior specification, not an API, storage, migration, or wire-format specification.

## Shared Glossary

These terms are canonical across the product documents:

- `Company`: the local operating structure rooted on one top-level EmploAI computer. It organizes objectives and responsibility without creating a hosted account.
- `Root operator`: the human using the root computer's local operating-system session. The root operator is the company owner and final authority for every company-level decision and operation.
- `Child computer operator`: a descriptive term for a human with local operating-system access to a child computer, not a company position, account, or identity. Local access permits that computer's operations and safety controls but grants no general company authority.
- `Computer`: a physical computer, VPS, or remote desktop environment running one complete EmploAI installation.
- `Manager`: the one mandatory orchestration identity on a computer. It owns that computer's local workers and is the route for coordinating its direct child computers.
- `CEO manager`: the root computer's manager acting as the company's top agentic manager. `CEO` is a display title and responsibility, not a separate technical identity role or an authority above the root operator.
- `Worker`: an execution identity owned by its source computer's manager. A computer is never itself a worker.
- `Manager branch`: one manager plus its local workers and direct child-manager routes. The authenticated Fleet hierarchy supplies the branch structure.
- `Department`: an optional, explicitly created flat worker pool owned by one manager for shared policy, routing, and queue visibility. Companies have no departments by default, and a department is not an HR position hierarchy.
- `Objective`: a durable outcome that may be decomposed into delegated tasks and must be accepted before it counts as finished.
- `Task`: one execution assignment sent to a worker. Task completion does not by itself accept an objective.
- `Report`: the structured result, evidence, artifacts, blockers, confidence, and next action returned by a task.
- `Fleet`: the execution infrastructure that connects computers and enforces identity, route, permission, presence, and resource boundaries.

The UI and documentation must not use `computer`, `worker`, `manager`, `department`, `objective`, and `task` as interchangeable terms.

## Company And Fleet Are Separate Layers

The company structure and computer topology solve different problems:

```text
Company operating layer                 Fleet execution layer
───────────────────────                 ─────────────────────
Company purpose                         Root computer
├─ Objectives                           ├─ Local manager
├─ Manager responsibility               ├─ Local workers
├─ Optional departments                 └─ Direct child computers
└─ Review and acceptance                    └─ Their managers and workers
```

Fleet answers where work can execute, who owns an identity, which route reaches it, and what the route permits. Company answers why work exists, which manager is responsible, how work is grouped, and whether its result was accepted.

The company model must never mirror or replace the parent-child computer tree. A department is not a computer, an intermediary computer is not a worker, and placing a worker in a department does not move that worker or change its source manager.

## Non-Negotiable Invariants

- One top-level Fleet root owns one active company in the first release.
- A standalone installation is already a one-computer company; company setup must not block ordinary local use.
- The company has no cloud login, hosted company account, agent accounts, or EmploAI-operated authority service.
- The root computer stores the authoritative company manifest. Children receive only relevant signed and versioned cached portions.
- The root operator is the ultimate company authority and may perform or override every company-level operation, including structure, objectives, reviews, acceptance, reassignment, archival, recovery, and company-controlled settings.
- A child computer operator is not a company role and receives no company-wide authority. They retain local control over that computer's runtime, credentials, tools, sensitive local approvals, troubleshooting, and pairing revocation.
- Root authority does not make an offline computer reachable, bypass its operating system, restore a revoked pairing, or defeat a hard security boundary. Remote child operations still use authenticated Fleet routes and the destination's effective local controls.
- Every computer remains authoritative for its local identities, chats, tools, secrets, workspaces, queues, reports, artifacts, and detailed execution history.
- Direct control follows Fleet routes. A manager controls local identities and direct children only; it cannot bypass an intermediary manager to control grandchildren.
- Company responsibility never overrides pairing permissions, local grants, resource locks, approvals, or safety boundaries. A denial at any layer wins.
- Workers never receive managerial delegation authority. They report blockers or assistance requests to their manager, which coordinates other workers.
- Worker execution completion and company acceptance are separate states.

## Company Creation, Membership, And Authority

### Local creation

The first start of a root installation creates a stable local company identity without a login or mandatory wizard. Until renamed, the UI may use a neutral label derived from the root computer name. Company Overview progressively invites the root operator to add a company name and purpose; dismissing that invitation does not disable Chat, Jarvis, local workers, or Fleet.

The first release supports one active company per Fleet root. Multiple companies, hosted membership, and cloud synchronization are out of scope. No department is created automatically; the root operator or an authorized manager creates one only when a shared worker pool is useful.

### Joining and transferring

Pairing a standalone computer beneath a parent explicitly joins it to the parent's company branch. Its previous standalone company becomes inactive and is retained as local historical metadata; it is not merged silently into the parent's company. The child keeps its local manager, workers, chats, files, secrets, and local history. It receives only the company material relevant to the objectives and policies routed into its branch.

A computer can have one parent. Moving it to another company requires the child computer operator to confirm detachment, revoke the old route, and complete fresh pairing with the new parent. Existing local data remains local; unresolved old-company work is retained as historical local state and is not silently transferred.

When a child leaves its parent and is not immediately joined to another company, it starts a new standalone company. Material from the former company remains read-only local history and never regains authority automatically. A planned transfer of the live company root to another computer is not supported in the first implementation; emergency root-loss recovery remains a separate explicit recovery flow.

### Manifest authority

The root manifest is authoritative for:

- company identity, name, purpose, and status;
- company-wide policies and defaults;
- manager-branch membership;
- department definitions and membership;
- objective identity, ownership, parentage, priority, due date, and acceptance state;
- published company handbook material;
- the latest accepted rollups from manager branches.

Children cache the minimum relevant manifest slice needed to understand and continue assigned work. Cached material is read-only while disconnected except for source-owned execution state described below.

## Managers, Workers, And Departments

The authenticated manager hierarchy is the primary company hierarchy. Each manager is responsible for its local workers and the objectives delegated into its branch. A child manager may decompose an assigned objective across its own workers and direct children without exposing its grandchildren as direct targets to the parent.

The root manager may be presented as the `CEO manager`. It receives direction and objectives from the root operator, may propose objectives within that direction, and coordinates subordinate manager branches. It remains a normal manager in Fleet authority terms and can never overrule the root operator.

Departments are deliberately lightweight:

- A company begins with no departments; creating one is always explicit.
- A department belongs to one manager.
- It is a flat pool, not a nested org chart and not a set of formal positions.
- It may contain workers that the owning manager is allowed to address directly.
- A worker may have at most one primary department in the company view and may remain unassigned.
- Interactive workers remain individually visible even when assigned to a department.
- Departments mainly provide shared instructions, capability expectations, queue visibility, and convenient routing for compatible background work.
- Department membership never changes the worker's source manager, source computer, tool grants, or pair permissions.
- Departments cannot contain indirect descendants in a way that bypasses their intermediary manager. A child manager reports its department rollups upward instead.

Company must not expose both a `Department` and a `Fleet group` as competing organization menus. A department is the user-facing company concept. Fleet may derive a routing target set from its membership, and legacy Fleet groups may remain as compatibility data until an implementation plan defines migration, but they are not a second source of organizational truth.

There are no position, title, reporting-line, nested-department, payroll, or employee-account objects in the first release. A worker's display name, capability tags, optional department, and saved behavior profile are sufficient.

### Interactive and background work

Interactivity is a property of a task and the resources it needs, not another identity role:

- An interactive task claims scarce resources such as the visible desktop, mouse, keyboard, live browser profile, or controlled application.
- Only one incompatible interactive task may control the same machine resource at a time.
- Background tasks may run concurrently only when their workspace, browser, credential, and compute locks are compatible.
- A department does not imply parallel capacity. The assignment preview must show the available targets, busy workers, and expected queues.

When work is assigned to a department, routing selects a compatible available worker by default. If all compatible workers are busy, it selects the shortest compatible queue. The complete selected route is shown before dispatch, and the manager may choose a different worker. The system never invents a department or silently routes work through one.

## Conceptual Company Records

The following records define product meaning only. Their database and API representations must be designed later, after this specification is locked.

### `CompanyManifest`

Identifies the company, its root computer, display name, purpose, manifest version, status, company policies, departments, objectives, handbook references, and branch rollups.

### `Department`

Identifies a flat worker pool, its owning manager, display name, optional description, shared behavior/policy reference, member identities, and active or archived state.

### `Objective`

Defines a durable outcome with:

- a stable local company ID;
- a title and intended outcome;
- explicit success criteria;
- one owning manager;
- an optional department;
- an optional parent objective when a manager delegates a child outcome;
- priority: `low`, `normal`, `high`, or `urgent`;
- an optional due date;
- acceptance mode: manager review or explicitly enabled low-risk automatic acceptance;
- linked assignments, tasks, reports, evidence, and artifacts;
- one lifecycle state.

Objective states are:

- `draft`: being defined; no work has started.
- `active`: approved work is queued or running.
- `paused`: progress was intentionally suspended; assignments and history remain intact, and no new objective work is dispatched until it resumes.
- `blocked`: progress requires a decision, permission, resource, or external change.
- `awaiting_review`: execution reports are ready for acceptance review.
- `rework_requested`: the latest result was not accepted and follow-up work is required.
- `accepted`: the outcome and required evidence were accepted.
- `failed`: the manager determined the objective cannot currently be completed.
- `canceled`: the objective was intentionally stopped; its history remains available.

### `ObjectiveAssignment`

Links an objective to one explicit route: issuing manager, destination computer, destination manager or worker, optional department, scope, originating chat/message, workspace context, task IDs, and assignment state. Its compact state is derived from the underlying Fleet work as `queued`, `running`, `blocked`, `completed`, `canceled`, or `detached`. It preserves reroutes and reassignments rather than overwriting history. Pausing an objective preserves each assignment's last execution state while the objective itself displays `paused`.

### `ObjectiveReview`

Records the reviewing manager or root operator, objective, decision, notes, evidence references, timestamp, and whether acceptance was manual or policy-driven. Decisions are `accepted` or `rework_requested`.

## Objective And Result Lifecycle

An objective begins as an outcome set by the root operator, created by an authorized manager such as the CEO manager, or proposed by a manager for approval. Before dispatch, its owning manager must be clear and its success criteria must be understandable enough to review. A broad request may be clarified in manager chat before an objective is created.

Managers may decompose the stated outcome but must not silently expand it. Work beyond the objective's outcome or success criteria remains a proposed follow-up until the root operator or an authorized owning manager explicitly approves it as new scope. There is no general `optional assignment` flag in the first implementation.

The owning manager may:

- create worker tasks under the objective;
- delegate a child objective to one direct child manager;
- assign compatible work to a department;
- pause, redirect, cancel, or reassign work;
- combine reports and request additional verification;
- accept the outcome or request rework.

A child manager receiving a child objective may create its own local tasks and further child objectives through its direct routes. The parent sees the assignment route, rollup state, blockers, and returned result; it does not gain direct control over grandchildren. Accepting a child objective closes that delegated outcome and returns its accepted report upward, but only the owning parent manager may accept the parent objective.

When a worker finishes a task, it submits the structured Fleet report. A completed report advances the objective toward `awaiting_review`; it does not make the objective `accepted`.

Pausing an objective stops new dispatch under it and requests that interruptible active tasks pause through the normal Fleet task controls. It preserves queues, sessions, evidence, reports, and route history so work can resume without recreating the objective.

Acceptance requires:

- success criteria to be addressed;
- assignments that contributed to the result to be completed, intentionally canceled, replaced, or waived with a recorded reason;
- no unresolved blocker that invalidates the outcome;
- required evidence and artifact references to be available or explicitly waived;
- an `ObjectiveReview` record.

The owning manager may accept normal work. The root operator can override any company review decision by accepting, requesting rework, reopening, canceling, or reassigning an objective. This is final authority over company judgment; it does not make an unreachable computer available or bypass operating-system controls, revoked pairing trust, or hard security boundaries. Low-risk automatic acceptance is off by default and may be enabled per objective or company policy only when the reports needed to establish the success criteria validate, no blocker or sensitive action remains, and the evidence policy is satisfied.

Rework keeps the original objective and review history. The manager may continue the same isolated task session when the target and scope are unchanged or create a linked replacement task when reassignment or a new approach is needed. Canceling or failing work never deletes its reports or audit trail.

## Routing And Collaboration

Managers receive objectives or coordination requests; workers receive executable tasks. The default routes remain:

- unqualified local action to the local default worker;
- named local worker to that worker;
- named child computer execution to its published default worker;
- child coordination to the child manager;
- explicit identity selection over automatic routing.

Every assignment must preserve and display the complete route:

```text
Issuing manager → destination computer → destination manager or worker → task state
```

When applicable, the route also shows the department, objective, queue position, workspace binding, and permission state. Route changes are appended to history rather than silently replacing the original destination.

Before dispatch, the manager receives a route preflight showing whether the destination has a compatible model/runtime, required tool capabilities, a valid workspace binding, available resource locks, and permission to accept the work. Missing capability blocks dispatch with an exact recovery choice: select another target, request an allowed grant, bind the workspace, change the task, or wait for the destination. The system must not silently change the model, computer, identity, workspace, or access mode.

Workers cannot assign other workers, create departments, restructure the company, or grant themselves tools. A worker that needs parallel help creates a blocker or assistance request. Its manager decides whether to answer directly, assign another worker, or delegate to a child manager.

## Company Desktop Experience

The current top-level `Fleet` surface becomes `Company`. Infrastructure remains available inside Company under `Computers`; the rename does not remove pairing, connection, update, preview, or child-settings capabilities.

The primary desktop navigation is:

- `Chat`
- `Jarvis`
- `Company`
- `Settings`

Company uses stable internal navigation rather than placing every function on one scrolling dashboard:

- `Overview`: active objectives, progress rollups, available capacity, and items requiring attention.
- `Work`: objectives, assignments, task reports, evidence, acceptance, and rework.
- `Workforce`: manager branches, optional departments, workers, capability summaries, and queues.
- `Computers`: local Fleet health, direct child computers, pairing, connection recovery, runtime/update controls, previews, and per-computer settings.

Navigating into a manager, worker, objective, department, or computer opens a dedicated page with a predictable back route. Returning restores the previous page's filter, scroll position, and selection.

Company-wide configuration is opened from a clearly labeled `Company settings` action in the Company header rather than adding another permanent navigation page. It contains company name and purpose, review/acceptance defaults, published handbook material, attention preferences, manifest backup/recovery, and destructive company lifecycle actions. Computer-specific configuration remains inside `Computers`; global application/runtime preferences remain in the main `Settings` surface.

### Role-aware views

When a manager identity is selected, Company exposes only the organization and infrastructure actions permitted for that manager's branch. When a worker identity is selected, Company becomes a focused `My Work` experience showing that worker's queue, active task, task session, reports, blockers, and direct chat entry. It must not show pairing, company restructuring, delegation, child settings, permission administration, or manager tool controls.

Changing identity must be an explicit user action. Refreshes, reconnects, background polling, and navigation must not switch the selected identity or briefly render another role's controls.

### Overview and attention

Overview begins with a compact attention feed, not a wall of infrastructure cards. It consolidates:

- blockers and questions;
- sensitive-action approvals;
- connection or capability permission requests;
- failed or stalled work;
- results awaiting acceptance;
- expiring grants and materially incompatible computers.

Items are deduplicated by their underlying request or objective. Opening an item routes to its actual context. Merely viewing an item does not resolve it; it disappears only when the underlying state is resolved. Empty sections collapse instead of reserving dead space. Resolved history remains searchable outside the default attention view.

### Descendant rollups

Direct authority and broad awareness are different. A parent receives aggregate rollups from each direct child manager: objective counts, progress, capacity, blockers, risks, and accepted outcomes. It does not receive a flattened list of every descendant worker, full transcript, or raw tool history.

Requests for more detail route through the direct child manager and remain subject to permissions and optional context-inspection policy. A stale or offline rollup always shows its source and last-updated time.

### Interaction quality requirements

- Use progressive disclosure: summary first, detail on demand.
- Keep empty, completed, and inactive panels compact; do not replace removed content with layout gaps.
- Show immediate pressed/loading feedback for asynchronous controls and a clear success or recovery state.
- Preserve one primary action per page and place destructive actions separately.
- Support keyboard navigation, visible focus, semantic labels, and a logical reading order.
- Do not communicate status by color alone.
- Avoid nested scroll regions where one page-level scroll is sufficient.
- Reserve space for loading content so background refreshes do not flicker or shift the layout.
- Use short, meaningful transitions and respect reduced-motion preferences.

## State Authority

| State | Authoritative source | What may be published or cached elsewhere |
| --- | --- | --- |
| Company identity, policy, departments, and objective ownership | Root company computer | Relevant signed/versioned manifest slices |
| Manager and worker identity/configuration | Identity's source computer | Label, role, status, default marker, visibility, and capability tags |
| Task, queue, delegated session, and report | Executing worker's source computer | Assignment state, milestones, validated report, and approved evidence |
| Child objective execution plan | Responsible child manager's computer | Parent objective linkage, rollup state, blockers, and final result |
| Pairing and connection permissions | Each paired endpoint, enforced by the destination | Effective permission summary and pending requests |
| Secrets and raw connector credentials | Computer that uses them | Capability availability only; never raw secret material |
| Artifact bytes | Computer or explicit destination holding the artifact | Metadata, evidence reference, availability, and approved copies |
| Automation definition and run history | Automation's selected source computer and identity | Schedule/status summary and permission-controlled reports |
| Descendant company health | Each child manager for its branch | Aggregated rollup with source and freshness |

Root company metadata wins conflicts about company structure. Source computers win conflicts about their local identities and execution records. Conflicts must be surfaced; neither side silently overwrites authoritative state owned by the other.

## Permissions, Security, And Privacy

The root operator may change every company-owned structure, policy, review, grant, or setting exposed by EmploAI. Execution of the resulting decision remains subject to whether the destination exists, is reachable, is authenticated, and can perform the operation. Effective execution is the intersection of:

1. company policy and objective ownership;
2. manager branch authority;
3. pair and connection permissions;
4. destination identity tool and connector grants;
5. local resource locks and approval requirements;
6. hard safety and security boundaries.

A denial or unavailable capability at any layer blocks execution until the responsible authority changes it or the capability becomes available. The root operator may change root-owned company settings and remotely configurable child settings through an authorized route, but cannot treat an offline computer, revoked route, missing capability, or operating-system refusal as successful. A company title, department assignment, or high-level objective never grants a tool, credential, workspace, or child-computer permission by itself.

The child manager enforces all work arriving at its computer. A parent may request child configuration or capability use only where the child's connection permissions allow it. A human at a child computer is not a subordinate company operator; local OS access gives them local operational and safety control only. Network reachability and knowledge of a Yggdrasil address are not authorization.

Company knowledge consists only of explicitly published handbook and policy material. Relevant sections may be cached for assigned work. The system does not silently copy chats, transcripts, full memory, provider state, absolute paths, secrets, or raw tool payloads into the company manifest.

Manager context inspection remains separately opt-in, redacted, audited, and limited by the direct manager hierarchy. Disabling it blocks new inspection and indexing according to the Fleet privacy policy.

Audit history must cover company creation/transfer, structural changes, objective assignment, routing, review, acceptance/rework, grants, permission decisions, artifact copies, automation changes, pairing revocation, quarantine, and recovery. Audit records exclude raw secrets.

## Offline Behavior And Reconciliation

When disconnected from the root, a child manager may:

- continue objectives already assigned to its branch using the cached policy;
- create and route local tasks under those existing objectives;
- continue authorized local automations;
- resolve local blockers and collect reports;
- queue milestones, reports, reviews, and evidence for later synchronization.

While disconnected, it may not:

- create, delete, or rename company departments;
- change company-wide policy or objective ownership;
- grant new upstream authority or connection permissions;
- reparent the computer or transfer company membership;
- claim that an objective was accepted by an unreachable parent manager.

The parent shows the branch as offline or stale with the last confirmed state. On reconnection, source-owned execution events append to the objective history. Root-owned structural state remains authoritative. Conflicts are shown as reviewable reconciliation items rather than resolved silently.

## Artifacts And Availability

Artifact metadata may remain visible after the producing computer disconnects, but metadata is not the artifact. The UI must mark an artifact `source offline` or `copy unavailable` when no reachable approved copy exists.

Copying an artifact to a parent or another computer is an explicit, permission-checked operation recorded in the audit trail. Company reports may reference local artifacts without automatically replicating their contents. Retention and deletion follow the authoritative source computer unless an approved copy has its own retention policy.

## Automations

An automation lives on one source computer and one manager or worker identity.

- An automation targeting an existing chat inherits that chat's model, reasoning, workspace, access mode, tool configuration, and identity.
- An automation creating a new chat requires an explicit model, destination identity, and workspace choice when applicable.
- A company objective may reference an automation, but does not become the authority for its runtime or secrets.
- Remote creation or modification is a permission-controlled request enforced by the destination manager.
- An offline destination may continue already authorized local schedules under cached policy.
- New remote changes wait for reconnection; the parent must not pretend they were applied.
- Renaming an identity preserves the stable automation binding. Removing or resetting the bound identity pauses the automation and requires explicit reassignment.

Automation runs produce normal task/report evidence and appear in the same attention and acceptance flow when root-operator or manager review is required.

## Recovery And Lifecycle Changes

### Local backup and root loss

The root operator must be able to export an encrypted local company-manifest backup containing company structure, objectives, reviews, handbook references, and known rollups. Secrets, raw credential material, chats, artifact bytes, and pair credentials are excluded by default.

Restoring a backup restores company metadata, not old network trust. Child computers must be paired again with fresh credentials. No child silently promotes itself when the root disappears.

Without a usable backup, a human with local OS access to the selected child may explicitly promote that computer to a new root and becomes the root operator of the recovered company. The new company begins from that child's latest eligible cached slice, clearly marks missing branches or incomplete history, and requires every remaining computer to pair again.

The first implementation does not support a planned transfer of a healthy company root. The original root remains authoritative while it is active. Backup restoration and explicit child promotion are emergency recovery operations after root loss or retirement, require fresh pairing, and are not a live ownership-handoff workflow.

### Company archival

The standard destructive company action is `Archive company`, not silent deletion. Archival stops new company dispatch, pauses or stops company-owned scheduled work, revokes child pairings, and preserves the manifest, objectives, reviews, reports, and audit history as read-only local history.

Permanent local erasure is a separate root-computer-only action requiring explicit destructive confirmation. It cannot erase data or historical records that remain authoritative on disconnected or formerly paired computers.

### Removal, revocation, and quarantine

- Removing a worker archives its company assignments and preserves reports; source-local deletion follows Fleet worker rules.
- Removing a child revokes the route and marks unresolved assignments detached until canceled, reassigned, or reconnected through an approved route.
- A removed child that does not immediately join another parent creates a new standalone company; former-company material remains read-only local history.
- Revoking a pairing invalidates its pair authority without deleting either computer's local state.
- A suspected compromised child can be quarantined: new dispatch stops, active remote authority is revoked, cached summaries are marked untrusted, and re-entry requires fresh pairing and review.
- Version-incompatible children remain visible with last-known health where safe, but unsupported company mutations and automatic objective routing are blocked with an update-required explanation.

## Specification Acceptance Scenarios

The specification is internally complete only when these scenarios have one unambiguous outcome:

1. A standalone computer starts without login and operates as a one-manager, one-worker company.
2. A root, child, and grandchild form a manager chain without flattening authority or calling a computer a worker.
3. An interactive worker waits for a conflicting desktop lock while compatible background work continues.
4. A manager assigns background workers to a flat department with shared routing policy and visible queues.
5. One objective is decomposed across local workers and a direct child manager.
6. Worker reports complete, the objective enters review, and the manager accepts it or requests linked rework.
7. A child loses the root connection, continues existing work, and later synchronizes source-owned events without changing company structure offline.
8. Company responsibility requests an action that child connection permissions deny; the action remains blocked.
9. One automation inherits an existing chat configuration while another new-chat automation requires a model and identity.
10. An artifact's metadata remains visible while its source computer is offline, but the artifact is marked unavailable.
11. A lost root is restored from an encrypted manifest backup or replaced through explicit promotion and fresh pairing.
12. Selecting a worker shows My Work and never flashes or exposes manager-only controls.
13. No company, pairing, recovery, delegation, or automation flow requires a cloud login or hosted account.
14. A new company has no departments; after explicit creation, department work selects an available compatible worker or the shortest compatible queue and shows the route before dispatch.
15. Pausing an objective preserves its assignments, sessions, evidence, and route history, then resumes without recreating the objective.
16. A manager proposes work outside approved objective scope, and the work is not dispatched until the root operator or authorized owning manager approves it.
17. A child detaches, creates a new standalone company, and retains its former-company material only as read-only history.
18. Archiving a company stops company work, revokes child pairings, and preserves company records as read-only local history.
19. The root operator overrides a company review decision, while an unreachable computer or revoked pairing remains technically unavailable.

## Locked Status And Implementation Boundary

The user explicitly approved this product specification as `Locked` on 2026-07-23 after resolving objective pausing, assignment summaries, department defaults and routing, root-transfer scope, child detachment, company archival, and operator authority.

The following remain mandatory implementation boundaries:

- terms must continue to match the main vision and Fleet specification;
- Company organization must remain separate from Fleet topology;
- no cloud-login or hosted-account assumption may be introduced;
- no UI may hide who issued work, who receives it, or which computer owns execution;
- offline, denial, recovery, and unavailable-artifact states must retain clear recovery paths;
- extra work outside an objective's approved scope must remain a proposal until approved;
- child computer operators must not become company roles merely because they have local OS access.

Changing these product behaviors requires an explicit specification revision. Application implementation still requires a separate plan mapping the locked behavior to APIs, persistence, migrations, renderer work, compatibility, and tests, followed by explicit user authorization. Locking this document does not itself authorize code changes.
