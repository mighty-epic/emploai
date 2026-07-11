# EmploAI

EmploAI is a local-first desktop agent for controlling your own computer with an AI assistant. The desktop app is the main UI: chat, Jarvis voice, files, terminal commands, browser automation, desktop control, automations, memory, and Fleet workers all run from the user's machine.

The current product direction is standalone desktop:

- no EmploAI account is required
- no EmploAI VPS, hosted domain, or cloud backend is required
- no mobile app pairing or hosted account routes are included in the active backend
- app state, chats, memory, settings, API keys, and local auth files stay on the user's computer
- Fleet workers pair directly through Yggdrasil and do not use an EmploAI cloud account

## What It Does

EmploAI can:

- chat through the desktop UI
- use Jarvis voice input/output paths
- read, write, edit, and search workspace files
- run terminal commands in the selected workspace
- browse the web and inspect browser state
- control desktop apps through screenshots, OCR, mouse, keyboard, and window tools
- run scheduled automations through the same local runtime
- keep local memory and recoverable workspace state
- create local Fleet workers and connect workers on other machines through the Yggdrasil overlay
- use model providers through local API keys or a local ChatGPT subscription sign-in

## Quick Start

From the repo root:

```powershell
npm start
```

`npm start` is the normal desktop startup command. On first run it installs missing desktop JavaScript dependencies, installs missing core Python backend packages from `requirements.txt`, builds the renderer, starts the Electron desktop shell, and lets Electron start or attach to the local Python runtime.

For a fuller setup pass that also installs Python dependencies:

```powershell
npm run setup
```

To check readiness without opening the app:

```powershell
npm run desktop:check
```

That preflight reports the Python runtime, core backend Python packages,
desktop JavaScript dependencies, and renderer build status. It does not install
anything; run `npm start` to let startup repair missing first-run dependencies.

You can also double-click or run:

```powershell
.\start-desktop.bat
```

The default start command runs the Yggdrasil Fleet bootstrap best-effort. Windows may ask for permission because Yggdrasil installs a service and virtual network adapter. If you are only using local chat and local workers, you can skip it:

```powershell
npm start -- -SkipFleetBootstrap
```

For a faster restart after the renderer has already been built:

```powershell
npm run start:fast
```

## Local Data

EmploAI writes runtime state to a local app home. You can override it with:

```powershell
$env:EMPLOAI_HOME="C:\Path\To\EmploAIData"
```

When packaged/frozen on Windows, the default runtime home is under:

```text
%LOCALAPPDATA%\EmploAI
```

In development contexts without `EMPLOAI_HOME`, shared fallback state is under:

```text
~/.agentshell
```

Important local files include chats, memory, logs, workspace recovery data, provider keys, Telegram bot settings, Fleet enrollment state, and ChatGPT subscription auth. These should not be committed. `.env`, `.env.*`, local logs, runtime data, voice packs, build outputs, and desktop packaged artifacts are ignored by git.

The root `config.json` is only the checked-in local-first default. The desktop runtime writes user-specific config under `EMPLOAI_HOME` or the default runtime home.

## Model Providers

Provider credentials are local to the machine.

API-key providers:

- OpenAI
- Anthropic
- Google Gemini
- xAI
- DeepSeek
- NVIDIA NIM
- OpenRouter

ChatGPT subscription provider:

- sign in from desktop Settings
- stored locally as ChatGPT/Codex auth
- exposed as separate model choices such as `chatgpt/gpt-5.5`, `chatgpt/gpt-5.4`, and `chatgpt/gpt-5.4-mini`

The subscription path is not a fallback for API keys. It is a separate provider lane. API-key models such as `gpt-5.5`, `gpt-5.4`, and `gpt-5.4-mini` remain under the normal OpenAI API provider.

API keys can be deleted from Settings because all credentials are stored locally.

## Fleet Workers

Fleet is still part of the local-first system.

Local workers can be created from the desktop Fleet UI.

Workers on other machines use Yggdrasil instead of an EmploAI VPS/domain:

```powershell
npm --prefix desktop_app run fleet:yggdrasil:bootstrap
npm --prefix desktop_app run fleet:yggdrasil:status
npm --prefix desktop_app run fleet:yggdrasil:pair
npm --prefix desktop_app run fleet:yggdrasil:join -- <pairing-token>
```

See [docs/yggdrasil_fleet_transport.md](docs/yggdrasil_fleet_transport.md) for the manager/worker flow.

## Repository Structure

```text
desktop_app/                 Electron desktop shell and React renderer
app_backend/                 Current local desktop backend and app API
desktop_runtime/             Local desktop runtime launcher, setup state, voice/Fleet helpers
deploy/windows/              Legacy Windows packaging scripts and compatibility wrappers
shared/                      Agent loop, memory, providers, local policy, Fleet transport
runtime_context/             Bundled prompt/context markdown copied into local runtime homes
runtime_support/             Shared hooks, security, UI formatting, system info helpers
cli/                         Terminal agent tooling and model registry
local_agent_runtime/         Browser tools, scheduler, legacy SingleAgent runtime pieces
legacy_agent_orchestration/  Older unified/dual-agent experiments and web orchestrator
telegram_bot/                Optional legacy Telegram control surface
mobile_app/client/           Preserved mobile client, currently disabled
mobile_app/docs/             Archived mobile/cloud design notes
mobile_app/backend/          Compatibility shim for old backend imports
legacy_web_app/              Older standalone web prototype
docs/history/legacy_agent_context/
                             Archived root agent context from the older multi-agent workflow
scripts/desktop/             Desktop setup/start scripts
docs/product/                Product vision and Fleet behavior specs
docs/                        Architecture notes and transport docs
tests/                       Python and renderer regression tests
```

See [docs/repository_map.md](docs/repository_map.md) for the current folder map and the legacy names that still need careful migration.

## Current Architecture

```text
Desktop UI
  -> Electron main process
  -> local Python runtime
  -> unified agent loop
     -> selected model provider
     -> local tool registry
     -> local tool executor
        -> files
        -> shell
        -> browser
        -> desktop control
        -> memory
        -> automations
        -> Fleet workers
```

The desktop app owns execution and durable state on the local machine. The hosted account, cloud backup, mobile relay, and phone-pairing implementations have been removed from the active product.

## Legacy And Disabled Paths

These folders are still present but are not the current default product path:

- `mobile_app/client/`: archived mobile client; it is not packaged or connected to the desktop product
- `mobile_app/docs/`: archived mobile/cloud design notes
- `mobile_app/backend/`: compatibility shim for older imports; backend code now lives in `app_backend/`
- `deploy/windows/`: older Windows packaging scripts plus compatibility wrappers for moved runtime modules
- `deploy/legacy_vps/`: older VPS deployment notes
- `telegram_bot/`: optional/legacy Telegram control surface
- `bot_core/`: compatibility shim for older imports; active support code now lives in `runtime_support/`
- `single_agent/`: compatibility shim for older imports; active code now lives in `local_agent_runtime/`
- `agent/`: compatibility shim for older imports; active legacy code now lives in `legacy_agent_orchestration/`
- `legacy_web_app/`: older standalone web prototype
- MSI packaging: disabled for now; use the desktop app directly

## Security Notes

- Never commit `.env`, API keys, Telegram bot tokens, OAuth tokens, or local runtime data.
- If a key or token was ever pushed to a public repo, rotate or revoke it even after removing it from the current files.
- Removing a secret from the latest commit does not remove it from public git history.
- Prefer Settings or local `.env` files for credentials.

## Verification

Useful checks while developing:

```powershell
python run_tests.py
npm run desktop:check
npm run desktop:typecheck
npm --prefix desktop_app/renderer_client run typecheck
npm --prefix mobile_app/client run typecheck
python -m pytest tests/test_model_registry_latest.py tests/test_desktop_runtime_config.py tests/test_desktop_model_providers.py
```

`python run_tests.py` runs the fast local desktop sanity group. Use `python run_tests.py all` for the full pytest suite, or named groups such as `desktop`, `local-first`, `legacy`, `brain`, and `integration`.
