# Whisper.cpp Testing Suite

This repo now includes a local benchmark harness for checking whether `whisper.cpp` is fast enough for EmploAI's computer-first voice input.

The first goal is not full integration. The goal is to answer a narrower question:

- how fast is local transcription on this machine?
- is it faster than real time for command-style input?
- how much transcript quality do we lose on small models?

## What It Does

The suite:

- downloads a Windows x64 prebuilt `whisper.cpp` binary if needed
- downloads one or more `ggml` models if needed
- generates short command-style WAV fixtures locally on Windows using `System.Speech`
- optionally benchmarks the official `jfk.wav` sample from `whisper.cpp`
- runs `whisper-cli`
- stores raw JSON outputs and a structured suite report under `test_outputs/whisper_cpp/`

## Run It

Quick command benchmark with the smallest English model:

```powershell
python -m app_backend.whisper_cpp_suite --fixture-profile commands --models tiny.en --iterations 2
```

Compare a tiny model against a larger quantized English model:

```powershell
python -m app_backend.whisper_cpp_suite --fixture-profile commands --models tiny.en base.en-q5_1 --iterations 2
```

Run with a domain prompt so `whisper.cpp` knows assistant and product names in advance:

```powershell
python -m app_backend.whisper_cpp_suite --fixture-profile commands --models base.en --initial-prompt "The wake phrase is EmploAI. Known terms: EmploAI, OpenAI, GitHub, GPT."
```

Run a mixed profile with both short commands and the official JFK sample:

```powershell
python -m app_backend.whisper_cpp_suite --fixture-profile mixed --models tiny.en
```

Force a fresh download of binaries, models, and generated fixtures:

```powershell
python -m app_backend.whisper_cpp_suite --fixture-profile commands --models tiny.en --force-download
```

## What To Look At

The report includes:

- `average_elapsed_seconds`
- `average_audio_duration_seconds`
- `average_realtime_factor`
- `average_word_error_rate`
- `recommendation`

The most important number for voice-assistant input is `average_realtime_factor`:

- under `1.0` means faster than real time
- under `0.5` is a strong sign the model may feel responsive enough for short commands

For command-style fixtures, the report also computes a simple word error rate against the synthetic prompt text.

## Current Scope

This suite currently targets Windows x64 prebuilt binaries first. That is intentional:

- it avoids requiring a local C/C++ toolchain
- it matches the likely user setup for a desktop EmploAI voice hub
- it keeps the benchmark focused on real usability rather than build troubleshooting

If the results are good enough, the next step is to wrap the same runtime helper into the actual desktop voice path as an optional local STT backend.

## Using Real Recordings

If you want to test your own voice instead of synthetic fixtures, pass one or more WAV files:

```powershell
python -m app_backend.whisper_cpp_suite --fixtures C:\path\to\wake1.wav C:\path\to\wake2.wav --models base.en-q5_1
```

If you also want WER scoring, create a JSON manifest like this:

```json
{
  "wake1.wav": "EmploAI open GitHub in Chrome",
  "wake2": "EmploAI pause the current task"
}
```

Then run:

```powershell
python -m app_backend.whisper_cpp_suite --fixtures C:\path\to\wake1.wav C:\path\to\wake2.wav --expected-manifest C:\path\to\expected.json --models base.en-q5_1
```

## Recording From The Microphone

List input devices:

```powershell
python -m app_backend.whisper_cpp_suite --list-input-devices
```

Record directly from the default microphone, then run the suite on that fresh recording:

```powershell
python -m app_backend.whisper_cpp_suite --record-mic --record-seconds 5 --models base.en-q5_1 --initial-prompt "The wake phrase is EmploAI. Known terms: EmploAI, OpenAI, GitHub, GPT."
```

Record from a specific device and score against an expected transcript:

```powershell
python -m app_backend.whisper_cpp_suite --record-mic --device-index 1 --record-seconds 5 --record-name wake_phrase --expected-text "EmploAI open GitHub in Chrome" --models base.en-q5_1 --initial-prompt "The wake phrase is EmploAI. Known terms: EmploAI, OpenAI, GitHub, GPT."
```

## Free-Talk Live Transcription

If you just want to speak freely into the microphone and watch local `whisper.cpp` transcribe in real time, use:

```powershell
python -m app_backend.whisper_cpp_live --spawn-window --device-index 1
```

Useful variants:

```powershell
python -m app_backend.whisper_cpp_live --list-input-devices
python -m app_backend.whisper_cpp_live --show-presets
python -m app_backend.whisper_cpp_live --spawn-window --preset fast
python -m app_backend.whisper_cpp_live --spawn-window --preset balanced --device-index 1
python -m app_backend.whisper_cpp_live --spawn-window --preset strict --device-index 1
python -m app_backend.whisper_cpp_live --spawn-window --preset dictation --keep-context
```

This mode uses `whisper-stream.exe`, not the benchmark harness, so it is meant for free speech and live experimentation rather than scored WER reports.

The live helper now defaults to the faster Windows BLAS build and laptop-oriented presets instead of the upstream `whisper-stream` defaults, which were noticeably higher-latency on this machine.

One important limitation remains: `whisper-stream.exe` does not expose an initial prompt flag, so names like `EmploAI`, `OpenAI`, or `GitHub` will usually be less reliable here than in the batch benchmark harness, where `whisper-cli` can accept a prompt.

If the live stream starts hearing words you did not say, use the stricter path first:

```powershell
python -m app_backend.whisper_cpp_live --spawn-window --preset strict --device-index 1
```

That preset raises the VAD threshold, lowers the max token budget, increases the high-pass filter, and disables decoder fallback so the stream is less eager to turn noise into text.

## Gated Command Mode

If background noise or tiny whispers are still being turned into text, use the gated microphone path instead of raw `whisper-stream`:

```powershell
python -m app_backend.whisper_cpp_live --engine gated-cli --preset strict --device-index 1 --gate-dbfs -29 --initial-prompt "The wake phrase is EmploAI. Known terms: EmploAI, OpenAI, GitHub, GPT."
```

This mode:

- measures microphone loudness in dBFS before transcription
- ignores audio below the gate threshold
- keeps a short preroll so the start of speech is not clipped
- sends only gated segments to `whisper-cli`
- supports `--initial-prompt`, unlike `whisper-stream`
- carries a rolling tail of recent confirmed transcript back into the next segment prompt for better continuity
- can stream draft partials from still-open segments when average token confidence is high enough

Useful tuning examples:

```powershell
python -m app_backend.whisper_cpp_live --engine gated-cli --preset balanced --device-index 1 --gate-dbfs -32
python -m app_backend.whisper_cpp_live --engine gated-cli --preset strict --device-index 1 --gate-dbfs -27
python -m app_backend.whisper_cpp_live --engine gated-cli --preset strict --device-index 1 --gate-dbfs -29 --gate-release-ms 400 --gate-min-ms 600
python -m app_backend.whisper_cpp_live --engine gated-cli --preset strict --device-index 1 --gate-dbfs -36 --gate-attack-ms 40 --gate-min-ms 120 --gate-release-ms 180 --gate-frame-ms 30
python -m app_backend.whisper_cpp_live --engine gated-cli --preset balanced --device-index 1 --context-chars 220
python -m app_backend.whisper_cpp_live --engine gated-cli --preset balanced --device-index 1 --draft-interval-ms 900 --draft-min-ms 1400 --draft-confidence 0.82
python -m app_backend.whisper_cpp_live --engine gated-cli --preset balanced --device-index 1 --model base.en-q5_1 --draft-model tiny.en
```

Less negative values such as `-27` are stricter and will ignore more quiet sounds. More negative values such as `-35` are more permissive.

If short words still feel inconsistent, lower `--gate-frame-ms`. The earlier gated path used coarse timing buckets, so very short attacks could still behave as if they were longer than requested. A `30 ms` frame is a good default for sharp command words.

If longer messages feel too slow, leave the gate responsive but enable draft streaming. That path transcribes overlapping snapshots of the still-open segment and emits partial text only when token confidence is high enough. It improves perceived latency at the cost of higher CPU use while you are speaking.

If draft streaming still feels slow, use a lighter `--draft-model` than the final model. A good default split on this machine is:

- final model: `base.en-q5_1`
- draft model: `tiny.en`

That keeps the final pass more accurate while making partials show up sooner.
