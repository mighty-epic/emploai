# Hebrew Live Voice Path

## Status

This document records the current working Hebrew local voice path and the desktop/installer integration that now uses it.

Current status:

- the Hebrew live terminal path is working well enough for real use
- responsiveness, accuracy, and start-of-phrase capture are in a good place
- the desktop app can now treat Hebrew as an optional local voice pack alongside English
- the MSI installer now exposes optional English/Hebrew voice pack selection
- if a user skips a pack during MSI, they can install or remove it later from the desktop app setup panel
- the remaining external step is publishing the runtime-ready Hebrew pack to a public model repo so fresh installs can download it without a local developer copy

## What Was Built

The current Hebrew voice path is a local CPU Whisper flow using a fine-tuned `whisper-small` checkpoint with a lightweight live terminal loop. The same core runtime shape now also powers the desktop-app Hebrew path.

It is not the older heavier Hebrew stack. The current path is:

- `scripts/hebrew_whisper_live_terminal.py`
- `scripts/start_hebrew_whisper_live.ps1`
- `scripts/test_hebrew_whisper_local.py`
- `app_backend/hebrew_transformers_runtime.py`
- `app_backend/voice_pack_manager.py`
- `app_backend/voice_runtime.py`

The runtime model currently used for testing is:

- `<models-dir>\hebrew-whisper-small-continue-public-v1-runtime-ready`

## Model Lineage

The current runtime model comes from:

1. initial Hebrew `whisper-small` fine-tune
2. continuation fine-tune on additional public Hebrew data
3. slim export from Colab
4. local runtime assembly using:
   - new model weights/config from the continuation export
   - known-good tokenizer/runtime support files from the previously working local runtime

This last step matters because the new slim export's tokenizer config was not directly compatible with the packaged local Transformers runtime in this repo.

So the effective local runtime swap is:

- replaced:
  - `model.safetensors`
  - `config.json`
  - `generation_config.json`
- preserved from the previously working runtime:
  - tokenizer/runtime support files needed for local compatibility

## Runtime Folder Shape

The working runtime-ready folder contains:

- `added_tokens.json`
- `config.json`
- `generation_config.json`
- `merges.txt`
- `model.safetensors`
- `normalizer.json`
- `preprocessor_config.json`
- `processor_config.json`
- `special_tokens_map.json`
- `tokenizer.json`
- `tokenizer_config.json`
- `vocab.json`

## Local Runtime Constraints

In source checkouts, the local Hebrew path uses the active Python environment
and the local voice-pack/runtime files managed by `app_backend/voice_pack_manager.py`.
Older packaged builds used a bundled backend runtime directory, but that path is
no longer part of the current source layout.

The Python environment must include the local `torch` / `transformers` stack used by:

- `scripts/test_hebrew_whisper_local.py`
- `scripts/hebrew_whisper_live_terminal.py`

Because of that constraint, tokenizer/runtime compatibility matters just as much as the model weights.

## Current Live Behavior

The current live mode is `app-chunks`, shaped to feel closer to the English app voice path while staying lightweight on CPU.

### Current tuned parameters

- `engine = app-chunks`
- `segment_ms = 850`
- `draft_min_ms = 850`
- `draft_interval_ms = 850`
- `silence_dbfs = -46.0`
- `start margin = +2.0 dB`
- `preroll = 300 ms`
- `commit_silence_ms = 850`
- `max_utterance_ms = 2550`
- `early_finish_confidence = 0.82`
- `discard_confidence = 0.62`
- `max_new_tokens = 48`

### Additional live-path behavior

- dynamic int8 CPU quantization is enabled for the local live model
- the terminal hides drafts by default and shows final transcript timing instead
- a preroll buffer preserves the start of the phrase before threshold crossing
- low-confidence first-pass chunks are discarded early
- high-confidence first-pass chunks finalize early
- long drifting utterances are capped

## Why This Version Feels Better

The working behavior came from a combination of:

- staying on `whisper-small` for CPU viability
- using a fine-tuned Hebrew checkpoint instead of the older heavier Hebrew path
- dynamic int8 quantization for faster local inference
- English-style chunking instead of a strict old gate-open/gate-close model
- faster confidence-based finalize/discard logic
- preroll capture to avoid clipping the first syllable

## Verified Scripts

### One-shot local test

Script:

- `scripts/test_hebrew_whisper_local.py`

Purpose:

- load the local runtime folder
- transcribe a saved WAV file
- sanity-check that the runtime assets and weights load together

### Live terminal test

Script:

- `scripts/hebrew_whisper_live_terminal.py`

Launcher:

- `scripts/start_hebrew_whisper_live.ps1`

Typical launch:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_hebrew_whisper_live.ps1 -DeviceIndex 1 --model-dir "<models-dir>\hebrew-whisper-small-continue-public-v1-runtime-ready"
```

## Training Notes

The continuation run that produced the current public-data model finished cleanly and improved throughout the run.

Final continuation metrics:

- step `500`: `WER 21.329823`, `CER 9.771308`
- step `1000`: `WER 20.292324`, `CER 9.342634`
- step `1500`: `WER 19.666039`, `CER 8.978570`
- step `2000`: `WER 19.412256`, `CER 8.912006`
- step `2500`: `WER 19.343433`, `CER 8.860253`
- step `3000`: `WER 19.283213`, `CER 8.842025`

This does not by itself prove better live behavior than the previous runtime on every phrase, but it was healthy enough to justify local testing.

## Desktop App Integration

The desktop app now uses the same app voice flow for both local English and local Hebrew:

- renderer microphone capture
- websocket `/ws/app/voice`
- backend `VoiceDraftState`
- partial/final transcript events into the existing shared chat/session path

Hebrew is now treated as a selectable local voice engine:

- `english_local`
- `hebrew_local`
- `none`

The desktop setup/settings UI exposes:

- request English pack
- request Hebrew pack
- install pack now
- delete pack now
- set default local voice engine

The backend runtime uses the approved local Transformers Hebrew path instead of the older CT2/faster-whisper Hebrew route.

### Important constraint

The current working Hebrew terminal path uses a local runtime folder assembled partly from known-good tokenizer/runtime assets. Desktop integration should preserve that packaging discipline instead of assuming a raw slim export is directly runnable.

## MSI Installer Option

The MSI now exposes installer-time feature selection for:

- core desktop app
- English voice pack request
- Hebrew voice pack request

The MSI does not embed the large voice assets directly. Instead it records the user’s requested packs, and on first launch the backend bootstrap installs the requested managed voice packs into the runtime home so the selected paths are ready at startup.

Current managed install behavior:

- English:
  - downloads/prepares `whisper.cpp` and the managed GGML English models
- Hebrew:
  - installs from one of:
    - a local developer runtime-ready folder
    - a downloadable zip
    - a Hugging Face model repo snapshot

Managed Hebrew runtime destination:

- `%LOCALAPPDATA%\EmploAI\voice_packs\hebrew_local\model`

Managed English assets live under the existing `whisper.cpp` runtime roots.

Because the MSI now only requests packs instead of always bundling them, users can choose:

- English only
- Hebrew only
- both
- neither

## Public Hebrew Pack Publication

The consumer-side install flow is ready, but the public Hebrew pack still needs to be published to a model repo that end users can access.

Prepared helper:

- `scripts/publish_hebrew_voice_pack.py`

Published public repo:

- [Mighty1234/hebrew-whisper-small-continue-public-v1](https://huggingface.co/Mighty1234/hebrew-whisper-small-continue-public-v1)

Expected runtime-ready file set:

- `added_tokens.json`
- `config.json`
- `generation_config.json`
- `merges.txt`
- `model.safetensors`
- `normalizer.json`
- `preprocessor_config.json`
- `processor_config.json`
- `special_tokens_map.json`
- `tokenizer.json`
- `tokenizer_config.json`
- `vocab.json`

Typical publish command:

```powershell
python .\scripts\publish_hebrew_voice_pack.py --repo-id your-org/hebrew-whisper-small-continue-public-v1
```

Runtime envs used by the app/backend:

- `EMPLO_APP_STT_HEBREW_MODEL_REPO`
- `EMPLOAI_HEBREW_VOICE_PACK_ARCHIVE_URL`
- `EMPLOAI_HEBREW_VOICE_PACK_SOURCE_DIR`
- `EMPLOAI_HEBREW_VOICE_PACK_REVISION`

The backend now defaults to:

- `EMPLO_APP_STT_HEBREW_MODEL_REPO=Mighty1234/hebrew-whisper-small-continue-public-v1`
