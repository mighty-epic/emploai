# Windows Beta Release

This release path builds a portable Windows console app for EmploAI beta testers.

## Beta tester experience

1. Download the latest release zip from GitHub.
2. Unzip it anywhere.
3. Run `EmploAI.exe`.
4. A console window opens and stays open for logs.
5. On first run, EmploAI prompts for:
   - Telegram bot token
   - allowed Telegram user ID(s)
   - workspace root
   - optional OpenAI / Anthropic API keys
6. The runtime files are stored under `%LOCALAPPDATA%\EmploAI`.

The executable is intentionally console-based. There is no separate desktop UI in this beta flow.

## Build locally

From the repo root on Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\build_beta_release.ps1
```

That produces:

- `dist\EmploAI\` — portable app folder
- `dist\EmploAI-windows-beta.zip` — release asset to upload to GitHub

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

## Current scope

This is a portable beta release path, not a full Windows installer yet. The GitHub release zip is the intended distribution format for now.
