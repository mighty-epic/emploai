# Long-Running Task Reliability Design

Updated: 2026-05-01

This document reviews three proposed systems for making EmploAI more reliable on long-running tasks, then adds two additional systems based on the long-running agent research notes and recent harness papers.

The goal is not to make the agent "try harder." The goal is to make the runtime hold task state, evidence, verification, and tool scope in ways that reduce drift, repeated failed approaches, premature completion, and context loss.

## Research Basis

The strongest recurring ideas from the reviewed sources are:

- Long tasks fail when state lives only in chat history.
- Compaction helps, but compaction alone does not reliably preserve task intent.
- Agents perform better when a harness forces incremental progress, explicit handoff artifacts, and clean resumable state.
- Agents are weak at judging their own work, so independent verification is a major reliability lever.
- Context should be managed actively: summarize, reset, retrieve, and branch based on task state, not only token count.
- Full-fidelity evidence should be stored externally and retrieved by index instead of compressed into vague summaries.
- Parallelism helps only when delegation boundaries are explicit and merge contracts are strict.

Useful source patterns:

- Anthropic, "Effective harnesses for long-running agents": initializer agent, feature list, progress log, init script, git history, one-feature-at-a-time work, end-of-session handoff.
- Anthropic, "Harness design for long-running application development": planner/generator/evaluator split, context resets, structured handoffs, external evaluation.
- Anthropic, "Scaling Managed Agents": decoupling the model, tools, sandbox, and session log.
- Memex(RL): indexed experience memory, compact working context, external exact archive.
- ClawVM: harness-managed virtual memory with typed pages and lifecycle writeback.
- ARC: active and reflection-driven context management.
- AgentSwing: adaptive parallel routing for long-horizon web tasks.

## System 1: Task Protocol And Goal Bulletin Board

### Proposal

When the user gives a real task rather than casual chat, EmploAI should enter a task protocol. The model creates a main goal, decomposes it into sub-goals, and uses those goals as the reference point for every tool call and decision.

During the task, the agent maintains a bulletin board containing:

- The main goal.
- Sub-goals.
- Current status of each sub-goal.
- What has been completed.
- What remains.
- Recently failed methods.
- Recently successful methods.
- The next method the agent intends to try.

If the task does not complete within a configured number of turns or tool calls, the agent performs a forced reassessment. It reviews the tool calls and results, identifies what worked and failed, rewrites the goal and sub-goals only as needed, and continues from the updated plan.

### Brutal Review

This is directionally correct and close to what the Anthropic harness papers recommend. Some version of this should exist.

The weak point is the phrase "the model senses." If the task detector is vague, the system will either over-trigger and turn normal chat into a bureaucratic task flow, or under-trigger and miss exactly the long tasks that need structure. This cannot be left as a pure vibes-based prompt instruction. It needs an explicit classifier and runtime state machine.

The second risk is goal rewriting. If the model is allowed to freely rewrite the main goal, it can accidentally drift away from the user's real request while thinking it is being adaptive. The main goal should be sticky. Reassessment should normally rewrite the plan, not the objective. Main-goal changes should require a reason, a diff, and sometimes user confirmation.

The third risk is overhead. If every task becomes planning, sub-goals, status marks, reassessment, and self-analysis, the agent may become slower and more verbose. This should be activated only for tasks with enough complexity to justify it.

### Requirements

- Add a task mode classifier with at least three states:
  - `chat`: ordinary conversation, no task protocol.
  - `single_turn_task`: one or two actions, lightweight plan only.
  - `managed_task`: durable task protocol with goals, sub-goals, reassessment, and state persistence.
- Trigger `managed_task` when the request has one or more of:
  - Multiple tool domains.
  - File edits plus verification.
  - Browser or desktop operations with uncertain state.
  - Research plus synthesis.
  - A task expected to take more than a small number of tool calls.
  - Any explicit user phrasing like "work on this", "implement", "fix", "audit", "build", "run until complete", or "long task".
- Persist the bulletin board outside the prompt, attached to the session or job.
- Use a strict schema rather than freeform Markdown for machine-controlled fields.
- Preserve a human-readable view for Telegram, desktop, and mobile.
- Require every reassessment to include:
  - Last attempted method.
  - Evidence that it failed or stalled.
  - Methods that succeeded.
  - Updated next method.
  - Sub-goals completed since the last reassessment.
  - Sub-goals still open.
  - Any user decision needed.
- Do not let the model mark a sub-goal done without a completion reason and, where possible, verifier evidence.
- Keep the main goal immutable by default.
- Allow main-goal edits only with an explicit `goal_revision_reason`.
- Reassess by counters and signals, not only time:
  - `N` tool calls without progress.
  - `N` failed tool calls of the same family.
  - Repeated identical error.
  - Context usage threshold.
  - Tool state contradiction.
  - Model declares completion while open sub-goals remain.

### Missing Details To Decide

- What exact classifier decides chat vs task?
- Where does the bulletin board live: session JSON, job JSON, SQLite, or a dedicated task state file?
- What is the canonical task ID?
- Is one session allowed to have multiple active managed tasks?
- How are tasks resumed across Telegram, desktop, mobile, and voice?
- How much of the bulletin board is injected into every model call?
- Which fields are model-writable and which are runtime-controlled?
- What counts as progress?
- Which events trigger reassessment?
- Does the user see every reassessment, or only material changes?

### Recommended Shape

Use this system, but make it runtime-owned. The model can propose updates, but the harness should validate and persist them.

The main goal should be a stable contract. The sub-goals should be flexible. The failed-method ledger is one of the highest-value pieces because it directly attacks repeated loops.

Recommended initial schema:

```json
{
  "task_id": "task_...",
  "mode": "managed_task",
  "main_goal": "User-facing objective in one sentence.",
  "goal_locked": true,
  "sub_goals": [
    {
      "id": "sg_1",
      "title": "Inspect current implementation",
      "status": "open",
      "completion_evidence": null
    }
  ],
  "current_focus": "sg_1",
  "successful_methods": [],
  "failed_methods": [],
  "next_method": "Read relevant code paths before editing.",
  "open_questions": [],
  "last_reassessment": null,
  "progress_markers": []
}
```

## System 2: Sub-Agent Delegation

### Proposal

For broad multi-domain tasks, the main agent can spawn sub-agents with scoped tools and instructions. For example, a research sub-agent gathers sources, a documentation sub-agent prepares structured notes, and the main agent begins coding in parallel where it is not blocked.

The goal is to reduce main-context bloat, increase parallelism, and keep each worker focused on a smaller task.

### Brutal Review

This is powerful, but it is also the easiest one to make chaotic.

Sub-agents do not automatically improve reliability. Bad delegation can make the system less reliable because the main agent now has to manage stale reports, conflicting changes, duplicated work, hidden assumptions, and merge risk. The research supports multi-agent structures, but the successful versions have very explicit roles and evaluation contracts.

The strongest version is not "spawn agents whenever broad." The strongest version is "spawn agents only when the task can be split into independent work packages with clear outputs and clear ownership."

This is especially important for coding. Two agents editing overlapping files can create conflict and subtle regressions. A research agent and a coding agent can run in parallel safely. Two coding agents in the same module usually cannot unless ownership boundaries are strict.

### Requirements

- Main agent remains the coordinator.
- Sub-agents must have explicit scopes:
  - Objective.
  - Allowed tools.
  - Allowed files or domains.
  - Forbidden files or domains.
  - Expected output format.
  - Reporting cadence.
  - Stop condition.
- Sub-agents should be used only when at least one of these is true:
  - Work packages are independent.
  - One package is read-only research.
  - One package is verification.
  - One package is documentation.
  - Coding changes have disjoint file ownership.
  - A blocked main task can continue while another agent gathers missing context.
- Main agent must maintain a delegation table:
  - Agent ID.
  - Task.
  - Status.
  - Owned resources.
  - Last report.
  - Dependencies.
  - Merge risk.
- Sub-agents must produce compact structured results, not long chat transcripts.
- Sub-agent outputs must include:
  - What they did.
  - Evidence found.
  - Files touched, if any.
  - Tests run, if any.
  - Risks.
  - Recommended next action.
- The main agent must verify or sanity-check sub-agent results before treating them as truth.
- Limit concurrent sub-agents to avoid coordination overhead.
- Default max should be low, likely 2 or 3.
- Sub-agents should not recursively spawn agents unless explicitly enabled.

### Missing Details To Decide

- What is the maximum number of sub-agents?
- Can sub-agents write files, or are they read-only by default?
- How are write conflicts detected?
- Can sub-agents access user memory?
- Can sub-agents access private app state?
- How often should they report?
- Do reports stream live to the user or only to the main agent?
- What happens if a sub-agent stalls?
- What happens if two sub-agents disagree?
- How does the main agent cite or preserve sub-agent evidence?

### Recommended Shape

Use sub-agents, but start conservatively:

- Phase 1: read-only research, code exploration, and verification sub-agents.
- Phase 2: coding sub-agents with disjoint file ownership.
- Phase 3: richer multi-agent workflows only after conflict detection and result verification are solid.

The best immediate value is not replacing the main agent. It is letting the main agent keep moving while a focused worker gathers context or checks work.

Recommended delegation schema:

```json
{
  "delegations": [
    {
      "agent_id": "research_1",
      "role": "research",
      "objective": "Find current docs for the selected API.",
      "allowed_tools": ["web_search", "open_url"],
      "write_scope": "none",
      "status": "running",
      "expected_output": "source_summary",
      "last_report": null,
      "merge_risk": "none"
    }
  ]
}
```

## System 3: Tool Pack Gating

### Proposal

Instead of giving the main agent every tool all the time, start it with a small base toolset. The agent can request tool packs by purpose:

- Browser pack.
- Windows/desktop pack.
- Cron/scheduler pack.
- Filesystem pack.
- App/session pack.
- Voice pack.
- Packaging/MSI pack.

The goal is to reduce tool confusion and decision fatigue when the runtime exposes many tools.

### Brutal Review

This is one of the best ideas, but implementation details matter a lot.

Tool overload is real. When a model sees dozens of tools, it becomes easier for it to pick a tool that is technically available but semantically wrong. Your browser-extension example is exactly the kind of failure tool gating can prevent.

The hard part is that tool availability often lives at the API/harness level, not just the prompt level. If all tools are still technically exposed and the prompt merely says "do not use these yet," the model may still call them. True tool packs should change the actual tool list available to the model call whenever possible.

Also, the base toolset you listed may already be too large for some modes. For pure chat, the model needs no desktop tools. For code tasks, it may need shell and file-edit tools, not screen tools. The base pack should depend on the task mode.

### Requirements

- Tool packs must be enforced by the harness, not only described in the prompt.
- Each model turn should have an active tool manifest.
- Tool packs should include:
  - Tool names.
  - Purpose.
  - Preconditions.
  - Risks.
  - Mutability level.
  - Whether user confirmation is needed.
  - Whether the pack can coexist with other packs.
- The agent should request a pack with a reason.
- The harness should allow, deny, or ask for clarification.
- Pack activation should be logged in the task ledger.
- Packs should expire when no longer needed.
- There should be a maximum number of active packs.
- Some packs should be mutually exclusive:
  - Browser extension pack vs. Selenium/browser-instance pack.
  - Vision-only desktop pack vs. DOM/browser-control pack.
  - Local cron pack vs. remote/VPS scheduler pack.
- Tool pack selection should depend on actual environment state:
  - Browser extension connected.
  - Desktop control available.
  - Current OS.
  - Active window.
  - App connection status.
  - User permissions.

### Missing Details To Decide

- Which tools belong to each pack?
- What is the minimum base toolset per mode?
- Can the model request packs mid-turn, or only between turns?
- Does requesting a pack cost a model call?
- Can the user pin or forbid packs?
- How are tool packs represented in desktop/mobile/Telegram UI?
- How does this work with provider APIs that require tool schemas up front?
- What fallback exists if dynamic tool lists are not supported?

### Recommended Shape

Use tool packs, but distinguish between "visible tools" and "available backend capabilities."

Recommended active packs:

- `none`: chat only.
- `code_core`: shell, read, patch, tests, git status.
- `screen_vision`: observe/describe screen, OCR fallback, click, type, focus.
- `browser_extension`: current user browser via extension only.
- `browser_selenium`: isolated automation browser only.
- `scheduler`: cron/job operations.
- `release_windows`: MSI/build/release operations.
- `app_runtime`: sessions, model settings, app connection, sync.

The browser packs need hard preconditions:

- If the task is in the user's Chrome and the extension is not connected, do not expose browser DOM tools.
- In that state, expose only `screen_vision` and atomic actions.
- Selenium should be exposed only when the task is explicitly in the model's own browser instance or an isolated automation browser is acceptable.

This directly addresses one of EmploAI's existing prompt/tool confusion patterns.

## System 4: Evidence Ledger And Indexed Memory

### Proposal

Add a durable evidence ledger for long-running tasks. The agent should store exact evidence outside the prompt and reference it by ID.

Examples:

- File paths and line references.
- Screenshots.
- Command outputs.
- Browser observations.
- Web sources.
- Tool errors.
- Successful settings.
- User decisions.
- Voice transcription corrections.
- App/session state snapshots.

The working prompt receives a compact index and the most relevant retrieved entries, not the entire history.

### Why This Is Different

The task bulletin board tracks intent and progress. The evidence ledger tracks truth.

A long task needs both. Without an evidence ledger, the agent will eventually rely on vague memory like "I think the test passed" or "the browser extension was unavailable earlier." That is where accuracy degrades.

This system is inspired by indexed experience memory and harness-managed virtual memory. The model keeps a small working set, while the harness preserves exact old data and retrieves it when needed.

### Brutal Review

This is less glamorous than sub-agents, but probably more important.

Most long-running failures are not caused by lack of intelligence. They are caused by the model losing exact state. A durable evidence ledger attacks that directly.

The risk is garbage memory. If the agent stores everything, retrieval becomes noisy and expensive. If it stores only polished summaries, it loses the exact evidence. The correct design is a two-layer memory:

- Compact searchable metadata.
- Exact artifact payload stored separately.

### Requirements

- Every important tool result can be saved as an evidence item.
- Evidence items need stable IDs.
- Evidence metadata should include:
  - Type.
  - Source.
  - Timestamp.
  - Related task ID.
  - Related sub-goal ID.
  - Confidence.
  - Whether it is user-confirmed.
  - Whether it invalidates previous evidence.
- Exact evidence should remain retrievable.
- The model should cite evidence IDs in reassessments and completion claims.
- Evidence should be deduplicated.
- Sensitive evidence should have retention rules.
- The ledger should support retrieval by:
  - Task.
  - Sub-goal.
  - Tool type.
  - File path.
  - Current surface.
  - Error text.
  - User-confirmed decisions.
- Completion should be blocked or downgraded if no evidence supports it.

### Missing Details To Decide

- Where are evidence payloads stored?
- Do screenshots live in the filesystem, database, or both?
- How are large command outputs truncated while preserving full logs?
- What can be injected automatically into prompts?
- What requires explicit retrieval?
- How is stale evidence marked?
- How are contradictions resolved?
- How is private/sensitive evidence redacted?

### Recommended Shape

Add a task-local `evidence_index` first, then generalize later.

Recommended schema:

```json
{
  "evidence_id": "ev_...",
  "task_id": "task_...",
  "sub_goal_id": "sg_1",
  "type": "command_output",
  "source": "pytest",
  "summary": "Targeted tests passed: 16 passed.",
  "artifact_ref": "artifacts/task_.../pytest_001.txt",
  "confidence": "high",
  "user_confirmed": false,
  "created_at": "2026-05-01T00:00:00Z",
  "invalidates": []
}
```

The final answer for a managed task should include or internally reference the evidence IDs that support completion.

## System 5: Verification Gates, Checkpoints, And Clean Handoffs

### Proposal

Add a verifier layer that checks whether progress is real before the agent marks work complete. Combine that with checkpoints and clean handoffs so a long-running task can pause, reset context, or resume without losing state.

This is the Anthropic long-running harness pattern translated to EmploAI.

### Why This Is Different

The goal bulletin board says what should happen. The evidence ledger says what was observed. The verifier decides whether the result is good enough.

This should not be optional for managed tasks. Long-running agents are too willing to declare victory when they have merely made plausible-looking progress.

### Brutal Review

This is the system most likely to improve real reliability, but it is also the system users will notice least when it works.

The hard truth: without verification gates, the other systems can make the agent more organized while still being wrong. A beautiful task plan with unchecked assumptions is just wrong in a more orderly way.

The verifier does not always need to be another AI model. Often the best verifier is boring:

- Run the tests.
- Open the app.
- Click the UI path.
- Check the file exists.
- Confirm the session model actually changed.
- Validate JSON schema.
- Compare before/after screenshots.
- Check the browser extension connection state.

For subjective work, a separate evaluator model can help, but it must be skeptical and criteria-driven.

### Requirements

- Each managed task should define verification criteria early.
- Each sub-goal should have a verifier type:
  - `test_command`.
  - `schema_check`.
  - `browser_e2e`.
  - `desktop_observation`.
  - `api_probe`.
  - `file_diff`.
  - `human_confirmation`.
  - `llm_evaluator`.
- The agent cannot mark a sub-goal done without either:
  - Passing verifier evidence.
  - A clear explanation that verification was impossible.
- The harness should create checkpoints at important moments:
  - Task start.
  - Before risky edit.
  - After successful sub-goal.
  - Before context reset.
  - Before final response.
- Checkpoints should include:
  - Bulletin board state.
  - Evidence index.
  - Active tool packs.
  - Current model and settings.
  - Current files touched.
  - Verification status.
  - Open questions.
- Context resets should be allowed for long tasks:
  - Summarize into handoff state.
  - Clear conversational noise.
  - Relaunch with task state and evidence index.
- Handoffs should be structured and short enough to be read at startup.

### Missing Details To Decide

- What verifier types are available in each channel?
- Which verifiers are mandatory for each task type?
- What happens when a verifier fails?
- Does the agent automatically retry, reassess, or ask the user?
- How are checkpoints surfaced in the UI?
- Are checkpoints tied to git commits for code tasks?
- Can the user manually restore a checkpoint?
- How are long-running background jobs resumed after app restart?

### Recommended Shape

Start with deterministic verifiers before evaluator models.

Recommended first verifier set:

- `python_pytest`: run targeted tests.
- `typescript_typecheck`: run frontend typecheck.
- `app_health_probe`: hit backend health endpoints.
- `desktop_voice_probe`: check voice websocket or bridge status.
- `session_sync_probe`: verify model/session state across app surfaces.
- `file_state_probe`: check expected files and diffs.
- `browser_connection_probe`: confirm extension vs. vision-only vs. Selenium availability.

Recommended handoff schema:

```json
{
  "checkpoint_id": "chk_...",
  "task_id": "task_...",
  "main_goal": "Stable user goal.",
  "current_focus": "sg_2",
  "completed_sub_goals": ["sg_1"],
  "open_sub_goals": ["sg_2", "sg_3"],
  "active_tool_packs": ["code_core"],
  "last_verified_state": "Targeted tests passed after session sync fix.",
  "failed_methods": [
    "Passive session detail reads mutated current session pointer."
  ],
  "next_action": "Verify desktop and phone both reflect model changes.",
  "evidence_refs": ["ev_1", "ev_2"]
}
```

## How The Five Systems Fit Together

The five systems should not be separate features that each shout instructions at the model. They should form one managed task harness:

1. Task classifier decides whether to enter managed task mode.
2. Task protocol creates the bulletin board.
3. Tool pack gating exposes only the tools needed for the current phase.
4. Evidence ledger records exact facts from tool use.
5. Sub-agents run scoped parallel work only when useful.
6. Verifier gates determine whether sub-goals are actually complete.
7. Checkpoints and handoffs allow context reset and resume.
8. Reassessment updates the plan when progress stalls.

## Recommended Priority

### Phase 1: Highest Reliability Per Unit Of Work

- Task mode classifier.
- Durable bulletin board.
- Failed-method ledger.
- Verification criteria per sub-goal.
- Manual and automatic reassessment.
- Evidence IDs for important tool results.

### Phase 2: Tool Confusion Reduction

- Runtime-enforced tool packs.
- Browser-extension vs. vision-only vs. Selenium preconditions.
- Pack activation logging.
- Max active pack count.

### Phase 3: Long-Horizon Resumability

- Checkpoints.
- Structured handoff payloads.
- Context reset protocol.
- Background job resume behavior.

### Phase 4: Parallelism

- Read-only sub-agents.
- Verifier sub-agents.
- Research sub-agents.
- Later, coding sub-agents with file ownership.

### Phase 5: Full Memory System

- Indexed evidence retrieval.
- Cross-session learned methods.
- User and environment profiles.
- Stale evidence invalidation.

## Strong Recommendations

- Do not start with sub-agents. Start with task state and verification.
- Do not let the model freely rewrite the user's main goal.
- Do not make tool packs prompt-only. If possible, enforce them in the actual tool manifest.
- Do not store only summaries. Store exact evidence with compact indexes.
- Do not treat compaction as the main reliability system. It is only one pressure valve.
- Do not show every internal update to the user. Show meaningful progress and important uncertainty.
- Do not let a task finish without a verifier result or an explicit verification gap.

## Bottom Line

Your three ideas are good, but they need runtime enforcement.

The task protocol is the backbone. Tool packs reduce wrong-tool behavior. Sub-agents can reduce context load and latency, but only after delegation rules are strict.

The two missing systems are evidence and verification. Without those, the agent may become more organized but not necessarily more correct. With them, EmploAI can become meaningfully better at long-running tasks: less drift, fewer repeated failures, safer resumes, and more accurate completion claims.
