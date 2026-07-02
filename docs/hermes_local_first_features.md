# Hermes-Inspired Local Features For EmploAI/Kraitos

This note captures the Hermes mechanisms worth adapting into EmploAI's current local-first, interactive-desktop-first direction. It is intentionally implementation-facing so future work can resume without re-reading the Hermes repository.

## Direction

EmploAI should keep the desktop app as the main control surface and treat local disk as the durable source of truth. Cloud login, cloud account profiles, and mobile relay code can remain parked for later, but memory, skills, prompts, automations, fleet control, and worker coordination should run without a VPS or account.

The Hermes ideas below should be adapted, not copied wholesale. The goal is a small set of local primitives that make Kraitos better at interactive work:

- stable prompt construction
- safe local memory
- progressive skill loading
- reusable learned procedures
- optional local/remote adapters at the edges

## High-Value Features To Adapt

### 1. Prompt Tiers

Hermes keeps prompt content in tiers:

- stable identity and tool guidance
- project/context files such as `AGENTS.md`, `SOUL.md`, `USER.md`, and `TOOLS.md`
- volatile runtime context such as memory, desktop state, skills, files, and current time

For EmploAI, this should preserve the interactive runtime prompt while making append-only custom instructions and memory context managed sections. The core desktop/tool prompt should stay authoritative and user custom instructions should append after it, never replace it.

### 2. Frozen Local Memory Snapshot

Hermes treats curated memory as a local file snapshot loaded into a session, while memory writes update disk for future turns/sessions. EmploAI already has `MEMORY.md` and daily logs. The next step is safer editing:

- atomic writes
- timestamped backups
- batch add/replace/remove operations
- duplicate prevention
- secret-like content rejection
- clear local delete/edit paths from the desktop UI

### 3. Local Fact Memory Provider

Hermes' local Holographic memory plugin is the best fit for EmploAI's no-cloud direction. EmploAI should add a small local SQLite fact store beside `MEMORY.md`:

- durable facts with category/tags/trust
- keyword search without external services
- feedback to raise/lower trust
- prompt snippets for high-trust facts
- no API keys or remote dependency

`MEMORY.md` remains the human-editable curated layer. SQLite facts become the structured recall layer.

### 4. Provider Boundary, Not Provider Bloat

Hermes uses a `MemoryProvider` interface so local, SQLite, and optional external memory systems can be swapped. EmploAI should use the same idea conservatively:

- built-in local memory always available
- optional local SQLite facts
- future adapters only behind explicit local settings
- no default cloud memory provider

### 5. Progressive Skills

Hermes lists skill metadata first, then loads the full `SKILL.md` body and resources only when a skill is selected. EmploAI already has a skill registry and `pull_skill`. It should tighten that into true progressive disclosure:

- skill list returns name, description, availability, active state, and resource names
- skill view returns the full skill body on demand
- active skills are explicitly loaded into context
- scripts/resources stay out of prompt unless needed

### 6. Local Skill Sync

Hermes seeds bundled skills into a user-owned local skill directory without overwriting user edits. EmploAI should eventually do the same:

- bundled default skills ship with the app
- user-modified skills are preserved
- deleted bundled skills stay deleted
- local manifest tracks origin hashes

This keeps the standalone app useful on first launch while still allowing the user to own their procedures.

### 7. Learn Workflow

Hermes has a `/learn` workflow that turns a conversation, file, URL, or repeated procedure into a reusable skill. Kraitos would benefit from an interactive version:

- "Save this workflow as a skill"
- draft `SKILL.md`
- review/edit in desktop UI
- validate resources
- activate immediately

### 8. Optional Skill Pulling

Hermes can pull skills from external hubs and GitHub with trust/quarantine controls. For EmploAI this should stay optional and disabled by default:

- local folders first
- manual GitHub import later
- no dependency on EmploAI-owned infrastructure
- audit log for pulled skills

## Implementation Order

1. Add managed prompt section helpers and use them for custom instructions, memory, and skills.
2. Add safe local memory operations around `MEMORY.md`.
3. Add a local SQLite fact store and fold it into memory search/context.
4. Make skill loading truly progressive and expose a skill detail endpoint.
5. Add local skill sync/manifest.
6. Add a desktop-first learn-skill flow.
7. Add optional external skill import.

## Current Implementation Status

Implemented:

- Managed prompt section helpers for local custom instructions, memory context, skill index, and active skills.
- Safe local memory helpers with atomic writes, backups, batch add/replace/remove operations, duplicate handling, and secret-like text rejection.
- Local SQLite fact memory with add/search/feedback/trust and prompt-context integration.
- Backend and renderer API hooks for memory operations, local facts, skill detail, and skill learning.
- Desktop setup has a compact local intelligence panel for inspecting structured facts, deleting facts, viewing skill bodies, opening skill folders, and saving local skills.
- Progressive skill loading: the skills index stays metadata-only, while full `SKILL.md` bodies load through pull/detail paths.
- Local bundled skill sync into `EMPLOAI_HOME/skills` with user edit/delete preservation.
- Desktop slash commands:
  - `/skillview <name>` to inspect full skill instructions.
  - `/learn_skill <name>` to draft a skill from recent local chat history.
  - `/learn_skill <name> | <workflow>` to save a pasted reusable local workflow and activate it.
  - `/memory_facts [category]` to list structured local facts.
  - `/memory_fact <fact>` or `/memory_fact <category> | <fact>` to save structured local fact memory.
  - `/memory_fact_delete <id> confirm` to delete a structured local fact.

Still remaining:

- Fact usefulness rating controls in the desktop settings UI.
- Rich edit controls for existing skill packages after creation.
- A richer guided desktop `/learn` flow with review/edit controls before writing the skill.
- Optional external skill import with quarantine/audit controls.
- Deeper prompt cache invalidation around settings and compression boundaries.

## Non-Goals

- Do not make Honcho, Supermemory, RetainDB, or any cloud memory service a default dependency.
- Do not require a domain, VPS, login, or mobile relay for these features.
- Do not bury interactive desktop guidance behind generic prompt abstractions.
- Do not add a large plugin framework before the local memory and skill primitives are solid.
