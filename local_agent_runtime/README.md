# Local Agent Runtime

This package contains the local automation runtime pieces that used to live in
`single_agent/`: browser tools, desktop/screen tools, cron scheduling, extension
bridge helpers, tool manifests, and the older `SingleAgent` implementation.

Prefer importing from `local_agent_runtime.*` in new code. The old
`single_agent.*` import path remains as a compatibility shim for older tests and
branches.
