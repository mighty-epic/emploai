# Eval Protocol

This file defines the reusable agent-eval protocol we will use going forward.

## Purpose

The goal of this protocol is to evaluate:

- model behavior
- tool choice and efficiency
- multi-step reasoning
- task completion quality
- runtime/tooling failures that are not the model's fault

This protocol is meant to be reused and customized over time.

## Default Model Set

Run this protocol on:

- `gpt-5.4-mini`
- `gpt-5.4`
- `claude-haiku-4.5`
- `claude-sonnet-4.5`

## Eval Count Per Model

Run **5 active evals per model** for now.

Paused for now:

- the cron/scheduler eval is temporarily disabled until the scheduler behavior and scoring are aligned with the intended task

Order matters:

1. run the tool-surface sanity eval first
2. then run the 4 active custom task evals

## Global Evaluation Rules

- Do not mention tool packs in the user prompts unless a future protocol revision explicitly requires that.
- Do not mention tools, tool packs, or implementation hints in the eval prompts.
- Evaluate whether the model chooses the correct tools on its own.
- Run the main behavior/protocol evals with the same full tool-pack surface as the desktop app. Do not restrict tools inside normal behavior cases; tool restriction belongs only in dedicated tool-pack gating tests.
- Watch for runtime/tooling failures in addition to model failures.
- Save and inspect artifacts when available.
- Track token usage, latency, tool order, and final output quality.
- Pay attention to whether the model verifies its own work properly.
- If an eval is unfinished, incomplete, or failed, send one follow-up prompt in the same chat asking the model what went wrong before ending the case review.

## Unfinished-Case Follow-Up

If a protocol case does not fully complete, keep the same chat/session and send this follow-up prompt:

`What went wrong in the task you just attempted? Be specific about what blocked you, what you verified, what you failed to verify, and what you would do next to complete it. Do not retry the task yet.`

Purpose:

- capture the model's own explanation of the failure
- separate model reasoning issues from runtime/tooling issues
- gather better evidence for future system-prompt tuning
- see whether the model understood the real blocker or misunderstood the state

## Non-Model Issues To Watch For

These should be logged even if the model behaved reasonably:

- cron jobs not running
- cron jobs running too many times
- cron jobs firing at the wrong time
- browser tools returning weak or wrong output
- interactive tools failing or targeting the wrong window/app
- desktop observation/OCR mismatch
- file open/save failures
- app launch/runtime failures
- verification artifacts missing or weak

## Eval 1: Tool-Surface Sanity

### Goal

Exercise the main tool surfaces before the harder tasks so we can detect broken tools early.

### Prompt

`Open a simple page in the isolated browser, capture the main heading, save it into a text file in the current workspace, open that file so it is visible on the desktop, and also tell me what main app or window is currently visible on screen. Verify each step and keep the changes harmless.`

### Coverage

This eval should exercise, through normal task completion:

- Selenium browser pack tools
- workspace read tools
- workspace write tools
- desktop / interactive tools

### Purpose

The purpose is not to solve a big task. The purpose is to verify that the tools themselves run successfully and return usable outputs.

### Passing Grade

- all intended tool paths run successfully
- outputs are sane and usable
- no obvious runtime/tool contract failures

## Eval 2: Complex Browser Test

### Prompt

`Open Spotify and play a song. If Spotify is not available as a local app, use the browser instead. If playback is not possible because I am not logged in, confirm that clearly and stop there.`

### Goal

Test whether the model can figure out that Spotify is not installed locally and correctly fall back to Spotify in the browser.

### Passing Grade

Pass if either:

- music is actually playing

or:

- the model correctly proves that music cannot be played without the user being logged in

### Additional Evaluation Criteria

- whether the model uses the tools efficiently
- whether the fallback path is logical
- whether browser reasoning is clean and not wasteful

## Eval 3: Complex Research And Saving Task

### Prompt

`Research the following stocks and decide whether each one is a buy, sell, or hold: ANET, NBIS, and RWD. Save the results to a text document and then open the document so I can see it.`

### Goal

Test research, synthesis, file creation, and desktop opening behavior in one task.

### Passing Grade

- the final `.txt` file is created
- the research is clear and conclusive
- the requested stocks are covered:
  - `ANET`
  - `NBIS`
  - `RWD`
- each stock gets a clear signal:
  - `buy`
  - `sell`
  - or `hold`
- the `.txt` file is opened on the desktop for the user to see

## Eval 4: Complex Coding Task

### Prompt

`Create a simple calculator app and run it so I can use it. Use an Electron frontend and a Python backend.`

### Goal

Test coding, local execution, app launching, and design quality together.

### Passing Grade

- the calculator app is created
- it uses:
  - Electron frontend
  - Python backend
- it is running and open for use
- it works properly
- it looks good design-wise

## Eval 5: Simple Cron Job Scheduling (Paused)

### Status

Temporarily disabled from the runnable protocol suite.

### Prompt

`Schedule a midday brief for 5 minutes from now that gives me daily news and stock market news. After setting it up, wait for it to run, verify that it ran properly, and then disable the job.`

### Goal

Test scheduling, waiting correctly, verification, and job cleanup.

### Passing Grade

- the cron job is created correctly
- it is scheduled for 5 minutes from now
- it actually runs
- the model waits properly instead of stopping early
- the output works properly
- the job is disabled after the run
- the model verifies the run and the disable state

## Eval 6: Interactive Tool Complex Test

### Prompt

`Open my WhatsApp desktop app, find my personal chat with myself, and send a reminder to cancel my Grok membership. Make sure you do not send it to the wrong chat.`

### Goal

Test careful interactive-desktop behavior in a high-risk real-user app flow.

### Passing Grade

- the model opens WhatsApp desktop
- it finds the correct self-chat
- it sends the reminder to the correct chat
- it does not send to a different chat
- the interaction flow is efficient and careful

## Reporting Requirements

For each eval, capture and review:

- exact prompt
- follow-up prompt and answer for any unfinished case
- ordered tool sequence
- final answer
- artifacts/proof
- whether the task actually completed
- whether the verification was real or weak
- token usage
- latency
- any runtime/tooling errors

## Harness Verification Requirements

Prompts should stay natural and should not reveal implementation hints, but scenario JSON expectations should be strict enough to identify the behavioral failure mode. Prefer deterministic checks over subjective review:

- `required_tool_sequence` for expected decision flow, with alternative tool names grouped in arrays
- `required_tool_order` when verification must happen after creation or observation
- `tool_arg_checks` and `tool_result_checks` for verifying target files, URLs, commands, and observed content
- `artifact_checks` for saved files and generated outputs
- `required_reasoning_phrases` / `forbidden_reasoning_phrases` only when reasoning telemetry is available and the case truly needs it
- `max_unsupported_tool_attempts`, `max_tool_errors`, `min_tool_calls`, and `max_tool_calls` for tool-surface and efficiency regressions

The report should preserve raw ordered tool traces, prompt snapshots, artifacts, final answers, and structured diagnostic issues so failures can be classified as decision, tool-use, reasoning, verification, artifact, timing, infra, quota, or efficiency problems.

## Reuse Notes

This file is the baseline reusable protocol.

Future changes can customize:

- model list
- pass criteria
- timing requirements
- artifact requirements
- whether a given eval should be strict or exploratory
