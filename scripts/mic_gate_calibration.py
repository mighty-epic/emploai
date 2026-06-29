"""Print live microphone levels for tuning Jarvis voice-gate thresholds.

This script does not save or transmit audio. It only samples the selected mic
and reports dBFS levels against candidate gates so a user can choose the lowest
threshold that captures speech without triggering on room noise or TTS playback.
"""

from __future__ import annotations

import argparse
import math
import queue
import sys
import time
from dataclasses import dataclass

try:
    import numpy as np
    import sounddevice as sd
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with: py -m pip install sounddevice numpy"
    ) from exc


EPSILON = 1e-8


@dataclass
class GateState:
    open: bool = False
    above_frames: int = 0
    below_frames: int = 0
    opened_at: float | None = None


def frame_dbfs(frame: np.ndarray) -> float:
    samples = np.asarray(frame, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    return 20.0 * math.log10(max(rms, EPSILON))


def parse_gates(raw: str) -> list[float]:
    gates = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        gates.append(float(value))
    if not gates:
        raise ValueError("At least one gate is required.")
    return sorted(set(gates))


def list_input_devices() -> None:
    print("Input devices:")
    for index, device in enumerate(sd.query_devices()):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        marker = "default" if index == sd.default.device[0] else "       "
        print(
            f"  {index:>2} {marker}  {device['name']} "
            f"({int(device['max_input_channels'])} ch, {device['default_samplerate']:.0f} Hz)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate EmploAI/Jarvis mic gate.")
    parser.add_argument("--device", type=int, default=None, help="sounddevice input device index")
    parser.add_argument("--sample-rate", type=int, default=None, help="input sample rate")
    parser.add_argument("--frame-ms", type=int, default=30, help="measurement frame size")
    parser.add_argument("--duration", type=float, default=180.0, help="seconds to run")
    parser.add_argument(
        "--gates",
        default="-42,-40,-37.5,-35,-32.5,-30,-27.5,-25,-22.5",
        help="comma-separated candidate dBFS thresholds",
    )
    parser.add_argument("--attack-ms", type=int, default=60, help="frames above threshold to open")
    parser.add_argument("--release-ms", type=int, default=900, help="frames below threshold to close")
    parser.add_argument("--list-devices", action="store_true", help="print input devices and exit")
    args = parser.parse_args()

    if args.list_devices:
        list_input_devices()
        return 0

    gates = parse_gates(args.gates)
    device_info = sd.query_devices(args.device, "input")
    sample_rate = int(args.sample_rate or device_info["default_samplerate"])
    frame_samples = max(1, int(sample_rate * args.frame_ms / 1000))
    attack_frames = max(1, math.ceil(args.attack_ms / args.frame_ms))
    release_frames = max(1, math.ceil(args.release_ms / args.frame_ms))
    states = {gate: GateState() for gate in gates}
    readings: queue.Queue[float] = queue.Queue()
    stop_at = time.monotonic() + args.duration

    def on_audio(indata, frames, when, status):  # noqa: ANN001
        del frames, when
        if status:
            print(f"audio warning: {status}", file=sys.stderr)
        readings.put(frame_dbfs(indata.copy()))

    print("Jarvis mic gate calibration")
    print("Speak normally, softly, then stay quiet while assistant audio or room noise plays.")
    print("Tell Codex the lowest gate that opens for your speech but stays closed otherwise.")
    print(f"Device: {args.device if args.device is not None else 'default'} - {device_info['name']}")
    print(f"Sample rate: {sample_rate} Hz, frame: {args.frame_ms} ms")
    print(f"Candidate gates: {', '.join(f'{gate:g}' for gate in gates)} dBFS")
    print()

    peak = -120.0
    recent: list[float] = []
    next_print = 0.0
    with sd.InputStream(
        device=args.device,
        channels=1,
        samplerate=sample_rate,
        blocksize=frame_samples,
        dtype="float32",
        callback=on_audio,
    ):
        while time.monotonic() < stop_at:
            try:
                dbfs = readings.get(timeout=0.2)
            except queue.Empty:
                continue
            now = time.monotonic()
            peak = max(peak, dbfs)
            recent.append(dbfs)
            if len(recent) > 40:
                recent.pop(0)

            for gate, state in states.items():
                if dbfs >= gate:
                    state.above_frames += 1
                    state.below_frames = 0
                else:
                    state.below_frames += 1
                    state.above_frames = 0

                if not state.open and state.above_frames >= attack_frames:
                    state.open = True
                    state.opened_at = now
                elif state.open and state.below_frames >= release_frames:
                    state.open = False
                    state.opened_at = None

            if now < next_print:
                continue
            next_print = now + 0.18
            recent_peak = max(recent) if recent else dbfs
            markers = []
            for gate in gates:
                state = states[gate]
                markers.append(f"{gate:g}:{'OPEN' if state.open else '....'}")
            print(
                f"level {dbfs:6.1f} dBFS | recent peak {recent_peak:6.1f} | "
                + "  ".join(markers),
                flush=True,
            )

    print()
    print(f"Finished. Peak observed: {peak:.1f} dBFS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
