# EmploAI Marketing Assets Directory

This folder contains marketing plans, copywriting, and visual storyboard assets for launching EmploAI.

## File Registry

1. **[social_posts.md](social_posts.md)**:
   - Finalized Twitter/X Thread copy (5 parts).
   - LinkedIn announcement copy.
   - Comprehensive Reddit post detailed for r/LocalLLaMA & r/selfhosted.

2. **[video_script.md](video_script.md)**:
   - Visual demo storyboard & timing sheets (20-second landscape video).
   - Optional Voiceover / TTS script.

---

## Rendering the Video Demo

We have pre-configured a Hyperframes composition project inside the local studio: `packages/studio/data/projects/edit-project`.

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
   bun run --cwd packages/cli dev render <hyperframes-workspace>\packages\studio\data\projects\edit-project\index.html -o emploai_demo.mp4
   ```
