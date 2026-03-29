# EmploAI Mobile App Client

Expo/React Native client for the VPS-hosted `app` channel.

Current state:
- Expo Router screens for Pair, Chat, Sessions, Jobs, and Settings
- Android package id `com.emploai.app`
- EAS build profiles: development, preview, production
- secure local storage for backend URL and device token
- live chat WebSocket client
- live voice capture client with chunk upload and partial transcript display
- screenshot refresh and live VPS screen feed
- attachment upload hooks for camera, gallery, and documents

Important packaging rule:
- do not ship this app with `127.0.0.1` as the default backend
- the packaged app should point to a real VPS URL entered by the user or injected through `EXPO_PUBLIC_EMPLOAI_APP_URL`

First Android build path:
1. Install dependencies in `mobile_app/client`.
2. Log in to Expo/EAS.
3. Build an internal Android APK/AAB with `eas build -p android --profile preview`.
4. Install the build on a physical phone.
5. Open Pair or Settings, save the VPS HTTPS URL, then complete trusted-device pairing.
6. Test chat, voice, uploads, sessions, jobs, and the VPS screen feed against the real server.

Backend dependency:
- the app expects the server contract documented in `mobile_app/docs/VPS_BOT_HANDOFF.md`

Current limitation:
- no verified local typecheck/build result is committed from this workspace until `node_modules` is installed
