# Kraitos Android Release Notes

Kraitos has two Android build lanes:

- Testing APK: `npm run build:android:apk`
- Local/LAN testing APK with Android cleartext enabled: `npm run build:android:local-apk`
- Google Play AAB: `npm run build:android:playstore`
- Submit latest Android build to Play: `npm run submit:android:playstore`

The Play package ID is `app.kraitos.mobile`. Do not change it after the first Google Play upload.

Production and Play builds keep Android cleartext traffic disabled. The `local-apk` profile sets
`KRAITOS_ALLOW_CLEARTEXT=1` only for device testing against local HTTP endpoints.

Before each Play upload:

1. Bump `expo.version`, `android.versionCode`, and `extra.mobileRelease.version` in `app.json`.
2. Bump `versionCode` and `versionName` in `android/app/build.gradle` when native Android is checked in.
3. Keep `extra.mobileRelease.desktopCompatibility` aligned with the desktop/fleet release line.
4. Build an APK first and smoke-test login, pairing, chat send/receive, verbose timeline, and settings.
5. Build the Play AAB with `npm run build:android:playstore`.
