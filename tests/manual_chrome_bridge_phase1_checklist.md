# Manual Chrome Bridge Smoke Checklist

1. Load the unpacked extension from [manifest.json](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/browser_extension/manifest.json) into Chrome.
2. Start the Telegram bot and run `/bridge on`.
3. Confirm `/bridge status` reports the extension bridge as online and shows a pinned task backend once a browser action runs.
4. Send a request that triggers `browser_navigate` and verify the bot opens or reuses one task-owned tab instead of creating a new tab on every navigation.
5. Run a task that uses `browser_snapshot`, `browser_click_ref`, and `browser_type(ref=..., text=...)` and confirm each action stays on the tracked task tab.
6. Open several tabs manually, run `browser_list_tabs`, and confirm `browser_activate_tab` only changes tabs when explicitly requested.
7. Force the bridge offline by disabling the extension during a task, then trigger another browser action and confirm the task falls back to Selenium and stays pinned there for the rest of that task.
8. Re-enable the extension, start a fresh task, and confirm the bridge is re-evaluated instead of staying pinned to Selenium forever.
