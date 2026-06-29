# Kraitos Marketing Assets Directory

This folder contains marketing plans, copywriting, visual storyboard assets, and Postiz scheduling seeds for launching **Kraitos**, formerly EmploAI during the migration window.

## Current Operating State

As of 2026-06-10:

- `https://kraitos.app` is live and ready to receive campaign traffic.
- The first Postiz campaign wave is refreshed for 2026-06-11 through 2026-06-19, with Instagram, Facebook, TikTok, and YouTube Shorts now treated as primary vertical-video channels.
- The rendered HyperFrames portrait short exists at `C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short\renders\kraitos_launch_short.mp4`.
- Local Postiz was not reachable at `http://localhost:4007` during the latest audit, so upload and scheduling remain dry-run only until Postiz is started and `POSTIZ_API_KEY` is set.
- C: drive free space has recently hovered near the 5 GB floor, so local Docker/Postiz compose is paused; use a remote Postiz API URL or free storage before local Docker work.
- `media_upload_log.json` should remain empty until real API upload calls succeed; `schedule_log.json` can also record manual fallback posts after they are actually published.
- `measurement_log.json` stays empty until real post/channel/site metrics are observed.

## CMO Operating Loop

Use this loop for every Kraitos social campaign:

1. **Position**: update `kraitos_launch_plan.md` when product positioning, domain state, public repo URL, or campaign objective changes.
2. **Create**: build or revise short-form assets in HyperFrames. Start with 1080x1920 vertical video, then adapt to text-first channels after the hook works.
3. **Register**: record rendered files in `rendered_assets.md` and reference them from `postiz_schedule_seed.json` under `mediaAssets`.
4. **Schedule seed**: write channel copy and UTC publishing slots in `postiz_schedule_seed.json`. Keep every date in the future.
5. **Dry-run**: run the Postiz operator without `--schedule` and fix all non-placeholder validation errors.
6. **Upload media**: when Postiz is running, upload media through the operator, then copy returned media placeholders into the scheduling dry-run.
7. **Schedule**: only after the dry-run preview is reviewed, run the operator with `--schedule`.
8. **Quick publish**: for a ready-made vertical video, use `scripts\postiz_publish_video_now.ps1` to preview, then publish immediately with `-PublishNow`.
9. **Measure**: copy Postiz responses into `schedule_log.json`, then review replies, visits, downloads, repo requests, and comments before the next wave.

## File Registry

1. **[kraitos_launch_plan.md](kraitos_launch_plan.md)**:
   - Brand migration plan from EmploAI to Kraitos.
   - Launch-week cadence, positioning, HyperFrames brief, and success metrics.

2. **[kraitos_social_posts.md](kraitos_social_posts.md)**:
   - Kraitos-first X thread.
   - LinkedIn architecture announcement.
   - Reddit self-hosted technical draft.

3. **[kraitos_content_calendar.md](kraitos_content_calendar.md)**:
   - Two-week channel calendar.
   - Weekly operating rhythm and content backlog prompts.

4. **[kraitos_vertical_video_distribution.md](kraitos_vertical_video_distribution.md)**:
   - Instagram/Facebook/TikTok/YouTube Shorts priority, first vertical wave, hooks, and metrics.
   - Source of truth for short-form distribution before new HyperFrames renders.

5. **[kraitos_site_copy.md](kraitos_site_copy.md)**:
   - Replacement copy for the live `kraitos.app` landing page.
   - SEO metadata, hero, sections, FAQ, and footer text.

6. **[kraitos_profile_migration.md](kraitos_profile_migration.md)**:
   - Social profile bios.
   - GitHub description/topics.
   - Rename checklist across domain, profiles, and repo.

7. **[kraitos_measurement_plan.md](kraitos_measurement_plan.md)**:
   - UTM map, launch KPIs, and post-publish review cadence.
   - Measurement loop for `kraitos.app`, project CTAs, and channel analytics.

8. **[kraitos_manual_publish_pack.md](kraitos_manual_publish_pack.md)**:
   - Manual fallback copy for Instagram, Facebook, TikTok, YouTube Shorts, X, and LinkedIn if Postiz is not connected in time.
   - Uses the same UTM links and schedule labels as `postiz_schedule_seed.json`.

9. **[kraitos_engagement_playbook.md](kraitos_engagement_playbook.md)**:
   - Reply principles, response bank, and objection-routing rules.
   - Turns launch replies into docs, demos, product tasks, and next-wave content.

10. **[kraitos_real_task_demo_brief.md](kraitos_real_task_demo_brief.md)**:
   - HyperFrames-ready brief for the next proof demo.
   - Shows a real operator loop: observe, act, log evidence, recover, verify.

11. **[rendered_assets.md](rendered_assets.md)**:
   - Rendered HyperFrames media paths.
   - Verification notes and Postiz upload placeholders.

12. **[postiz_schedule_seed.json](postiz_schedule_seed.json)**:
   - Postiz `/public/v1/posts` payload seeds.
   - Safe placeholders for integration IDs and uploaded media IDs.

13. **[postiz_launch_runbook.md](postiz_launch_runbook.md)**:
   - Safe launch-day operating checklist for Postiz.
   - Exact dry-run, upload, integration lookup, and scheduling commands.

14. **[schedule_log.json](schedule_log.json)**:
   - Audit log for scheduled Postiz posts.
   - Keep empty until real API scheduling succeeds.

15. **[measurement_log.json](measurement_log.json)**:
   - Audit log for manual performance snapshots.
   - Records observed post, site, project-page, and download metrics.

16. **[media_upload_log.json](media_upload_log.json)**:
   - Audit log for Postiz media upload responses.
   - Keep empty until real API uploads succeed.

17. **[postiz.env.example](postiz.env.example)**:
   - Safe environment template for Postiz base URL, API key, and integration IDs.

18. **[video_drop/README.md](video_drop/README.md)**:
   - Ignored folder for local ready-made videos.
   - Explains the dry-run-first quick publish command.

19. **[social_posts.md](social_posts.md)**:
   - Legacy EmploAI-first copy redirect.
   - Do not schedule from this file.

20. **[video_script.md](video_script.md)**:
   - Legacy EmploAI-first video script redirect.
   - Do not render new assets from this file.

---

## Rendering the Video Demo

Use HyperFrames for rendered launch assets. Current Kraitos launch guidance lives in `kraitos_launch_plan.md`; rendered outputs are tracked in `rendered_assets.md`.

To render the 20-second promo video:
1. Drop your raw screen recording or demo video in `packages/studio/data/projects/edit-project/` and rename it to `video.mp4`.
2. Run the studio server:
   ```bash
   bun run dev
   ```
3. Open the studio in your browser to preview the animations over your video:
   [http://localhost:5190/#project/edit-project](http://localhost:5190/#project/edit-project)
4. To export the finished video to MP4, run:
   ```bash
   bun run --cwd packages/cli dev render <hyperframes-workspace>\packages\studio\data\projects\edit-project\index.html -o kraitos_demo.mp4
   ```

## Scheduling With Postiz

The scheduling operator is dry-run by default:

```bash
python scripts/postiz_kraitos_operator.py
```

On Windows, the PowerShell wrapper will find `python`, `py`, or the local Codex bundled Python:

```powershell
.\scripts\postiz_kraitos_operator.ps1
```

To list connected Postiz channels:

```bash
python scripts/postiz_kraitos_operator.py --list-integrations
```

To run a no-network readiness check:

```bash
python scripts/postiz_kraitos_operator.py --preflight
```

To print the daily no-network campaign status:

```bash
python scripts/postiz_kraitos_operator.py --status
```

To audit marketing asset consistency:

```bash
python scripts/postiz_kraitos_operator.py --audit-marketing
```

To audit outbound campaign links without downloading media/installers:

```bash
python scripts/postiz_kraitos_operator.py --audit-links
```

To preview with explicit integration IDs:

```bash
python scripts/postiz_kraitos_operator.py --integration POSTIZ_X_INTEGRATION_ID=<x-channel-id> --integration POSTIZ_LINKEDIN_INTEGRATION_ID=<linkedin-channel-id>
```

To export a resolved local review bundle:

```bash
python scripts/postiz_kraitos_operator.py --export-preview marketing_assets/generated/postiz_preview_export.json
```

The export command refuses to write while unresolved `POSTIZ_*` placeholders remain.

To record a manually published fallback post:

```bash
python scripts/postiz_kraitos_operator.py --record-published x-rename-thread --published-url https://x.com/<account>/status/<id> --published-at 2026-06-11T13:05:00Z
```

To record a manual metrics snapshot:

```bash
python scripts/postiz_kraitos_operator.py --record-metrics x-rename-thread --source x-analytics --metric impressions=1200 --metric clicks=37 --metric replies=4
```

To preview a post with uploaded media placeholders:

```bash
python scripts/postiz_kraitos_operator.py --label x-demo-follow-up --integration POSTIZ_X_INTEGRATION_ID=<x-channel-id> --placeholder POSTIZ_KRAITOS_SHORT_MEDIA_ID=<media-id> --placeholder POSTIZ_KRAITOS_SHORT_MEDIA_PATH=<media-path>
```

To preview the rendered MP4 upload:

```bash
python scripts/postiz_kraitos_operator.py --upload-media kraitos-launch-short
```

To preview a ready-made video for Instagram, Facebook, TikTok, and YouTube Shorts:

```powershell
.\scripts\postiz_publish_video_now.ps1 -Video "marketing_assets\video_drop\your-video.mp4"
```

To publish that video immediately after the preview and environment are correct:

```powershell
.\scripts\postiz_publish_video_now.ps1 -Video "marketing_assets\video_drop\your-video.mp4" -PublishNow
```

Only after reviewing the media path, upload it:

```bash
python scripts/postiz_kraitos_operator.py --upload-media kraitos-launch-short --upload
```

The upload response is appended to `media_upload_log.json` and prints the `--placeholder` arguments needed for the demo post.

Only after reviewing the preview, schedule with:

```bash
python scripts/postiz_kraitos_operator.py --schedule
```

PowerShell equivalent:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --schedule
```

The script refuses to schedule while placeholders remain unresolved and appends successful API responses to `schedule_log.json`.
