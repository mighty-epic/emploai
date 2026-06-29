# Kraitos Launch Plan

Current date: 2026-06-10

## Objective

Move the public brand from EmploAI to **Kraitos** while preserving technical continuity for people who already saw the EmploAI name, repository, or demos.

## Public Domain State

As of 2026-06-10, `https://kraitos.app` is live with the Kraitos landing page, Windows MSI download path, and scroll-reactive workstation scene. It is ready to receive campaign traffic while product-demo media continues to improve.

## Positioning

**Kraitos is a self-hosted AI operator layer for real computer tasks.**

It accepts tasks through desktop, Telegram, or CLI surfaces, reasons with multiple LLM providers, and acts through controlled tools: browser snapshots, a Chrome extension bridge, terminal/file tools, OCR fallback, desktop input, memory, and scheduled jobs.

## Migration Language

- First-touch copy: "Kraitos, formerly EmploAI"
- Technical copy: "Kraitos is the new public name for the EmploAI codebase while the public repo migration is in progress."
- Short bio: "Self-hosted AI operator layer for browser, desktop, terminal, and remote VPS workflows."
- Domain CTA: https://kraitos.app
- Public project CTA during transition: https://kraitos.app

## Audience

- Self-hosters who want auditable, local-first automation.
- Developers building computer-use agents.
- DevOps/sysadmin users who need remote VPS-controlled workflows.
- Technical founders who want automation without hiding state in a black box.

## Channel Priority

The first social priority is short vertical video:

1. **TikTok**: fastest hook-testing loop for "desktop AI agent controls the computer" framing.
2. **Instagram Reels**: primary visual brand surface for the Jarvis-style workstation concept.
3. **YouTube Shorts**: evergreen discovery surface for every strong proof clip.
4. **Facebook Reels/Page**: secondary reach and broader automation audience.
5. **X and LinkedIn**: supporting technical credibility, reply mining, and founder/developer context.

Every major proof asset should start as a 1080x1920 vertical cut. Landscape and text-first variants come after the vertical version works.

## Narrative Pillars

1. **Real machine control, not just chat**: Kraitos executes tasks on a live machine through constrained tools.
2. **Inspectable state**: Memory, logs, screenshots, and work artifacts stay human-readable.
3. **Multiple control paths**: Browser ARIA snapshots, Chrome extension bridge, Selenium, OCR, and desktop input are available in one loop.
4. **Self-hosted trust boundary**: Users own the runtime, credentials, and authorization list.
5. **Remote operation**: Telegram and VPS workers turn one-off automation into ongoing operations.

## Launch Week Cadence

All dates are UTC and should be shifted in Postiz if the connected audience analytics suggest a better local slot.

| Date | Channel | Asset | Goal |
| --- | --- | --- | --- |
| 2026-06-11 13:00 | X | Rename thread | Establish Kraitos as the new name and technical category |
| 2026-06-11 14:00 | Instagram | Launch reel | Lead visual discovery and MSI interest |
| 2026-06-11 14:15 | Facebook | Launch reel | Broaden reach beyond technical networks |
| 2026-06-11 14:30 | TikTok | Launch short | Test the strongest desktop-agent hook |
| 2026-06-11 14:45 | YouTube Shorts | Launch short | Seed evergreen short-form discovery |
| 2026-06-11 16:00 | LinkedIn | Architecture post | Reach technical founders and engineering managers |
| 2026-06-12 13:00 | X | Browser bridge proof | Prove the core automation claim |
| 2026-06-12 18:00 | Reddit | Technical show post | Earn feedback from self-hosters and agent builders |
| 2026-06-15 13:00 | X | Security/observability post | Build trust around machine control |
| 2026-06-16 13:00 | X | Demo follow-up | Drive domain visits and project-page clicks |

## HyperFrames Asset Brief

Create a 20-second portrait short first. Make the landscape version only after the vertical version has a strong hook and clear CTA.

Scene timing:

| Time | Visual | Copy |
| --- | --- | --- |
| 0.0-3.0 | Terminal and browser split | "Kraitos" |
| 3.0-6.5 | Telegram task enters queue | "Send a task from anywhere" |
| 6.5-10.5 | Browser snapshot with refs | "Acts through inspectable tools" |
| 10.5-14.5 | OCR fallback over desktop | "Recovers when DOM control is not enough" |
| 14.5-20.0 | Domain and project CTA | "Self-host it: kraitos.app" |

Visual rules:

- Avoid vague AI glow. Show real control surfaces: terminal, browser refs, Telegram, screenshots, logs.
- Use "formerly EmploAI" only once in a small transition line.
- CTA frame should include `kraitos.app`. Add the repo URL only after the public product repo link passes the link audit.

## Next Proof Demo

After the launch short, build the real-task proof asset from `kraitos_real_task_demo_brief.md`.

Recommended demo:

> Verify the Kraitos landing page download path and capture evidence that the Windows MSI link is available.

This follow-up should show the actual operator loop: task request, browser observation, controlled action, evidence/logs, fallback path, and verified result. Do not render this next asset until local storage has a safe buffer above the 5 GB floor.

## Postiz Operating Notes

- Fetch integrations before scheduling so each payload has a real `integration.id`.
- Upload rendered HyperFrames media with `/public/v1/upload`, then attach returned media IDs and paths to post payloads.
- Use `marketing_assets/postiz_schedule_seed.json` as the source payload seed.
- After scheduling, append the Postiz response IDs to `marketing_assets/schedule_log.json`.
- The first portrait launch short is rendered and tracked in `marketing_assets/rendered_assets.md`.
- The next real-task demo brief is tracked in `marketing_assets/kraitos_real_task_demo_brief.md`.

## Success Metrics

- Vertical video reach, completion rate, rewatches, saves, shares, and profile visits.
- Project-page clicks, repo requests, and docs requests after each post.
- `kraitos.app` visits from social referrals.
- Postiz analytics per channel.
- Replies that ask for setup help, deploy docs, or contribution tasks.
- Self-hosted deployment attempts reported by users.
