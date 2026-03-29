# Open Questions for EmploAI Mobile App

## Answered
1. **Auth model**
   - Single private app per owner/instance, not multi-user SaaS.

2. **Phone platform priority**
   - Android first.

3. **Backend hosting target**
   - Reachable remotely early, connecting to EmploAI on the VPS.

4. **Notification expectations**
   - Push notifications can wait, but the architecture should leave room for them.

5. **Primary app features for v1**
   - Must-have on day one:
     - live chat
     - streamed tool logs
     - scheduled jobs view/interface
     - file upload
     - voice input
     - session history

6. **Runtime relationship**
   - Share the same underlying sessions/history as Telegram.
   - Handle presentation mismatch between Telegram and app at the rendering layer.

7. **Auth UX preference**
   - QR-based pairing preferred, but it must be secure.

8. **App identity**
   - Working name direction: `EmploAI App`.

## Still open
1. **Voice implementation detail**
   - Prioritize the smoothest and most instant-feeling path.
   - User is open to VPS-side transcription for v1 if that is the simpler, more reliable implementation.
   - Final decision still needed after implementation tradeoff check.

2. **Lazy app backend lifecycle**
   - User wants everything to start from `telegram_agent.py`, but is concerned about waste if the app backend runs constantly.
   - Need to decide between:
     - always-on lightweight embedded app backend, or
     - a smarter on-demand startup path with activity detection.
