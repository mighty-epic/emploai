# Kraitos Engagement Playbook

Current date: 2026-06-10

Use this after each launch post goes live. The goal is to turn attention into trust: answer technical questions clearly, admit current limits, and route useful objections into docs, demos, or product tasks.

## Reply Principles

- Be specific. Mention the actual subsystem: browser refs, Chrome bridge, OCR fallback, Markdown memory, logs, Telegram control, desktop input, or scheduled workers.
- Do not overclaim autonomy. Kraitos is an operator layer with human-owned control boundaries.
- Do not argue with vague criticism. Ask for the concrete failure mode they care about.
- Push serious technical questions toward docs/demo follow-ups until the public product repo URL is verified.
- Keep public replies short, then offer deeper detail in a thread, issue, or demo.
- Never share secrets, local paths, API keys, Postiz IDs, or private machine details.

## First-Hour Workflow

Within 10 minutes:

1. Confirm the post rendered correctly.
2. Confirm links work and preserve UTM parameters.
3. Save the live post URL for measurement.
4. Watch for immediate corrections: broken link, unclear wording, bad media attach, misleading claim.

Within 60 minutes:

1. Reply to every genuine technical question.
2. Like or acknowledge constructive criticism.
3. Convert repeated objections into a next-post note.
4. Record strong replies in the measurement review.
5. If a reply exposes a product weakness, create a docs/demo/product follow-up note.

## Response Bank

### "Is this just another chatbot?"

```text
Not really. The positioning is intentionally "operator layer" rather than chat UI.

Kraitos is built around observe -> choose tool -> act -> verify. The interesting parts are browser snapshots, desktop observation, OCR fallback, logs, memory, and controlled tool access.
```

### "How is this different from Selenium?"

```text
Selenium is one useful layer, but it is not the whole control model.

Kraitos can use structured browser refs, a Chrome extension bridge for real-session workflows, and desktop/OCR fallback when DOM automation is not enough.
```

### "Is a real computer-control agent safe?"

```text
That is the main design constraint.

Kraitos is meant to be self-hosted and inspectable: explicit authorized users, visible logs/screenshots, Markdown memory, and a constrained tool registry. The goal is not unchecked autonomy.
```

### "Can I run it locally?"

```text
That is the target path: self-hosted first, with the owner controlling runtime, credentials, memory, logs, and machine access.

The public project page is live while the repo migration is being cleaned up:
https://kraitos.app
```

### "What is the Chrome bridge for?"

```text
Some workflows depend on real browser state: active tabs, existing sessions, logged-in context, or pages that behave differently under automation.

The Chrome bridge is there so the operator loop can observe and act in that real session while still leaving evidence.
```

### "Why Telegram?"

```text
Telegram is one remote control surface, not the whole product.

It is useful because an operator loop often needs to receive tasks, report checkpoints, and ask for human approval while the actual work happens on a machine or VPS.
```

### "Where is the demo?"

```text
The launch short is the first brand/demo asset.

The next stronger demo should show a real browser task end to end: browser refs, action log, OCR fallback if needed, and final result.
```

### "The website looks cool, but what can it actually do?"

```text
Fair question. The site is the brand surface.

The product work is the operator runtime: browser state, desktop input, files, terminal, memory, Telegram control, and scheduled jobs. The next demo needs to make that control loop visible.
```

### "Why rename EmploAI to Kraitos?"

```text
EmploAI sounded like an AI employee concept.

Kraitos is a better fit for the direction: a self-hosted operator layer for controlled computer work across browser, desktop, terminal, memory, and remote surfaces.
```

### "Is this open source?"

```text
The public project page is live at:
https://kraitos.app

The brand/domain are moving to Kraitos, and the public product repo URL should be shared once it passes verification.
```

### "What should I review first?"

```text
The highest-signal feedback would be on the control boundary:

- what actions should require confirmation
- what logs/screenshots should be retained
- what a safe browser bridge should expose
- what install docs would make you trust running it
```

## Objection Routing

| Objection | Reply posture | Follow-up artifact |
| --- | --- | --- |
| "Unsafe" | Agree safety is central, explain constraints | Trust-boundary post or docs page |
| "Just Selenium" | Clarify layered control model | Browser bridge demo |
| "No clear demo" | Acknowledge, point to next demo | HyperFrames demo brief |
| "Install unclear" | Ask what environment they use | Installer/docs task |
| "Why Telegram?" | Position as remote control surface | Remote ops post |
| "Too much hype" | Ground in current subsystems | Architecture thread |
| "Where are logs?" | Explain inspectable evidence loop | Observability screenshot/demo |

## Escalation Rules

Create an internal task, docs task, or public issue after the repo URL is verified when:

- Two or more people ask the same technical question.
- Someone identifies a real safety or install concern.
- A reply would require code-level discussion.
- A missing demo prevents people from understanding the product.
- A claim in the copy is ambiguous enough to cause confusion.

Do not escalate:

- Generic low-context criticism.
- Requests for secrets, private infrastructure, or machine access.
- Off-topic debates that do not improve the product or launch.

## Follow-Up Content Triggers

Use these triggers to decide the next post:

| Signal | Next content |
| --- | --- |
| Many questions about safety | Trust boundary post |
| Many questions about browser automation | Chrome bridge explainer |
| Many questions about practical value | Real task demo |
| Many questions about self-hosting | Install/deploy walkthrough |
| Many questions about Telegram/VPS | Remote operator workflow |
| High saves but few replies | Deeper technical thread |
| High comments but low clicks | Shorter CTA-focused follow-up |

## Logging Template

Record notable engagement like this:

```text
Date:
Platform:
Post label:
Live post URL:
Reply/comment:
Theme:
Response given:
Follow-up needed:
Owner:
```

Store the summary in the next measurement review or a launch notes file.
