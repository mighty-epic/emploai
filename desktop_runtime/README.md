# Desktop Runtime

`desktop_runtime` contains the local desktop launcher and setup/runtime helpers for the Electron app. This package is the current home for code that used to live under `deploy/windows/release_*`.

Use these entry points for local development:

```powershell
python -m desktop_runtime.backend status
python -m desktop_runtime.backend run-daemon
```

`scripts/desktop/start.ps1` and the root `npm start` script call into this package when launching the desktop app.

## Module Guide

| Module | Purpose |
| --- | --- |
| `backend.py` | Runtime command entry point and local backend process management. |
| `bootstrap.py` | First-run checks, dependency bootstrap, voice pack install helpers, cleanup helpers. |
| `config.py` | Local setup state, runtime-home paths, and persisted desktop configuration. |
| `launcher.py` | Small helpers for launching the packaged/local backend process. |
| `records.py` | Local runtime records used by the desktop setup/status flow. |
| `services.py` | Process/service discovery and duplicate-worker cleanup. |
| `update.py` | Preserved desktop update helpers. |
| `cloud.py` | Preserved remote/cloud wiring used only by legacy or explicitly enabled paths. |

Compatibility wrappers still exist in `deploy/windows/` so old commands keep working while new code imports `desktop_runtime.*`.
