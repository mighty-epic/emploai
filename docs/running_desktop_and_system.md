# Running the EmploAI Desktop and Local System

This is the operator runbook for getting EmploAI working from a fresh checkout. It covers the normal desktop launch, manual runtime commands, model providers, Jarvis voice packs, Fleet computer connections over Yggdrasil, diagnostics, tests, and common recovery steps.

EmploAI is local-first:

- The Electron desktop app is the primary interface.
- The Python app backend and agent runtime run on the same computer.
- EmploAI does not require an EmploAI account, hosted domain, VPS, or cloud backend.
- Chats, settings, memory, provider credentials, recovery data, and Fleet enrollment state stay on the local machine.
- A ChatGPT/Codex device sign-in is an optional local model-provider credential. It is not an EmploAI account.
- Other computers connect directly through the Yggdrasil overlay.

All commands below run from the repository root unless a section says otherwise.

## 1. Prerequisites

The supported development path is Windows 10/11 with PowerShell.

Install:

- Git
- A current Node.js LTS release with `npm` on `PATH`
- Python 3 with `pip` on `PATH`
- A microphone only if Jarvis voice input is needed
- Administrator permission only when installing or starting Yggdrasil

The launcher looks for Python in this order:

1. `EMPLOAI_DESKTOP_PYTHON`
2. `py -3`
3. `python`
4. `python3`

When more than one Python installation exists, select one explicitly before setup:

```powershell
$env:EMPLOAI_DESKTOP_PYTHON="C:\Path\To\python.exe"
```

Confirm the base tools:

```powershell
git --version
node --version
npm --version
python --version
```

If `python` is not the correct launcher on Windows, use:

```powershell
py -3 --version
```

## 2. Clone the Repository

```powershell
git clone https://github.com/mighty-epic/emploai.git
cd emploai
```

## 3. Fastest Complete Start

The normal first-run command is:

```powershell
npm start
```

It performs the complete development startup path:

1. Verifies `npm` and Python.
2. Installs missing Python packages from `requirements.txt`.
3. Installs Electron shell dependencies when missing.
4. Installs renderer dependencies when missing.
5. Exports the current renderer into `desktop_app/renderer_client/dist`.
6. Bootstraps Yggdrasil best-effort for Fleet.
7. Launches the Electron app.
8. Lets Electron start or attach to the local Python runtime.

Yggdrasil can trigger a Windows UAC prompt because it installs a service and virtual network adapter. For local Chat, Jarvis, and local Fleet workers without other computers, skip that optional step:

```powershell
npm start -- -SkipFleetBootstrap
```

## 4. Explicit First-Time Setup

To install dependencies and build without launching the app:

```powershell
npm run setup
```

Then launch with the existing renderer build:

```powershell
npm run start:fast
```

The setup script can be narrowed when needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\desktop\setup.ps1 -SkipPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\desktop\setup.ps1 -SkipRendererBuild
```

Use those flags only when the skipped dependency or build already exists.

## 5. Readiness Check

Check the machine without installing anything or opening Electron:

```powershell
npm run desktop:check
```

The check reports:

- detected Python runtime
- required core Python modules
- Electron shell dependencies
- renderer dependencies
- renderer export status

## 6. Everyday Launch Commands

### Normal launch

Installs missing dependencies, rebuilds the renderer, attempts Yggdrasil bootstrap, and starts Electron:

```powershell
npm start
```

### Fast relaunch

Reuses the existing renderer and skips Yggdrasil bootstrap:

```powershell
npm run start:fast
```

Use this after the renderer has already been exported and no renderer source changed.

### Launch without dependency installation

```powershell
npm start -- -NoInstall
```

This fails if required dependencies are missing.

### Launch without Yggdrasil setup

```powershell
npm start -- -SkipFleetBootstrap
```

### Windows batch launcher

```powershell
.\start-desktop.bat
```

## 7. Renderer Development

Install renderer dependencies:

```powershell
npm --prefix desktop_app/renderer_client install
```

Run the renderer development server:

```powershell
npm --prefix desktop_app/renderer_client start
```

The web development server does not provide the complete Electron preload bridge. Use the actual Electron app for final Chat, Jarvis, Fleet, Remote, Settings, menu, and exit-flow validation.

Type-check the renderer:

```powershell
npm run desktop:typecheck
```

Export a production renderer:

```powershell
npm run desktop:build-renderer
```

After changing renderer code, rebuild before using `start:fast`:

```powershell
npm run desktop:build-renderer
npm run start:fast
```

## 8. Manual Electron and Runtime Control

Normal users should use `npm start`. These commands are useful for diagnostics and development.

### Install shell dependencies

```powershell
npm --prefix desktop_app install
```

### Launch Electron only

The renderer must already be exported:

```powershell
npm --prefix desktop_app run start:electron
```

### Inspect bootstrap state

```powershell
python -m desktop_runtime.backend bootstrap
python -m desktop_runtime.backend setup-state
```

### Start the managed local runtime

```powershell
python -m desktop_runtime.backend start
```

### Check runtime status

```powershell
python -m desktop_runtime.backend status
```

### Stop the managed local runtime

```powershell
python -m desktop_runtime.backend stop
```

### Run the runtime daemon directly

This is primarily for debugging:

```powershell
python -m desktop_runtime.backend run-daemon
```

Optional explicit bind values:

```powershell
python -m desktop_runtime.backend run-daemon --host 127.0.0.1 --port 8787
```

## 9. Local Data and Configuration

The packaged Windows default is:

```text
%LOCALAPPDATA%\EmploAI
```

Development fallback state is generally stored under:

```text
~/.agentshell
```

Override the runtime home before starting the app:

```powershell
$env:EMPLOAI_HOME="C:\Path\To\EmploAIData"
npm start
```

Use desktop Settings for normal provider, workspace, memory, voice, Telegram, and recovery configuration.

An optional `.env` can be created for advanced or legacy configuration:

```powershell
Copy-Item .env.example .env
```

Never commit `.env` or files from the runtime home.

## 10. Model Providers

At least one usable model provider is required for agent responses. Configure it in desktop Settings.

Supported API-key lanes include:

- OpenAI API
- Anthropic
- Google Gemini
- xAI
- DeepSeek
- NVIDIA NIM
- OpenRouter

The optional ChatGPT/Codex subscription lane uses a local device sign-in. It is separate from OpenAI API keys and is not an EmploAI account.

Check its local status from the command line:

```powershell
python -m desktop_runtime.backend codex-auth-status
```

Start and poll the device flow only when diagnosing Settings:

```powershell
python -m desktop_runtime.backend codex-auth-start-device
python -m desktop_runtime.backend codex-auth-poll-device
```

Remove locally stored ChatGPT/Codex credentials:

```powershell
python -m desktop_runtime.backend codex-auth-logout
```

Provider credentials and device tokens must remain local.

## 11. Jarvis Voice

Grant microphone permission to Electron/EmploAI in Windows before using Jarvis.

Voice packs are normally installed from Settings. Equivalent CLI commands are:

```powershell
python -m desktop_runtime.backend install-voice-pack --pack english_local --stream-progress
python -m desktop_runtime.backend install-voice-pack --pack hebrew_local --stream-progress
python -m desktop_runtime.backend install-voice-pack --pack kokoro_tts --stream-progress
python -m desktop_runtime.backend install-voice-pack --pack kyutai_clone_tts --stream-progress
```

Select a local speech-to-text engine:

```powershell
python -m desktop_runtime.backend set-voice-engine --engine english_local
python -m desktop_runtime.backend set-voice-engine --engine hebrew_local
python -m desktop_runtime.backend set-voice-engine --engine none
```

Remove a managed voice pack:

```powershell
python -m desktop_runtime.backend remove-voice-pack --pack english_local
```

Validate the bundled Hebrew runtime:

```powershell
python -m desktop_runtime.backend validate-hebrew-runtime
```

Voice models can be large. They belong in the local runtime home and are ignored by Git.

## 12. Fleet on the Same Computer

Start the normal app:

```powershell
npm start -- -SkipFleetBootstrap
```

Open Fleet and create a local worker. No network overlay is required for workers that run on the manager computer.

## 13. Fleet Between Computers with Yggdrasil

Yggdrasil connects EmploAI computers directly without an account or EmploAI cloud backend. Pairing a computer does not create a worker and does not copy chats, agents, settings, files, or provider state.

Run the setup on both computers from their EmploAI checkout:

```powershell
npm run setup
npm run fleet:yggdrasil:bootstrap
npm run fleet:yggdrasil:status
```

Windows may request administrator permission during installation.

### Manager computer

Create a short-lived pairing token for one additional computer:

```powershell
npm run fleet:yggdrasil:pair
```

The command prints an `emploai-yggdrasil-v1...` token and configures the manager runtime for Yggdrasil reachability. Create a separate single-use code from this same manager for every additional computer.

Optional token controls:

```powershell
python -m desktop_runtime.backend fleet-yggdrasil-pair --display-name "Office computer" --expires-in-seconds 1800 --configure-manager-bind
```

### Other computer

Use the token printed by the manager:

```powershell
npm run fleet:yggdrasil:join -- <pairing-token>
```

The join command saves the durable computer connection, starts its paired-computer host, and registers that host to start invisibly at Windows sign-in. The host survives closing Electron. That computer keeps its own local manager and workers; the manager can send delegation messages only after the other computer reports and allows its connection permissions.

To save the connection without starting the relay immediately:

```powershell
python -m desktop_runtime.backend fleet-yggdrasil-join <pairing-token> --no-start-relay
```

Start the paired-computer relay manually:

```powershell
python -m desktop_runtime.backend run-remote-control-worker
```

Check or repair background-host persistence:

```powershell
npm run fleet:host:status
npm run fleet:host:start
npm run fleet:host:install
```

`fleet:host:start` repairs sign-in registration and starts the host immediately. `fleet:host:install` only repairs the next-sign-in registration.

The manager-triggered preview command captures on the paired computer and returns one bounded JPEG through Yggdrasil. A connected computer can still report **Screen unavailable** when Windows is locked or an RDP-only VPS has no rendered display. For unattended screenshots, configure a persistent interactive or virtual display through the VPS/virtualization environment; EmploAI never captures the Windows lock screen.

Recheck the overlay at any time:

```powershell
npm run fleet:yggdrasil:status
```

See [yggdrasil_fleet_transport.md](yggdrasil_fleet_transport.md) for transport details.

## 14. Optional Telegram Worker

Telegram is an optional legacy control surface, not part of the required desktop path.

Configure the Telegram bot token locally in Settings or `.env`, then run:

```powershell
python -m desktop_runtime.backend run-telegram-worker
```

An explicit runtime home can be supplied:

```powershell
python -m desktop_runtime.backend run-telegram-worker --home "C:\Path\To\EmploAIData"
```

## 15. Verification Commands

### Fast repository sanity suite

```powershell
python run_tests.py
```

### Desktop group

```powershell
python run_tests.py desktop
```

### Local-first and Yggdrasil group

```powershell
python run_tests.py local-first
```

### Full pytest suite

```powershell
python run_tests.py all
```

Equivalent direct command:

```powershell
python -m pytest -q
```

### Pass arguments to pytest

```powershell
python run_tests.py desktop -- -vv
```

### Renderer checks

```powershell
npm run desktop:typecheck
npm run desktop:build-renderer
```

### Electron JavaScript syntax

```powershell
node --check desktop_app/main.js
node --check desktop_app/preload.js
node --check desktop_app/remote_control_services.js
node --check desktop_app/session_store.js
```

### Desktop Chat smoke test

Run the desktop/runtime first, then in another PowerShell window:

```powershell
npm run desktop:smoke-chat
```

### Release hygiene

```powershell
npm --prefix desktop_app run release:check
```

## 16. Common Recovery Commands

### The app shows an older UI after source changes

`start:fast` reuses the last renderer export. Rebuild and relaunch:

```powershell
npm run desktop:build-renderer
npm run start:fast
```

### The local runtime is offline

```powershell
python -m desktop_runtime.backend status
python -m desktop_runtime.backend stop
python -m desktop_runtime.backend start
```

Then relaunch Electron:

```powershell
npm run start:fast
```

### Dependencies are missing or inconsistent

Run the supported setup again without deleting local state:

```powershell
npm run setup
```

### Python is detected from the wrong installation

```powershell
$env:EMPLOAI_DESKTOP_PYTHON="C:\Path\To\python.exe"
npm run desktop:check
npm start
```

### Yggdrasil is unavailable

```powershell
npm run fleet:yggdrasil:bootstrap
npm run fleet:yggdrasil:status
```

If installation is blocked, reopen PowerShell with administrator permission and rerun the bootstrap.

### Local Chat works but model calls fail

Open Settings and verify that the selected provider has a valid local API key or local ChatGPT/Codex credential. A provider quota or authentication failure is not a failure of the file, terminal, browser, or desktop tools.

## 17. What Must Not Be Committed

Keep these local:

- `.env` and `.env.*`
- API keys, bot tokens, OAuth/device tokens, and private keys
- `%LOCALAPPDATA%\EmploAI` or a custom `EMPLOAI_HOME`
- `.agentshell` runtime state
- chats, memory, recovery records, logs, screenshots, and analytics
- `node_modules`, Expo caches, renderer exports, packaged builds, and test output
- downloaded voice packs and model weights
- Yggdrasil enrollment/session files
- generated marketing media

Use `git status --short` before every commit. If a credential has ever been pushed, revoke or rotate it; deleting it from the latest commit does not remove it from Git history.

## Command Summary

```powershell
# First run
npm start

# Explicit setup and fast launch
npm run setup
npm run start:fast

# Readiness
npm run desktop:check

# Rebuild renderer
npm run desktop:build-renderer

# Runtime status and recovery
python -m desktop_runtime.backend status
python -m desktop_runtime.backend stop
python -m desktop_runtime.backend start

# Fleet over Yggdrasil
npm run fleet:yggdrasil:bootstrap
npm run fleet:yggdrasil:status
npm run fleet:yggdrasil:pair
npm run fleet:yggdrasil:join -- <pairing-token>
npm run fleet:host:status
npm run fleet:host:start

# Checks
python run_tests.py
npm run desktop:typecheck
npm run desktop:build-renderer
```
