# Windows Beta Release

This release path builds both:

- `EmploAI.exe` — portable console runtime
- `EmploAI.msi` — per-user Windows installer with upgrade support

## Beta tester experience

1. Download `EmploAI.msi` from the latest GitHub release.
2. Run the installer.
3. On first install, keep `Launch EmploAI now` checked on the installer finish page.
4. Launch `EmploAI` from the Start Menu any time after that.
4. A console window opens and stays open for logs.
5. On first run, EmploAI prompts for:
   - Telegram bot token
   - allowed Telegram user ID(s)
   - workspace root
   - optional provider API keys (OpenAI, Anthropic, Google, xAI, DeepSeek, OpenRouter)
6. The runtime files are stored under `%LOCALAPPDATA%\EmploAI`.

The executable is intentionally console-based. There is no separate desktop UI in this beta flow.

## Build locally

From the repo root on Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1
```

The build now bundles the native Tesseract OCR engine into the EXE/MSI. The build machine must either:

- have Tesseract installed on PATH, or
- set `EMPLOAI_TESSERACT_ROOT` to a folder containing `tesseract.exe` and `tessdata\`

That produces:

- `dist\EmploAI.exe` — portable fallback asset
- `dist\EmploAI.msi` — installer with in-place upgrade support

If you also want the extra zip fallback, build with:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1 -IncludeZip
```

That additionally produces:

- `dist\EmploAI-windows-beta.zip`

## Re-run setup

Testers can rerun the first-run wizard by launching:

```powershell
.\EmploAI.exe --setup
```

## Runtime location

The portable build keeps writable state in:

```text
%LOCALAPPDATA%\EmploAI
```

That folder contains:

- `.env`
- `.env.example`
- `config.json`
- `memory\`
- `logs\`

## Updates

The installer path is designed for upgrades:

- MSI upgrades replace the installed app in place
- the runtime checks GitHub Releases for a newer MSI on every startup
- if found, it offers to download, install, and restart automatically
- the updated MSI relaunches EmploAI after the upgrade completes

The preferred GitHub release asset is `EmploAI.msi`.
