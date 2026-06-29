# Kraitos Real-Task Demo Brief

Current date: 2026-06-10

This is the next HyperFrames asset after the rendered launch short. The launch short establishes the brand; this demo must prove the operator loop with a concrete task.

## Goal

Create a 25-30 second social demo that shows Kraitos doing real computer work through an inspectable loop:

`task request -> browser observation -> tool action -> evidence/logs -> fallback/recovery -> verified result`

The viewer should leave understanding that Kraitos is not a chatbot skin. It is a self-hosted operator layer that can see state, choose controlled tools, act, and leave evidence.

## Recommended Demo Task

Use a low-risk public task for the first proof asset:

> "Verify the Kraitos landing page download path and capture evidence that the Windows MSI link is available."

Why this task:

- It uses `kraitos.app`, so it reinforces the migration.
- It can be shown without private credentials.
- It naturally includes browser state, link inspection, terminal/log evidence, and a final verification state.
- It avoids risky destructive desktop actions.

## Format

Primary:

- 1080x1920 portrait social short.
- 25-30 seconds.
- Designed for X and LinkedIn.

Secondary, if time permits:

- 1920x1080 landscape cut for website/demo pages.
- Same source captures, wider composition.

## Visual Identity

Use the existing `kraitos-launch-short` design system:

- Mood: technical, controlled, auditable, sharp.
- Background: near-black operational grid.
- Primary: `#0fd48f`
- Secondary: `#ffb84d`
- Alert: `#eb5757`
- Text: `#f4f7fb`
- Muted text: `#b6c0cc`
- Surface: `#0a0f17`
- Large titles: system sans.
- Evidence/log details: Consolas or system monospace.
- Avoid generic AI glow, abstract orbs, and decorative filler.

## Required Captures

Capture these as short clips or screenshots before editing:

1. Task request surface:
   - Desktop, Telegram, or CLI prompt with the task request.
   - Keep private data out of frame.

2. Browser observation:
   - `kraitos.app` open in the browser.
   - Highlighted download CTA or inspected link target.
   - If available, show browser snapshot/ref output rather than only a normal browser view.

3. Tool/action evidence:
   - Terminal/log line showing the URL/link was checked.
   - File/log snippet proving the operator captured evidence.

4. Fallback/recovery proof:
   - Short OCR/screenshot fallback moment.
   - If OCR is not available for this exact task, show a labeled "fallback path available" panel using a real screenshot/log artifact, not fictional UI.

5. Verified result:
   - Final state: MSI link available, page verified, evidence saved.
   - End card with `kraitos.app`. Add the repo URL only after the public product repo link is verified.

## Scene Plan

| Time | Scene | Visual | Copy |
| --- | --- | --- | --- |
| 0.0-2.5 | Task arrives | Task request enters queue | "Kraitos gets a real task" |
| 2.5-6.5 | Observe | Browser/state snapshot of `kraitos.app` | "First: observe the machine state" |
| 6.5-11.0 | Act | Download CTA/link target inspection | "Then act through controlled tools" |
| 11.0-16.5 | Evidence | Terminal/log/evidence artifact | "Every step leaves evidence" |
| 16.5-21.5 | Recovery path | OCR/screenshot fallback panel | "Fallbacks keep the loop grounded" |
| 21.5-27.0 | Verified result | Final verified state and CTA | "Verified. Inspectable. Self-hosted." |

## On-Screen Copy

Use short lines. Avoid explaining the whole system at once.

Primary copy options:

- "Real task, real machine state"
- "Observe before acting"
- "Controlled tools, not blind clicks"
- "Evidence after every step"
- "Fallbacks when DOM control is not enough"
- "Self-host it: kraitos.app"

End card:

```text
Kraitos
Self-hosted AI operator layer

kraitos.app
Public repo link coming from kraitos.app
```

## HyperFrames Implementation Notes

Suggested project:

`C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-real-task-demo`

Suggested structure:

- `design.md`: copy tokens from `kraitos-launch-short/design.md`.
- `index.html`: root portrait composition.
- `assets/`: raw clips/screenshots, kept small.
- `renders/`: final MP4/poster outputs.

Use sub-compositions if the timeline gets dense:

- `compositions/task-arrival.html`
- `compositions/browser-observe.html`
- `compositions/evidence-log.html`
- `compositions/fallback-proof.html`
- `compositions/final-cta.html`

Keep animation deterministic:

- No `Date.now()`.
- No unseeded `Math.random()`.
- No render-time network fetches.
- Use fixed text and local assets.
- Use paused GSAP timelines registered on `window.__timelines`.

## Layout Requirements

- Build each scene's hero frame first before adding motion.
- Keep content inside safe margins for portrait video.
- Do not let terminal/log text become tiny filler; crop to the meaningful lines.
- Use zoom/pan only to reveal evidence, not to simulate fake complexity.
- Make the mouse/cursor path legible if included.
- Keep brand CTA visible for at least 3 seconds at the end.

## Audio

Use no voiceover for the first version unless there is a clear narration asset.

Optional caption-only rhythm:

- Short caption entrances per scene.
- Subtle UI tick/success sound only if already available locally.
- No generated TTS until storage is safely above the 5 GB floor.

## Acceptance Checks

Before rendering or posting:

- The task shown is specific and non-private.
- The browser state is recognizable as `kraitos.app`.
- Evidence/logs are real captures or honest mock overlays from real output.
- The video shows a before/after verification state.
- The viewer can name at least one concrete capability after watching.
- The CTA includes `kraitos.app`.
- No unverified repo URL appears in the frame.
- The composition passes:

```powershell
npx hyperframes lint
npx hyperframes validate
npx hyperframes inspect
```

Only render when local storage has a safe buffer above the 5 GB floor.

## Postiz Follow-Up Slot

Suggested label for the next queue:

`x-real-task-demo`

Suggested copy:

```text
This is the Kraitos demo I care about most:

not a clean chatbot prompt, but a real operator loop.

observe -> act -> log evidence -> verify result

kraitos.app
```

Attach the rendered MP4 after upload through Postiz.
