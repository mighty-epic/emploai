# EmploAI Pending, Degraded, and Discarded Features

This document tracks items that are currently planned but not yet implemented, as well as documents/assets that have been degraded or discarded.

---

## 1. Pending Features (Not Yet Implemented)

These features represent the planned future work for the EmploAI desktop and mobile ecosystems:

### A. Remote Agent Connection Hub (Other Computers Backend)
* **Status**: Scaffolding UI exists; Backend logic is pending.
* **Details**: The desktop renderer displays remote status cards and preview window placeholders.
* **Work Remaining**:
  * Implement agent registration and discovery schemas.
  * Build secure transport for remote desktop view stream frames.
  * Wire backend remote control event loops (relaying actions from the host machine to target servers/VPSs).

### B. Assistant Voice Output (Text-to-Speech / TTS)
* **Status**: Voice input is functional; Output (TTS) is pending.
* **Details**: The architecture is designed to handle audio streams, but the TTS backend generator and client speaker/audio players are not yet integrated.
* **Work Remaining**:
  * Build a low-latency TTS generation pipeline on the server/VPS runtime (extending current voice channel).
  * Update client Websocket handlers to stream and play assistant speech chunks.

### C. Advanced Parameter Desktop Tuning
* **Status**: Direct links to Telegram commands/TUI commands exist; Redesigned parameters UI is pending.
* **Details**: Granular agent tuning controls are not fully built into the new Electron settings panel.
* **Work Remaining**:
  * Redesign and wire UI settings for model tool authorization (which tools are allowed).
  * Implement interactive cron schedules editor.
  * Add configurable heartbeat tuning parameters.

---

## 2. Degraded and Discarded Files

These files were moved out of active documentation because they are outdated, redundant, or unrelated:

* **[new_sys.md](docs/pending_and_discarded/new_sys.md)**: Discarded prompt scratchpad. Prompt rules are now hardcoded into [cli/tui_constants.py](cli/tui_constants.py) as Python string constants.
* **[openai_cookbook_recursive.md](docs/pending_and_discarded/openai_cookbook_recursive.md)**: Discarded raw copy of the OpenAI Cookbook README file.
* **nyc-real-estate-ml-readme.md** (Deleted): Completely unrelated machine learning analysis document that has been removed from the repository.
