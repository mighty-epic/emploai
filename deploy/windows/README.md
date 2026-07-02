# Windows Desktop Runtime And Legacy Packaging

The current development and user path is to run the desktop app directly:

```powershell
npm start
```

This folder now contains legacy Windows packaging scripts plus compatibility wrappers for runtime modules that moved to `desktop_runtime/`. MSI packaging is preserved for later but is not the default standalone desktop workflow right now.

Use `python -m desktop_runtime.backend <command>` for current local runtime helper commands. The old `python -m deploy.windows.release_backend <command>` path remains as a compatibility wrapper.

## Legacy MSI Release

The preserved release path builds the desktop-first Windows app:

- `EmploAI.msi` - per-user Windows installer with upgrade support.
- `dist\desktop\EmploAI-win32-x64\EmploAI.exe` - packaged Electron app produced before MSI wrapping.
- `dist\EmploAIBackend\EmploAIBackend.exe` - bundled Python backend helper/runtime used by the Electron app.

The MSI installs the Electron desktop UI. It is no longer a console-only beta flow.

## Optional voice packs

The MSI now installs only the core desktop app and packaged backend.

- No English voice pack is bundled in the MSI.
- No Hebrew voice pack is bundled in the MSI.
- No Jarvis TTS pack is bundled in the MSI.
- The installer does not download voice packs during setup.

Voice is now fully app-driven after install:

- install English or Hebrew voice input from the desktop setup/settings panel
- install Kokoro or Kyutai Jarvis speech output from the same panel
- remove any managed pack from the same UI
- switch the default voice input engine and Jarvis speech backend from the same UI

All managed voice packs are expected to come from pinned Hugging Face sources configured for the release.

## Beta tester experience

1. Download `EmploAI.msi` from the latest GitHub release.
2. Run the installer.
3. Keep `Launch EmploAI now` checked on the installer finish page, or launch `EmploAI` later from the Start Menu.
4. Complete setup in the desktop app if required.
5. If you want local voice input, install English or Hebrew from the app.
6. If you want local Jarvis speech output, install Kokoro or Kyutai from the app.
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
- `voice_packs\` for managed downloadable English/Hebrew input packs and Kokoro/Kyutai Jarvis speech packs

## Architecture

The desktop app is an Electron shell around the exported desktop Expo web renderer.

Build artifacts are assembled as follows:

1. `npm --prefix desktop_app/renderer_client run export:web` writes the renderer to `desktop_app/renderer_client/dist`.
2. PyInstaller builds `desktop_runtime/backend.py` into `dist\EmploAIBackend\EmploAIBackend.exe`.
3. The build copies the renderer into `desktop_app\renderer`.
4. The build copies the backend bundle into `desktop_app\backend`.
5. `electron-packager` builds `dist\desktop\EmploAI-win32-x64`.
6. WiX wraps that packaged Electron app into `dist\EmploAI.msi`.

Electron development mode and packaged mode intentionally differ only in where they load artifacts from:

- Development Electron uses `desktop_app/renderer_client/dist/index.html` and `python -m desktop_runtime.backend`.
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

Jarvis mode speech output is selected separately from voice input. Managed TTS pack ids are:

- `kokoro_tts`
- `kyutai_clone_tts`

Kokoro is a runtime-ready ONNX pack. Kyutai/Pocket uses a prepared `.safetensors` voice state; depending on how the pack is prepared, Pocket may still resolve its base model weights from Kyutai/Hugging Face on first use.

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
npm --prefix desktop_app/renderer_client run typecheck
npm --prefix desktop_app/renderer_client run export:web
python -m pip install -r requirements.txt
python -m desktop_runtime.backend status
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
- Voice setup offers English/Hebrew input install actions and Kokoro/Kyutai Jarvis speech install actions when no pack is installed.
- Voice recording reaches `/ws/app/voice` and returns transcript events after a pack is installed from the app.
- Switching English/Hebrew from the conversation voice panel changes the actual backend engine and survives restart.
- Sending text and finalized voice transcripts uses the same shared session.
- Closing the app respects `channels.desktop.keep_runtime_on_app_close`.

## Publishing the voice packs

The packaged app expects pinned Hugging Face sources for optional input and speech packs.

English helpers:

```powershell
python .\scripts\prepare_english_voice_pack.py
python .\scripts\publish_english_voice_pack.py --repo-id your-org/english-whisper-cpp-desktop-pack
```

Hebrew helper:

```powershell
python .\scripts\publish_hebrew_voice_pack.py --repo-id your-org/hebrew-whisper-small-continue-public-v1
```

Kokoro TTS helpers:

```powershell
python .\scripts\prepare_kokoro_tts_pack.py
python .\scripts\publish_kokoro_tts_pack.py --repo-id your-org/emploai-kokoro-tts-pack
```

Kyutai/Pocket TTS helpers:

```powershell
python .\scripts\prepare_kyutai_tts_pack.py --voice-file C:\path\to\jarvis.safetensors
python .\scripts\publish_kyutai_tts_pack.py --repo-id your-org/emploai-kyutai-clone-tts-pack
```

If you only have an authorized audio prompt, prepare the Kyutai pack by exporting a voice state first:

```powershell
python .\scripts\prepare_kyutai_tts_pack.py --audio-prompt C:\path\to\voice.wav
```

Release configuration lives in `deploy/windows/release_info.json`. For public builds, set:

- `english_voice_pack_repo`
- `english_voice_pack_revision`
- `hebrew_voice_pack_repo`
- `hebrew_voice_pack_revision`
- `kokoro_tts_voice_pack_repo`
- `kokoro_tts_voice_pack_revision`
- `kyutai_tts_voice_pack_repo`
- `kyutai_tts_voice_pack_revision`

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
- The desktop app checks the configured VPS release manifest first, then falls back to GitHub Releases.
- If an update is found, the app can download, install, and restart into the updated build.

The default manifest URL is `https://api.kraitos.app/api/releases/desktop/windows/latest`.
The hosted installer asset is versioned as `EmploAI-<msi_version>.msi`. For backward compatibility with older beta clients, the release manifest keeps `assetName` as `EmploAI.msi` while `assetUrl` points at the versioned hosted installer.

### Publishing desktop updates

`build_beta_release.ps1` publishes the generated MSI to the Kraitos updater endpoint by default after a successful build:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_beta_release.ps1
```

For local-only smoke builds, pass `-SkipPublish`. For publish validation without uploading, use the publisher directly with `-DryRun`; it writes the exact manifest that will be served to clients and prints the MSI size/SHA256.

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_beta_release.ps1 -SkipPublish
powershell -ExecutionPolicy Bypass -File deploy\windows\publish_desktop_release.ps1 -DryRun
```

For the current updater path, publish to the Kraitos/VPS release directory:

```powershell
$env:EMPLOAI_RELEASE_SSH_HOST = "<server-host>"
$env:EMPLOAI_RELEASE_SSH_USER = "<ssh-user>"
$env:EMPLOAI_RELEASE_SSH_KEY = "<optional-private-key-path>"
powershell -ExecutionPolicy Bypass -File deploy\windows\publish_desktop_release.ps1 -Target Kraitos
```

If those environment variables are not set, the publisher falls back to an SSH config host named `kraitos-vps`. Override that fallback with `EMPLOAI_RELEASE_SSH_CONFIG_HOST` or `-KraitosSshConfigHost`.

The script uploads:

- `dist\EmploAI-<msi_version>.msi` to `<remote-data-dir>/desktop_windows_releases/EmploAI-<msi_version>.msi`
- `desktop_windows_release_manifest.json` to `<remote-data-dir>/desktop_windows_release_manifest.json`

The default remote data directory is `/var/lib/emploai-remote/data`. Override it with `EMPLOAI_RELEASE_REMOTE_DATA_DIR` or `-KraitosRemoteDataDir` if the VPS service uses a custom `EMPLOAI_HOME`/data path.

The script verifies both:

- `https://api.kraitos.app/api/releases/desktop/windows/latest`
- the versioned installer URL listed by the live manifest `assetUrl`

GitHub Releases are supported as a backup target:

```powershell
$env:GH_TOKEN = "<token-with-release-write-access>"
powershell -ExecutionPolicy Bypass -File deploy\windows\publish_desktop_release.ps1 -Target GitHub
```

Existing beta clients rely on the Kraitos manifest as the update source. A GitHub-only publish is not enough unless the live Kraitos manifest is also updated or unavailable, because current clients check the manifest first.

## Re-run setup

Setup is normally handled by the desktop UI. Advanced users can also run backend setup helpers directly from a development checkout or packaged backend when needed.
