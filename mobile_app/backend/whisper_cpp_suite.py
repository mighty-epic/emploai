from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_app.backend.whisper_cpp_runtime import (
    DEFAULT_BINARY_FLAVOR,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_RELEASE_TAG,
    WhisperFixture,
    build_suite_report,
    custom_fixture_collection,
    ensure_ggml_model,
    ensure_prebuilt_whisper_cpp,
    fixture_collection,
    list_input_devices,
    output_root,
    record_microphone_fixture,
    run_whisper_cli_once,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local whisper.cpp benchmark suite for EmploAI voice input.")
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG, help="whisper.cpp GitHub release tag for prebuilt binaries")
    parser.add_argument(
        "--binary-flavor",
        default=DEFAULT_BINARY_FLAVOR,
        choices=["plain", "blas", "cublas-11.8", "cublas-12.4"],
        help="prebuilt binary flavor to download/use",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[DEFAULT_MODEL],
        help="one or more ggml model names, e.g. tiny.en base.en-q5_1",
    )
    parser.add_argument(
        "--fixture-profile",
        default="commands",
        choices=["commands", "jfk", "mixed"],
        help="fixture set to run",
    )
    parser.add_argument(
        "--fixtures",
        nargs="+",
        default=[],
        help="one or more custom WAV fixture paths; if provided, these override --fixture-profile",
    )
    parser.add_argument(
        "--expected-manifest",
        default="",
        help="optional JSON file mapping fixture path, file name, or stem to the expected transcript",
    )
    parser.add_argument("--iterations", type=int, default=1, help="number of runs per model and fixture")
    parser.add_argument("--list-input-devices", action="store_true", help="list microphone-capable input devices and exit")
    parser.add_argument("--record-mic", action="store_true", help="record a fresh microphone fixture before running the suite")
    parser.add_argument("--record-seconds", type=float, default=4.0, help="recording length when --record-mic is used")
    parser.add_argument("--countdown", type=int, default=3, help="countdown before microphone recording begins")
    parser.add_argument("--device-index", type=int, default=None, help="optional PyAudio input device index")
    parser.add_argument("--record-name", default="live_command", help="base name for a recorded microphone fixture")
    parser.add_argument("--expected-text", default="", help="optional expected text for a microphone recording")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="language passed to whisper.cpp")
    parser.add_argument("--initial-prompt", default="", help="optional transcription prompt for brand names and domain terms")
    parser.add_argument("--threads", type=int, default=None, help="override whisper.cpp thread count")
    parser.add_argument("--no-gpu", action="store_true", help="pass --no-gpu to whisper.cpp")
    parser.add_argument("--force-download", action="store_true", help="re-download binaries, models, and generated fixtures")
    parser.add_argument(
        "--output-dir",
        default=str(output_root()),
        help="directory where reports and output JSON files will be written",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.list_input_devices:
        for device in list_input_devices():
            marker = "*" if device["is_default"] else " "
            print(
                f"{marker} [{device['index']}] {device['name']} "
                f"(channels={device['max_input_channels']}, default_rate={device['default_sample_rate']})"
            )
        return 0

    whisper_cli = ensure_prebuilt_whisper_cpp(
        release_tag=args.release_tag,
        flavor=args.binary_flavor,
        force=args.force_download,
    )
    if args.record_mic:
        fixtures = [
            record_microphone_fixture(
                seconds=args.record_seconds,
                countdown_seconds=args.countdown,
                device_index=args.device_index,
                fixture_name=args.record_name,
                expected_text=args.expected_text.strip() or None,
            )
        ]
        fixture_profile = "recorded_mic"
    elif args.fixtures:
        fixtures = custom_fixture_collection(
            [Path(item) for item in args.fixtures],
            expected_manifest_path=(Path(args.expected_manifest).expanduser().resolve() if args.expected_manifest else None),
        )
        fixture_profile = "custom"
    else:
        fixtures = fixture_collection(args.fixture_profile, force=args.force_download)
        fixture_profile = args.fixture_profile

    runs = []
    for model_name in args.models:
        model_path = ensure_ggml_model(model_name, force=args.force_download)
        for fixture in fixtures:
            for iteration in range(1, args.iterations + 1):
                runs.append(
                    run_whisper_cli_once(
                        whisper_cli=whisper_cli,
                        model_path=model_path,
                        model_name=model_name,
                        fixture=fixture,
                        iteration=iteration,
                        language=args.language,
                        initial_prompt=args.initial_prompt.strip() or None,
                        no_gpu=args.no_gpu,
                        threads=args.threads,
                        output_dir=out_dir,
                    )
                )

    report = build_suite_report(
        release_tag=args.release_tag,
        binary_flavor=args.binary_flavor,
        model_names=list(args.models),
        fixture_profile=fixture_profile,
        fixtures=fixtures,
        iterations=args.iterations,
        whisper_cli=whisper_cli,
        runs=runs,
    )

    report_name = f"report_{fixture_profile}_{'_'.join(model.replace('.', '_') for model in args.models)}.json"
    report_path = out_dir / report_name
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Whisper.cpp benchmark report saved to: {report_path}")
    print()
    print("Overall summary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print()
    print("Per-model summary:")
    for model_name, summary in report["per_model_summary"].items():
        print(f"  {model_name}:")
        for key, value in summary.items():
            print(f"    {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
