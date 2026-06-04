# Windows Desktop Release

This release path builds the desktop-first Windows app:

- `EmploAI.msi` - per-user Windows installer with upgrade support.
- `dist\desktop\EmploAI-win32-x64\EmploAI.exe` - packaged Electron app produced before MSI wrapping.
- `dist\EmploAIBackend\EmploAIBackend.exe` - bundled Python backend helper/runtime used by the Electron app.

The MSI installs the Electron desktop UI. It is no longer a console-only beta flow.

## Optional voice packs

The MSI now installs only the core desktop app and packaged backend.

- No English voice pack is bundled in the MSI.
- No Hebrew voice pack is bundled in the MSI.
- The installer does not download voice packs during setup.

Voice is now fully app-driven after install:

- install English from the desktop setup/settings panel
- install Hebrew from the desktop setup/settings panel
- remove either pack from the same UI
- switch the default engine from the same UI

Both voice packs are expected to come from pinned Hugging Face sources configured for the release.

## Beta tester experience

1. Download `EmploAI.msi` from the latest GitHub release.
2. Run the installer.
3. Keep `Launch EmploAI now` checked on the installer finish page, or launch `EmploAI` later from the Start Menu.
4. Complete setup in the desktop app if required.
5. If you want local voice, install English or Hebrew from the app.
6. The local runtime starts from the desktop app and serves the same app API used by local development.

Writable runtime files are stored under:

```text
%LOCALAPPDATA%\EmploAI
```

That folder contains:

- `.env`
- `.env.example`
- `config.json`
- `memory\`
- `logs\`
- `browser_extension\`
- `voice_packs\` for managed downloadable English/Hebrew local voice packs

## Architecture

The desktop app is an Electron shell around the exported Expo web client.

Build artifacts are assembled as follows:

1. `npm --prefix mobile_app/client run export:web` writes the renderer to `mobile_app/client/dist`.
2. PyInstaller builds `deploy/windows/release_backend.py` into `dist\EmploAIBackend\EmploAIBackend.exe`.
3. The build copies the renderer into `desktop_app\renderer`.
4. The build copies the backend bundle into `desktop_app\backend`.
5. `electron-packager` builds `dist\desktop\EmploAI-win32-x64`.
6. WiX wraps that packaged Electron app into `dist\EmploAI.msi`.

Electron development mode and packaged mode intentionally differ only in where they load artifacts from:

- Development Electron uses `mobile_app/client/dist/index.html` and `python -m deploy.windows.release_backend`.
- Packaged Electron uses `renderer/index.html` and `backend/EmploAIBackend.exe` from the installed app directory.

The app functionality should be identical across both paths.

## Voice path

The supported desktop voice path is:

```text
Electron renderer getUserMedia -> /ws/app/voice -> local backend voice runtime
```

The renderer sends `voice_start`, `voice_chunk`, `voice_commit`, and `voice_cancel` websocket events. The backend handles transcription and can route finalized voice transcripts into the shared chat/session path.

The local voice runtime now supports managed pack selection:

- `english_local`
- `hebrew_local`
- `none`

Hebrew uses the same UI/UX flow as English and is backed by the local Transformers runtime documented in [docs/hebrew_live_voice_path.md](../../docs/hebrew_live_voice_path.md). The desktop setup panel remains the source of truth for pack state, while the conversation/sidebar voice panel now switches the real backend engine instead of just flipping local UI state.

Do not add a separate Electron IPC voice bridge unless the renderer is changed to use it end-to-end. Keeping two voice paths caused drift between local and packaged behavior.

## Build locally

From the repo root on Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1
```

If you also want a portable zip fallback:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1 -IncludeZip
```

The build machine must have:

- Node/npm available for the Expo web export and Electron packaging.
- Python capable of installing the project dependencies used by PyInstaller analysis.
- Tesseract OCR 5.5.2 installed or `EMPLOAI_TESSERACT_ROOT` pointing to a matching bundle.
- Network access the first time Tesseract/WiX assets must be prepared.

## Release parity checklist

Before shipping an MSI, verify:

```powershell
npm --prefix mobile_app/client run typecheck
npm --prefix mobile_app/client run export:web
python -m pip install -r requirements.txt
python -m deploy.windows.release_backend status
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1
```

Then run the packaged app from:

```text
dist\desktop\EmploAI-win32-x64\EmploAI.exe
```

Check that:

- The desktop app opens without falling back to the "renderer not built" screen.
- Setup state loads inside the desktop UI.
- The local runtime reaches `/api/app/health` with `"ok": true`.
- Voice setup offers English/Hebrew install actions when no pack is installed.
- Voice recording reaches `/ws/app/voice` and returns transcript events after a pack is installed from the app.
- Switching English/Hebrew from the conversation voice panel changes the actual backend engine and survives restart.
- Sending text and finalized voice transcripts uses the same shared session.
- Closing the app respects `channels.desktop.keep_runtime_on_app_close`.

## Publishing the voice packs

The packaged app expects pinned Hugging Face sources for both optional voice packs.

English helpers:

```powershell
python .\scripts\prepare_english_voice_pack.py
python .\scripts\publish_english_voice_pack.py --repo-id your-org/english-whisper-cpp-desktop-pack
```

Hebrew helper:

```powershell
python .\scripts\publish_hebrew_voice_pack.py --repo-id your-org/hebrew-whisper-small-continue-public-v1
```

Release configuration lives in `deploy/windows/release_info.json`. For public builds, set:

- `english_voice_pack_repo`
- `english_voice_pack_revision`
- `hebrew_voice_pack_repo`
- `hebrew_voice_pack_revision`

Optional archive-url overrides are still supported, but the standard packaged flow is now Hugging Face first.

## Startup parity

Compare the packaged backend bootstrap timings against the validated local desktop baseline:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\measure_startup_parity.ps1
```

Target:

- packaged cold/warm startup should stay within `25%` or `2 seconds`, whichever is larger, of the local baseline on the same machine

## Updates

The installer path is designed for upgrades:

- MSI upgrades replace the installed app in place.
- The desktop app can check GitHub Releases for a newer MSI.
- If an update is found, the app can download, install, and restart into the updated build.

The preferred GitHub release asset is `EmploAI.msi`.

## Re-run setup

Setup is normally handled by the desktop UI. Advanced users can also run backend setup helpers directly from a development checkout or packaged backend when needed.
