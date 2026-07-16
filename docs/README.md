# EmploAI Docs

EmploAI is currently a local-first desktop app. The desktop UI and local runtime are the product path; cloud/mobile and Telegram paths are preserved for future or legacy use, but they are not the default onboarding flow.

## Start Here

- [../README.md](../README.md) - quick start and current product summary
- [running_desktop_and_system.md](running_desktop_and_system.md) - complete setup, launch, runtime, Jarvis, Fleet, testing, and recovery command runbook
- [repository_map.md](repository_map.md) - current folder map and legacy naming notes
- [local_artifacts.md](local_artifacts.md) - ignored runtime folders, caches, and generated local state
- [product/main_vision.md](product/main_vision.md) - fleet-scale product north star
- [product/fleet_system_details.md](product/fleet_system_details.md) - practical Fleet behavior spec
- [yggdrasil_fleet_transport.md](yggdrasil_fleet_transport.md) - direct paired-computer Fleet connections without an EmploAI cloud backend
- [android_yggdrasil_mobile_pairing.md](android_yggdrasil_mobile_pairing.md) - future Android mobile pairing without EmploAI cloud
- [hermes_local_first_features.md](hermes_local_first_features.md) - Hermes features worth carrying into EmploAI

## Main Runtime Areas

- `desktop_app/` - Electron shell and desktop renderer
- `app_backend/` - current local app backend and desktop app API
- `desktop_runtime/` - local runtime launcher, setup state, voice helpers, Fleet commands
- `local_agent_runtime/` - browser/desktop automation tools, scheduler, legacy SingleAgent runtime
- `runtime_context/` - bundled prompt/context markdown copied into local runtime homes
- `runtime_support/` - hooks, security, UI formatting, analytics, and system info helpers
- `shared/` - agent loop, providers, memory, local policy, Fleet transport
- `scripts/desktop/` - setup/start scripts for contributors
- `docs/product/` - product vision/specs that inform current Fleet and local-first work

## Legacy Or Preserved Areas

- `mobile_app/client/` - preserved mobile client, disabled by default
- `mobile_app/docs/` - archived mobile/cloud design notes
- `mobile_app/backend/` - compatibility shim for old backend imports
- `deploy/windows/` - legacy Windows packaging scripts and compatibility wrappers
- `deploy/legacy_vps/` - old VPS/control-plane deployment notes
- `telegram_bot/` - optional Telegram control surface
- `bot_core/` - compatibility shim for old runtime support imports
- `legacy_agent_orchestration/` - older unified/dual-agent experiments and web orchestrator
- `agent/` - compatibility shim for old orchestration imports
- `single_agent/` - compatibility shim for old local-agent imports
- `legacy_web_app/` - older standalone web prototype

Prefer updating this index when docs move, rather than letting old primary-path docs drift.
