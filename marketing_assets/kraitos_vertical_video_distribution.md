# Kraitos Vertical Video Distribution

Current date: 2026-06-10

Short vertical video is the primary social surface for Kraitos. X and LinkedIn are useful for technical credibility, but Instagram Reels, Facebook Reels/Page, TikTok, and YouTube Shorts are the channels most likely to make the "desktop AI agent controls your computer" idea legible quickly.

## Priority Order

1. **TikTok**: fastest hook testing. Judge by completion, rewatches, comments, and saves before clicks.
2. **Instagram Reels**: best brand surface for the high-tech workstation/Jarvis feel.
3. **YouTube Shorts**: evergreen discovery. Every strong proof short should land here.
4. **Facebook Reels/Page**: broader automation audience and possible retargeting surface.
5. **X/LinkedIn**: supporting technical explanation and reply mining after video proves the hook.

## Initial Asset

Use the rendered portrait HyperFrames MP4 for the first vertical wave:

`C:\Users\Magsihim_AI\Downloads\hyperframes\projects\kraitos-launch-short\renders\kraitos_launch_short.mp4`

Do not render a new asset while C: drive free space is near the 5 GB floor. The next vertical asset should be the real-task proof demo from `kraitos_real_task_demo_brief.md`, but only after storage is cleaned up or a cloud render path is chosen.

## First Vertical Wave

Seeded in `postiz_schedule_seed.json`:

| Label | Channel | Time UTC | Asset | Goal |
| --- | --- | --- | --- | --- |
| `instagram-launch-reel` | Instagram | 2026-06-11 14:00 | Launch short | Make the brand visually understandable |
| `facebook-launch-reel` | Facebook | 2026-06-11 14:15 | Launch short | Broaden reach and test mainstream automation interest |
| `tiktok-launch-short` | TikTok | 2026-06-11 14:30 | Launch short | Test the hook quickly |
| `youtube-launch-short` | YouTube Shorts | 2026-06-11 14:45 | Launch short | Seed evergreen discovery |

## Postiz Placeholders Needed

Before live scheduling:

- `POSTIZ_INSTAGRAM_INTEGRATION_ID`
- `POSTIZ_FACEBOOK_INTEGRATION_ID`
- `POSTIZ_TIKTOK_INTEGRATION_ID`
- `POSTIZ_YOUTUBE_INTEGRATION_ID`
- `POSTIZ_KRAITOS_SHORT_MEDIA_ID`
- `POSTIZ_KRAITOS_SHORT_MEDIA_PATH`

Use `.\scripts\postiz_kraitos_operator.ps1 --list-integrations` after Postiz is connected, then upload the MP4 once with `--upload-media kraitos-launch-short --upload`.

## Ready-Made Video Drop

For finished videos that should go live immediately, use:

```powershell
.\scripts\postiz_publish_video_now.ps1 -Video "marketing_assets\video_drop\your-video.mp4"
```

That previews the upload/post plan without calling Postiz. To actually upload and publish now:

```powershell
.\scripts\postiz_publish_video_now.ps1 -Video "marketing_assets\video_drop\your-video.mp4" -PublishNow
```

The wrapper defaults to Instagram, Facebook, TikTok, and YouTube. Use `-Platform instagram,tiktok` to limit the post to selected platforms.

## Hook Ladder

Use these as future HyperFrames cuts or captions:

1. "This AI agent can operate your desktop, but you stay in control."
2. "Not a chatbot. A computer operator loop."
3. "Before it clicks, it observes."
4. "A useful agent leaves evidence after every step."
5. "Browser refs fail? Fall back to screenshots and OCR."
6. "Self-hosted computer-use automation should be inspectable."

## Measurement

For vertical video, prioritize:

- Views
- Completion rate
- Average view duration
- Rewatches
- Saves
- Shares
- Comments asking what it can do
- Profile visits
- Site sessions by `utm_source`
- MSI download clicks

If views are high and site sessions are low, the end card or caption CTA needs work. If completion is low, the first three seconds need a clearer live-computer hook. If comments ask whether it is real, the next asset must show a concrete operator task with evidence.
