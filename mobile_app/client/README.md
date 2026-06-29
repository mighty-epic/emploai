# Kraitos Mobile App Client

Expo/React Native client for the public Kraitos remote-control product.

The current mobile app is a remote companion to the desktop app. It signs into
the public control plane, pairs with one of the user's desktops, and sends chat
and control actions through that paired desktop. The desktop remains the
execution owner for local tools, files, browser/desktop automation, voice
runtime, and agent runs.

Current code-backed facts:
- Expo package name: `kraitos-mobile`
- app display name: `Kraitos`
- Android package id: `app.kraitos.mobile`
- default release API base: `https://api.kraitos.app`
- EAS profiles: development, preview, local APK, Play Store, and production
- production and Play builds keep Android cleartext traffic disabled
- remote-cloud mobile v1 is text-first; mobile voice capture is intentionally disabled
- file intake supports camera, gallery/media selection, and document picking

Primary mobile screens/routes:
- account sign-in and signup
- desktop pairing
- chat and shared timeline
- fleet dashboard
- cron/automations
- agent settings and diagnostics
- app settings and recovery controls

Build and verification:
1. Install dependencies in `mobile_app/client`.
2. Run `npm run typecheck`.
3. Log in to Expo/EAS.
4. Build with one of the package scripts, for example `npm run build:android:preview`
   or `npm run build:android:playstore`.
5. Smoke test login, pairing, chat, timeline updates, fleet/automation screens,
   attachments, and settings against the public control plane.

Current architecture docs:
- `mobile_app/docs/ARCHITECTURE.md`
- `mobile_app/docs/REMOTE_CONTROL_PLANE.md`
- `mobile_app/client/PLAYSTORE.md`

Historical note:
- `mobile_app/docs/VPS_BOT_HANDOFF.md` is now an archive marker, not the mobile
  product contract.
