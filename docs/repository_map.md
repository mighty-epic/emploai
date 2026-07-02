# Repository Map

This repo is in the middle of a local-first desktop cleanup. Some package names still reflect the older mobile/cloud/Telegram architecture, so this map separates the current product path from preserved legacy paths.

## Current Product Path

| Path | Purpose | Notes |
| --- | --- | --- |
| `desktop_app/` | Electron desktop shell and Expo web renderer | Main UI for chat, Jarvis, settings, automations, Fleet, and local credentials. |
| `app_backend/` | Local app backend and disabled remote-control backend | This is the backend Electron starts in local desktop mode. |
| `desktop_runtime/` | Local runtime launcher, setup state, voice-pack helpers, Fleet helper commands | Prefer `python -m desktop_runtime.backend` for development/runtime commands. |
| `local_agent_runtime/` | Browser/desktop automation tools, scheduler, extension bridge, legacy SingleAgent runtime | Prefer `local_agent_runtime.*` imports in new code. |
| `runtime_context/` | Bundled prompt/context markdown copied into runtime homes | Current home for `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, and related runtime context. |
| `runtime_support/` | Shared hooks, security, analytics, UI formatting, and system-info helpers | Prefer `runtime_support.*` imports in new code. |
| `shared/` | Agent loop, memory, provider registry, local policy, Fleet transport | Keep new shared runtime code here when it is not UI-specific. |
| `cli/` | Terminal UI and command-mode agent tooling | Still useful for local development and agent debugging. |
| `scripts/desktop/` | Contributor setup and launch scripts | Prefer adding desktop startup helpers here instead of scattering root scripts. |
| `docs/product/` | Product vision and Fleet behavior specs | Keep product-shaping docs here instead of the repo root. |

## Preserved Or Legacy Paths

| Path | Purpose | Cleanup Direction |
| --- | --- | --- |
| `mobile_app/client/` | Preserved mobile client | Disabled by default. Keep compiling until mobile is intentionally removed or reconnected. |
| `mobile_app/docs/` | Archived mobile/cloud design notes | The `LEGACY_*.md` names are intentional so they are not mistaken for the current local-first architecture. |
| `mobile_app/backend/` | Compatibility shim for the old backend package path | Keep until older branches/docs no longer reference `mobile_app.backend`. New code should import `app_backend`. |
| `deploy/windows/` | Legacy Windows packaging scripts and compatibility wrappers | Runtime modules moved to `desktop_runtime/`; old `deploy.windows.*` imports are wrappers. MSI/package publishing is disabled for the current desktop-direct workflow. |
| `deploy/legacy_vps/` | Older VPS/control-plane deployment docs/scripts | Preserve for reference; do not make it part of normal local startup. |
| `telegram_bot/` | Optional Telegram control surface | Keep tokens local only. New desktop UI work should not be added here. |
| `single_agent/` | Compatibility shim for the old local-agent package path | Active code now lives in `local_agent_runtime/`. Keep until older branches/docs no longer reference `single_agent.*`. |
| `legacy_web_app/` | Older local web UI prototype | Do not use for new desktop app work. Generated screenshots should stay untracked under ignored runtime folders. |
| `legacy_agent_orchestration/` | Older unified/dual-agent experiments and legacy web orchestrator | Treat as preserved reference/test code. New runtime work should use `shared/`, `app_backend/`, or `local_agent_runtime/`. |
| `docs/history/legacy_agent_context/` | Archived root `agent_data/` context from an older multi-agent workflow | Historical reference only. It is not loaded as current runtime context. |
| `agent/` | Compatibility shim for the old generic orchestration package path | Active legacy code now lives in `legacy_agent_orchestration/`. |
| `bot_core/` | Compatibility shim for the old runtime-support package path | Active support helpers now live in `runtime_support/`. |

## Naming Cleanup Rules

- Import-heavy package moves should include a compatibility wrapper and targeted tests.
- When a legacy path is still imported by current runtime/tests, document it here and add a compatibility wrapper before moving it.
- Runtime output, screenshots, analytics, local memory, voice packs, `.env` files, and packaged app artifacts should remain untracked.
- See [local_artifacts.md](local_artifacts.md) for the ignored root-level runtime folders and scratch files.
- The root `config.json` is a checked-in local-first default. User-specific runtime config is written under `EMPLOAI_HOME` or the default runtime home.
- Keep bundled runtime prompt/context files in `runtime_context/`; keep root `agent_data/` for ignored local notes only.
- New startup scripts belong in `scripts/desktop/`; thin root wrappers are okay when they improve first-run ergonomics.
- Product/status docs should live under `docs/`, with current product specs under `docs/product/` and historical handoffs under `docs/history/`.
