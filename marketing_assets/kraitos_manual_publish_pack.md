# Kraitos Manual Publish Pack

Current date: 2026-06-10

Use this only if Postiz is not connected before the first launch slots. `postiz_schedule_seed.json` remains the source of truth for automated scheduling; this pack is the manual fallback copy.

## Publish Rules

- Keep the scheduled UTC times if practical.
- Use the UTM links exactly as written so measurement still works.
- Keep X thread posts in the listed order.
- Attach the HyperFrames MP4 to `instagram-launch-reel`, `facebook-launch-reel`, `tiktok-launch-short`, `youtube-launch-short`, and `x-demo-follow-up`.
- Do not paste any Postiz API keys, integration IDs, media IDs, or local secrets into social platforms.
- After manual posting, record the live post URL with `.\scripts\postiz_kraitos_operator.ps1 --record-published <label> --published-url <url>`.

## Asset

HyperFrames short:

`C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short\renders\kraitos_launch_short.mp4`

Alt text:

`Kraitos launch short showing a self-hosted AI operator layer for real computer tasks.`

## 2026-06-11 13:00 UTC - X - x-rename-thread

Post 1:

```text
Kraitos is the new name for EmploAI.

Self-hosted AI operator layer for real computer tasks across browser, desktop, terminal, memory, and scheduled jobs.

https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=rename_thread
```

Post 2:

```text
The core bet: agentic systems need observable control surfaces.

Kraitos gives the loop structured tools: file operations, shell commands, browser snapshots, OCR, screenshots, and desktop input.
```

Post 3:

```text
Browser automation is layered.

Kraitos can use Selenium, but it can also connect to a real Chrome session through a WebSocket extension bridge when tasks depend on active tabs or logged-in state.
```

Post 4:

```text
When DOM control is not enough, the system can fall back to desktop observation.

Screenshots plus OCR make failures visible, then the loop can recover through controlled keyboard, mouse, and window tools.
```

Post 5:

```text
Trust model: self-host it, inspect it, constrain it.

Memory is Markdown. Logs and screenshots are visible. Authorization is explicit.

Project page:
https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=rename_thread_project
```

## 2026-06-11 14:00 UTC - Instagram - instagram-launch-reel

Attach the HyperFrames MP4 listed in the Asset section.

```text
Kraitos, formerly EmploAI.

A desktop AI agent that can operate your computer with you in control: browser, desktop, terminal, memory, and scheduled jobs.

Download the Windows MSI:
https://kraitos.app/?utm_source=instagram&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_reel

#Kraitos #AIAgent #Automation #SelfHosted #DesktopAI
```

## 2026-06-11 14:15 UTC - Facebook - facebook-launch-reel

Attach the HyperFrames MP4 listed in the Asset section.

```text
Kraitos is the new name for EmploAI.

It is a desktop AI agent for real computer work: browser state, desktop input, terminal commands, memory, logs, and scheduled jobs, with the human still in control.

Download the Windows MSI:
https://kraitos.app/?utm_source=facebook&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_reel
```

## 2026-06-11 14:30 UTC - TikTok - tiktok-launch-short

Attach the HyperFrames MP4 listed in the Asset section.

Title:

```text
Kraitos: desktop AI operator
```

Caption:

```text
Kraitos is a desktop AI agent that can operate your computer with you in control. Download the Windows MSI: https://kraitos.app/?utm_source=tiktok&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_short #Kraitos #AIAgent #Automation
```

Recommended posting settings:

- Visibility: public
- Comments: on
- Duet: on
- Stitch: on
- Auto music: off

## 2026-06-11 14:45 UTC - YouTube Shorts - youtube-launch-short

Attach the HyperFrames MP4 listed in the Asset section.

Title:

```text
Kraitos: desktop AI operator #Shorts
```

Description:

```text
Kraitos is the new name for EmploAI: a desktop AI agent that can operate your computer with you in control.

It connects model reasoning to browser state, desktop input, terminal commands, files, logs, memory, and scheduled jobs.

Download the Windows MSI:
https://kraitos.app/?utm_source=youtube&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_short

#Shorts #Kraitos #AIAgent #Automation
```

Suggested tags:

```text
kraitos, ai agent, desktop automation, self hosted
```

## 2026-06-11 16:00 UTC - LinkedIn - linkedin-architecture-post

```text
Kraitos is the new public name for EmploAI.

The product direction is sharper now: Kraitos is a self-hosted AI operator layer for real computer tasks.

Most agent demos stop at chat or a clean browser sandbox. Kraitos is built around the messier systems problem: how do you let an LLM-driven loop act on a live machine while keeping the work observable, constrained, and recoverable?

The architecture is intentionally layered:

1. Browser snapshots expose stable element references instead of raw coordinate guessing.
2. A Chrome extension bridge can connect to a real user session when standard automation is too brittle.
3. OCR and screenshot fallback keep the loop grounded when DOM-level control fails.
4. Telegram, desktop, and CLI surfaces route tasks into the same tool-oriented runtime.
5. Memory and logs stay inspectable in plain files.

Domain:
https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=architecture_post

Project page during the migration:
https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=architecture_post_project

#AI #OpenSource #SelfHosted #DevOps #Automation #AgenticAI
```

## 2026-06-12 13:00 UTC - X - x-browser-bridge-proof

Post 1:

```text
Browser automation breaks when the model has to guess.

Kraitos builds inspectable browser snapshots with stable refs, then acts on those refs instead of raw coordinates.

That gives the loop evidence before every click.
```

Post 2:

```text
When standard automation is too brittle, Kraitos can use a Chrome extension bridge to talk to a real user session.

Active tabs. Logged-in state. Fewer auth dances.

Still self-hosted. Still inspectable.
```

Post 3:

```text
This is the difference between a demo agent and an operator layer:

observe -> choose a tool -> act -> observe again

The loop is only useful if every step leaves evidence.
```

## 2026-06-15 13:00 UTC - X - x-observability-security

```text
A computer-use agent should not be a black box.

Kraitos keeps the trust boundary visible:

- self-hosted runtime
- explicit authorized users
- plain Markdown memory
- screenshots and logs
- fallback paths when tools fail
```

## 2026-06-16 13:00 UTC - X - x-demo-follow-up

Attach the HyperFrames MP4 listed in the Asset section.

```text
HyperFrames-built launch short.

Next demo: a real browser task with refs, action logs, OCR fallback, and final result.

https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=demo_follow_up
```

## 2026-06-17 16:00 UTC - LinkedIn - linkedin-selfhosted-ops

```text
The most interesting part of Kraitos is not the prompt. It is the operating model.

A useful computer-use system needs more than a model call:

- a controlled tool registry
- browser and desktop observations
- recovery paths when automation fails
- remote control surfaces such as Telegram
- scheduled workers for recurring tasks
- logs and memory that humans can inspect

That is why Kraitos is being positioned as a self-hosted operator layer, not as a chatbot. The model reasons, but the system owns the loop: observe, choose, act, verify, and persist evidence.

Domain: https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=selfhosted_ops
Project page during migration: https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=selfhosted_ops_project
```

## 2026-06-19 13:00 UTC - X - x-contributor-call

Post 1:

```text
If you're testing self-hosted agents, I want hard feedback on Kraitos.

What would make you trust a local operator loop with browser, desktop, terminal, memory, and scheduled jobs?
```

Post 2:

```text
Useful feedback:

- bridge safety
- install docs
- approval boundaries
- log retention
- real-task demos

Project page:
https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=contributor_call_feedback
```

## After Posting

Record:

- Platform
- Label
- Published URL
- Published time
- Whether media was attached
- Any immediate replies or objections

Then update the measurement review using `kraitos_measurement_plan.md`.

For the schedule audit log, run:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --record-published x-rename-thread `
  --published-url "https://x.com/<account>/status/<id>" `
  --published-at "2026-06-11T13:05:00Z"
```
