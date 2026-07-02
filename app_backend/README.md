# Local App Backend

This package is the local backend used by the desktop app.

## Current Role

The desktop Electron shell starts or attaches to this backend through `desktop_runtime/backend.py`. It serves the local app API, websocket chat/voice routes, setup state, automations, session state, workspace operations, voice pack management, Fleet helpers, and preserved remote-control routes.

The backend server entry point is `local_runtime_server.py`. The old
`desktop_runtime.py` module remains only as a compatibility wrapper, because
the active desktop launcher package now lives at the top-level `desktop_runtime/`
folder.

Important local routes include:

- `/api/app/health`
- `/api/app/me`
- `/api/app/sessions`
- `/api/app/chat/send`
- `/api/app/automations`
- `/ws/app/chat`
- `/ws/app/voice`

## Legacy Remote-Control Role

Remote account, mobile pairing, and VPS control-plane code still live here because those paths were previously shared by desktop and mobile. They are disabled by default in standalone desktop mode.

Do not add new cloud-first behavior here unless the local-first policy explicitly allows it. For local/cloud gating, use `shared/standalone_policy.py`.

## Voice Path

The supported desktop voice flow is:

```text
renderer microphone capture -> /ws/app/voice -> VoiceDraftState -> shared session/chat flow
```

Local input engines:

- `english_local`
- `hebrew_local`
- `none`

Jarvis speech output backends:

- `openai`
- `kokoro_onnx`
- `pocket`

Voice packs are managed by `voice_pack_manager.py`. The desktop setup/settings panel owns install, remove, and engine selection.

## Compatibility Notes

This code used to live under `mobile_app/backend/`. A small compatibility package remains at that old path so older imports and commands can keep working while downstream code migrates.

`app_backend.desktop_runtime` is also preserved as a wrapper around
`app_backend.local_runtime_server`.

See [../docs/repository_map.md](../docs/repository_map.md).
See [../desktop_runtime/README.md](../desktop_runtime/README.md) for the local desktop launcher package.
