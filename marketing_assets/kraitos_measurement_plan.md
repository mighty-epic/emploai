# Kraitos Launch Measurement Plan

Current date: 2026-06-10

The first Kraitos campaign wave should measure whether the rename and operator-layer positioning are landing with the right audience. Use the UTM-tagged links in `postiz_schedule_seed.json` as the source of truth for campaign attribution.

## Tracking Rules

- Campaign name: `kraitos_rename_launch`
- Use `utm_source=x` for X posts.
- Use `utm_source=linkedin` for LinkedIn posts.
- Use `utm_source=instagram`, `facebook`, `tiktok`, and `youtube` for vertical video posts.
- Use `utm_medium=social` for all seeded Postiz posts.
- Use `utm_content` values that match the Postiz label or the specific CTA role.
- Keep `shortLink` disabled unless Postiz link behavior is reviewed, because raw UTMs are easier to inspect during this first launch wave.

## Seeded URL Map

| Postiz label | CTA | Tracking URL |
| --- | --- | --- |
| `x-rename-thread` | Domain | `https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=rename_thread` |
| `x-rename-thread` | Project page | `https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=rename_thread_project` |
| `linkedin-architecture-post` | Domain | `https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=architecture_post` |
| `linkedin-architecture-post` | Project page | `https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=architecture_post_project` |
| `instagram-launch-reel` | Domain | `https://kraitos.app/?utm_source=instagram&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_reel` |
| `facebook-launch-reel` | Domain | `https://kraitos.app/?utm_source=facebook&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_reel` |
| `tiktok-launch-short` | Domain | `https://kraitos.app/?utm_source=tiktok&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_short` |
| `youtube-launch-short` | Domain | `https://kraitos.app/?utm_source=youtube&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=launch_short` |
| `x-demo-follow-up` | Domain | `https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=demo_follow_up` |
| `linkedin-selfhosted-ops` | Domain | `https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=selfhosted_ops` |
| `linkedin-selfhosted-ops` | Project page | `https://kraitos.app/?utm_source=linkedin&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=selfhosted_ops_project` |
| `x-contributor-call` | Feedback CTA | `https://kraitos.app/?utm_source=x&utm_medium=social&utm_campaign=kraitos_rename_launch&utm_content=contributor_call_feedback` |

## Launch KPIs

Track these during the first 72 hours after each post:

| Signal | Why it matters | Source |
| --- | --- | --- |
| `kraitos.app` sessions by `utm_content` | Tells which narrative drives site visits | Site analytics or Netlify analytics |
| MSI download clicks | Measures high-intent desktop app interest | Site analytics or server logs |
| Public project CTA clicks and technical replies | Measures developer interest until the product repo URL is public | Site analytics and channel replies |
| Instagram reach, profile visits, saves, and reel retention | Measures whether the visual concept lands with a broader audience | Postiz/channel analytics |
| TikTok views, completion, rewatches, saves, and comments | Fastest signal for hook quality and demo clarity | Postiz/channel analytics |
| YouTube Shorts views, average view duration, likes, and subs | Measures durable video discovery | YouTube/Postiz analytics |
| Facebook reach, link clicks, comments, and shares | Measures broader automation audience response | Postiz/channel analytics |
| X replies/bookmarks/reposts | Measures technical resonance and saved intent | Postiz/channel analytics |
| LinkedIn comments/profile clicks | Measures founder/operator audience fit | Postiz/channel analytics |
| Demo video completion or engagement | Measures whether HyperFrames asset carries the concept | Channel analytics |

## Review Cadence

Daily during launch week:

1. Check Postiz/channel analytics for posts that published in the previous 24 hours.
2. Check `kraitos.app` traffic grouped by `utm_source` and `utm_content`.
3. Check MSI download clicks and any installer support questions.
4. Use `kraitos_engagement_playbook.md` to answer notable replies, questions, and objections.
5. Convert repeated objections into either a docs task, demo task, or next social post.
6. Record observed metrics with `--record-metrics` so `measurement_log.json` becomes the launch performance timeline.

Weekly:

1. Compare Instagram, TikTok, YouTube Shorts, and Facebook reach-to-click quality before judging X/LinkedIn.
2. Identify the best-performing opening hook, not just the best-performing channel.
3. Decide whether the next HyperFrames asset should show browser bridge, OCR fallback, Telegram control, or installer flow.
4. Update `kraitos_content_calendar.md` with the next wave.

## Interpretation Guide

- High visits and low downloads means the landing page or installer CTA needs clearer trust proof.
- High comments and low clicks means the positioning is interesting but the CTA is weak or buried.
- High project-page clicks and low downloads means developer-first messaging is working better than installer intent.
- Strong saves/bookmarks on X suggest a follow-up technical thread.
- Strong LinkedIn comments suggest a founder/operator post about trust boundaries, deployment, or ROI.
- Strong vertical video views but weak site sessions means the hook is interesting but the CTA/end card is not forceful enough.
- Strong YouTube Shorts retention suggests the same concept deserves a longer landscape demo.

## Next Measurement Setup

Before posts go live, confirm one of these is available:

- Netlify analytics for `kraitos.app`.
- Another privacy-safe analytics script on the landing page.
- Server/CDN logs that can filter query strings.

If none is available, use Postiz/channel analytics plus manual reply tracking as the temporary measurement layer.

## Manual Metrics Logging

Use the Postiz operator to append observed metrics without calling external services:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --record-metrics x-rename-thread `
  --source x-analytics `
  --metric impressions=1200 `
  --metric clicks=37 `
  --metric replies=4 `
  --observed-at "2026-06-11T18:00:00Z"
```

Useful metric keys:

- `impressions`
- `clicks`
- `replies`
- `reposts`
- `shares`
- `bookmarks`
- `saves`
- `likes`
- `views`
- `average_view_duration`
- `completion_rate`
- `rewatches`
- `subscribers_gained`
- `profile_clicks`
- `site_sessions`
- `msi_downloads`
- `project_page_clicks`
- `repo_requests`
- `docs_requests`

Use the same Postiz label as `postiz_schedule_seed.json` so the metrics can be tied back to the original payload.
