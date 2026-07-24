# EmploAI Company Operating System and Fleet UX Specification

> **Specification authority: Primary product contract.** When this document conflicts with `main_vision.md`, `company_system_details.md`, or `fleet_system_details.md`, this document controls. Every required behavior in this contract is part of the intended implementation scope, although delivery may be divided into the product slices defined below.

Status: Authoritative product contract

Last updated: 2026-07-23

Scope: Whole-company operation, specialized AI jobs, organization and workforce management, operating workflows, governance, and the Fleet execution layer

First-implementation scope: one locally owned root company per physical computer. The same computer may also hold isolated worker memberships for companies it serves, and the application exposes one active company context at a time. Every company-owned record, event, cache, route, identity, permission, and workspace carries an immutable `company_id`; only identities bound to the selected company membership may act in that company. A later product version may allow several locally owned root companies on one computer without changing this isolation model.

## Purpose

This document defines the intended product and user experience for EmploAI as a system capable of operating an entire digital company. It also defines how Fleet, the private network of computers and agents that performs the work, expands from the current implementation into that company operating system.

It is the decision source for:

- what it means for EmploAI to operate a company rather than act as a single assistant;
- how a company is created, structured, governed, measured, and changed;
- how specialized jobs from the agency-agents corpus become locally stored EmploAI job templates and individual agent contracts;
- how departments, positions, AI employees, goals, runbooks, assignments, approvals, reports, and company knowledge fit together;
- what the company-wide interface contains and how its key flows behave;
- what Fleet means to the company operator;
- how computers connect through the local-only Yggdrasil transport;
- how the current Fleet computer workspace, worker activity, and view-only preview are preserved and expanded;
- how loading, failure, recovery, privacy, accessibility, and scale are presented;
- what must be true before either the company system or Fleet UX is considered complete.

This document supersedes the **Fleet Dashboard UX** section of [fleet_system_details.md](fleet_system_details.md). It does not replace the task, queue, report, or concurrency rules in that document. The current direct connection behavior remains defined by [../yggdrasil_fleet_transport.md](../yggdrasil_fleet_transport.md). Where this document describes future company-wide UX, it is a product contract rather than a claim that the capability already exists.

EmploAI is local-first and Fleet is local-only. There is no EmploAI account, hosted relay, or cloud control plane in the active product path. Data is stored locally in company-isolated partitions. A computer retains control of its hardware, local runtime, models, applications, and secrets, while each company controls only the identities, workspaces, grants, and records inside that company's partition. Fleet exchanges only the minimum approved membership, capability, assignment, request, status, and report data over direct Yggdrasil connections.

## Normative language

The terms **must**, **should**, and **may** are intentional:

- **Must** means required product behavior.
- **Should** means the default behavior unless a documented constraint prevents it.
- **May** means an optional enhancement.

All **Must** and **Should** requirements are committed implementation scope. **Should** permits only a documented constraint-specific fallback; it does not remove the feature from scope. **May** remains optional until explicitly promoted.

## Settled architecture decisions

This section is the shortest authoritative handoff for an engineer or agent entering the project without the preceding product discussion. The detailed sections below explain the UX, data placement, migration, and edge cases behind each decision.

1. EmploAI is local-first. It has no required EmploAI account, hosted relay, or cloud control plane.
2. A company is the highest logical tenant and isolation boundary. Selecting a company scopes the entire app, not only Fleet.
3. In version one, one physical computer may own one root company and may additionally host worker memberships for other companies. Each company has separate data, identities, work, memory, credentials/grants, and Fleet membership. Companies on the same computer are peers, not parent/child companies. Supporting several root companies on one computer is a later expansion.
4. A physical computer is never globally a root or child. It has a separate role through its membership in each company. The same computer may be a worker node for Company A and root controller for Company C.
5. A physical computer has at most one membership in a particular company. That membership may have at most one direct upstream relationship and zero or more direct children for that company.
6. Version one has one authoritative writable root controller per company: the computer where that company was created. The root cannot be transferred, replaced, or automatically promoted in version one.
7. A worker computer may create and own one unrelated local root company unless it already owns one or a device-owner installation policy deliberately disables company creation.
8. An identity belongs permanently to one company and has one home computer at a time. The identity's job may change inside that company; the identity itself never transfers to another company or belongs to two companies.
9. Computers provide execution capacity and local trust boundaries. Identities delegate work. Fleet topology is transport/control routing and must never be treated as the employee organization chart.
10. Every company starts immediately with two separate identities: a CEO/manager, which is also the user's default assistant, and a minimally permitted general worker. Every additional computer membership in that company likewise reconciles one protected local manager and one protected default worker for that membership. All of these identities are company-bound and have their own chats, settings, job contract, and long-term memory.
11. Business onboarding is optional and suggested rather than blocking. A company may remain a personal, business-less assistant context indefinitely. When onboarding begins, its first choice is only **I already have a business** or **Help me create a new business**.
12. Onboarding has three separate scopes: device setup, optional company/business onboarding, and identity-specific employee onboarding. Workspace setup contains project facts, not employee identity or job authority.
13. Managers and the CEO may create and delegate work within their authority. Workers wake for manager assignments or enabled scheduled jobs, complete the assigned scope, and do not independently create company initiatives.
14. Remote company work requires a live authenticated Yggdrasil session to the company's root. Enrollment persists across disconnects, but the work lease expires and that company's remote work pauses until reconciliation succeeds.
15. Every non-CEO assignment output becomes a structured report to the assigning manager. The manager must review it; the assignment remains **Submitted** until accepted. Reports then move upward through any manager chain, while every original report remains visible in the human owner's Company Inbox.
16. The CEO synthesizes company information for the human when asked. CEO runs, tasks, delegations, reports, and material decisions are all visible in the human inbox. CEO reports are informational by default and do not require human acceptance; dangerous, material, legally reserved, or company-configured decisions require human approval and may actively ping the owner.
17. External actions default to **Draft only**. Company settings may independently disable an action, require approval, or grant bounded or broad autonomy by action, channel, recipient, identity, job, assignment, budget, or time window.
18. New-business onboarding begins by developing an idea with the user. Each step uses predefined evidence gates, and demand cannot be marked validated without observable target-customer behavior and an approved form of economic commitment.
19. Departments, automations, schedules, and the fuller organization are optional additions proposed later in onboarding. Proposed recurring work does not run until the user activates it.
20. The fixed-root company supports manual and optional scheduled encrypted backups. Deleting the company revokes connected workers; an offline worker can never resume that company and may remove its unavailable local partition.
21. Existing Fleet connection, parent/current/direct-child, activity, preview, permission, delegation, request, response, and report behavior must be preserved while becoming company-scoped.
22. Startup restores the last explicitly selected available company. A permanently visible company switcher changes the complete application context and never switches implicitly.
23. Every company partition uses its own encryption-at-rest key protected by the local operating system, without claiming protection from that computer's OS administrator while the company is running.
24. Portable backups use a user-created passphrase with an optional separate recovery key. OS-backed convenience storage is opt-in and is never the only decryption path.

If implementation language conflicts with these decisions, this section and the more specific company-scope rules below take precedence over legacy naming. In particular, legacy `manager`, `worker`, and `root_manager` values describe network/runtime state unless a company job contract explicitly describes an employee manager.

## Whole-company north star

EmploAI should let one human owner create, direct, inspect, and improve a company made primarily of specialized AI employees. The product is not a chatbot with many personas and it is not only a remote-computer dashboard. It is a company operating system:

- the owner defines what the company exists to do;
- EmploAI turns that charter into an organization, jobs, policies, goals, and operating rhythms;
- specialized AI employees own recurring responsibilities rather than waiting for isolated prompts;
- managers coordinate work, specialists produce artifacts, and independent reviewers check it;
- every important action is attributable to a goal, role, policy, assignment, approval, result, and metric;
- Fleet supplies the private computers, models, tools, and execution capacity on which the company runs;
- the system learns from outcomes without silently changing the company's authority or policy.

The intended feeling is not “I have several agents.” It is:

> I own and govern a functioning digital company. I can see what it is trying to achieve, who is responsible, what is happening, what requires me, and whether the company is succeeding.

Revenue and positive profit are the ultimate business outcomes for a commercial company. EmploAI therefore must connect day-to-day work to revenue, cost, customer value, risk, and operating health instead of optimizing only for agent activity.

## What “replace a company” means

EmploAI should be able to perform and coordinate the digital operating work normally spread across a company:

| Company capability | EmploAI responsibility |
|---|---|
| Direction | Maintain the company charter, strategy, objectives, constraints, and decision record |
| Leadership | Convert goals into plans, allocate responsibility, resolve routine conflicts, and escalate material decisions |
| Product | Research needs, maintain a roadmap, specify work, validate outcomes, and manage releases |
| Engineering and IT | Design, build, test, operate, secure, and recover digital systems under explicit controls |
| Marketing | Define audiences, create campaigns and content, operate approved channels, and measure acquisition |
| Sales | Manage leads, qualification, proposals, pipeline stages, follow-up, forecasting, and handoffs |
| Customer success and support | Onboard customers, answer requests, track health, resolve issues, and surface product feedback |
| Finance | Track revenue, costs, invoices, budgets, forecasts, and management reporting |
| Operations and project management | Run recurring processes, coordinate dependencies, manage incidents, and improve throughput |
| Security, privacy, and compliance | Enforce policies, review sensitive changes, preserve evidence, and escalate uncertainty |
| Workforce management | Define jobs, hire and onboard agents, review performance, reorganize, retrain, replace, and retire roles |
| Knowledge management | Maintain verified company facts, policies, decisions, procedures, customer context, and lessons learned |

“Replace” refers to the operational structure and digital labor of a company. It does not pretend that software can be the legal signatory, director, taxpayer, bank-account owner, regulated professional, or accountable natural person where law or a third party requires a human. The human owner remains the legal principal and final authority for:

- incorporation, banking, taxation, and regulated filings;
- contracts and representations requiring a natural or authorized legal person;
- actions that create exceptional financial, legal, safety, privacy, or reputational exposure;
- irreversible closure of the company or destruction of its authoritative records;
- decisions explicitly reserved by the company charter.

The product should remove operational dependence on a conventional staff while making these retained human obligations obvious and manageable.

## Current implementation baseline

This specification is intentionally split between **implemented foundations** and **planned expansion**. Future UX must evolve the existing product without discarding working behavior.

### Current company foundations

The current product already has local workspaces, local project onboarding, persistent agent/worker identities, tasks, queues, reports, approvals, local credentials and providers, and direct Fleet relationships. Project onboarding can capture role, mission, tools, workflows, constraints, and working style for a workspace. Today, that onboarding mixes project facts with employee identity and job configuration, and durable runtime memory can be shared at workspace scope. The company expansion must migrate those concerns deliberately rather than preserve that ambiguity.

These are useful foundations, but they do not yet form a complete company model. In particular:

- a project profile is not a company charter;
- a worker name is not a complete job contract;
- a collection of agents is not an organization chart;
- task queues are not company operating processes;
- reports are not yet unified into company objectives, KPIs, finances, customers, and decisions;
- onboarding is not yet fully identity-specific;
- long-term employee memory is not yet isolated per identity;
- company selection is not yet the mandatory storage and runtime boundary for every object;
- Fleet topology is not itself management structure.

The company system should compose these existing primitives rather than replace them with a second unrelated implementation.

### Current Fleet foundation reviewed for this document

The Fleet portion of this specification was last reconciled against `emplo-changes` at commit `f1a52d5` on 2026-07-22. The implemented UI includes:

- an explicit path showing the computer above, this computer, and the number of computers directly below;
- a separate **Your direct manager** panel for the one computer immediately above a leaf or connected hub;
- a **Computers directly managed from here** panel that shows only direct child computers and deliberately does not repeat this computer as a card;
- direct-child cards showing agent count, active work, queue or request attention, and latest activity;
- an expandable computer workspace beneath the card grid;
- a local activity surface for incoming work and requests on leaf and connected-hub computers;
- a **Latest on this computer** activity panel inside a selected direct child's workspace for workers and explicitly exposed identities on that child;
- a **Current screen** view-only preview inside a selected direct child's workspace;
- manual capture or bounded periodic capture at 1, 2, or 4 screenshots per minute;
- preview frames held only in the open panel's memory and discarded when it closes;
- no remote mouse, keyboard, or continuous-video access;
- standalone, root, leaf, and connected-hub/intermediary relationship states;
- separate **reporting to the manager above** and **managing computers below** panes for a connected hub;
- private Start Fleet and Join Fleet code flows with Yggdrasil preparation;
- direct-computer permissions for delegating to the main identity, delegating to workers, and creating workers;
- delegation, permission request, upstream request, response, and report controls;
- local and remote agent creation, currently with a limited name-first flow;
- per-computer manager identities, default worker behavior, and manager-tool configuration;
- compatibility warnings when a connected computer has not published the current capability directory;
- direct-relationship filtering so unrelated or non-child desktop records do not appear as manageable computers;
- hidden helper subprocess windows on Windows so Fleet startup and reconnection do not flash console windows.

Every future Fleet section below must be read as an expansion of that implementation. It must not regress the separate parent/current/direct-child point of view, local activity, direct-child workspace, direct-child activity, bounded view-only preview, direct relationship filtering, permission ownership, delegation, requests, reports, or local-only transport.

## Company scope, local hosting, and multi-computer operation

The company is the highest logical boundary in EmploAI. In version one, a physical computer can own one root company and participate as a worker member in additional companies. Those companies are peers and must remain fully isolated. Companies are never nested merely because they share a computer or Yggdrasil connection.

### Company selection is the application context

When EmploAI opens, it restores the last explicitly selected company when that membership is still locally available. If it is unavailable, incomplete, or was removed, the app opens the company chooser with a clear explanation instead of silently selecting another company. The company switcher remains permanently visible whenever a company context is active. After selection, the entire application operates inside that company; company selection is not merely a filter on the Fleet tab.

The selected `company_id` scopes:

- identities, positions, job contracts, settings, and private memories;
- chats, assignments, queues, reports, approvals, and automations;
- company knowledge, policies, decisions, artifacts, and metrics;
- workspaces and their bindings;
- credential references, tool grants, models, and resource policies;
- Fleet memberships, topology, permissions, and company-visible computer state.

Every stored record, runtime event, cache key, lookup, dispatch, and permission check for company data must require the company context. Isolation must be enforced below the UI, not simulated by hiding records after a global query.

Switching companies must atomically replace the whole visible context. Drafts, navigation state, and selections are saved per company. Background work may continue for other companies, but notifications must name their company and opening one must switch through an explicit company boundary.

Outside a selected company, EmploAI may expose a small device-level shell containing:

- the company chooser;
- **This computer**, for hardware, installed runtimes/models/apps, total resource limits, and company memberships;
- root-company creation when this computer does not already own one, encrypted backup export, deletion, and device-membership entry points.

The device shell must never merge the private work, identities, or knowledge of its companies.

### Three separate setup scopes

EmploAI must keep these onboarding scopes distinct:

| Scope | Runs when | Owns |
|---|---|---|
| Device setup | Once per EmploAI installation or when hardware changes | Local storage, hardware, runtimes, installed models/apps, owner controls, total resource caps |
| Company/business onboarding | Optional, suggested after company creation, resumable, and editable | Existing-business context or new-business formation, charter, goals, authority, policies, optional organization, shared knowledge, operating defaults |
| Employee onboarding | Once per identity and again as a controlled delta after a job change | Identity, position, job contract, manager, tools, workspaces, permissions, memory, reporting, resource policy, readiness |

Workspace setup owns project or repository facts such as paths, commands, constraints, and reference material. It must not define who an employee is or silently assign a job. Existing project-onboarding fields must be split during migration: project facts remain with the workspace, while role, mission, working behavior, and job authority move to the identity's job contract.

An identity is the persistent employee. Its job is a versioned, replaceable contract. An identity may be promoted, transferred, or reassigned within the same company after delta onboarding and renewed readiness checks, but an identity must never move between companies. A partially created identity remains **Setup incomplete** and cannot accept ordinary assignments.

### Immediate company defaults

Creating or first opening EmploAI must not force business onboarding. The app creates a renameable local company on the current computer with:

- one CEO/manager identity selected as the primary chat assistant;
- one separate default general worker with minimal permissions;
- no required departments, business idea, automation, schedule, connector, or external-action authority;
- a visible but dismissible suggestion to begin business onboarding.

The CEO may answer directly or delegate suitable execution work to the default worker. The user may also chat with the worker directly. Both identities are ordinary persistent company employees and can later receive revised job contracts; the default worker begins as a generalist rather than pretending to have unconfigured specialist capability.

The root manager starts with company-management, delegation, memory, and automation capabilities. Compatible execution tool packs may be enabled deliberately. The default worker starts with the standard local execution profile—interactive desktop, isolated browser, workspace read/write, and web research—but no external connector credentials, spending authority, public-action authority, or sensitive company grants are implied by that profile.

### Physical computer versus company membership

A computer is a physical device, VPS, or runtime host. A **company computer membership** is the company-scoped enrollment that gives one company limited use of that computer. The computer is not globally a root, child, manager, or worker; that role belongs to one membership in one company.

Rules:

- one physical computer may host multiple isolated companies;
- one physical computer has at most one membership in a given company;
- a membership has one direct upstream computer at most and may have direct downstream computers;
- the same computer may be a worker node in Company A and the root controller of Company C;
- membership in one company never reveals that computer's other companies or memberships;
- “child computer” always means a distinct remote computer connected through Yggdrasil, never another identity or company on the same machine.

Every company membership reconciles exactly one protected local manager and one protected default worker for that membership. Joining Company A therefore creates Company A-bound local identities even when the same physical computer already has separate manager and worker identities for its own Company C. The identity selector and every dispatch surface show identities from the active company only. The membership manager owns that membership's local workers, enforces local capability boundaries, and coordinates its direct child memberships; on the root membership, the protected manager is the company's CEO manager by default.

For example:

```text
Computer Y
  Company A: root controller; workers also run on Q and V

Computer Q
  Company A: worker membership
  Company C: root controller

Computer V
  Company A: worker membership
  Company C: worker membership
  Company D: root controller
```

Companies A, C, and D remain unrelated. They share execution hosts only. V may host Company A identities and separate Company C identities, but no identity belongs to both. On Q, choosing Company A opens the restricted Company A worker experience; choosing Company C opens Company C's full root-owned experience.

A normal owner-controlled desktop installation may create its one locally owned root company even while it works for another company. Once it owns a root company, creating another root company is unavailable in version one. A deliberately locked or headless worker installation may disable company creation as a device policy, not as a consequence of being a child membership.

### Company authority and organizational authority are separate

Computers provide execution environments: local workspaces, installed tools and models, credentials, network reachability, processing capacity, and a trust boundary. Computers do not hold jobs and do not delegate business work.

Company identities delegate to other identities only when:

1. both identities belong to the same company;
2. the delegating identity's job contract permits the delegation;
3. the assignment and company policy permit it;
4. the destination computer membership exposes the required capability and accepts the work.

Physical parent/child topology is transport and control routing, not the organization chart. A manager identity may run on a worker node, and a root computer may host a non-manager specialist. The product must model two independent roles:

- **membership authority:** fixed root controller or worker node in version one;
- **employee authority:** owner delegate, executive, manager, specialist, reviewer, or another job.

Existing backend terms such as `manager`, `worker`, and `root_manager` may remain during migration, but UI and new domain logic must not infer an employee reporting line from them.

The effective permission for an action is the intersection of company policy, job contract, identity grant, assignment scope, and the hosting computer's ownership and capability. A manager cannot silently expand a worker's access. Missing access produces a scoped request with reason, duration, and expected effect.

### Root controller and worker data placement

Version one uses one authoritative root controller per company. The company lives permanently on the computer where it was created. It can operate across many enrolled computers without copying a fully writable company database to every one.

The root controller holds the authoritative company charter, organization, policy, company-wide indexes, membership registry, and root keys. Every local company partition, including the root partition, is encrypted at rest with a distinct company key protected through the operating system's credential protection. A worker membership receives only its encrypted, company-scoped partition, such as:

- its membership certificate and relationship state;
- the company identities hosted on that computer;
- assigned and locally queued work;
- relevant identity memory and task working state;
- explicitly approved company or team knowledge;
- workspace, credential, model, tool, and resource grants;
- reports and events awaiting return to the root.

A worker computer does not receive the full company database and may perform company work only while it has a live authenticated session to the root. The root background service may run while its UI is closed, but if the service or Yggdrasil route becomes unavailable, remote work for that company pauses. The same worker computer remains free to operate its own local companies.

Company data should use separate storage roots such as `companies/{company_id}` with company-scoped caches, events, identifiers, keys, and Yggdrasil membership tokens. A shared transport connection does not create shared authorization. Workspaces are exclusive to one company by default, and credentials are either company-owned references or local secrets explicitly granted to one company membership.

Per-company encryption protects stored data from casual cross-company access and offline file inspection without the OS-protected key. It cannot protect a running company from the physical operating-system administrator of its host. Stronger hostile-host isolation requires separate OS users, containers, hardware-backed isolation, or a similarly explicit deployment boundary; the UX must not claim otherwise.

### Moving an employee; keeping the company root fixed

**Move an identity within its company**

1. pause new dispatch and acquire a migration lease;
2. transfer the encrypted identity, job, memory, and relevant task state to another enrolled computer;
3. verify integrity and readiness on the destination;
4. change the identity's single home-computer membership;
5. archive or remove the source copy only after acknowledgement.

The destination remains whatever membership role it already had. Moving a manager identity to a worker node does not promote that computer to root.

Moving, restoring, promoting, replicating, or failing over the company root is outside version one. An encrypted backup preserves the complete company for safekeeping and future compatibility, but version one does not activate that backup as a new root on another computer. If the original root computer and its storage are permanently lost, that company cannot resume in version one.

### Persistent enrollment and live work sessions

Joining a company creates a durable, encrypted membership on the worker computer; disconnecting does not delete or log out that membership. Performing work requires a separate live session:

1. the worker proves its device identity and company membership to the root;
2. the root sends current permissions, assignments, and a short-lived work lease;
3. heartbeats keep the lease active while the authenticated route remains healthy;
4. the worker durably records checkpoints, artifacts, action outcomes, and reports in a local company outbox before sending them;
5. the root stores and acknowledges each item, and the worker retains anything not acknowledged;
6. if the connection or lease disappears, the worker starts no new company step and attempts to stop interruptible tools;
7. an indivisible action already underway may finish, but its outcome is recorded and the worker pauses immediately afterward;
8. reconnecting first reconciles assignments, checkpoints, side effects, reports, and acknowledgements before a new lease allows work to resume.

Unknown external-action outcomes must never be retried blindly. They remain visibly uncertain until the root and worker reconcile them.

### Backup and deletion

The fixed root supports manual export and optional scheduled encrypted backups to a user-chosen local destination. A portable backup is encrypted with a user-created backup passphrase and may also produce a separate recovery key. The operating system may remember the passphrase locally only after explicit user consent, but an OS-bound secret must never be the sole way to decrypt a portable backup. Passphrase creation, confirmation, recovery-key handling, verification, and failed-unlock behavior must be explicit and must not expose the secret in logs, notifications, or agent context.

Backups contain the company charter, organization, identities and job contracts, objectives, work records, reports, reviews, approved memory and knowledge, policy, audit history, artifact metadata, and approved artifact copies. They exclude raw credential values, pairing/session keys, provider secrets, operating-system-bound secret material, and absolute local workspace bindings; only safe references and reconfiguration requirements are retained. Every backup states its creation time, included/excluded classes, encryption and integrity result, and must not imply that version one can activate it on another computer.

Deleting a company is a root-only operation with an impact preview, active-work handling, optional final backup, and deliberate confirmation. Connected memberships are revoked and instructed to remove their company partition. An offline worker can no longer authenticate after deletion; its UI marks the membership permanently unavailable and offers **Remove unavailable company data**. A minimal signed deletion tombstone may remain on the root device so a later reconnect can receive the revocation without preserving business data.

### Multi-company runtime and UI rules

One application window has one active company. Separate company-pinned windows may be added later, but split-screen company operation is not required. Background assignments from several companies may run concurrently within device-owner quotas.

The interactive desktop, live browser profile, mouse, and keyboard form a device-global exclusive lease unless true isolation exists. Headless browsers and compute-only jobs may run concurrently under a fair scheduler and per-company limits. Company authority never overrides the device owner's total resource cap or emergency stop.

Removing or revoking a membership deletes or archives only that company's local partition and grants. It must not damage another company on the same computer.

### Migration from the current single-context app

An existing installation with workspaces, identities, chats, tasks, or Fleet relationships must not wake up as an empty multi-company app. On first upgraded launch, EmploAI offers **Turn this installation into a company** and shows a preview of what will move before writing anything.

The migration:

1. creates one immutable company ID and uses the user-confirmed company name;
2. makes the current computer that company's initial root controller;
3. places existing local identities, chats, workspaces, tasks, reports, approvals, settings, and knowledge into that company partition without deleting their source until verification succeeds;
4. marks name-only identities **Setup incomplete** and asks the user to confirm identity-specific jobs, managers, memory, tools, and workspace bindings;
5. splits existing workspace onboarding so repository/project facts stay with the workspace while employee role and behavior move to the relevant job contract;
6. converts current direct Fleet relationships into proposed memberships of that company, preserving the existing parent/current/direct-child UI and controls;
7. requires capability negotiation or re-enrollment before a legacy peer can receive company-scoped work if it cannot prove support for company IDs;
8. writes a local backup and migration report containing counts, mappings, warnings, and recovery instructions.

Until every connected computer understands company-scoped membership, compatibility mode must fail closed: legacy connections may remain visible and diagnosable, but they must not receive cross-company-capable routes, identities, credentials, or new company work. Migration must not silently merge two previously separate installations into one company.

## Company conceptual model

The product should use explicit company objects rather than hide the entire company inside prompts.

| Object | Purpose | Owns or contains |
|---|---|---|
| Company | The top-level isolated business tenant, addressed by an immutable `company_id` | Charter, status, operating currency, time zone, jurisdiction notes, storage and authority boundary |
| Charter | The durable source of direction and authority | Purpose, offer, customers, business model, principles, hard constraints, reserved decisions |
| Product or service | One thing the company builds, sells, or operates | Offer, lifecycle, owner, customers, economics, evidence, artifacts |
| Brand | A customer-facing identity used by one or more company offers | Name, audience, positioning, voice, channels, approved assets |
| Customer | A real organization or person served by the company | Contacts, relationship, consent, commitments, products, health, evidence |
| Lead or opportunity | A potential customer and commercial process | Source, qualification, stage, value, next action, evidence, owner |
| Contract or commercial commitment | A governed promise between the company and another party | Parties, scope, value, dates, obligations, approvals, source document |
| Invoice or financial record | A typed record of requested, received, owed, refunded, or spent money | Counterparty, amount, currency, status, dates, evidence, reconciliation |
| Support case | A customer request, problem, complaint, or service obligation | Customer, severity, owner, deadline, communication, resolution evidence |
| Campaign | A bounded coordinated external-communication effort | Audience, offer, channels, content, authority, budget, measurements |
| Release | A governed change delivered to a product or service | Scope, owner, tests, approvals, deployment, rollback, customer impact |
| Incident | A material operational, security, privacy, customer, or financial failure | Severity, commander, timeline, evidence, communications, recovery, follow-up |
| Objective | A measurable company outcome with a time horizon | Owner, target metric, deadline, confidence, linked initiatives |
| Department | A durable area of responsibility | Mandate, manager, positions, policies, KPIs, budget |
| Position | A seat in the organization independent of the current occupant | Job template, manager, authority, required capacity |
| Job template | A reusable specialization blueprint | Mission, workflows, deliverables, skills, suggested tools, success measures |
| Job contract | The company-specific agreement for one position | Responsibilities, exclusions, permissions, approvals, resources, reporting and escalation |
| Agent | The persistent, company-bound AI employee occupying a position | Identity, settings, private memory, readiness, work history, one home computer |
| Team | A group assembled around a stable function or temporary initiative | Members, manager, working agreement, shared context |
| Runbook | A versioned operating process | Trigger, steps, roles, handoffs, gates, retry and escalation rules |
| Initiative | A bounded body of work serving one or more objectives | Sponsor, owner, plan, budget, dependencies, status |
| Assignment | A durable unit of accountable work | Owner, outcome, inputs, constraints, evidence, due state |
| Handoff | A structured transfer of work between roles | Deliverable, acceptance criteria, evidence, known risks |
| Approval | A governed decision checkpoint | Requester, approver, policy basis, scope, expiry, decision |
| Artifact | A produced company asset | Source assignment, version, owner, review state, storage location |
| Report | A structured result or operating update | Outcome, evidence, confidence, metric movement, blockers, next action |
| KPI | A defined measurement of company or role success | Formula, source, owner, target, cadence, confidence |
| Decision | An auditable choice that changes direction or policy | Context, alternatives, rationale, authority, consequences |
| Policy | A durable rule constraining company behavior | Scope, owner, enforcement, exceptions, version |
| Computer | A physical, device-global runtime and trust boundary | Hardware, installed runtimes/models/apps, owner resource limits, isolated company partitions |
| Company computer membership | One company's enrollment of a computer | Company role, hosted identities, grants, capabilities, upstream/downstream relationships |
| Fleet relationship | A company-scoped direct private connection between computer memberships | Capabilities, permissions, status, assignment and report exchange |

The relationships should be visible:

```text
Human owner
    └── Company charter and reserved decisions
            ├── Objectives and KPIs
            ├── Organization
            │     └── Department
            │           └── Position
            │                 └── Job contract
            │                       └── Agent hosted through one company computer membership
            ├── Initiatives and runbooks
            │     └── Assignment → Handoff → Review → Report
            └── Policies, approvals, decisions, knowledge, and audit trail
```

An agent can change computers within its company without changing jobs. A position can receive a new agent without losing its mandate or history. A job template can be updated without silently changing an active job contract. An identity cannot cross the company boundary, and a physical computer's other memberships do not become visible through the agent. These distinctions are required for a stable company.

## Policy and authority precedence

When instructions conflict, the product must resolve them in this order:

1. safety and non-overridable local product protections;
2. company charter and owner-reserved decisions;
3. company policy;
4. department mandate and policy;
5. position job contract;
6. initiative or runbook contract;
7. assignment constraints;
8. live instruction.

A lower layer may narrow authority but must not grant more authority than a higher layer allows. A live message such as “ignore approvals and publish this now” cannot override a publication approval policy. The UI must show which higher rule blocked an action and who can legitimately change it.

## Whole-company information architecture

The global desktop modes remain stable:

```text
Chat · Jarvis · Company · Settings
```

Chat and Jarvis operate through the explicitly selected identity in the active company. Company opens the operating-system navigation defined below. Settings remains the device/application/runtime configuration surface; company-specific policy, workforce, work, and Fleet configuration stays inside Company. Background refresh, reconnect, or navigation must never switch the active company or identity implicitly.

The Company shell shows the active company at all times:

```text
[Company A ▾]   Command Center · Inbox · Company · Workforce · Work · Knowledge · Performance · Fleet · Governance
```

The selector is a context boundary, not a navigation tab. In version one, it groups entries as **Company owned here** and **Companies this computer works for**, shows the local membership role, and requires an explicit switch. A worker membership opens a restricted company console containing only locally hosted identities, assigned work, granted resources, and permitted topology. A root-controller membership opens the full company experience.

Within that active context, Company's internal navigation represents the company rather than the underlying database or agent framework:

1. **Command Center**
2. **Inbox**
3. **Company**
4. **Workforce**
5. **Work**
6. **Knowledge**
7. **Performance**
8. **Fleet**
9. **Governance**

### Command Center

The Command Center answers:

- Is the company moving toward its objectives?
- What happened since I last checked?
- What needs my decision?
- What is at risk?
- What is producing revenue or consuming resources?
- Which customers, projects, incidents, or workers need attention?

It contains:

- objective and KPI scorecards;
- revenue, cost, cash, pipeline, and customer-health summaries when configured;
- active initiatives and operating runbooks;
- an attention queue for approvals, blockers, incidents, low-confidence results, and policy conflicts;
- a concise company narrative generated from traceable reports;
- recent material decisions;
- quick actions such as create objective, start initiative, hire for a position, and review the day.

Routine worker activity should not dominate this screen. A company with 100 agents must still present a small, ranked attention surface.

### Inbox

Inbox is the human owner's complete, company-scoped visibility and action surface:

- every employee report from every assignment, including reports already routed to and reviewed by a manager;
- every CEO run, task, delegation, report, material decision, and escalation;
- manager decisions, requested revisions, acceptance state, and upward summaries;
- approvals, blockers, questions, incidents, connection failures, and other items requiring human action;
- original artifacts, evidence, task history, reporting chain, and source reports behind every summary.

CEO reports and human-action items remain pinned above routine employee reports. The same report object appears in the assigning manager's review queue and the human inbox; the system must not create contradictory copies. The inbox may collapse and filter routine items, but it must never make a worker report inaccessible to the human owner.

Inbox visibility does not mean the human must review every worker report. The assigning manager owns mandatory review. CEO reports are informational by default, so routine CEO work may complete without human acknowledgement even when the human requested it directly. Dangerous, material, legally reserved, or company-configured decisions remain pending when human acceptance or approval is required. The CEO efficiently synthesizes company state when the human asks, while notifications interrupt the human only under the configured ping policy.

### Company

Company is the selected company's charter and organization area; it does not create the company boundary by itself. It contains:

- charter;
- offer, customer, and business-model definitions;
- strategy and objectives;
- organization chart;
- departments and their mandates;
- operating calendar and cadences;
- company policies and decision log;
- company setup and change history.

One company may operate multiple products, services, offers, or brands while retaining one charter, root computer, owner authority, and organization. Departments and typed business areas are added only when useful; a casual company does not need to configure them.

### Workforce

Workforce contains:

- organization chart and position map;
- AI employees;
- open positions and hiring proposals;
- job-template library;
- team composition;
- readiness, workload, performance, and development;
- onboarding, transfer, replacement, suspension, and retirement flows.

### Work

Work contains:

- objectives and initiatives;
- recurring operations;
- runbook library;
- assignments;
- dependencies and handoffs;
- approvals and requests;
- artifacts and reports;
- incidents and improvement actions.

### Knowledge

Knowledge contains:

- verified company facts;
- customer and product knowledge;
- policies and procedures;
- research and source material;
- decisions and lessons;
- artifact registry;
- staleness, ownership, access, and provenance.

### Performance

Performance contains:

- company KPIs;
- revenue, costs, profit, and forecast views when data exists;
- objective progress;
- department scorecards;
- role and employee scorecards;
- throughput, quality, rework, approval delay, incident, and customer metrics;
- metric definitions and data confidence.

### Fleet

Fleet remains the selected company's private infrastructure and execution-capacity view. It shows company memberships, not every company installed on those physical computers:

- computers and their workers;
- computer activity and bounded screen previews;
- connection hierarchy;
- capacity and availability;
- exposed capabilities;
- direct-computer permissions;
- technical delegation, requests, reports, and diagnostics.

Fleet does not become the organization chart. A “Head of Sales” is managed under Workforce even if that agent currently runs on “Office PC.” Fleet shows where and how the employee runs; Workforce shows what the employee is responsible for.

The same physical computer may therefore render different Fleet roles after a company switch. It may be a worker/leaf in Company A and the root controller in Company C without either company learning that the other exists.

### Governance

Governance contains:

- approval policy;
- authority and spending limits;
- credentials and integration access;
- privacy and data-handling policy;
- model and resource policy;
- audit and decision records;
- emergency stop and recovery;
- policy exceptions and expiry;
- human-reserved decisions.

## Company onboarding flow

Business onboarding is optional, dismissible, resumable, editable, and visibly suggested from the already usable default company. It must not block casual assistant use or imply that the user already has a business.

### Step 1: Starting point

Ask exactly one business question:

```text
Where are you starting?

[I already have a business]
[Help me create a new business]
```

There is no third “assistant only” answer inside the wizard because dismissing or never opening business onboarding is already the default assistant-only state.

**I already have a business** continues by collecting verified existing-business context: company name, offer, customers, operations, commitments, revenue/cost state, assets, people, constraints, and goals. Unknown facts remain unknown.

**Help me create a new business** begins with the CEO working with the user to generate, compare, and select business ideas. It does not invent a charter or large organization before the user chooses an idea worth testing.

### Step 2: Owner and retained authority

Ask:

- What is your role in this company?
- Which decisions must always come to you?
- What may EmploAI decide without asking?
- What communication, financial, privacy, legal, and deletion actions require approval?
- What is the preferred review cadence?

The user can start from a safe approval preset, then change individual rules. External actions default to **Draft only**. Settings may independently make an action disabled, approval-required, bounded-autonomous, or broadly autonomous within company policy. The review shows concrete examples rather than abstract permission labels.

### Step 3: Company identity and purpose

Collect:

- company name;
- one-sentence purpose;
- products or services;
- target customers;
- customer problem and promised outcome;
- business model and pricing assumptions;
- stage: idea, validation, pre-revenue, operating, or scaling;
- primary operating currency, time zone, and relevant jurisdiction notes.

If the business idea is not yet validated, the setup must mark validation as the first company objective instead of inventing a large organization around an unproven plan.

### Step 4: Current reality

Ask what already exists:

- customers, leads, revenue, and costs;
- products, repositories, websites, domains, and documentation;
- active commitments and deadlines;
- available computers and model providers;
- connected tools and channels;
- known legal, technical, budget, or brand constraints;
- existing people or agents and their responsibilities.

Each answer can be “unknown.” Unknown facts become explicit setup gaps, not guessed truths.

### Step 5: Goals and success measures

The owner defines the next company horizon:

- primary outcome;
- deadline;
- target measures;
- maximum risk or spend;
- unacceptable outcomes;
- evidence that would prove success or failure.

For a new company, the proposed initial chain should normally be:

```text
Validate painful problem
    → validate reachable buyer
    → validate willingness to pay
    → deliver manually or with existing tools
    → learn from real use
    → approve product investment
    → build only what repeated evidence justifies
```

This preserves the principle that EmploAI should not write a product before the need is proven.

Every arrow in this chain is an evidence gate with criteria defined before execution. The validation contract records target segment, evidence type, sample expectations, deadline, pass threshold, failure/falsification criteria, and the approved meaning of willingness to pay. Model opinion, generated research, compliments, survey intent, traffic, or an employee's confidence cannot independently pass the demand gate. Passing normally requires observable target-customer behavior plus an approved economic commitment such as payment, deposit, preorder, signed pilot, or a deliberately accepted equivalent.

The employee gathering evidence reports it to its manager. That manager must review the source evidence and acceptance criteria before the result moves upward. The CEO or human owner performs the appropriate final verification; the evidence-gathering employee cannot mark its own validation work accepted.

### Step 6: Proposed organization

EmploAI proposes the smallest complete organization able to pursue the current objective. Departments are optional organization, not a prerequisite for using the company. The proposal includes:

- departments needed now;
- positions needed now;
- positions intentionally deferred;
- reporting lines;
- independent reviewers or approval gates;
- job-template sources;
- required tools, credentials, computers, and data;
- estimated capacity and model-resource needs;
- gaps that prevent readiness.

The user can approve the organization, edit it, or choose a simpler alternative. The system must not create dozens of decorative agents just because job templates exist.

### Step 7: Operating model

Choose or edit:

- daily, weekly, monthly, and quarterly cadences;
- status and reporting expectations;
- how initiatives are planned;
- how work is handed off and reviewed;
- how incidents are escalated;
- how customer-facing output is approved;
- how performance and role fit are reviewed.

Automations, recurring duties, and schedules are proposals until the user activates them. Activation makes the scheduled assignment a legitimate manager-issued trigger; it does not authorize unrelated worker initiative.

### Step 8: Tools, data, and Fleet placement

For every initial position, show:

- required tools and data;
- what is already available;
- which credentials require human setup;
- the proposed Fleet computer;
- model and capacity requirements;
- what remains unavailable.

The user may place agents manually. Automatic placement may propose a computer but must respect local ownership, availability, privacy, and permissions.

### Step 9: Readiness review and launch

The final screen groups positions into:

- ready to work;
- ready after a specific approval;
- blocked by missing tool, credential, data, model, or computer;
- intentionally deferred.

The user launches the company with an explicit first operating cycle. Setup completion must not be confused with business validation or operational readiness.

### Onboarding wireframe

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Build your business                                      Step 6 of 9 │
├─────────────────────────────────────────────────────────────────────┤
│ Proposed organization                                                │
│                                                                     │
│  You · Owner                                                        │
│    └─ AI CEO / Operating Lead                    Ready after review  │
│        ├─ Customer Discovery Lead                 Ready              │
│        ├─ Offer & Sales Lead                      Needs email access  │
│        └─ Research Reviewer                       Ready              │
│                                                                     │
│ Deferred until validation: Engineering · Support · Paid Media       │
│                                                                     │
│ Why this team? [View reasoning]   Missing requirements: 1           │
│                                                                     │
│ [Back]                [Edit organization]        [Approve and next]  │
└─────────────────────────────────────────────────────────────────────┘
```

## Specialized jobs using agency-agents

EmploAI should use [agency-agents](https://github.com/msitarzewski/agency-agents) as a reference corpus for specialization. The reviewed snapshot, commit `86a6695d4cee1c9720e2be4fd8ae007f9b6d96ae`, contains 245 role files across 17 divisions, plus coordination prompts, handoff templates, phased operating guidance, and machine-readable scenario runbooks.

The reviewed divisions are Academic, Design, Engineering, Finance, Game Development, GIS, Healthcare, Marketing, Paid Media, Product, Project Management, Sales, Security, Spatial Computing, Specialized, Support, and Testing. This gives EmploAI broad specialist coverage but does not prove that every company function is complete. Executive leadership, people operations, legal operations, accounting controls, procurement, and industry-specific regulated work may require curated EmploAI templates, combinations of existing operational patterns, or retained human responsibility.

The value of the repository is not merely a list of job titles. Its role files contain reusable operational structure:

- identity and role framing;
- communication style;
- critical behavioral rules;
- core mission;
- concrete technical deliverables;
- workflow process;
- success metrics;
- advanced capabilities;
- suggested external services;
- memory and learning expectations.

EmploAI should convert this material into structured, versioned job templates. It must not paste a large role Markdown file into every prompt and call that an employee.

### Role catalog ingestion

The ingestion path should be:

```text
Source role file
    → parse metadata and sections
    → normalize into an EmploAI job template
    → attach source, version, and license metadata
    → review and test the template
    → store in the local role catalog
    → apply a company-specific overlay
    → create a position and job contract
    → onboard one agent into that position
```

This should be a build-time or explicit local import/update process. Running a company must not depend on a live GitHub connection, and a remote repository update must never silently rewrite active employees.

Identity onboarding must expose the locally imported list of successfully parsed `agency-agents` jobs alongside custom jobs. The complete imported list may be browsed before every template has received an EmploAI stability review, but each entry must show its source version and review status. Selecting an unreviewed or experimental job never grants tools, credentials, authority, or readiness automatically; the company overlay, job contract, missing-requirement review, and readiness test still apply.

### Job-template schema

Every normalized template should contain:

| Field | Meaning |
|---|---|
| Template identity | Stable local ID, source slug, title, division, version, source commit |
| Purpose | Why the job exists and which company capability it serves |
| Mission | The outcome the role continuously owns |
| Responsibilities | Work the role is expected to perform |
| Non-responsibilities | Work explicitly outside the role |
| Deliverables | Recurring and event-driven outputs |
| Inputs | Facts, artifacts, events, and decisions needed to work |
| Workflows | Repeatable methods and ordered steps |
| Handoffs | Upstream inputs and downstream consumers |
| Quality gates | Required reviews, evidence, checks, and acceptance criteria |
| Suggested tools | Capabilities that may help; never implied permission |
| Suggested services | External integrations that may be configured separately |
| Success measures | Candidate outcome, quality, speed, cost, and risk metrics |
| Escalations | Conditions that require a manager, reviewer, or human |
| Memory guidance | What the role should remember and what it must not retain |
| Communication contract | Expected structure, detail, cadence, and audiences |
| Source metadata | Attribution, original file, license, import date, local changes |

Suggested tools and services describe requirements only. They must not create credentials, authorize use, or imply that an integration exists.

### Company overlay and job contract

A reusable template becomes useful only after it is adapted to the company. The company overlay supplies:

- the actual company, product, customer, and strategy context;
- the position's department and manager;
- current objectives and priorities;
- approved tools, accounts, data, workspaces, and channels;
- authority and approval boundaries;
- budget and model limits;
- concrete inputs, outputs, and recipients;
- reporting cadence and KPI definitions;
- privacy and retention rules;
- company terminology, brand rules, and communication constraints.

The resulting job contract belongs to the position. The agent accepts and passes a readiness check against that contract.

### Role discovery UX

Users should not need to know the agency-agents folder structure or exact title.

The role picker asks:

- What outcome should this employee own?
- What work will recur?
- What decisions should it make?
- Who supplies its inputs?
- Who uses its outputs?

It then proposes up to three relevant templates and explains the difference:

```text
You said: “Own the reliability of our production database.”

Recommended
  Database Reliability Engineer
  Best when the role owns availability, backup, recovery, and performance.

Alternative
  Backend Architect
  Broader application architecture; less operationally focused.

Alternative
  Incident Response Commander
  Best for coordinating incidents, not owning database health every day.
```

The user can choose one, combine responsibilities deliberately, create a custom role, or leave the position open.

### Role catalog UX

The catalog should support:

- search by outcome, responsibility, deliverable, division, and skill;
- filters for available tools, data sensitivity, approval level, and computer needs;
- preview of mission, workflows, outputs, metrics, and dependencies;
- comparison of two or three roles;
- source and local modification history;
- status: available, needs configuration, deprecated, or experimental;
- “Use in new position” rather than “spawn agent” as the primary action.

### Template updates

When the source corpus or local template changes:

- existing job contracts remain pinned to their current version;
- the product shows a readable change summary;
- the manager can test the new version with representative work;
- migration requires explicit approval;
- rollback remains available;
- local company overlays are preserved unless the changed field conflicts;
- attribution and source history remain intact.

### Corpus safeguards

The imported corpus is a strong starting point, not unquestionable truth. Before a template is marked stable:

- tool and service references must be checked for present availability;
- proposed metrics must be checked for measurability and incentives;
- domain-specific claims must be treated as guidance, not authority;
- legal, medical, financial, and security roles must have suitable human escalation;
- workflows must be tested on representative company tasks;
- redundant or overly broad roles should be split or clarified;
- license and attribution obligations must be retained.

## Organization design

The system should build a legible chain of accountability:

```text
Owner / legal principal
    └── Company operating lead
          ├── Department manager
          │     ├── Specialist
          │     ├── Specialist
          │     └── Independent reviewer or quality gate
          └── Cross-functional initiative lead
```

### Position rules

Every active position must have:

- one primary manager;
- one durable mission;
- clear responsibilities and exclusions;
- defined inputs and deliverables;
- at least one outcome or quality measure;
- a reporting cadence;
- explicit decision and tool authority;
- an escalation route;
- a current occupant or an open-position state.

An agent may contribute to multiple initiatives, but it should occupy one primary position. If one agent informally becomes sales, finance, engineering, and compliance, the UI should flag role overload and propose a split.

### Manager responsibilities

A manager agent is responsible for:

- turning objectives into coherent work;
- keeping work within policy and capacity;
- resolving normal priority and dependency conflicts;
- ensuring handoffs contain usable evidence;
- reviewing performance and role fit;
- escalating decisions outside its authority;
- reporting outcomes rather than inflating activity.

Every worker output for an assignment is submitted as a structured report to the manager that assigned it. The manager must review every report and either accept it, request a bounded revision, continue the workflow, reassign incomplete work, or escalate. A report cannot become accepted merely because a deterministic check passed or a recurring runbook produced it.

If a manager has a manager above it, the lower manager synthesizes material subordinate reports into its own upward report while preserving links to every original report and artifact. This chain continues to the CEO. Manager summaries reduce reading load but never remove the human owner's ability to inspect the original evidence.

A manager is not automatically allowed to inspect every private conversation, file, credential, or screen on a subordinate computer. Organizational authority and Fleet access remain separate.

### Independent review

High-impact work should not be created and approved by the same agent. Runbooks should be able to require:

- peer review;
- specialist review;
- security or compliance review;
- manager approval;
- human approval.

The reviewer receives the artifact, requirements, evidence, and known uncertainty—not the author's private chain of thought.

### Organization chart UX

The org chart shows positions first and occupants second:

```text
Growth
  Head of Growth                         Maya · Ready
    Customer Research Lead              Atlas · Working
    Content Strategist                  Open position
    Paid Media Specialist               Deferred

Engineering
  Engineering Lead                      Forge · Blocked
    Full-Stack Engineer                 Nova · Ready
    QA Automation Engineer              Checkpoint · Ready
```

Selecting a position opens:

- mandate and responsibilities;
- occupant and readiness;
- manager and direct reports;
- active objectives and recurring operations;
- job-contract version;
- tools, authority, approvals, and computer placement;
- workload and performance;
- recent handoffs, decisions, and exceptions;
- replace, transfer, suspend, or close-position actions.

## Hiring and individual agent onboarding

“Create agent” should evolve from the current name-first control into a position-based hiring flow. It remains possible to create a lightweight personal agent outside a company, but a company employee must have an explicit job contract.

### Hiring flow

1. **Choose or create a position.**
2. **Select a job template** from agency-agents, another local source, or a custom template.
3. **Adapt the job contract** to this company.
4. **Choose the manager and collaborators.**
5. **Assign tools, data, workspaces, model policy, and Fleet computer.**
6. **Set authority, approval, budget, memory, and reporting rules.**
7. **Review conflicts and missing requirements.**
8. **Run a readiness test.**
9. **Activate, save as blocked, or return the position to open.**

By default, the CEO or manager proposes each additional employee and the human approves creation. Company settings may make hiring more lenient by granting bounded authority over approved job templates, headcount, model/resource cost, computer capacity, departments, and time windows. No hiring setting may exceed the company owner's configured ceiling.

### Readiness test

The agent should demonstrate that it can:

- explain its mission and non-responsibilities;
- identify current company objectives relevant to the job;
- locate an approved input without reaching private data;
- produce a representative deliverable in the required format;
- identify when approval is required;
- hand the result to the correct next role;
- report uncertainty and a blocker honestly.

Readiness is not a claim that the model is generally intelligent. It is evidence that this specific employee can operate this specific job contract with the currently available resources.

### Missing requirement behavior

If a template expects a service, credential, model, file, or capability that is unavailable:

- the employee is not shown as fully ready;
- the missing item is named;
- the impact is explained;
- a safe configuration action is offered;
- the user may approve a limited mode with stated degraded capabilities;
- the system must not fabricate access or silently substitute a risky tool.

## Company operating system UX

### Command Center wireframe

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Kraitos Labs              Friday, 17 July              Company: Active │
├────────────────────────────────────────────────────────────────────────┤
│ PRIMARY OBJECTIVE                                                       │
│ Validate 5 paid design partners by 31 Aug        2 / 5 · At risk       │
│ Revenue €4,000 MRR target · Current €1,200        [Open objective]      │
├───────────────────────┬────────────────────────┬───────────────────────┤
│ NEEDS YOU · 3         │ OPERATING HEALTH       │ TODAY                 │
│ Publish proposal      │ 12 employees · 10 ready│ 7 assignments done    │
│ Approve €150 spend    │ 1 blocked · 1 incident │ 2 customer replies    │
│ Decide pricing change │ Cost today: €18.40     │ 1 failed handoff      │
├───────────────────────┴────────────────────────┴───────────────────────┤
│ ACTIVE INITIATIVES                                                      │
│ Design-partner outreach   On track   Sales Lead   Next: review replies │
│ Onboarding validation     At risk    Product Lead Blocked: 2 interviews│
├────────────────────────────────────────────────────────────────────────┤
│ MATERIAL CHANGES SINCE LAST REVIEW                                      │
│ Pipeline +3 qualified leads · One customer requested SSO · No policy   │
│ changes · Forecast confidence fell from medium to low.                  │
└────────────────────────────────────────────────────────────────────────┘
```

Every summary item must open its evidence. Generated narrative without traceable reports, records, or metric sources must be labeled as an interpretation.

### Objective flow

An objective includes:

- outcome statement;
- owner;
- baseline and target;
- deadline;
- measurement source;
- confidence;
- guardrails;
- linked initiatives;
- contributing departments and positions;
- review cadence;
- stop, pivot, or success conditions.

When a user creates an objective, EmploAI proposes initiatives and required roles. It must not automatically activate major work or hire agents until the user reviews the plan and resource implications.

### Initiative planning

An initiative moves through:

1. proposed;
2. scoped;
3. approved;
4. active;
5. blocked or at risk;
6. completed, stopped, or superseded;
7. reviewed.

The planning view shows the outcome, owner, runbook, contributors, dependencies, budget, risk, acceptance evidence, and expected KPI contribution.

### Recurring operations

Recurring work should appear as operating processes, not an endless stream of automatically created tasks. Examples:

- daily pipeline follow-up;
- weekly customer insight synthesis;
- release readiness review;
- support queue triage;
- security patch review;
- invoice reconciliation;
- monthly management report.

Each operation has a trigger, owner, runbook, schedule, inputs, output, quality gate, escalation timer, and history. It remains inactive until the user enables it. Each run is a manager-authorized scheduled assignment and ends in a report requiring manager review.

### Company runbooks

The agency-agents repository includes scenario runbooks such as startup MVP, enterprise feature, marketing campaign, and incident response, plus phased guidance from discovery through ongoing operation. EmploAI should use these as seed team/runbook templates.

A normalized runbook contains:

- objective and activation condition;
- required positions or capabilities;
- phases and ordered steps;
- per-step owner;
- expected artifact and acceptance criteria;
- handoff recipient;
- dependencies and parallelizable work;
- approval and quality gates;
- retry limit;
- escalation and stop conditions;
- completion report;
- post-run learning review;
- source and version.

### Handoff contract

Every cross-role handoff should include:

| Field | Requirement |
|---|---|
| From / to | One accountable sender and receiver |
| Purpose | Why the recipient needs this |
| Deliverable | Artifact or decision being transferred |
| Acceptance criteria | What makes it usable |
| Evidence | Sources, tests, customer data, or verification |
| Assumptions | Important beliefs not yet proven |
| Known risks | Failure modes or uncertainty |
| Requested action | Review, approve, continue, publish, or decide |
| Deadline | When the downstream step becomes at risk |

The recipient can accept, reject with a reason, request a bounded revision, or escalate. A runbook must cap automatic revision loops. Repeated failure becomes a manager-visible blocker rather than infinite agent-to-agent chatter.

### Work detail UX

A work item opens one coherent detail surface:

```text
Assignment: Draft design-partner proposal
Objective: Validate 5 paid design partners
Owner: Offer & Sales Lead
Runbook: Design-partner outreach v2 · Step 4 of 7

Outcome     Evidence     Handoffs     Approvals     Activity     Cost

Current state: Waiting for owner approval
Requested action: Approve external send to Acme
Policy basis: First contact to a new recipient requires approval
Artifact: Proposal v3 · Reviewed by Brand Reviewer
Confidence: Medium · pricing assumption is not yet validated
```

Raw chat remains secondary. The work object, result, evidence, policy, and next decision are primary.

## Company operating loops

The core closed loop is:

```text
Company signal or goal
    → objective
    → initiative or recurring operation
    → runbook
    → accountable assignments
    → artifacts and handoffs
    → review or approval
    → external or internal outcome
    → KPI and financial effect
    → learning and decision
    → updated plan, procedure, or job contract
```

### Validation and product loop

1. Collect observed customer problems.
2. Separate evidence from interpretation.
3. Prioritize a testable assumption.
4. Design the smallest valid test.
5. Obtain any required external-contact approval.
6. Run the test and capture evidence.
7. Decide continue, change, stop, or build.
8. Update product knowledge and roadmap.

No engineering assignment should be created solely because an agent suggested a feature. It must link to an approved objective and evidence threshold.

### Marketing and sales loop

1. Define audience and claim.
2. Validate contact source and communication policy.
3. Create campaign assets.
4. Review brand, truthfulness, privacy, and channel rules.
5. Publish or send under the required approval level.
6. Capture responses and pipeline movement.
7. Qualify, follow up, propose, negotiate within authority, and close with human signature where required.
8. Hand the customer to onboarding and finance.
9. Update acquisition and revenue metrics.

### Customer loop

1. Receive request, behavior signal, or health change.
2. Identify the customer and service commitment.
3. Resolve from verified knowledge or route to the right specialist.
4. Ask approval before exceptional promises, credits, sensitive disclosure, or contract changes.
5. Confirm resolution with the customer.
6. Update customer health and product feedback.
7. Escalate systemic issues into product or incident workflows.

### Finance loop

1. Ingest approved revenue and cost records.
2. Reconcile source, amount, currency, date, customer or vendor, and purpose.
3. Flag missing evidence, duplicates, anomalies, and overdue items.
4. Prepare forecasts and management reports.
5. Request approval for payments or commitments.
6. Preserve the human/legal step required by the financial provider.
7. Close the period and report revenue, cost, profit, cash, variance, and confidence.

### Incident loop

1. Detect or receive an incident.
2. Assign severity and incident owner.
3. Protect customers and company assets.
4. Activate the relevant response team and runbook.
5. Record timeline, decisions, changes, and evidence.
6. Communicate through approved channels.
7. Verify recovery.
8. Perform a blameless review.
9. Create owned prevention work and update runbooks.

## Operating cadences

Cadences create organizational memory and control without requiring the owner to watch every task.

### Daily

- review urgent approvals, incidents, customer risk, and blocked revenue work;
- reconcile major external outcomes;
- check resource or provider failures;
- summarize material changes, not all activity.

### Weekly

- review objective progress and confidence;
- inspect sales pipeline, customer learning, product movement, and operating costs;
- resolve cross-department dependencies;
- review overloaded, idle, or repeatedly blocked positions;
- approve next week's priorities.

### Monthly

- review revenue, cost, profit, cash, forecast, and KPI definitions;
- evaluate department and employee outcomes;
- review policy exceptions, incidents, access, and stale knowledge;
- improve runbooks and role contracts;
- decide hiring, replacement, reorganization, or retirement.

### Quarterly or strategic

- revisit the charter, market assumptions, offer, pricing, and major objectives;
- review whether company structure still matches strategy;
- stop low-value recurring work;
- test major template, model, or infrastructure changes before adoption;
- record the owner's decisions and rationale.

The owner can change cadence, but the system should warn when a critical function has no review path.

## Company knowledge and memory

Company memory must be layered:

| Layer | Examples | Default visibility |
|---|---|---|
| Company truth | Charter, product facts, pricing, policies, active objectives | All roles that need it |
| Department knowledge | Sales playbook, engineering standards, support procedures | Department and approved collaborators |
| Initiative context | Scope, decisions, artifacts, current risks | Initiative team |
| Position memory | Durable lessons and procedures belonging to the seat rather than one occupant | Current occupant and manager as policy allows |
| Agent private memory | One identity's durable experience, preferences, commitments, and private conversation context | That identity on its home computer |
| Task working state | Checkpoints, open steps, evidence, and resumable execution state for one assignment | Assigned identity and authorized reviewers |
| Sensitive vault | Credentials, regulated or secret values | Explicitly authorized tools; values not exposed in normal UI |

Long-term memory must be keyed by both `company_id` and `identity_id`. Two identities in the same workspace must not inherit one another's private memory, and switching companies must never place another company's memory in retrieval context. Position knowledge and shared company knowledge are explicit layers, not a reason to use one shared employee-memory store.

Durable memory writes should include timestamp, source/provenance, confidence, sensitivity, and optional review or expiry. The employee should save stable decisions, learned preferences, commitments, outcomes, and reusable lessons; it should not indiscriminately store raw transcripts, secrets, or short-lived scratch text. Identity migration transfers the private-memory partition through the controlled migration flow, while replacing an occupant does not silently give the replacement the former occupant's private memory.

Every authoritative knowledge item should show:

- owner;
- source and provenance;
- verification state;
- effective date;
- last reviewed date;
- sensitivity;
- consumers;
- superseded version, when relevant.

If an agent finds a conflict between an authoritative record and a live instruction, it should stop the affected action, surface both sources, and request a legitimate resolution.

## Universal employee runtime behavior

Every specialized job runs on one universal employee runtime. The job contract changes what the employee is responsible for, but every employee must share the same reliable operating behavior:

- receive a structured assignment with objective, acceptance criteria, priority, creation time, deadline, dependencies, inputs, allowed tools and spend, approval gates, required outputs, and reporting cadence;
- preflight the assignment against company policy, job authority, readiness, computer capability, and resource conflicts;
- decompose work into checkpoints, preserve resumable task state, warn before a deadline becomes impossible, and escalate blockers with their likely impact;
- verify the result against acceptance criteria and return evidence, uncertainty, side effects, and a recommended next action;
- use the current date, time, time zone, time remaining, and elapsed time supplied dynamically by the runtime so deadlines and stale commitments are meaningful;
- retrieve and write only the identity, position, team, company, and task memory layers authorized for that employee.

The runtime is event-driven, not a continuously thinking loop. A worker wakes for a manager assignment or an enabled scheduled assignment, then works until it submits, blocks, pauses, or is stopped. It may decompose the assigned objective into internal steps, but it does not independently create company initiatives or unrelated work. Managers and the CEO may wake for owner instructions, subordinate reports, configured company events, deadlines, approvals, and enabled management schedules, then create work only within their authority.

Every completed non-CEO execution produces an artifact or outcome plus a structured report to the assigning manager. Submission changes the assignment to **Submitted**; only manager acceptance changes it to **Completed**. CEO executions and delegations also create visible inbox records so the human owner can reconstruct what the CEO did, why it did it, what it delegated, and what resulted. A routine CEO report is informational and may complete against its acceptance criteria without human acknowledgement, including when the human assigned it directly; dangerous, material, legally reserved, or company-configured CEO work remains pending for human approval or acceptance.

Tool packs describe technical capability, not business authority. Access is composed from permanent job permissions, identity-specific grants, temporary task grants, one-action approvals, and explicit prohibitions. Temporary grants expire with their scope. When access is missing, the employee requests the smallest useful permission and states why it is needed, for which action, and for how long.

Employees request changes to tools, permissions, responsibilities, instructions, or job contracts through their manager. A manager may approve only within company policy and its own delegated authority. The CEO sends changes to its own job or authority to the human owner; it cannot approve its own authority expansion.

The runtime already supplies current time dynamically; the company system should make employee behavior use it consistently for planning, checkpoints, due dates, overdue escalation, recurring work, and reports rather than adding a static onboarding value.

## Performance and economics

The company must measure results without turning agent busyness into success.

### Measurement hierarchy

1. company outcome: revenue, profit, customer value, strategic evidence, or risk reduction;
2. department outcome: contribution to company objectives;
3. process health: quality, time, cost, rework, failure, and approval delay;
4. position outcome: contracted deliverables and decisions;
5. activity: supporting diagnostic data only.

Tokens used, messages sent, tasks created, and hours active are costs or operational signals, not success metrics.

### Metric safeguards

Each KPI must include:

- exact definition;
- source;
- time window;
- owner;
- target and baseline;
- confidence or data quality;
- known incentive risk;
- at least one balancing measure when gaming is plausible.

For example, “support tickets closed” should be balanced by repeat contact, resolution confirmation, customer satisfaction, and policy compliance.

### Profit view

When finance sources are connected, the Command Center should separate:

- booked or verified revenue;
- pipeline or forecast revenue;
- direct model and infrastructure cost;
- tool and channel cost;
- refunds, credits, and failed collection;
- gross and operating profit definitions;
- unknown or unreconciled items.

The UI must not present estimated pipeline as earned revenue or hide the cost of agent operation.

## Governance and autonomy

### Autonomy levels

Each job contract and action category should use a clear level:

| Level | Behavior |
|---|---|
| Observe | Read approved context and report; no mutation |
| Draft | Prepare work, but a person or authorized agent must approve use |
| Act with approval | Request a scoped approval immediately before the governed action |
| Act within limits | Execute autonomously while scope, budget, recipient, channel, and policy remain within limits |
| Emergency only | Available only during a declared incident and fully audited |

Autonomy is not one global switch. An agent may autonomously organize internal research while requiring approval to contact a customer or spend money.

### External-action settings

External actions include sending messages, publishing, contacting customers, spending, deploying, mutating external accounts, and similar effects outside private drafting. Each action category can independently be:

- **Disabled**;
- **Draft only**;
- **Approval required**;
- **Autonomous within configured scope**;
- **Broadly autonomous within company policy**.

New companies default to **Draft only**. The owner may expand scope in settings by company, job, identity, assignment, channel, recipient or audience, campaign, budget, action type, and time window. Lower-level grants cannot exceed a higher-level company boundary, but the product must not impose a permanently narrow approval model where the owner has deliberately granted lawful authority. Actions reserved to a human by law or real-world account ownership remain human decisions.

### Approval request quality

An approval must state:

- exact action;
- intended recipient or system;
- artifact or payload;
- reason and objective;
- expected benefit;
- cost or commitment;
- material risks;
- policy that caused the request;
- alternatives;
- expiry and whether the underlying facts may change.

“Allow?” is not sufficient.

### Emergency stop

The owner must be able to:

- pause one assignment;
- pause one employee;
- pause one department or runbook;
- stop external communication;
- stop spending or tool mutation;
- stop all company execution while preserving records;
- isolate or disconnect a Fleet computer.

Emergency controls must show what was stopped, what may still be in flight externally, what data was preserved, and how recovery will be reviewed.

## Whole-company edge cases

### Conflicting goals

If two active objectives compete for the same capacity or require contradictory outcomes, the system shows the conflict, affected deadlines, and current authority. It must not let whichever agent runs first silently win.

### Conflicting policies or instructions

The action pauses at the narrowest safe boundary. The UI shows both rules, their precedence, owners, and possible resolutions. Only an authorized policy change or exception can unblock it.

### No qualified role

If no job template fits, EmploAI proposes a custom position or a bounded discovery task. It must not assign specialist authority to the nearest vaguely related agent.

### Missing employee or manager

An open, suspended, offline, or failed position causes its owned recurring work and dependencies to appear in an uncovered-responsibility queue. Temporary reassignment must be explicit and time-limited.

### Missing tool, credential, data, or computer

Affected work enters **blocked by requirement**, not generic failure. The dependency, owner, safe setup action, degraded alternative, and deadline impact are shown.

### Stale company knowledge

If a required fact is past its review date or contradicted by newer evidence, the agent marks the output as uncertain and requests verification before high-impact use.

### Duplicate work

Before starting, an assignment checks for matching active work, artifacts, and initiatives. The user or manager can reuse, merge, supersede, or intentionally run an independent comparison.

### Infinite agent loops

Runbooks must have bounded retries, maximum handoff cycles, time and resource budgets, and an escalation route. Repeated revision without new evidence becomes a blocker.

### KPI gaming

Suspicious metric improvement accompanied by worse balancing metrics, missing evidence, or changed definitions is flagged. Agents may not redefine their success measure to appear successful.

### Low-confidence result

Low confidence is never hidden behind a completed state. Depending on impact, the result is sent for review, rerun with a different method, or escalated with the unknowns.

### Model or provider failure

The assignment retains its state and evidence. A fallback model may run only if allowed by the job's model, privacy, cost, and quality policy. The UI identifies the fallback.

### External integration outage or expired authorization

Work stops before the external action, the local artifact is preserved, and the system reports whether retry is safe. Reauthorization must not expose credentials through agent conversation.

### External platform rejection

A rejected email, post, payment, deployment, or API request is not marked complete. The system stores the returned evidence, distinguishes retryable from policy failures, and escalates account restrictions or legal concerns.

### Approval timeout

The request expires or escalates according to policy. The agent must not reinterpret silence as permission. If facts changed while waiting, a previously granted approval may require reconfirmation.

### Suspicious or malicious instruction

Instructions from customers, documents, websites, emails, or tools are treated as untrusted inputs. They cannot change company policy, reveal secrets, authorize payment, or expand scope without the proper authority path.

### Customer complaint or safety incident

The case receives an accountable owner, severity, response deadline, evidence preservation, communication policy, and escalation route. Agents must not optimize for closing the ticket over resolving harm.

### Legal or regulatory uncertainty

The system labels the uncertainty, preserves sources and jurisdiction context, and routes the decision to a qualified human. It must not present model-generated text as legal authorization.

### Financial anomaly or fraud signal

The affected transaction or action is held. Evidence is preserved, access is not broadened, and the owner receives a concise risk report. A suspected compromised agent or credential can be isolated.

### Employee underperformance

The manager distinguishes unclear contract, missing resources, capacity conflict, model limitation, bad runbook, and genuine repeated failure. Corrective actions may update the job, tools, training examples, model, placement, or occupant.

### Agent replacement

Replacing an agent preserves the position, contract, approved shared knowledge, active work, decisions, and audit history. Private memory is not copied unless policy explicitly allows a reviewed transfer.

### Reorganization

Moving a position between departments previews changes to manager, policy, knowledge access, approvals, metrics, active work, and Fleet placement. The reorganization is versioned and reversible before finalization.

### Job-template migration failure

The active contract remains on the previous version. The failed test and incompatible fields are shown. No position is partially migrated.

### Human override

An authorized owner can override a non-safety decision with a reason. The override is scoped, time-limited where appropriate, visible in the audit record, and does not silently rewrite the standing policy.

### Company pause or shutdown

A planned pause stops schedules and new assignments, handles work in flight, preserves knowledge and audit records, revokes or suspends external access according to policy, and identifies outstanding obligations. Company shutdown is not the same as deleting local data.

### Company switch with unsaved or active work

The app saves drafts and navigation state under the current company before switching, or blocks the switch with a specific unsaved-change choice. Active background work may continue, but any notification names its company. No modal, search result, recent item, clipboard helper, or cached screen from the old company may remain active in the new context.

### Root controller offline

Every remote work lease for that company expires and worker execution pauses at the next safe boundary. Workers preserve unacknowledged checkpoints and outcomes in their local company outbox but do not start or continue new company steps until the original root reconnects, reconciliation succeeds, and a new lease is issued. Their unrelated local companies remain operational. Version one offers reconnect/restart of the original root, not restore elsewhere, authority transfer, or worker promotion.

### Computer belongs to several companies

Device-level resource scheduling may account for all workloads, but each company sees only its own membership, hosted identities, grants, usage allowance, and jobs. The interactive desktop is leased globally, while company-private errors and activity remain in their own partitions.

### Cross-company delegation is attempted

The dispatch is rejected before context or capability disclosure. If future inter-company collaboration is supported, it must use an explicit export/import or approved external bridge with a named sender, recipient, payload, authority, and audit record; it must not behave like an internal delegation.

### Company deletion or membership removal

Deleting a company requires root authority, an impact preview, handling for active work, an optional final encrypted backup, and deliberate confirmation. Connected worker memberships are revoked and cleaned up. An offline worker remains unable to work for the deleted company and offers local removal when it learns the membership is permanently unavailable. Removing or deleting one company cannot remove another company or device-global runtime.

## Whole-company acceptance scenarios

### Scenario 0: First-run casual assistant

The first launch creates a renameable local company with a CEO selected as the main chat identity and a separate minimally permitted default worker. The user chats immediately, may let the CEO delegate suitable work, and sees a dismissible business-onboarding suggestion. No business idea, department, automation, schedule, or external authority is required.

### Scenario A: Start from an unvalidated idea

The CEO and owner generate and compare ideas, then choose a target customer, problem, and offer. Before outreach, they define a validation contract with evidence and falsification criteria. EmploAI defers engineering, runs approved discovery, preserves real source evidence, and cannot mark demand validated until manager review confirms the agreed customer behavior and economic-commitment threshold.

### Scenario B: Hire from agency-agents

The owner describes a database reliability need. The system proposes relevant role templates, creates a position and company-specific job contract, identifies missing monitoring access, places the agent on an appropriate computer, runs readiness checks, and activates it only when requirements are satisfied.

### Scenario C: Run a cross-functional launch

A launch objective activates a versioned runbook across product, engineering, QA, marketing, sales, support, finance, and security. Handoffs and gates are visible; no team silently claims completion while a required downstream role is blocked.

### Scenario D: Generate revenue with control

A sales employee qualifies a lead, drafts a proposal, requests approval for a new-recipient send and pricing exception, records the outcome, hands the customer to onboarding and finance, and updates verified revenue separately from forecast pipeline.

### Scenario E: Operate a customer incident

Support detects a severe issue, activates incident response, preserves the timeline, coordinates engineering and communication, requests human approval where required, verifies recovery, and creates owned prevention work.

### Scenario F: Monthly company review

The owner sees objective movement, revenue, cost, profit, customer risk, incidents, policy exceptions, and workforce health. Every summary opens evidence, and unknown finance data remains visibly unknown.

### Scenario G: Replace an employee

A repeatedly failing employee is reviewed. The system identifies whether the cause is role, resources, runbook, model, or occupant. Replacing the occupant preserves company work and shared knowledge without copying private memory improperly.

### Scenario H: Fleet computer goes offline

The live lease expires, the worker stops Company A execution at a safe boundary, and unacknowledged state remains durable locally. The company view identifies affected positions and processes, avoids duplicate dispatch, and reconciles before returning to normal when the connection to the original root recovers. Other companies on the worker continue normally.

### Scenario I: One computer serves several companies

Computer Q is a worker node for Company A and root controller for Company C. Switching between them replaces the entire visible context and changes Q's Fleet role. Company A cannot see Company C, while device-level resource limits prevent either from monopolizing Q.

### Scenario J: Move an employee without moving the company

An authorized Company A manager moves one identity from Q to V. Dispatch pauses, encrypted identity and task state are verified on V, readiness reruns, and the old copy is retired only after acknowledgement. Q and V retain their existing Company A membership roles.

### Scenario K: Back up and delete a fixed-root company

The owner creates and verifies a complete encrypted backup, reviews active work and connected/offline memberships, then deliberately deletes Company A from its original root. Connected workers revoke the membership; offline workers can never resume it and later remove the unavailable partition. The backup is retained for safekeeping but cannot be activated on another computer in version one.

### Scenario L: Report chain and human inbox

A worker submits an output to its assigning manager, leaving the assignment Submitted. The manager reviews and accepts it, then includes the material result in an upward report. The CEO synthesizes it for the owner when asked. The human inbox contains the original worker report, manager decision, upward summary, CEO record, evidence, and artifacts, with the CEO layer prioritized rather than hiding the underlying chain.

## Product delivery slices

This specification should be implemented as connected, segregated product slices rather than one rewrite:

1. **Company foundation:** automatic default company, CEO and default worker, company registry and chooser, immutable company IDs, isolated storage/event boundaries, optional business onboarding, fixed root authority, encrypted backup/export, deletion, and migration of existing local data into one explicit company.
2. **Job system:** versioned agency-agents import, normalized templates, company overlays, positions, and job contracts.
3. **Workforce:** organization chart, position-based hiring, readiness, settings, and lifecycle changes.
4. **Operating work:** initiatives, recurring operations, runbooks, assignments, handoffs, artifacts, approvals, and reports.
5. **Company intelligence:** Command Center, knowledge provenance, KPI definitions, cost, revenue, profit, and review cadences.
6. **Fleet integration:** convert physical relationships into company-scoped computer memberships, then link positions and company work to the already implemented computers, activity, preview, permissions, capacity, and recovery behavior without removing current controls.
7. **Functional expansion:** add sales, marketing, product, engineering, support, finance, security, and other departmental connectors only when the required company loop is defined and verifiable.

Each slice should reuse the objects created before it, expose a migration path for existing local workers and workspaces, and ship with its own empty, loading, failure, permission, audit, and rollback behavior. The initial migration should place current records into one user-confirmed local company rather than treating missing `company_id` as globally visible data. No slice should require a hosted EmploAI account or weaken local ownership.

## Fleet expansion contract

The rest of this document defines Fleet in detail. It expands the current computer workspace into a stable infrastructure area inside the selected company. Existing screens may continue to derive their relationship from current local records during migration, but the destination model derives every role and route from the active company membership.

The following rules apply to all Fleet evolution:

- preserve the current computer-above / this-computer / direct-children point of view inside each selected company;
- preserve the direct-parent panel and direct-child-only card list;
- preserve local incoming-work activity and per-direct-child worker activity;
- preserve the bounded, view-only direct-child preview and its explicit privacy model;
- preserve local ownership and direct-computer permission decisions;
- preserve delegation, request, response, report, and compatibility states;
- scope snapshots, routes, permissions, tasks, and events by `company_id` and membership identity before rendering them;
- recalculate standalone, root, leaf, and connected-hub state per company membership rather than per physical computer;
- evolve the inline workspace into a stronger computer-detail experience without hiding current controls;
- evolve name-only employee creation into the position and job-contract onboarding flow;
- link Fleet workers to Workforce positions without making the org chart depend on topology;
- show company impact when a computer, worker, model, or capability is unavailable;
- do not add remote input control as an implied consequence of preview;
- keep protocol, address, firewall, and relay details under progressive diagnostics.

## Fleet product outcome

A user must be able to open Fleet for the selected company and quickly answer five questions:

1. How is this computer connected?
2. Which computer memberships, hosted identities, and capabilities are available to this company from here?
3. What work is active, blocked, waiting for approval, or finished?
4. What may each connected computer or agent do?
5. What needs my attention now?

The interface should feel like managing the infrastructure of a small organization. Business responsibility remains in Workforce and Work; Fleet should not feel like configuring a network protocol or browsing raw runtime records.

## Fleet product principles

### 1. Computers are not agents

Pairing enrolls one computer membership in the selected company. It does not expose the computer's other companies, create an agent, or copy an identity.

A physical computer can host isolated company partitions. Within one selected company membership it can expose:

- its protected local membership manager;
- its protected default worker;
- zero or more additional local agents;
- a connection to at most one upstream computer for that company;
- zero or more direct child computers.

Every agent has its own job profile, settings, permissions, memory policy, readiness state, and work history.

### 2. Relationships are direct and understandable

Within the selected company, the UI must distinguish:

- the upstream computer directly above this company membership;
- this computer;
- direct child memberships below this membership;
- descendants known only through summarized hierarchy metadata.

The interface must not imply that a computer can inspect private state on a grandchild or any other computer simply because it can see that the relationship exists.

### 3. Local ownership is visible

The company partition on the computer hosting an agent stores that agent's local execution state. The physical host retains control of:

- chats and detailed history;
- local files and workspaces;
- credentials and provider configuration;
- tool access;
- installed tool and model availability;
- local device resource and credential grants.

The company root remains authoritative for the identity, job contract, organization, and company policy. The upstream computer may route a company-authorized request or assignment, but the hosting computer can still deny a local capability, credential, or interactive-resource request. Neither side may see another company partition on the host.

### 4. Progressive disclosure

The normal flow must use plain product language such as **private Fleet connection**. Technical Yggdrasil, relay, firewall, address, and protocol details belong under diagnostics.

### 5. Attention before activity

Approvals, blockers, failures, unsafe conflicts, and stale connections must be more prominent than routine completed work.

### 6. No ambiguous destructive action

The UI must always distinguish:

- stop this assignment;
- stop this agent after its current step;
- stop all agents on this computer;
- disconnect a computer;
- delete an agent and optionally wipe its local state.

### 7. Safe defaults with explicit autonomy

Normal low-risk work may proceed under the assigned autonomy policy. External communication, money, deletion, public publishing, credentials, sensitive data, broad dispatch, and unusual scope expansion must follow explicit approval rules.

## Terminology and disambiguation

These definitions apply throughout the specification. They are intentionally explicit because the current code and earlier UI sometimes use company, computer, manager, worker, agent, and identity language for different concepts.

### Company and employee terms

| Product term | Meaning | Important distinction |
|---|---|---|
| Company | One isolated business tenant with an immutable `company_id` | Not a workspace, Fleet, computer, account, or container for another company |
| Active or selected company | The one company currently scoping the application window, navigation, queries, actions, and visible data | Not a visual filter over globally loaded data |
| Human or company owner | The legal principal and final authority for owner-reserved company decisions | Not automatically the physical device administrator on every worker computer |
| Device owner | The local authority over one physical computer, its installation policy, secrets, total resources, and emergency stop | Cannot inspect or govern another company merely through Fleet authority |
| Company owned here | A company created on this computer, which remains its fixed authoritative root in version one | Does not make the computer globally primary for other companies |
| Company this computer works for | A company in which this computer has a worker membership | Does not prevent this computer from owning unrelated companies |
| Company partition | The isolated local storage, cache, event, key, and runtime namespace for one company on one computer | Not a full company copy on every worker node |
| Company onboarding | Creation of one company's charter, goals, authority, policies, organization, and shared operating defaults | Not device setup or employee onboarding |
| Identity | The persistent, company-bound continuity record for one AI employee | Remains the same through an internal job change or same-company computer migration; never crosses companies |
| Agent or AI employee | The operating employee represented by an identity and occupying a position | In this specification, “identity” emphasizes the durable record and “agent” emphasizes the acting employee/runtime; neither means computer |
| Position | A durable seat in the organization with a mandate and reporting line, independent of its current occupant | Not the identity occupying it |
| Job template | A reusable specialization blueprint, potentially derived from agency-agents | Not an active employee prompt or permission grant |
| Job contract | The versioned company-specific responsibilities, exclusions, authority, tools, outputs, KPIs, reporting, and escalation rules for one position/occupant | May change without replacing the identity; cannot grant more than company policy |
| Job profile | The UI/runtime view composed from the active job template, company-specific contract, and identity overrides | Not a separate authority source or one pasted prompt |
| Employee onboarding | Identity-specific setup of job, manager, tools, workspaces, permissions, memory, reporting, model/resource policy, and readiness | Never shared merely because two identities use one workspace |
| Manager identity | An employee whose job contract grants organizational responsibility for other positions or work | Not an upstream computer or Fleet root |
| Home computer | The one computer membership currently hosting an identity's authoritative local execution and private-memory state | May change only through controlled same-company identity migration |
| Workforce | The product area that owns identities, positions, jobs, reporting lines, readiness, and employee lifecycle | Fleet may show placement but is not the workforce source of truth |

The phrase **company identity** is ambiguous and must not be used in implementation or primary UI copy. Use **company** for the business tenant, **identity** for an employee, or **company computer membership** for a computer's role in that company.

### Computer and Fleet terms

| Product term | Meaning | Important distinction |
|---|---|---|
| Device or computer | A physical computer, VPS, or runtime host with hardware, installed runtimes/models/apps, and owner resource limits | Not a worker, employee, identity, company, or globally rooted node |
| Device-level shell | The company-neutral UI containing the company chooser, This Computer, device resources, memberships, root-company creation when none is owned, backup export, and deletion entry points | Must not display combined private company work or offer version-one root transfer |
| Company computer membership | One company's isolated enrollment, grants, and topology role on a physical computer | A computer may have several memberships, but at most one for each company |
| Membership role | The infrastructure role of one company membership: fixed root controller or worker node in version one | Not an employee job, reporting authority, standby, or automatically promotable role |
| Root controller | The computer where the company was created and the single authoritative writable controller for that company in version one | Not the CEO identity, device owner, movable role, or globally primary computer |
| Worker node or worker membership | A durable company enrollment that receives scoped work and data only during a live authenticated session to the root | May simultaneously be root controller for an unrelated company on the same computer |
| Live work lease | Short-lived root authorization permitting one connected worker to execute company work while heartbeats and policy remain valid | Enrollment alone does not permit offline execution |
| Company outbox | Durable worker-local records awaiting root acknowledgement, including checkpoints, artifacts, action outcomes, and reports | Not authority to continue working while disconnected |
| Fleet | The active company's private hierarchy of enrolled computer memberships and execution capacity | Not an account, cloud, remote desktop, organization chart, or list of every company on a device |
| Fleet relationship | A company-scoped direct Yggdrasil relationship between two computer memberships | Sharing transport does not share company authorization |
| Upstream or parent computer | The one direct computer above this membership inside the active company | Not an employee manager; “parent” is topology shorthand only |
| Child or downstream computer | A distinct remote computer paired directly below this membership for the active company | Never another identity, workspace, or company on the same physical machine |
| Root membership | A membership with no upstream that holds the company's root authority | Not every temporarily disconnected worker |
| Leaf membership | A worker membership with an upstream and no children in that company | The same computer can have another role in another company |
| Connected hub | A worker membership with both an upstream and one or more children in that company | Does not gain company-root or employee-manager authority |
| Standalone | Legacy/current Fleet state with no saved upstream or child relationship; after company migration, usually a root-owned company with no connected computers | Must not imply absence of other company memberships on the device |
| Membership manager | The protected local manager identity for one company membership | Coordinates that membership's workers and direct child memberships; not a global identity or physical-computer role |
| Default worker | The protected general execution identity for one company membership | Not the computer itself and never shared across company memberships |
| Yggdrasil | The direct private network transport used by Fleet connections | Provides reachability, not company authorization or organization structure |

Unless a paragraph explicitly describes the legacy implementation, unqualified **parent**, **child**, **root**, **worker**, **leaf**, **hub**, and **standalone** language in the Fleet sections means the relationship state of this computer's membership in the active company, never a global role for the physical device.

### Work, access, and movement terms

| Product term | Meaning | Important distinction |
|---|---|---|
| Workspace | A company-bound project/repository resource containing paths, commands, constraints, and reference material | Does not define an employee identity, job, manager, or private memory |
| Tool pack | A reusable bundle describing technical tools an employee may need | Capability does not itself grant business authority |
| Capability | A safe summary of a tool, model, workspace, credential-backed action, or resource that a membership or identity can technically provide | Not a private settings snapshot or permission |
| Permission or grant | A scoped authorization allowing an identity or membership to use or request something | Effective access is still limited by company policy, job contract, task scope, and device capability |
| Assignment or task | A durable unit of accountable work with objective, acceptance criteria, priority, time/deadline, inputs, constraints, approvals, outputs, and evidence | Not a transient chat message or raw command |
| Delegation | An authorized identity assigning company work to another identity in the same company | Computers route delegation but do not possess organizational authority; cross-company delegation is blocked |
| Request | A structured question, approval need, blocker, or resource/access request | Not a generic error |
| Report | A structured assignment outcome containing evidence, confidence, effects, blockers, and next action; non-CEO reports require assigning-manager review, while CEO reports are informational unless human review is required by task or policy | Not merely a final chat response or invisible activity |
| Company Inbox | The human owner's complete company-scoped view of every employee report, CEO action/delegation record, manager review, approval, blocker, and escalation | Visibility does not make the human the mandatory reviewer of every worker report |
| Identity migration | The controlled movement of one identity's job, private memory, and task state to another enrolled computer in the same company | Does not change company root or copy the identity between companies |
| Company backup | A complete encrypted export created manually or on a schedule for safekeeping | Version one cannot activate it as a root on another computer |
| Interactive desktop lease | The device-global exclusive right to use the live mouse, keyboard, desktop application, or non-isolated browser profile | Unlike isolated compute, it cannot safely be used by two companies simultaneously |

### Legacy implementation language

Backend names may continue to use `worker`, `manager`, `root_manager`, or `target` during migration. They must be interpreted through company membership and explicit job authority:

- `root_manager` or network `manager` means an infrastructure routing state unless an employee job contract separately grants management authority;
- `worker` may mean a legacy agent record or a worker computer depending on the current code path, so new domain objects and UI copy must say **identity** or **worker node** explicitly;
- `target` identifies a technical dispatch destination, not a person, job, or permission;
- **reports above** and **manages below** in the current Fleet UI mean upstream/downstream infrastructure routing and should migrate to that language;
- no legacy field may be used alone to infer `company_id`, employee reporting lines, root authority, or cross-company access.

## Fleet conceptual object model

```text
Selected company
    ├── Organization
    │       └── Position / job contract
    │               └── Agent identity
    │                       └── Hosted through one company computer membership
    └── Fleet memberships
            └── Root controller membership
                    └── Upstream / this / direct-child membership hierarchy

Physical computer
    ├── Device-global runtimes, models, apps, and resource limits
    ├── Isolated Company A partition and membership role
    └── Isolated Company C partition and membership role

Work lifecycle
    Objective → Assignment → Execution → Request or Report → Review → KPI/history
```

The relationship between an agent and its company computer membership must survive normal reconnects. Moving an agent between computers is a controlled, same-company migration and must never happen implicitly during pairing. Company-root transfer is not supported in version one.

## Fleet information architecture

The destination Fleet area uses a stable company-scoped header and five infrastructure sections:

1. **Overview**
2. **Computers**
3. **Connections**
4. **Resources & access**
5. **Settings**

The sections remain in the same order for every membership role. Content adapts to what this computer may see and manage in the selected company. Identities and reporting lines live primarily in Workforce; assignments, reports, blockers, and approvals live primarily in Work. Fleet may show hosted-identity placement, local activity, and relevant attention links, but it does not become their second source of truth.

During migration, the currently implemented agent, worker-activity, request, report, permission, and delegation controls remain available in their existing computer workspace. They should be progressively backed by the company objects and linked to Workforce or Work before any duplicate Fleet surface is removed.

### Global Fleet header

The header contains:

- selected company name and this membership's role;
- this computer's display name;
- one overall connection state;
- parent relationship, when present;
- number of direct children;
- number of local agents;
- attention summary;
- one primary contextual action;
- an overflow menu for infrequent and destructive actions.

Example:

```text
Company A · Office PC                          ● Ready
Root controller · 3 direct child connections

2 approvals · 1 blocker · 4 active assignments     [Add computer]
```

The header must not lead with raw values such as `ROOT_MANAGER`, `LEAF`, or `INTERMEDIARY`. Those are implementation states. Use **Root controller**, **Worker node**, or plain relationship copy, and never imply an employee-management role.

### Section visibility by relationship

| Company membership state | Overview | Computers | Connections | Resources & access | Settings |
|---|---|---|---|---|---|
| Company not enrolled on this computer | Not shown; use device-level company chooser | Join/import entry point | None | None | Device diagnostics only |
| Root controller with no children | Company capacity summary | This computer | Add-computer flow | Local company grants and capacity | Root, backup, transfer, diagnostics |
| Root controller with children | Full company infrastructure summary | Direct children + permitted tree | Downstream relationships | Company-visible capabilities, grants, capacity | Memberships, requests, recovery, diagnostics |
| Worker leaf | Local membership summary | This computer + upstream | Upstream relationship | Local grants, hosted identities, assigned capacity | Access granted to company + diagnostics |
| Worker hub | Up/down membership summary | Upstream + this + direct children | Upstream and downstream relationships | Local and permitted child capabilities | Upstream access + child requests + diagnostics |

## Responsive layout

### Wide desktop: 1180 px and above

- Global header across the top.
- Section navigation below the header.
- Overview uses a hierarchy pane and an attention/work pane.
- Computers uses a persistent list/tree on the left and selected-computer detail on the right.
- Resources & access may use a third contextual capability or permission pane when space allows.

```text
┌──────────────── Fleet header ────────────────────────────────┐
├ Overview | Computers | Connections | Resources & access | Settings ┤
├───────────────────────┬──────────────────────────────────────┤
│ Hierarchy/list        │ Selected object or operational view  │
│                       │                                      │
└───────────────────────┴──────────────────────────────────────┘
```

### Medium desktop: 760-1179 px

- Navigation may scroll horizontally but must not wrap into an ambiguous second row.
- List and detail stack vertically.
- Selecting a computer scrolls/focuses its detail region.
- The layout is automatic; there is no user-facing side-by-side/stacked preference.

### Narrow window: below 760 px

- Sections use full-width pages.
- Selecting a computer or agent opens a drill-down page with a visible Back action.
- Tables become labeled cards.
- Action bars remain reachable without horizontal scrolling.
- Dialogs occupy most of the viewport and preserve a dismiss action.

### Large Fleet behavior

At 20 or more visible computers or agents:

- search appears automatically;
- filters are available by status, relationship, attention, computer, agent, and job;
- lists use incremental rendering or virtualization;
- completed activity is paginated;
- summary counts are not calculated only from the visible page;
- bulk selection is explicit and always shows the selected count.

## Overview

The Overview is a status and attention surface, not a configuration form.

### No connected computers

```text
COMPANY A FLEET
This computer is the root controller

No other computers serve Company A yet.
[Add a computer]

What stays private
Other companies and ungranted device data remain private.
```

The current standalone **Start a private Fleet / Join an existing Fleet** screen remains usable until company selection is introduced. During migration, **Start** becomes **Add a computer** inside the active root-owned company, while **Join** moves to the device-level company chooser because it creates or restores a worker membership for a specific company. Network repair and diagnostics remain secondary.

### Connected overview

The connected overview contains:

- a compact relationship tree;
- connection health;
- active assignments;
- approvals and blockers;
- recent reports;
- local agent readiness;
- an event summary for the last 24 hours.

Routine completed activity must not push current blockers below the fold.

### Hierarchy visualization

```text
Main VPS
├── Office PC                    ← THIS COMPUTER
│   ├── Build PC                 ● Ready
│   └── Research PC              ○ Reconnecting
└── Laptop                       ● Ready
```

Rules:

- The current computer is always visually distinct.
- Direct relationships use solid lines.
- Descendants visible only through summaries use lighter lines and cannot be opened unless the direct child exposes navigation data.
- Status never relies on color alone.
- Selecting a direct computer opens Computers detail.
- Selecting a summarized descendant explains which direct child manages it.
- A cycle or duplicate identity is shown as a topology error, not rendered as an infinite tree.

## Computers

### Computer list

The implemented foundation is the current **Computers directly managed from here** grid. It includes only direct child computers; this computer is the point of view and is deliberately not repeated as a card. The direct-child cards already show agent and active counts, queue/request/latest context, and open an inline workspace.

The expanded list/tree should preserve that information while improving navigation at scale. Each row/card shows:

- display name;
- direct relationship: parent, child, or this computer;
- connection state;
- last confirmed contact;
- available agents, using the label **agents**, not **targets**;
- active and queued assignment counts;
- pending approval/blocker count;
- child count for a connected hub;
- update-required state when the capability protocol is stale.

`Latest` must identify what it means, for example `Latest assignment: completed 8m ago`, rather than showing a raw status word.

### Computer detail

The current inline direct-child computer workspace is the starting point. It already contains worker activity, view-only preview, delegation, creation, permissions, requests, responses, and recent reports. Local incoming work and upstream access remain in the current-computer side of the Fleet layout rather than being presented through a fake local card.

The expanded selected-computer detail contains these internal tabs:

- **Summary**
- **Available agents**
- **Activity**
- **View-only preview**
- **Assign work**
- **Requests**
- **Reports**
- **Connection**

On a wide layout, the detail should evolve into a persistent pane beside the computer list so selection and scroll position remain stable. On medium and narrow layouts, the current stacked workspace may evolve into a full-width drill-down. This is a layout migration, not a removal of current capabilities.

Until the persistent detail is implemented, the existing inline workspace remains valid and must not be stripped down.

### Summary content

- relationship and connection health;
- last contact and protocol version state;
- local capabilities explicitly exposed by that computer;
- current workload;
- outstanding requests;
- company positions and operating processes affected by this computer;
- privacy reminder;
- child-count summary, if the computer is a connected hub.

### Activity

The current **Latest on this computer** panel is retained as the foundation. It shows explicitly visible workers and identities with role, status, current task or report summary, and confidence context.

The expanded activity view should:

- keep the compact current summary at the top;
- distinguish active work, queued work, requests, failures, and recent reports;
- link technical work records to the company assignment, objective, runbook, and position when those links exist;
- show **No workers exposed yet** without implying the computer is disconnected;
- keep private chats and unexposed local state on the hosting computer;
- never substitute an activity feed for structured assignments or reports.

### View-only preview

The current **Current screen** implementation is retained. It provides:

- one deliberate **Capture now** action;
- manual, 1/min, 2/min, and 4/min options;
- clear capture time, image dimensions, and capture backend;
- offline, empty, loading, and capture-failure states;
- screenshots held only in the currently open panel's memory;
- automatic frame disposal when the panel closes or the selected computer changes;
- no mouse, keyboard, or continuous-video control.

The expanded UX should add company context without broadening the access boundary:

- show which agent and assignment are expected to be using the interactive desktop, when known;
- warn if a human or another assignment owns the interactive desktop;
- explain that the screenshot may contain sensitive local content before the first capture;
- stop scheduled capture immediately when the detail closes, the computer changes, or the user selects Manual;
- never save a frame into company knowledge unless the user performs a separate explicit artifact action;
- never start capture merely because a computer card was selected;
- preserve the user's selected rate only for the open detail session unless a future persistent-preview policy is explicitly designed.

### Offline computer behavior

When a computer is offline:

- show the last confirmed contact time;
- preserve known agents and assignment history but mark them stale;
- allow queueing a new assignment only when the user explicitly accepts `Send when reconnected`;
- do not claim a stop, permission change, or deletion succeeded remotely;
- show `Request queued; delivery is unconfirmed` where applicable;
- offer reassign and cancel for queued work;
- preserve the ability to inspect previous reports.

## Connection flows

The existing single-use Yggdrasil connection flow remains the transport foundation. Its enrollment payload and saved relationship must become company-scoped. The code identifies the company, root authority, intended upstream membership, expiry, and requested grants; it never enrolls the physical computer globally.

## Flow A: Start a private Fleet

### Entry

The user selects **Add a computer** from Fleet while operating an authorized root or worker-hub membership in the selected company. The existing **Start a private Fleet** label may remain only during the pre-company migration state.

### Step 1: Name the other computer

Fields:

- other computer name, required;
- optional description, such as `Build VPS` or `Office workstation`.

Validation:

- trim surrounding whitespace;
- reject an empty name;
- allow duplicate human-readable names but warn and append a disambiguating short identity in lists;
- preserve Unicode;
- constrain display length without silently altering the actual input;
- explain that the name may be edited later.

### Step 2: Prepare and create code

The app automatically:

1. checks the private network service;
2. installs or starts it if required;
3. verifies a local private address;
4. creates a single-use enrollment for this company and intended relationship only;
5. creates the single-use connection code;
6. attempts to copy it.

The primary progress view uses product language:

```text
Preparing private connection
✓ Private network ready
✓ One-time connection created
… Waiting for the other computer
```

Technical details are expandable.

### Step 3: Transfer and wait

The screen shows:

- expected computer name;
- expiry countdown;
- Copy code;
- Revoke code;
- Create replacement code after expiry;
- brief instructions for the other computer;
- live waiting state;
- success transition when pairing completes.

The code should be visually masked after a successful copy. The user may reveal it deliberately. The full secret must not appear in accessibility live-region announcements, logs, notifications, screenshots generated by the product, or error text.

### Success

Success copy:

```text
Build VPS now serves Company A
No other company, chat, file, credential, or setting was exposed.
```

Next actions:

- Review connection access.
- Review the automatically reconciled local manager and default worker.
- Optionally onboard additional specialized employees on that computer.
- Return to Overview.

The protected membership manager and default worker exist immediately after the company membership is created. Additional employee setup is optional for the computer connection, but an additional employee may not receive assignments until its own onboarding is complete.

## Flow B: Join an existing company Fleet

This flow begins from the device-level company chooser. It creates a worker membership for the company named in the signed code. It does not merge that company into any company already on the computer.

### Step 1: Paste code

- Provide a multiline paste field and **Paste from clipboard** where supported.
- Ignore surrounding whitespace.
- Detect obviously malformed content before starting network setup.
- Never echo the complete code in an error.

### Step 2: Verify destination

Before committing, show the identity available from the signed code:

```text
Connect this computer to:
Company A via Main VPS
Private address: available in details
Code expires in 18 minutes
```

If the code cannot safely identify the company, intended upstream membership, and root authority, the user must receive a warning before continuing.

### Step 3: Name this computer and review access

The user names this computer for Company A and reviews that company's initial permissions:

- Send coordination work to the protected Company A membership manager.
- Assign execution work to the protected default worker and individually exposed Company A identities on this computer.
- Create additional local employees.

Recommended defaults:

- membership manager: allowed for coordination after baseline reconciliation succeeds;
- default worker: allowed for compatible execution after baseline reconciliation and preflight succeed;
- existing additional identities: allowed only when they already belong to Company A and are individually exposed through this membership;
- create additional employees: blocked.

Identities belonging to another local company are never listed as candidates and cannot be attached to the new membership.

### Step 4: Connect

Progress states:

1. Preparing private network.
2. Validating single-use code.
3. Saving direct relationship.
4. Reconciling the protected Company A membership manager and default worker.
5. Starting the durable connection.
6. Publishing approved capability summary.

The completion screen must not appear until the durable connection has either started or been clearly marked `Connected; finishing setup`.

### Success

Show:

- company name and upstream computer name;
- current connection health;
- permissions granted;
- local agents currently available;
- a direct path to local Agent settings.

## Flow C: Add a child from an already connected computer

A top-level computer, leaf, or connected hub may select **Add computer below**.

The same Start flow is reused. A leaf becomes a connected hub after the first child connects. The role transition must happen without reloading the whole application or losing the user's current section.

The success screen must explain:

> This computer still reports to Main VPS and now directly manages Build PC.

## Pairing and connection edge cases

| Edge case | Required UX |
|---|---|
| Yggdrasil is not installed | Automatic setup with an explanation that administrator approval may appear. Advanced manual instructions remain secondary. |
| Administrator approval is denied | Preserve form input, explain nothing was connected, and offer Retry or View manual setup. |
| Service is installed but stopped | Attempt restart, then show a specific restart failure rather than a generic pairing error. |
| Firewall rule cannot be created | Explain that the private network may be ready but incoming connections are blocked; offer Retry as administrator and diagnostics. |
| No private address appears | Keep the user on the progress step, time out clearly, and show service logs under diagnostics. |
| Clipboard copy fails | Keep the code available through a deliberate Reveal action and say `Code created, but it was not copied`. |
| Code is malformed | Validate immediately and do not run setup work. |
| Code is expired | Explain expiry, discard it from the field, and direct the user to create a new code on the parent. |
| Code was already used | Say `This single-use code has already connected a computer`; do not imply a password error. |
| Code was revoked | Say the parent revoked it and a replacement is required. |
| Code is for the same computer | Block self-pairing and explain the detected conflict. |
| Computer already has a parent | Do not silently replace it. Offer Cancel or a separate Disconnect and reconnect flow with consequences. |
| Parent already knows this installation | Reconcile the existing relationship rather than create a duplicate computer card. |
| Join saves locally but relay does not start | Show `Connection saved; reconnecting` with Retry, diagnostics, and Disconnect. Do not show Ready. |
| Parent becomes unreachable during join | Preserve safe local state, show whether the code was consumed, and explain whether a new code is required. |
| App closes while waiting for a child | Restore the active unexpired pairing screen on reopen. Expired secrets must not be restored as usable. |
| App closes while joining | Resume durable connection startup or show a recoverable incomplete-setup state. |
| Two codes target the same display name | Permit the connections but disambiguate with relationship and short identity. |
| System clocks differ | Show expiry based on the issuing computer's signed value and avoid misleading negative countdowns. |
| Pairing completes after visible expiry | Accept only if the backend confirms it was valid; replace the expiry screen with the confirmed result. |

## Connection state model

The primary UI exposes one of these states:

| Product state | Meaning | Primary action |
|---|---|---|
| Checking | Initial state is not yet known | None; skeleton only |
| Not connected | No parent or child relationship | Start or Join |
| Preparing | Private network setup is running | Cancel when safe |
| Waiting for computer | Valid pairing code exists | Copy, revoke, or replace |
| Connecting | Relationship is being established | View progress |
| Finishing setup | Relationship saved; capability/relay handshake pending | Retry automatically; diagnostics secondary |
| Ready | Connection and current capability handshake confirmed | Normal Fleet actions |
| Reconnecting | Previously healthy relationship is temporarily unavailable; work lease is not renewed | Worker pauses new company steps; wait, retry, or diagnostics |
| Offline | Contact is stale beyond the reconnect window; remote company work is paused | Inspect history or queue for reconnect |
| Needs approval | Local or remote permission decision is pending | Review |
| Update required | Connected peer uses an incompatible or stale capability protocol | Update instructions |
| Private network stopped | Local service is not running | Start service |
| Connection error | A known failure prevents operation | Specific recovery action |

Rules:

- Never show `0 computers` or `Not connected` while initial status is still loading.
- Do not flip between hierarchy roles during temporary snapshot/status disagreement. Show `Syncing Fleet state` until the sources reconcile.
- `Paired` is not equivalent to `Ready`.
- `Online` requires a recent confirmed relay/capability exchange, not merely a saved connection file.
- Every non-ready state includes a plain-language next step.

## Agents

This is the transitional Fleet-hosted identity surface needed to expand the current mixture of local worker creation, worker cards, groups, and remote identity creation. Its company source of truth belongs in Workforce; Fleet retains placement, readiness, local approval, and computer-impact views with direct links to the Workforce record.

### Agent list

Each agent card/row shows:

- name;
- job title and department;
- hosting computer;
- readiness state;
- current assignment;
- queue count;
- blocker or approval state;
- autonomy level;
- latest report time;
- menu for settings, pause, archive, reset, or delete.

Agents are grouped by department or computer through a view selector. The group is presentation only unless an organizational group or dispatch group has explicitly been created.

### Agent readiness states

| State | Meaning |
|---|---|
| Draft | Onboarding started but not saved |
| Awaiting host approval | A parent proposed the agent; the hosting computer must approve local access |
| Needs setup | Required model, tool, workspace, permission, or job field is missing |
| Testing | Readiness checks are running |
| Ready | Can accept an assignment |
| Working | Currently executing |
| Waiting | Queued or waiting for an external dependency |
| Blocked | Cannot proceed without a decision or resource |
| Paused | Intentionally prevented from starting new work |
| Offline | Hosting computer is unavailable |
| Archived | Retained for history but not assignable |

An agent with incomplete onboarding must not appear as a normal available destination. Every row is resolved inside the active `company_id`; Fleet must never aggregate identities from other company partitions on the same host.

## Agent onboarding flow

This flow describes the Fleet-aware portion of the company hiring flow. Employee onboarding is identity-specific, not workspace-specific or app-wide. The current implementation can create a local or remote agent from a name. The expansion must preserve that working action while guiding each company employee into a position, specialized template, job contract, readiness test, and Fleet placement.

Every new company employee must complete onboarding. Entering only a name is never sufficient for a Ready employee. A name-only record may be saved as **Setup incomplete** so the current quick action remains usable during migration. Creating or onboarding one identity must not change another identity's settings, memory, job, tools, or workspace bindings.

### Step 1: Identity and job

- Agent name.
- Department.
- Manager/reporting destination.
- Job selection from the specialized job catalog or **Custom job**.
- One-sentence mission.

The job catalog may be seeded from specialized role references, but the selected job becomes a structured local profile, not one giant pasted prompt.

### Step 2: Responsibilities and deliverables

- Primary responsibilities.
- Explicit non-responsibilities.
- Required deliverables and formats.
- Recurring workflows/SOPs.
- Completion and quality criteria.
- KPIs or service expectations.

### Step 3: Tools, data, and workspaces

- Tool packs.
- Integrations/connectors.
- Workspace bindings.
- Project facts imported from existing workspace onboarding, without importing another identity's role or memory.
- File read/write scope.
- Browser/app access.
- Credential references without exposing raw secrets.

Unavailable requirements remain visible as blockers. The UI must not let a job title imply capability that has not been verified.

### Step 4: Authority and approvals

- Observe/draft only.
- Act with approval.
- Act autonomously within listed limits.
- Actions that always require approval.
- External communication rules.
- Deletion and financial limits.
- Escalation destination.

### Step 5: Model and resource policy

- Preferred model/provider.
- Fallback model/provider.
- Local-only requirement, if applicable.
- Usage or cost limit.
- Concurrency restrictions.
- Queue behavior.

### Step 6: Memory and reporting

- What remains private to the agent.
- What may enter shared company memory.
- Reporting cadence.
- Required evidence.
- Retention expectations.

### Step 7: Review and readiness test

Show a plain-language contract:

```text
Research Analyst
Reports to: Strategy Manager
May: browse approved sources, read Research workspace, create reports
Must ask before: contacting people, publishing, spending money, deleting files
Success: sourced report with confidence and evidence by the agreed deadline
```

Readiness checks verify:

- hosting computer online;
- selected model available;
- required tools available;
- required workspaces mapped;
- permissions consistent;
- required credentials configured;
- no unsafe resource conflict;
- test assignment can start and produce a report.

The agent becomes **Ready** only after required checks pass or the user explicitly accepts a clearly listed limitation.

### Remote agent proposal

When an authorized same-company identity proposes creating an agent on a downstream computer membership:

1. The requester creates a complete draft job contract inside the selected company.
2. The downstream computer receives `New Company A employee proposed by Main VPS`.
3. The downstream host reviews local tools, workspace, credentials, provider, resource, and permission impact for Company A only.
4. The host approves, modifies, or denies the proposal.
5. The requester sees the decision and readiness result.

Granting `May create agents` may allow automatic creation only within a pre-approved template and resource policy. It must not become unrestricted remote creation with only a name.

Promotion, transfer, and reassignment retain the same identity only inside the same company. The proposed job-contract revision shows an exact delta, reruns affected onboarding and readiness checks, and preserves private memory under policy. Moving to another company always creates a new identity; no cross-company identity transfer or shared identity record exists.

## Agent settings

Agent settings use these sections:

- **Identity**: name, company membership, home computer, status, and personal continuity.
- **Job**: position, department, manager, mission, responsibilities, deliverables, KPIs, and contract version.
- **Tools & access**: tool packs, connectors, credentials, files, apps.
- **Workspaces**: local bindings and read/write ownership.
- **Authority**: autonomy, approvals, budgets, escalation.
- **Models**: provider, model, fallback, resource limits.
- **Schedule**: recurring duties and availability.
- **Memory & reporting**: identity-private memory, position knowledge, shared-company promotion rules, retention, and reporting cadence.
- **Activity & audit**: assignments, configuration revisions, approvals, failures.

Changes that reduce access take effect immediately. Changes that increase access must pass the applicable local approval checks. Every saved revision shows who initiated it, when it became effective, and whether active work is affected.

## Work & approvals

This transitional embedded surface feeds the selected company's unified operational inbox under **Work**. It replaces separate piles of delegations, request cards, report rows, and status notices spread across current computer and worker panels, while Fleet retains only a contextual subset for the selected membership or computer.

### Views

- **Needs attention**
- **Active**
- **Queued**
- **Reports ready**
- **Completed**
- **Failed/canceled**
- **All activity**

Filters:

- computer;
- agent;
- job/department;
- status;
- priority;
- requester;
- date;
- project/workspace;
- approval type.

### Attention ordering

Default order:

1. safety or security approval;
2. blocked assignment;
3. failed assignment;
4. permission request;
5. report awaiting review;
6. question/resource request;
7. active assignment;
8. queued assignment;
9. completed history.

### Unified item detail

Every work item detail shows:

- assignment/request/report identity;
- originating computer and agent;
- destination computer and agent;
- objective;
- current state;
- priority and deadline;
- acceptance criteria;
- requested approval or blocker;
- evidence and artifacts;
- activity timeline;
- available actions;
- audit metadata.

## Assignment flow

### Quick assignment

Required:

- destination agent;
- desired outcome.

Every non-CEO assignment also records one accountable reviewing manager. Normally this is the destination employee's organizational manager even if the human initiated the work directly. A human may explicitly assume direct review. CEO work is informational unless it contains a dangerous, material, legally reserved, or company-configured decision that requires human authority.

Optional expansion:

- project/workspace;
- context and constraints;
- priority;
- deadline;
- completion criteria;
- required evidence/report format;
- autonomy/approval policy for this assignment;
- usage limit.

The initial single textarea remains available as **Quick assignment**, but the resulting assignment is durable and structured.

### Preflight

Before Send, the UI checks:

- agent readiness;
- computer connection state;
- queue/concurrency state;
- required workspace binding;
- required capabilities and permissions;
- active resource locks;
- broad/high-risk scope;
- estimated fan-out for group assignments.

Preflight results are categorized:

- **Ready**: may send.
- **Warning**: may send after explicit acknowledgement.
- **Blocked**: cannot send; provide a fix action.

### Confirmation rules

Confirmation is required when the effective company/job/identity/assignment policy requires it. New companies are **Draft only** for external actions, so a draft cannot execute until settings or an approval grants authority. Common confirmation categories include:

- more than one agent unless the user has enabled a trusted recurring runbook;
- external communication not covered by a configured grant;
- public publishing not covered by a configured grant;
- financial action outside configured authority;
- deletion or destructive modification;
- new credential or sensitive-data access;
- full-permissions execution;
- an offline destination when delivery cannot be confirmed;
- an assignment that conflicts with active workspace or interactive-desktop ownership.

The confirmation shows exact agents, computers, queues, risks, and expected start behavior.

### Assignment result

After Send:

- keep the text until acknowledgement succeeds;
- show one durable assignment identifier;
- avoid duplicate dispatch when the user retries after a timeout;
- indicate `Started`, `Queued`, `Waiting for computer`, or `Needs approval`;
- provide Open assignment and Undo/cancel where still safe.

## Assignment states

| State | User-facing meaning | Main actions |
|---|---|---|
| Queued | Waiting behind other work or a resource lock | Reorder, edit when safe, cancel |
| Waiting for computer | Destination is offline; delivery is not confirmed | Reassign, cancel, wait |
| Running | Agent is actively working | View progress, redirect, request update, stop |
| Paused | Work intentionally paused | Resume, redirect, stop |
| Blocked | Agent needs a decision, tool, permission, or resource | Resolve request, reassign, stop |
| Submitted | Worker report returned to the assigning manager and awaiting mandatory review | Accept, request changes, ask a reviewer, reassign, escalate |
| Needs decision | A risky next action or request requires approval before execution continues | Approve, reject, condition, reassign |
| Completed | Assigning manager accepted the submitted report | Inspect evidence, continue workflow, archive |
| Failed | Execution ended without a valid completion | Inspect cause, retry, revise, reassign |
| Stopped | Manager or local user stopped execution | Resume as new assignment or archive |
| Canceled | Work was removed before successful completion | Duplicate/recreate or archive |

The interface must distinguish a transport state from an assignment state. `Computer offline` is not the same as `Assignment failed`.

## Request and approval flow

Agents may send upward:

- question;
- approval request;
- blocker;
- resource/tool request;
- permission request;
- scope clarification;
- incident/escalation.

The request composer should default the originating agent and related assignment. It asks:

- what is needed;
- why it is needed;
- what remains blocked;
- recommended decision;
- urgency/deadline.

Manager actions:

- Approve.
- Deny.
- Reply without approving.
- Approve with conditions.
- Reassign.
- Ask another agent to review.

A response must update both the parent and hosting computer. If acknowledgement is not received, show `Response sent; delivery unconfirmed` rather than resolved.

## Permission experience

### Permission categories

The initial direct-connection permissions are:

- Send coordination work to this membership's protected local manager.
- Assign execution work to its protected default worker and individually exposed local employees.
- Propose or create additional local employees under the configured policy.

Future permissions may cover specific agent classes, runbooks, workspaces, or temporary capabilities, but should follow the same ownership model.

### Local owner view

The hosting computer may reduce access immediately. Increasing access requires local confirmation where it affects additional agents, tools, workspaces, or credentials.

Each permission shows:

- current state;
- effect in plain language;
- affected agents;
- whether active assignments depend on it;
- last change and initiator.

### Parent request view

The parent edits a proposed state, then sees a diff before sending:

```text
Coordinate through manager    Allowed → Allowed
Assign to default worker      Allowed → Allowed
Assign to other employees     Blocked → Allowed
Create additional employees  Blocked → Blocked
```

The child receives the same diff plus the requesting computer and reason.

### Permission edge cases

| Edge case | Required UX |
|---|---|
| Identical request already pending | Reuse or update the existing request; do not create duplicates. |
| New request supersedes old request | Mark the old request superseded and show only the newest as actionable. |
| Child is offline | Parent may draft but cannot claim the request was delivered. |
| Request expires | Mark expired and require a new request. |
| Child denies | Preserve the reason and leave controls at the confirmed state. |
| Permission reduced during queued work | Re-run preflight before the assignment starts and block with a specific explanation. |
| Permission reduced during active work | Stop the newly forbidden capability at the next safe boundary and raise a blocker; explain whether existing local work continues. |
| Agent archived/deleted | Remove it from the capability summary and pending destination choices. |
| Capability summary is stale | Disable increased-access actions and show Update required. |
| Local user approves with modifications | Return the confirmed modified state, not a generic approved result. |

## Reports

Every non-CEO assignment execution ends with a structured report to the manager that assigned it. Submission does not equal completion. The assigning manager must review every worker or subordinate-manager report; there is no automatic acceptance path for recurring or deterministic work.

Every CEO execution, task, and delegation also creates a structured report or activity record in the human Company Inbox. It is informational by default and does not require human approval. If it contains a dangerous or important business decision, a legally or owner-reserved decision, or an action configured to require human authority, the affected decision remains pending and the owner is notified according to policy.

Report cards show:

- agent and computer;
- assignment objective;
- completion status;
- concise summary;
- evidence count and artifact types;
- confidence;
- blockers or caveats;
- next suggested action;
- completion time;
- review state.

Reports must never imply evidence exists when only prose was returned. Missing or invalid evidence is visibly marked.

Review actions:

- Accept report.
- Request changes.
- Ask a reviewer agent.
- Open artifacts/evidence.
- Start suggested follow-up.
- Reassign incomplete portions.

If the reviewer has a manager above it, accepted or material results are synthesized into the reviewer's next upward report with links to the original. The chain continues through intermediate managers to the CEO. Every original report, manager decision, summary, artifact, and evidence item also appears in the human owner's Company Inbox.

CEO runs, assignments, delegations, reports, and material decisions create inbox records even when no subordinate report exists. Routine entries may be collapsed or filtered, and CEO reports remain prioritized at the top, but the human can always inspect the complete history.

Accepting a report may advance the worker queue only according to that agent's queue policy. The action must say whether another queued assignment will start.

## Settings

Fleet Settings contains:

### This computer

- display name;
- parent relationship;
- child relationship summary;
- private Fleet address under technical details;
- automatic reconnect state;
- local membership-manager and default-worker availability;
- local data/privacy explanation.

### Access from parent

- parent permissions;
- pending request;
- exposed local agents;
- per-agent availability to Fleet;
- emergency block-all-upstream-work action.

### Child connection policies

- default requested permissions for new child connections;
- pairing-code expiry default;
- whether queued work may wait for offline children;
- notification preferences.

### Diagnostics

- Yggdrasil installed/running state;
- private address;
- firewall rule state;
- relay process state;
- last connection error;
- last capability handshake;
- protocol version;
- restart service;
- repair private network;
- copy sanitized diagnostic report.

Diagnostics must redact pairing secrets, session tokens, credentials, local file contents, and private chat content.

### Destructive actions

- Disconnect from parent.
- Disconnect selected child.
- Revoke all active pairing codes.
- Reset private network integration.

These actions are grouped separately and require consequence-specific confirmation.

## Disconnect and deletion flows

### Disconnect from parent

The confirmation explains:

- this computer stops receiving assignments from the parent;
- local agents, chats, files, and settings remain;
- queued remote assignments become disconnected/unconfirmed;
- if this computer has children, it becomes the top of its existing subtree;
- reconnecting later requires a new code unless a safe reconnect path is explicitly supported.

### Disconnect a child

The confirmation shows:

- child name;
- active and queued assignments;
- pending requests;
- descendant count;
- whether the child is online to acknowledge the disconnect.

If offline, the local relationship may be revoked, but the UI must warn that the child cannot confirm until it reconnects.

### Delete an agent

The flow distinguishes:

- Archive agent: retain history; no new assignments.
- Delete identity: revoke identity and remove from active UI.
- Delete and wipe local state: remove agent-specific sessions, queue, cached grants, and local state when supported.

The hosting computer owns the final wipe decision. A parent may request deletion but cannot claim a remote wipe occurred without confirmation.

## Stop and emergency controls

`Stop All` must not be a normal header action.

Emergency actions live in an overflow menu and require scope confirmation:

```text
Stop active work on this computer?

This requests a safe stop for 3 active assignments hosted here.
Connected child computers are not affected.

[Cancel] [Stop 3 assignments]
```

Remote stop states:

- **Stop requested**: sent but not acknowledged.
- **Stopping**: remote computer acknowledged and is reaching a safe boundary.
- **Stopped**: confirmed.
- **Unconfirmed**: computer disconnected before confirmation.

The UI must never display `Stopped` solely because a request was sent.

## Notification model

The Company Inbox stores every report and CEO activity record; notifications are selective pings layered on top of that complete history. Fleet and company notifications are grouped by assignment, reporting chain, or connection to avoid floods. Company settings control thresholds, destinations, quiet periods, and which events interrupt the human.

Notify immediately for:

- security-sensitive approval;
- blocked high-priority assignment;
- parent/child connection loss beyond the reconnect window;
- failed high-priority assignment;
- permission request;
- agent creation proposal;
- destructive-action acknowledgement failure;
- CEO or manager escalation requiring the human owner's decision;
- material legal, financial, privacy, security, customer, or deadline risk.

Summarize rather than interrupt for:

- routine assignment completion;
- normal queue changes;
- successful reconnection;
- repeated progress events.

Every notification opens the exact relevant detail and remains understandable after the underlying state changes.

## Loading, empty, stale, and error states

### Loading

- Use skeletons or `Checking Fleet…`.
- Do not render empty counts before the first successful snapshot.
- Preserve the last confirmed snapshot during quiet refresh and mark it `Updating` when necessary.

### Empty

Empty states explain both meaning and next action:

- No child computers: `Add a computer to delegate work elsewhere.`
- No local agents: `Set up an agent with a job before assigning work.`
- No assignments: `Work sent to agents will appear here.`
- No approvals: `Nothing needs your attention.`
- No reports: `Completed assignment reports will appear here.`

### Stale

Data is stale when its last confirmed update exceeds the defined threshold. Show:

- last updated time;
- affected scope;
- whether actions are still safe;
- Retry.

### Error

Errors appear near the failed action and remain until dismissed or resolved. A global error banner is reserved for failures affecting the whole Fleet surface.

Error messages contain:

- what failed;
- what did not happen;
- whether local data was preserved;
- the next safe action;
- expandable technical details.

Successful actions clear obsolete errors in the same scope.

## Concurrency and resource-conflict UX

The preflight and active-work surfaces must expose conflicts before damage occurs.

### Same agent already working

Offer:

- Queue after current assignment.
- Redirect current assignment.
- Stop current and start new.
- Choose another agent.

### Workspace write lock

Show which agent and assignment owns the write lock. Offer queue, use read-only mode where meaningful, or choose another workspace/agent.

### Interactive desktop lock

Only one active user of mouse, keyboard, live browser profile, or app-control surface may own the interactive desktop unless isolation is confirmed. Show the current owner and estimated release behavior.

### Provider unavailable

Offer an approved fallback model/provider if configured. Otherwise block start and link to the hosting agent's Model settings. Do not expose raw keys or provider secrets.

### Missing workspace

The hosting computer must map the workspace locally. The parent may send a workspace label/reference but cannot choose an absolute path on another computer. The assignment remains blocked until mapping is confirmed.

### Application occupied by a human

If local interaction would interfere with a human session, show the conflict locally and follow the agent's authority policy: wait, request approval, or use a non-interactive alternative.

## Hierarchy edge cases

| Scenario | Required UX |
|---|---|
| Upstream membership is removed while this worker has children | Preserve the company-scoped subtree locally, mark its route disconnected, and require authorized reparenting; do not promote it to company root. |
| Child has descendants | Show child count and expandable summarized subtree without implying direct control. |
| Unknown descendant details | Show a generic descendant node and explain that its direct parent owns details. |
| Cycle detected | Quarantine the invalid edge, show Topology error, and provide diagnostics; never render recursively. |
| Duplicate computer identity | Reconcile or block; do not show two cards as if they are separate healthy machines. |
| Duplicate display names | Add parent relationship or short identity to disambiguate. |
| Very long names | Truncate visually with full accessible label and tooltip/detail text. |
| Child changes from leaf to hub | Update the tree in place and announce the relationship change without resetting selection. |
| Last child disconnects from a hub | Preserve the parent relationship and transition to leaf presentation. |
| Parent reconnects after local computer became temporarily standalone | Reconcile saved relationship before showing Start/Join options. |
| Capability count disagrees with snapshot | Show Syncing rather than flickering counts or removing agents immediately. |
| More than one upstream is attempted for the same company membership | Block the second upstream and require an explicit disconnect/reparent flow. Another company membership on the same device is unaffected. |
| Root controller or Yggdrasil route is offline | Expire the work lease, pause that company's remote execution at a safe boundary, retain the durable outbox, and reconcile before resuming. |
| A worker claims root authority | Reject and quarantine the claim; version-one root authority never moves from the computer where the company was created. |
| This physical computer is root in one company and a worker in another | Show the role for the active company only and keep both partitions, keys, activity, and navigation state isolated. |
| The same physical child is enrolled in two companies | Create two independent memberships; neither company can discover the other through Fleet. |
| Fifty or more direct children | Use search, status grouping, virtualization, and attention-first ordering. |

## Privacy and security UX

A persistent, concise privacy statement appears in Overview and connection setup:

> Company data stays in isolated local partitions. This Fleet shows only the selected company's memberships and exchanges only its approved assignments, reports, requests, and capability labels.

The UX must not:

- imply remote chat synchronization;
- reveal that a computer hosts another company or company membership;
- resolve a record, route, cache entry, event, search result, or notification without its company context;
- imply remote file browsing unless a specific approved artifact is returned;
- display or log raw pairing/session tokens;
- expose credential values;
- expose full local paths to another computer by default;
- treat a computer name as authenticated proof of identity;
- capture or show a screen outside the explicitly opened per-computer preview flow;
- capture at a rate the user did not deliberately select for the current open panel;
- turn the view-only preview into mouse, keyboard, or continuous-video control;
- automatically expose every local agent after pairing.
- reuse a pairing/session token, credential grant, workspace binding, or identity across companies.

Sensitive values:

- are masked by default;
- have deliberate Reveal and Copy controls;
- disappear when expired or revoked;
- are excluded from notification text and diagnostic exports;
- are not preserved in form history after successful use.

## Accessibility

Fleet must be fully usable with keyboard and assistive technology.

Requirements:

- All actions have a 44 x 44 px minimum target where practical.
- Visible focus indicators meet contrast requirements.
- Hierarchy is exposed using tree/treeitem semantics or an equivalent understandable list structure.
- Tabs use tablist/tab/tabpanel semantics.
- Selection is not communicated by color alone.
- Online/offline/attention states include text or icons with accessible labels.
- Dialog focus moves to the dialog, remains trapped, and returns to the triggering control on close.
- Dynamic state changes use polite live regions; destructive or blocking failures may use assertive announcements.
- Live regions never announce full pairing secrets.
- Tooltip information is available by focus and click, not hover only.
- Escape closes non-destructive popovers/dialogs.
- Reduced-motion preference removes animated status pulses and large transitions.
- Screen readers receive full names even when visual names are truncated.
- Error messages are associated with their fields.
- Countdown expiry is not announced every second; announce meaningful thresholds and expiry once.

## Copy guidelines

Primary copy should answer `what is happening` and `what should I do`.

Prefer:

- `Preparing private connection`
- `Waiting for Build VPS`
- `Connected; finishing setup`
- `Build PC has been offline for 6 minutes`
- `Permission request sent; delivery unconfirmed`

Avoid in primary copy:

- `relay missing`
- `remote worker websocket`
- `capability directory source mismatch`
- `Yggdrasil tunnel failed`
- `target selector`
- `intermediary role`

Technical language may appear in diagnostics with a plain-language summary.

## Help model

The interface should not place an information icon on every panel.

Use:

- one **How private Fleet works** drawer;
- short inline consequences beside permission decisions;
- contextual help inside setup steps;
- diagnostics for technical details;
- tooltips only for compact labels that cannot be self-explanatory.

Help content must not be required to understand the primary flow.

## Current-component migration map

This is a product decomposition guide, not an implementation requirement.

| Current component/area | Intended responsibility |
|---|---|
| `DesktopFleetWorkspace` | Preserve current standalone/root/leaf/connected-hub rendering, the above/current/below path, and separate upstream/downstream panes; derive them from the selected company membership and evolve them into the Fleet shell |
| `DesktopFleetConnectionPanel` | Split into Start Fleet wizard, Join Fleet wizard, and diagnostics; no simultaneous two-sided form |
| `DesktopFleetChildConnectionPanel` | Reuse the Start Fleet wizard with child-specific success copy |
| `DesktopFleetParentPanel` | Retain as the explicit one-direct-upstream summary for leaf and connected-hub memberships; add identity detail only when the same-company relationship can safely provide it |
| `DesktopFleetMachinesPanel` | Preserve the current direct-child-only cards and all child-workspace controls; progressively split navigation into direct-child list/tree plus persistent detail on wide layouts |
| `DesktopFleetComputerActivity` | Retain as the per-computer activity summary; add links to positions, assignments, objectives, and runbooks without exposing private local state |
| `DesktopFleetLivePreview` | Retain the current bounded, memory-only, user-rate-controlled screenshot behavior; place it in computer detail and add assignment/interactive-lock context without adding remote input |
| `DesktopFleetActivityPanel` | Feed the unified Work & approvals section; keep a compact local summary for leaf computers |
| `DesktopFleetUpstreamAccessPanel` | Move primary controls to Settings > Upstream access for this company; surface pending approvals in the company attention inbox |
| Local worker controls in `DesktopConversationDerivedTail` | Preserve during migration; move company employees into Workforce and agent detail/onboarding while retaining local personal-agent controls |
| Fleet groups in `DesktopConversationDerivedTail` | Preserve existing dispatch behavior during migration; map deliberately to teams or dispatch groups and never silently reinterpret them as departments |
| `DesktopFleetInfoButton` | Retain selectively; replace repeated privacy tooltips with one help drawer and inline consequences |
| Fleet manager chat sidebar | Keep available, but prevent it from competing with navigation and operational attention |

The current direct-child workspace and older worker/group dashboard must converge without a flag-day replacement. At every migration step, local workers, local incoming-work activity, the direct-parent summary, direct-child activity, previews, delegations, requests, permissions, and reports must remain reachable.

## Interaction feedback standards

For every mutation:

1. Disable only the affected action, not the entire Fleet UI.
2. Preserve user input until acknowledgement.
3. Show an in-place progress label.
4. Return a durable success or actionable failure message.
5. Refresh only the affected object where possible.
6. Keep the user's selection and scroll/context stable.
7. Avoid duplicate execution on retry.

Success toasts may disappear, but important results must also be reflected in the persistent object state. Errors remain visible until resolved or dismissed.

## Acceptance scenarios

### Scenario 1: First connection

1. A non-technical user opens Fleet on two computers.
2. The user selects Start on one and Join on the other.
3. The app prepares the private network automatically.
4. The user transfers one single-use code.
5. Both computers show the confirmed relationship and privacy boundary.
6. No agent, chat, file, setting, or credential is silently copied.

Pass condition: the user completes the connection without needing to understand Yggdrasil or relay terminology.

### Scenario 2: Connected hub

1. A worker membership already connected upstream adds a child for the same company.
2. Overview updates from leaf to connected-hub presentation.
3. Parent and child relationships remain visually distinct.
4. The user can see incoming company work above and downstream company work below without choosing a layout preference.

Pass condition: the user can explain this membership's upstream and downstream connections without confusing them with employee reporting lines.

### Scenario 3: Agent onboarding

1. The user creates an agent on a local or connected computer.
2. The user selects a specialized job and customizes the job contract.
3. Required tools, workspace, provider, permissions, and reporting are checked.
4. Missing requirements remain visible.
5. Only a Ready agent becomes a delegation destination.

Pass condition: every assignable agent has a known job, authority boundary, and verified operating requirements.

### Scenario 4: Delegation and report

1. The manager creates a structured assignment.
2. Preflight verifies readiness and conflicts.
3. The assignment starts or queues with a clear state.
4. The agent returns a structured report with evidence.
5. The manager accepts or requests changes.
6. Queue progression follows the stated policy.

Pass condition: no assignment is represented only by a transient prompt or final chat message.

### Scenario 5: Blocker and approval

1. An agent cannot continue safely.
2. It creates a blocker tied to its assignment.
3. Work & approvals raises it above routine activity.
4. The manager approves, denies, replies, reassigns, or requests review.
5. Both computers confirm the resulting state.

Pass condition: the blocker cannot be lost in a computer card or activity feed.

### Scenario 6: Offline recovery

1. A child disconnects during active work.
2. The parent shows last contact and uncertain assignment state.
3. The manager may wait, reassign, or cancel where safe.
4. The child reconnects.
5. Assignment, request, report, and permission state reconcile without duplication.

Pass condition: the UI never reports an unconfirmed remote action as complete.

### Scenario 7: Permission change

1. The parent requests additional access.
2. Both sides show the same current-to-proposed diff.
3. The child approves, modifies, or denies.
4. The parent displays only the confirmed state.
5. Affected queued or active work is re-evaluated.

Pass condition: ownership and consequences remain clear on both computers.

### Scenario 8: Scale

1. A top-level computer has at least 50 direct or summarized descendant computers and 200 agents.
2. Search, filters, virtualization, and attention ordering remain usable.
3. The hierarchy does not expose private detail through aggregation.
4. Bulk action requires an exact target and queue confirmation.

Pass condition: a manager can find a blocked agent or offline computer without scanning every card.

### Scenario 9: Keyboard and screen reader

1. A user connects a computer, selects an agent, sends an assignment, reviews a permission request, and opens a report without a mouse.
2. Focus remains predictable through dialogs and drill-downs.
3. Status and selection remain understandable without color.
4. Pairing secrets are not repeatedly announced.

Pass condition: all primary Fleet flows are independently operable and understandable.

## UX completion checklist

The company and Fleet UX are not complete until:

- [ ] First launch is immediately usable with a default CEO/assistant and separate default worker, while business onboarding remains suggested and optional.
- [ ] Business onboarding begins only with existing-business or create-new-business paths; casual assistant use requires no wizard answer.
- [ ] New-business validation uses predefined evidence and falsification gates and cannot be self-accepted by the evidence-gathering employee.
- [ ] Departments, automations, and recurring schedules remain optional and proposed work requires activation.
- [ ] External actions default to Draft only and can be expanded or restricted through scoped company settings.
- [ ] Every non-CEO assignment output becomes Submitted, receives mandatory assigning-manager review, and becomes Completed only after acceptance.
- [ ] Every original employee report and every CEO run/task/delegation record remains visible in the human Company Inbox, with CEO reports and action-required items prioritized.
- [ ] Routine CEO reports are informational even when directly assigned by the human, while dangerous, material, legally reserved, or configured CEO decisions wait for human approval or acceptance.
- [ ] Notifications ping the human under configurable approval, risk, incident, deadline, and blocker rules without hiding routine inbox history.
- [ ] Startup company selection scopes the entire application, and a company switch cannot leak stale UI or cached data.
- [ ] Startup restores the last explicitly selected available company, and the permanently visible switcher never changes company context implicitly.
- [ ] Every local company partition uses a distinct OS-protected encryption-at-rest key and accurately explains the OS-administrator boundary.
- [ ] Portable backups require a user-created passphrase, support a separately handled recovery key, exclude raw secrets, and can be verified without exposing key material.
- [ ] Every company-owned entity, route, event, cache, notification, search result, and permission lookup is scoped by `company_id` below the UI.
- [ ] One physical computer can hold multiple isolated memberships and display a different Fleet role for each selected company.
- [ ] Root-controller, computer-membership, and employee-manager authority are separate concepts in storage, routing, and UI copy.
- [ ] Worker nodes receive only their scoped company partition and execute company work only under a live root-issued work lease.
- [ ] Connection loss pauses remote execution, preserves an acknowledged/outbox boundary, and reconciles before resumption.
- [ ] The company root remains fixed to its creation computer; no transfer, restore elsewhere, standby, or automatic promotion path is exposed in version one.
- [ ] Existing local records and Fleet relationships migrate into one explicit company with a verified backup, mapping report, and no silent deletion or merge.
- [ ] The new hierarchy experience and old worker/group dashboard are unified under one information architecture.
- [ ] Standalone setup begins with Start or Join, not two simultaneous technical forms.
- [ ] A real topology view distinguishes parent, this computer, children, and summarized descendants.
- [ ] Computers and agents use distinct product language everywhere.
- [ ] The current computer workspace has evolved into stable detail navigation without losing any of its controls.
- [ ] Per-computer activity remains available and links to company work where applicable.
- [ ] View-only preview retains manual and bounded-rate capture, memory-only frames, and no remote input.
- [ ] Every agent receives identity-specific onboarding, persistent settings, and isolated long-term memory.
- [ ] Unready agents cannot receive work as if they were operational.
- [ ] Assignments have outcome, state, acceptance, evidence, and audit identity.
- [ ] Requests, approvals, blockers, and reports share one attention inbox.
- [ ] Permission changes show an exact diff and confirmed result.
- [ ] Offline and partial-success states do not overclaim success.
- [ ] Stop, disconnect, delete, and wipe actions have distinct scopes and confirmations.
- [ ] Primary flows avoid protocol jargon while diagnostics remain sufficient.
- [ ] Loading, empty, stale, error, retry, and reconciliation states are designed.
- [ ] Wide, medium, narrow, keyboard, screen-reader, and reduced-motion behavior are verified.
- [ ] Local-only privacy boundaries remain visible and technically accurate.

## Non-goals

This specification does not define:

- exact API routes or database migrations;
- a hosted account or cloud control plane;
- remote mouse or keyboard control, continuous video, or unattended screenshot recording;
- automatic copying of chats, files, settings, providers, or credentials;
- unrestricted remote creation of agents;
- moving, restoring, replicating, failing over, or automatically promoting the fixed company root to another computer in version one;
- an arbitrary visual agent-graph builder disconnected from accountable positions and runbooks;
- legal authority for an AI agent to bind a company without explicit real-world authorization.

## Final product statement

EmploAI is a local-first company operating system. It turns a human owner's charter into objectives, an organization, specialized jobs, governed operating processes, measurable work, durable knowledge, and auditable decisions. The agency-agents corpus supplies a broad starting library of job and team expertise, while company-specific contracts turn those references into accountable employees.

Fleet is the private execution layer beneath that company. Computers provide trust boundaries and capacity. Agents are persistent employees hosted on those computers. Positions and job contracts define responsibility. Runbooks, assignments, handoffs, requests, approvals, reports, evidence, KPIs, and financial outcomes make the company operable and verifiable.

The UX succeeds when one owner can understand and govern the company without micromanaging agent activity or understanding the underlying transport, while every privacy, permission, failure, authority, cost, and legal boundary remains explicit.
