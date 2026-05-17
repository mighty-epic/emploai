# Windows Desktop Release

This release path builds the desktop-first Windows app:

- `EmploAI.msi` - per-user Windows installer with upgrade support.
- `dist\desktop\EmploAI-win32-x64\EmploAI.exe` - packaged Electron app produced before MSI wrapping.
- `dist\EmploAIBackend\EmploAIBackend.exe` - bundled Python backend helper/runtime used by the Electron app.

The MSI installs the Electron desktop UI. It is no longer a console-only beta flow.

## Optional voice packs

The MSI now exposes optional feature selection for local voice packs:

- English voice pack
- Hebrew voice pack

Users can choose:

- English only
- Hebrew only
- both
- neither

The installer records those choices and now tries to install the requested packs during setup through the packaged backend helper. If a voice-pack download fails, the MSI still completes and the desktop setup panel shows the pack as requested-but-missing so it can be retried later.

If the user skips a pack during MSI, they can still install it later from the desktop app setup/settings panel. Installed packs can also be deleted from that same UI.

English is intentionally no longer bundled by default in the build. The build script now expects voice assets to be optional downloads unless you explicitly pass:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1 -BundleEnglishVoicePack
```

## Beta tester experience

1. Download `EmploAI.msi` from the latest GitHub release.
2. Run the installer.
3. Choose the optional English/Hebrew voice packs you want in the MSI feature tree.
4. Keep `Launch EmploAI now` checked on the installer finish page, or launch `EmploAI` later from the Start Menu.
5. Complete setup in the desktop app if required.
6. Start the app. Requested packs should already be ready unless setup-time download failed.
7. The local runtime starts from the desktop app and serves the same app API used by local development.

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
- `voice_packs\` for managed downloadable packs such as Hebrew local voice

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

If you also want to publish the pass-3 Hebrew runtime as the download target used by MSI-time install:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1 -IncludeHebrewVoicePackArchive -HebrewVoicePackSourceDir "C:\path\to\hebrew-whisper-small-pass3-knesset-runtime-ready"
```

The build machine must have:

- Node/npm available for the Expo web export and Electron packaging.
- Python capable of installing the project dependencies used by PyInstaller analysis.
- Tesseract OCR 5.5.2 installed or `EMPLOAI_TESSERACT_ROOT` pointing to a matching bundle.
- Network access the first time Whisper/Tesseract/WiX assets must be prepared.

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
- `dependency_status.voice.ok` is true.
- Voice recording reaches `/ws/app/voice` and returns transcript events.
- MSI-selected voice packs are shown correctly in desktop setup and can be installed/removed there.
- Switching English/Hebrew from the conversation voice panel changes the actual backend engine and survives restart.
- Sending text and finalized voice transcripts uses the same shared session.
- Closing the app respects `channels.desktop.keep_runtime_on_app_close`.

## Publishing the Hebrew pack

The Windows release now expects a downloadable pass-3 Hebrew archive. By default, the packaged backend derives the archive URL from `deploy/windows/release_info.json` using:

- `github_repo`
- `hebrew_voice_pack_asset`
- `hebrew_voice_pack_release_tag` (or the main `release_tag`)

So the release process should upload the Hebrew archive to the same GitHub release as the MSI.

Prepared helper:

```powershell
python .\scripts\publish_hebrew_voice_pack.py --repo-id your-org/hebrew-whisper-small-continue-public-v1
```

The desktop backend can source Hebrew from:

- `EMPLO_APP_STT_HEBREW_MODEL_REPO`
- `EMPLOAI_HEBREW_VOICE_PACK_ARCHIVE_URL`
- `EMPLOAI_HEBREW_VOICE_PACK_SOURCE_DIR`

For release builds intended for external users, prefer the archive URL / GitHub release asset path so the MSI and desktop setup panel both install the same pass-3 runtime-ready pack.

## Updates

The installer path is designed for upgrades:

- MSI upgrades replace the installed app in place.
- The desktop app can check GitHub Releases for a newer MSI.
- If an update is found, the app can download, install, and restart into the updated build.

The preferred GitHub release asset is `EmploAI.msi`.

## Re-run setup

Setup is normally handled by the desktop UI. Advanced users can also run backend setup helpers directly from a development checkout or packaged backend when needed.
