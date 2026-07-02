# Preserved Kraitos Mobile App Client

Expo/React Native client for the preserved Kraitos remote-control product.

Status: preserved, but not part of the current default EmploAI startup path.
The desktop app is local-first and starts without account login, cloud backend,
VPS, or mobile pairing. This mobile client remains here so the remote companion
can be reconnected later without losing the existing implementation.

Current code-backed facts:
- Expo package name: `kraitos-mobile`
- app display name: `Kraitos`
- Android package id: `app.kraitos.mobile`
- default release API base: `https://api.kraitos.app`
- EAS profiles: development, preview, local APK, Play Store, and production
- production and Play builds keep Android cleartext traffic disabled
- remote-cloud mobile v1 is text-first; mobile voice capture is intentionally disabled
- file intake supports camera, gallery/media selection, and document picking

Preserved mobile screens/routes:
- account sign-in and signup
- desktop pairing
- chat and shared timeline
- fleet dashboard
- cron/automations
- agent settings and diagnostics
- app settings and recovery controls

Build and verification when intentionally working on mobile:
1. Install dependencies in `mobile_app/client`.
2. Run `npm run typecheck`.
3. Log in to Expo/EAS.
4. Build with one of the package scripts, for example `npm run build:android:preview`
   or `npm run build:android:playstore`.
5. Smoke test login, pairing, chat, timeline updates, fleet/automation screens,
   attachments, and settings against a deliberately configured control plane.

Legacy architecture docs:
- `mobile_app/docs/LEGACY_REMOTE_ARCHITECTURE.md`
- `mobile_app/docs/LEGACY_REMOTE_CONTROL_PLANE.md`
- `mobile_app/client/PLAYSTORE.md`

Historical note:
- `mobile_app/docs/LEGACY_VPS_BOT_HANDOFF.md` is an archive marker, not the
  current product contract.
