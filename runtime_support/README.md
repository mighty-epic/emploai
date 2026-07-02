# Runtime Support

Shared support helpers used by the desktop app backend, CLI, Telegram bridge,
and shared runtime code.

This package used to be named `bot_core`, but the helpers are no longer only for
the Telegram bot. Prefer `runtime_support.*` imports in new code. The old
`bot_core.*` path remains as a compatibility shim.
