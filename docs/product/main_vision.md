# Main Vision: Accountless AI Company

> This is a concise north-star summary. The authoritative product contract is [emploai_company_operating_system_and_fleet_ux_spec.md](emploai_company_operating_system_and_fleet_ux_spec.md), which controls wherever product details differ.

## North Star

EmploAI is a local-first AI employee operating system. One human should be able to direct a manager, delegate real computer work to workers, and scale that operating model across a hierarchy of paired computers without creating a cloud account for the company or separate accounts for its agents.

Every computer contributes the same smallest useful unit:

```text
Computer
├─ Manager
├─ Protected default worker
├─ Optional additional workers
└─ Direct child computers
```

Workers use real tools, files, browsers, applications, credentials, connectors, and workspaces. Managers translate human intent into objectives and tasks, choose routes, supervise progress, recover from blockers, verify reports, and present accepted outcomes.

The main surface is the desktop app. Chat and Jarvis provide direct manager or worker interaction. Company provides the operating view for objectives, workforce, attention, and the underlying computers.

## Product Documents

- [company_system_details.md](company_system_details.md) defines the locked company operating model, shared glossary, objectives, review, Company UX, offline behavior, governance, and recovery. Locking the specification does not itself authorize application implementation.
- [fleet_system_details.md](fleet_system_details.md) defines the execution infrastructure: computers, identities, pairing, routing, queues, reports, permissions, locks, and transport.

These layers are related but not interchangeable. Company organizes purpose and responsibility. Fleet determines where execution lives and which authenticated route may reach it.

## Existing Foundation

EmploAI already contains the foundation for this direction:

- The desktop runtime owns local execution: tools, files, browser control, screen vision, OCR, shell commands, and app control.
- The Fleet runtime provides computer identity, direct pairing, presence, task routing, permissions, reports, and persistent host recovery over Yggdrasil.
- Every installation reconciles one local manager and one protected default worker before pairing.
- Chat, Jarvis, Company/Fleet, automations, workspaces, and structured task reports provide the main operating surfaces.
- Mobile and Telegram can remain optional command surfaces attached to a chosen local installation without becoming identity authorities.

The personal one-computer use case remains first-class. It is simply the smallest company: one operator, one manager, one worker, and one computer.

## Local-First And Accountless By Design

EmploAI does not use a cloud login, hosted user account, agent account, or central company account. This is intentional.

Agents control private computers, files, applications, connectors, and credentials. Making a hosted account authoritative would add a remote dependency and create a high-value centralized copy of company topology, activity, access metadata, and potentially sensitive work.

Instead:

- The root computer owns the local company manifest.
- Every computer owns its local identities, chats, tools, secrets, workspaces, task execution, reports, and detailed history.
- Computers establish explicit parent-child relationships through short-lived pairing codes and persistent pair credentials stored only on paired machines.
- Yggdrasil supplies encrypted network transport; EmploAI independently authenticates and authorizes every paired request.
- Parents receive only published identity/capability summaries, delegated-work state, approved reports, evidence, and company rollups needed to manage their direct children.
- The root operating-system user is the sole root operator and ultimate company authority in the first release. A human with OS access to a child computer is not a company role and has authority only over that computer's local operations and safety controls.

One-computer EmploAI remains useful offline. Child branches may continue already authorized work while disconnected. Removing a pairing removes the route without deleting either computer's local identities or data.

## Company And Fleet

The company operating model never mirrors the physical computer tree.

- `Company` contains objectives, manager responsibility, optional lightweight departments, attention, review, and acceptance.
- `Fleet` contains computers, manager routes, workers, capabilities, presence, connection permissions, resource locks, and transport.

A computer is a complete EmploAI node and is never itself a worker. A department does not own a computer, move an identity, grant a tool, or bypass a child manager. Interactive work is constrained by scarce machine resources; background work may run concurrently only when its locks are compatible.

## Roles And Authority

### Root Operator

The root operator is the human using the root computer's local OS session and is the company owner. The operator can perform or override every company-level operation: direction, structure, objectives, reviews, acceptance, reassignment, archival, recovery, grants, settings, and pairing decisions. Root authority cannot make an offline computer reachable, bypass its operating system, or restore revoked pairing trust. Multiple human account roles are outside the first release.

### Manager

Every computer has one mandatory manager identity. A manager is the human-facing orchestration agent for that computer and the coordination route for its direct children.

Managers have role-locked orchestration, memory, automation, and verification capabilities. The user may explicitly enable compatible execution tools on a manager, but workers never inherit manager authority. A manager coordinates grandchildren through the direct child manager instead of bypassing it.

The root manager may be presented as the company's `CEO manager`: the top agentic manager working beneath the root operator. `CEO` is a display title and responsibility, not a separate technical role or a human authority above the operator.

### Worker

A worker is an execution identity owned by its source computer's manager. The protected default worker guarantees that every manager can delegate ordinary action without setup. Additional workers may specialize by behavior, tools, connectors, workspace, or optional department.

Workers execute tasks, report milestones, raise blockers, and return structured reports. They do not create departments, grant themselves tools, assign other workers, or control managers.

## Work, Review, And Acceptance

Company work is organized around durable objectives rather than unrelated prompts. An objective describes an intended outcome, success criteria, owning manager, priority, optional deadline and explicitly created department, and the tasks and reports used to achieve it. Companies have no departments by default.

A manager may decompose an objective across local workers or delegate a child objective to a direct child manager. Worker completion produces a report; it does not by itself finish the business outcome. The owning manager verifies the evidence and either accepts the objective or requests linked rework. Explicit low-risk policy may allow automatic acceptance, but it is off by default.

Managers may decompose approved scope but cannot silently expand it. Extra work appears as a proposal until the root operator or authorized owning manager approves it. Objectives may be paused without losing assignments, sessions, evidence, or route history.

Direct manager and worker chats remain normal conversations. Delegated tasks use isolated sessions and preserve route, origin, evidence, and report linkage.

## Company Desktop Experience

The top-level Fleet surface evolves into `Company` with four focused internal pages:

- `Overview`: objectives, progress, capacity, and a compact attention feed.
- `Work`: objectives, assignments, reports, acceptance, and rework.
- `Workforce`: manager branches, workers, optional departments, capabilities, and queues.
- `Computers`: Fleet health, direct child computers, pairing, connection recovery, updates, previews, and per-computer settings.

The surface is role-aware. Managers see only the company and infrastructure controls allowed for their branch. Workers see a focused My Work view and never receive manager-only connection, delegation, or configuration controls.

Every assignment must make its route visible: issuing manager, destination computer, destination manager or worker, optional department, and state. Approvals, blockers, failed work, permission requests, and results awaiting acceptance converge in one attention model rather than being scattered across oversized panels.

The interface should use progressive disclosure, compact empty states, stable navigation, immediate interaction feedback, accessible keyboard/focus behavior, and layouts that neither waste space nor leave gaps when content collapses.

## Access, Security, And Privacy

Company responsibility never creates technical access. Effective authority is the intersection of company policy, manager ownership, pair permissions, identity grants, local approvals, resource locks, and hard safety boundaries. A denial at any layer wins.

Credentials remain locally brokered. Models may use an authorized connector without seeing raw passwords, OAuth tokens, API keys, recovery codes, or session tokens. Company knowledge contains only explicitly published handbook and policy material. Chats, full memory, provider state, absolute paths, secrets, and raw tool payloads are not silently copied upward.

Context inspection is separately opt-in, redacted, and audited. Artifact metadata may remain visible when its source is offline, but the UI must not imply that unavailable artifact bytes are present.

## Scale Without Flattening

Managers directly control local identities and direct child routes only. Child managers publish aggregate objective progress, capacity, blockers, risks, and accepted outcomes upward. This gives the top manager company-scale awareness without flattening every descendant worker or weakening intermediary authority.

Remote control is the transport layer, not the product. The product is the ability to define outcomes, assign responsibility, coordinate capable local agents, observe work without leaking unnecessary context, and accept verified results.

## Non-Goals

This vision does not authorize code implementation and does not define APIs, database schemas, migrations, or wire formats. The company product specification is locked, but implementation begins only after a separate engineering plan and explicit user authorization.

The first release does not include:

- cloud login, hosted company accounts, or agent accounts;
- multiple companies on one Fleet root;
- multiple human operator profiles;
- planned live transfer of an active company root in the first implementation;
- HR-style positions, payroll, or nested department bureaucracy;
- peer-to-peer worker management authority;
- automatic copying of child chats, secrets, full memory, or artifact contents;
- a generic connector marketplace unrelated to real assigned work.

Implementation must continue to build on local desktop execution, direct authenticated Fleet routing over Yggdrasil, optional local command surfaces, and the unified agent runtime as the worker brain.
