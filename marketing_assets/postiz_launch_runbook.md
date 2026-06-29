# Kraitos Postiz Launch Runbook

Current status as of 2026-06-10:

- `kraitos.app` is live and ready for campaign traffic.
- The first seeded campaign wave is set for 2026-06-11 through 2026-06-19.
- The HyperFrames portrait short exists at `C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short\renders\kraitos_launch_short.mp4`.
- The latest upload dry-run found the MP4 at 2,808,419 bytes.
- The Postiz schedule dry-run passes when temporary integration and media placeholders are provided.
- Local Postiz was not reachable at `http://localhost:4007` during the latest audit.
- Docker Desktop is off-limits for now because the C: drive has been hovering near the 5 GB floor.

## Safety Rules

- Keep local free space above 5 GB at all times.
- Do not run Docker image pulls, Docker builds, local Postiz compose startup, npm installs, video renders, or other storage-heavy work while the machine is this close to the 5 GB floor.
- Use a remote or hosted Postiz base URL as the no-Docker workaround until local free space is cleaned up.
- Treat `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\postiz-app\docker-compose.yaml` as sensitive because it may contain local secrets.
- Do not paste API keys, OAuth secrets, or Postiz tokens into docs, commits, screenshots, or chat.
- Do not run `--upload` until the dry-run confirms the media path.
- Do not run `--schedule` until the full payload preview has been reviewed.
- Keep `marketing_assets\media_upload_log.json` empty until real API upload calls succeed.
- Keep `marketing_assets\schedule_log.json` empty until either Postiz scheduling succeeds or a manual fallback post is actually published.
- Keep `marketing_assets\measurement_log.json` empty until real post, site, project-page, or download metrics are observed.

## Key Paths

| Item | Path |
| --- | --- |
| EmploAI/Kraitos repo | `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai` |
| Postiz repo | `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\postiz-app` |
| Schedule seed | `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai\marketing_assets\postiz_schedule_seed.json` |
| Operator script | `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai\scripts\postiz_kraitos_operator.py` |
| PowerShell wrapper | `C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai\scripts\postiz_kraitos_operator.ps1` |
| HyperFrames project | `C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short` |
| Rendered MP4 | `C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short\renders\kraitos_launch_short.mp4` |

## Storage Gate

Current storage state:

| Drive | Free space | Decision |
| --- | --- | --- |
| C: | Recently observed between roughly 5.4 GB and 6.4 GB | Too close to the 5 GB floor for Docker/Postiz compose |

The operator now checks local free space before live `--upload` and `--schedule` actions. The default minimum is 5 GB and can be raised with:

```powershell
$env:KRAITOS_MIN_FREE_GB = "10"
```

For Docker-based Postiz, use a larger manual buffer. Do not start Docker compose unless C: has at least 15 GB free or the user explicitly approves a cleanup/storage plan.

Run this no-network preflight before any hosted Postiz action:

```powershell
Set-Location "C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai"
.\scripts\postiz_kraitos_operator.ps1 --preflight
```

The preflight checks campaign dates, selected payloads, media file presence, log counts, local free space, API-key presence, local/remote base URL mode, and unresolved placeholders without contacting Postiz. It proves local campaign readiness, not remote API reachability.

Use this no-network status report as the daily CMO dashboard:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --status
```

The status report summarizes Postiz readiness, schedule window, next payload, UTM link count, media availability, log counts, required docs, disk space, and manual fallback readiness.

Run this no-network consistency audit before scheduling, exporting, or manually publishing:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --audit-marketing
```

The audit checks seed labels against the calendar and manual publish pack, tracking URLs against the payloads and measurement plan, media paths, log shapes, required docs, schedule dates, and X character limits.

Run this safe external link audit before posts go live:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --audit-links
```

The link audit checks campaign outbound URLs with `HEAD` requests and uses a tiny `GET` fallback only when a server rejects `HEAD`. It does not download media or installers.

## Bring Postiz Online Without Docker

Use an already hosted Postiz instance or any remote Postiz server that exposes the public API. This avoids local Docker images and protects disk space.

```powershell
Set-Location "C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai"
$env:POSTIZ_BASE_URL = "https://your-postiz-host.example"
$env:POSTIZ_API_KEY = "<postiz-api-key>"
```

Then continue with `--list-integrations`, upload dry-run, media upload, campaign dry-run, and scheduling.

Before the first live API command against the remote instance, run:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --preflight
```

After integration IDs and media placeholders are known, export a local review bundle before scheduling:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --export-preview marketing_assets\generated\postiz_preview_export.json
```

The export refuses to write while unresolved `POSTIZ_*` placeholders remain. The `marketing_assets\generated\` folder is ignored by git and is the safe place for local review files that may contain real integration or media IDs.

## Bring Postiz Online With Local Docker

Only use this path after the storage gate is satisfied. Start Docker Desktop first, then start the production-style Postiz compose stack:

```powershell
Set-Location "C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\postiz-app"
docker compose -f docker-compose.yaml up -d
```

Confirm the app is reachable:

```powershell
Invoke-WebRequest "http://localhost:4007"
```

The operator default base URL is already `http://localhost:4007`.

## Configure Operator Environment

Run these from the EmploAI/Kraitos repo:

```powershell
Set-Location "C:\Users\Magsihim_AI\Documents\GitHub\powerful-project-collection\emploai"
$env:POSTIZ_BASE_URL = "http://localhost:4007"
$env:POSTIZ_API_KEY = "<postiz-api-key>"
```

List connected Postiz channels:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --list-integrations
```

Set the channel IDs returned by Postiz:

```powershell
$env:POSTIZ_X_INTEGRATION_ID = "<x-integration-id>"
$env:POSTIZ_LINKEDIN_INTEGRATION_ID = "<linkedin-integration-id>"
$env:POSTIZ_INSTAGRAM_INTEGRATION_ID = "<instagram-integration-id>"
$env:POSTIZ_FACEBOOK_INTEGRATION_ID = "<facebook-integration-id>"
$env:POSTIZ_TIKTOK_INTEGRATION_ID = "<tiktok-integration-id>"
$env:POSTIZ_YOUTUBE_INTEGRATION_ID = "<youtube-integration-id>"
```

## Upload HyperFrames Media

Preview the upload target first:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --upload-media kraitos-launch-short
```

Only after the preview points at the expected MP4, upload it:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --upload-media kraitos-launch-short --upload
```

Copy the returned media values into environment placeholders:

```powershell
$env:POSTIZ_KRAITOS_SHORT_MEDIA_ID = "<media-id>"
$env:POSTIZ_KRAITOS_SHORT_MEDIA_PATH = "<media-path>"
```

## Publish A Ready-Made Video Now

Use this path when you already have a finished vertical video and want to publish it immediately to Instagram, Facebook, TikTok, and YouTube Shorts.

The script does not copy the video into the repo. It uploads the file from its current path, reuses the returned Postiz media ID/path across the selected platforms, and records upload/post responses in the existing logs.

First preview:

```powershell
.\scripts\postiz_publish_video_now.ps1 `
  -Video "marketing_assets\video_drop\your-video.mp4"
```

Preview a custom caption. Use `{url}` where the tracked platform URL should appear:

```powershell
.\scripts\postiz_publish_video_now.ps1 `
  -Video "marketing_assets\video_drop\your-video.mp4" `
  -Caption "Kraitos can operate your desktop while you stay in control. {url}" `
  -Title "Kraitos: desktop AI operator"
```

Preview only selected platforms:

```powershell
.\scripts\postiz_publish_video_now.ps1 `
  -Video "marketing_assets\video_drop\your-video.mp4" `
  -Platform instagram,tiktok
```

Publish immediately only after the preview is correct and the environment has:

- `POSTIZ_BASE_URL`
- `POSTIZ_API_KEY`
- `POSTIZ_INSTAGRAM_INTEGRATION_ID`
- `POSTIZ_FACEBOOK_INTEGRATION_ID`
- `POSTIZ_TIKTOK_INTEGRATION_ID`
- `POSTIZ_YOUTUBE_INTEGRATION_ID`

```powershell
.\scripts\postiz_publish_video_now.ps1 `
  -Video "marketing_assets\video_drop\your-video.mp4" `
  -PublishNow
```

For raw operator access, the equivalent is:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --quick-video "marketing_assets\video_drop\your-video.mp4" --publish-now
```

## Preview And Schedule

Preview the complete campaign payload:

```powershell
.\scripts\postiz_kraitos_operator.ps1
```

Export the complete campaign payload for review:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --export-preview marketing_assets\generated\postiz_preview_export.json
```

Preview a single post if needed:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --label x-demo-follow-up
```

Preview only the vertical video wave if needed:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --label instagram-launch-reel `
  --label facebook-launch-reel `
  --label tiktok-launch-short `
  --label youtube-launch-short
```

Only after the preview is approved, schedule the campaign:

```powershell
.\scripts\postiz_kraitos_operator.ps1 --schedule
```

The script refuses to schedule while unresolved `POSTIZ_*` placeholders remain.

## Validation Evidence

Latest local checks completed without posting:

| Check | Result |
| --- | --- |
| Schedule JSON parse | Valid JSON, campaign `kraitos-rename-launch`, 11 payloads |
| Full schedule dry-run with temporary IDs | Passed; all 11 payloads previewed across Facebook, Instagram, LinkedIn, TikTok, X, and YouTube |
| Upload dry-run | Passed; MP4 found at 2,808,419 bytes |
| HyperFrames project check | Passed with 0 errors and 0 layout issues |
| Postiz local reachability | Failed; no usable response from `http://localhost:4007` |
| Docker readiness | Paused; local Docker is disallowed while free space is near the 5 GB floor |
| Storage guard | Added to live Postiz upload/schedule actions |
| No-network preflight | Added to validate campaign readiness before API calls |
| No-network status | Added to summarize launch readiness and next scheduled payload |
| No-network marketing audit | Passed with 11 payloads, 12 tracking URLs, and 9/9 required docs |
| Safe link audit | Passed with 12 campaign URLs returning 200 |
| Preview export | Added to produce a resolved local JSON review bundle before scheduling |
| Ready-made video quick publish | Added as dry-run-first wrapper: `scripts\postiz_publish_video_now.ps1` |
| X copy length check | Added to warn when X post items exceed 280 raw characters |
| UTM tracking | Added to seeded domain and project-page CTAs |
| Manual fallback | Added `kraitos_manual_publish_pack.md` for launch posts if Postiz is not connected in time |

## Next Operational Step

Use a remote or hosted Postiz base URL, then run `--list-integrations`. Local Docker should wait until there is at least 15 GB free or a cleanup plan is approved.

If Postiz is not connected before a scheduled slot, publish manually from `kraitos_manual_publish_pack.md`, then record the live post URL and published time for measurement.

After any post goes live, use `kraitos_engagement_playbook.md` for the first-hour reply workflow and response bank.

To record a manual fallback publication:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --record-published x-rename-thread `
  --published-url "https://x.com/<account>/status/<id>" `
  --published-at "2026-06-11T13:05:00Z"
```

Use the matching Postiz label from `postiz_schedule_seed.json`. This appends a manual entry to `schedule_log.json` and does not call Postiz.

To record a metrics snapshot after a post has live data:

```powershell
.\scripts\postiz_kraitos_operator.ps1 `
  --record-metrics x-rename-thread `
  --source x-analytics `
  --metric impressions=1200 `
  --metric clicks=37 `
  --metric replies=4
```

This appends to `measurement_log.json` and does not call Postiz or analytics APIs.
