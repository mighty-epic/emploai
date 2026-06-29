# Ready Video Drop

Drop finished vertical videos here only when local free space is safely above the 5 GB floor.

Files in this folder are ignored by git so large videos are not committed by accident. Publish a dropped video with:

```powershell
.\scripts\postiz_publish_video_now.ps1 -Video "marketing_assets\video_drop\your-video.mp4"
```

That command previews only. Add `-PublishNow` after Postiz is connected, the platform integration IDs are set, and the preview looks right.
