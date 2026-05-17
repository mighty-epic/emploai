from __future__ import annotations

import math
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import wave
import zipfile
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable, Optional

try:
    import pyaudio
except ImportError:  # pragma: no cover
    pyaudio = None


DEFAULT_RELEASE_TAG = "v1.8.4"
DEFAULT_MODEL = "tiny.en"
DEFAULT_BINARY_FLAVOR = "blas"
DEFAULT_LANGUAGE = "en"
WHISPER_BUNDLE_ENV = "EMPLOAI_WHISPER_BUNDLE"
DEFAULT_COMMAND_PHRASES = (
    "EmploAI open GitHub in Chrome",
    "EmploAI summarize my latest session",
    "EmploAI switch to GPT five point four",
    "EmploAI pause the current task",
    "EmploAI search for the latest OpenAI API docs",
)
JFK_SAMPLE_URL = "https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/samples/jfk.wav"
MODELS_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
TINYDIARIZE_MODELS_BASE_URL = "https://huggingface.co/akashmjn/tinydiarize-whisper.cpp/resolve/main"


def recommended_thread_count(cpu_count: Optional[int] = None) -> int:
    logical_processors = int(cpu_count or (os.cpu_count() or 1))
    if logical_processors <= 2:
        return 1
    if logical_processors <= 4:
        return logical_processors - 1
    return min(logical_processors - 1, 6)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_root() -> Path:
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    if getattr(sys, "frozen", False):
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
        return (Path(base) / "EmploAI").resolve()

    return repo_root()


def tools_root() -> Path:
    return runtime_root() / ".tools"


def bundled_whisper_root() -> Optional[Path]:
    candidates: list[Path] = []
    configured = os.getenv(WHISPER_BUNDLE_ENV, "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "vendor" / "whisper")

    candidates.append(Path(sys.executable).resolve().parent / "vendor" / "whisper")
    candidates.append(repo_root() / "build" / "windows-vendor" / "whisper")

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved
    return None


def bundled_whisper_cli(*, flavor: str = DEFAULT_BINARY_FLAVOR) -> Optional[Path]:
    root = bundled_whisper_root()
    if root is None:
        return None

    asset_dir = _release_asset_name(flavor=flavor).removesuffix(".zip")
    candidates = (
        root / asset_dir / "Release" / "whisper-cli.exe",
        root / "Release" / "whisper-cli.exe",
        root / "whisper-cli.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def bundled_ggml_model(model_name: str) -> Optional[Path]:
    root = bundled_whisper_root()
    if root is None:
        return None

    filename = f"ggml-{model_name}.bin"
    candidates = (
        root / "models" / filename,
        root / "whisper_cpp_models" / filename,
        root / filename,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def output_root() -> Path:
    return runtime_root() / "test_outputs" / "whisper_cpp"


def models_root() -> Path:
    return tools_root() / "whisper_cpp_models"


def fixtures_root() -> Path:
    return output_root() / "fixtures"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "fixture"


def _normalized_text(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def pcm16le_dbfs(frame_bytes: bytes) -> float:
    if not frame_bytes:
        return -120.0

    samples = array("h")
    samples.frombytes(frame_bytes)
    if not samples:
        return -120.0

    sum_squares = 0.0
    for sample in samples:
        normalized = float(sample) / 32768.0
        sum_squares += normalized * normalized

    if sum_squares <= 0.0:
        return -120.0

    rms = math.sqrt(sum_squares / len(samples))
    return 20.0 * math.log10(max(rms, 1e-6))


def write_pcm16_mono_wav(path: Path, frames: Iterable[bytes], sample_rate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(b"".join(frames))
    return path


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _decode_subprocess_output(payload: bytes | str | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    for encoding in ("utf-8", sys.getfilesystemencoding() or "utf-8", "cp1255", "cp1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _word_error_rate(expected: str, actual: str) -> Optional[float]:
    lhs = _normalized_text(expected).split()
    rhs = _normalized_text(actual).split()
    if not lhs:
        return None

    rows = len(lhs) + 1
    cols = len(rhs) + 1
    dp = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if lhs[i - 1] == rhs[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )

    return dp[-1][-1] / float(len(lhs))


def _release_asset_name(*, flavor: str = DEFAULT_BINARY_FLAVOR) -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "windows":
        raise RuntimeError("This first-pass whisper.cpp test suite currently supports Windows prebuilt binaries only")

    if machine not in {"amd64", "x86_64"}:
        raise RuntimeError(f"Unsupported Windows architecture for prebuilt whisper.cpp binaries: {machine}")

    if flavor == "plain":
        return "whisper-bin-x64.zip"
    if flavor == "blas":
        return "whisper-blas-bin-x64.zip"
    if flavor == "cublas-11.8":
        return "whisper-cublas-11.8.0-bin-x64.zip"
    if flavor == "cublas-12.4":
        return "whisper-cublas-12.4.0-bin-x64.zip"
    raise RuntimeError(f"Unsupported whisper.cpp binary flavor: {flavor}")


def _download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def ensure_prebuilt_whisper_cpp(
    *,
    release_tag: str = DEFAULT_RELEASE_TAG,
    flavor: str = DEFAULT_BINARY_FLAVOR,
    force: bool = False,
) -> Path:
    asset_name = _release_asset_name(flavor=flavor)
    extract_dir = tools_root() / asset_name.removesuffix(".zip")
    whisper_cli = extract_dir / "Release" / "whisper-cli.exe"
    if whisper_cli.exists() and not force:
        return whisper_cli

    bundled_cli = bundled_whisper_cli(flavor=flavor)
    if bundled_cli is not None and not force:
        return bundled_cli

    zip_path = tools_root() / asset_name
    if force or not zip_path.exists():
        url = f"https://github.com/ggml-org/whisper.cpp/releases/download/{release_tag}/{asset_name}"
        _download_file(url, zip_path)

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    if not whisper_cli.exists():
        raise RuntimeError(f"Failed to locate whisper-cli.exe after extracting {zip_path}")
    return whisper_cli


def ensure_ggml_model(model_name: str, *, force: bool = False) -> Path:
    models_root().mkdir(parents=True, exist_ok=True)
    destination = models_root() / f"ggml-{model_name}.bin"
    if destination.exists() and not force:
        return destination

    bundled_model = bundled_ggml_model(model_name)
    if bundled_model is not None and not force:
        return bundled_model

    base_url = TINYDIARIZE_MODELS_BASE_URL if "tdrz" in model_name else MODELS_BASE_URL
    url = f"{base_url}/ggml-{model_name}.bin"
    return _download_file(url, destination)


def ensure_jfk_fixture(*, force: bool = False) -> Path:
    destination = fixtures_root() / "official_jfk.wav"
    if destination.exists() and not force:
        return destination
    return _download_file(JFK_SAMPLE_URL, destination)


def generate_windows_command_fixtures(
    phrases: Iterable[str] = DEFAULT_COMMAND_PHRASES,
    *,
    force: bool = False,
) -> list["WhisperFixture"]:
    if platform.system().lower() != "windows":
        raise RuntimeError("Synthetic command fixture generation currently requires Windows")

    out_dir = fixtures_root() / "commands"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[WhisperFixture] = []
    for index, phrase in enumerate(phrases, start=1):
        slug = _slugify(phrase)
        audio_path = out_dir / f"{index:02d}_{slug}.wav"
        if force or not audio_path.exists():
            escaped_path = str(audio_path).replace("'", "''")
            escaped_phrase = phrase.replace("'", "''")
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                f"$path = '{escaped_path}'; "
                f"$text = '{escaped_phrase}'; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$synth.SetOutputToWaveFile($path); "
                "$synth.Speak($text); "
                "$synth.Dispose();"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                check=False,
                **_hidden_subprocess_kwargs(),
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "Failed to generate Windows speech fixture: "
                    f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
                )

        fixtures.append(
            WhisperFixture(
                name=audio_path.stem,
                audio_path=audio_path,
                expected_text=phrase,
                source="windows_speech",
            )
        )
    return fixtures


def fixture_for_jfk(*, force: bool = False) -> "WhisperFixture":
    return WhisperFixture(
        name="official_jfk",
        audio_path=ensure_jfk_fixture(force=force),
        expected_text="And so my fellow Americans ask not what your country can do for you, ask what you can do for your country.",
        source="whisper_cpp_sample",
    )


def fixture_collection(profile: str, *, force: bool = False) -> list["WhisperFixture"]:
    if profile == "jfk":
        return [fixture_for_jfk(force=force)]
    if profile == "commands":
        return generate_windows_command_fixtures(force=force)
    if profile == "mixed":
        return [fixture_for_jfk(force=force), *generate_windows_command_fixtures(force=force)]
    raise RuntimeError(f"Unsupported fixture profile: {profile}")


def _load_expected_manifest(path: Optional[Path]) -> dict[str, str]:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Expected transcript manifest must be a JSON object mapping file names or paths to text")
    return {str(key): str(value) for key, value in payload.items()}


def custom_fixture_collection(
    fixture_paths: Iterable[Path],
    *,
    expected_manifest_path: Optional[Path] = None,
) -> list["WhisperFixture"]:
    expected_map = _load_expected_manifest(expected_manifest_path)
    fixtures: list[WhisperFixture] = []

    for path in fixture_paths:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise RuntimeError(f"Fixture not found: {resolved}")
        if resolved.suffix.lower() != ".wav":
            raise RuntimeError(f"whisper.cpp CLI currently expects WAV fixtures for this suite: {resolved}")

        expected_text = (
            expected_map.get(str(resolved))
            or expected_map.get(resolved.name)
            or expected_map.get(resolved.stem)
        )
        fixtures.append(
            WhisperFixture(
                name=resolved.stem,
                audio_path=resolved,
                expected_text=expected_text,
                source="custom_recording",
            )
        )

    if not fixtures:
        raise RuntimeError("No custom fixtures were provided")
    return fixtures


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
        if frame_rate <= 0:
            raise RuntimeError(f"Invalid WAV frame rate in {path}")
        return frame_count / float(frame_rate)


def _load_output_json(path: Path) -> dict:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(data.decode("cp1255", errors="replace"))


def transcript_from_output_json(path: Path) -> str:
    payload = _load_output_json(path)
    segments = payload.get("transcription", [])
    parts = [str(item.get("text", "")).strip() for item in segments if str(item.get("text", "")).strip()]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def transcript_confidence_from_output_json(path: Path) -> tuple[str, Optional[float]]:
    payload = _load_output_json(path)
    segments = payload.get("transcription", [])

    parts: list[str] = []
    token_probs: list[float] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if text:
            parts.append(text)
        for token in segment.get("tokens", []):
            token_text = str(token.get("text", "")).strip()
            token_prob = token.get("p")
            if not token_text or token_text == "<|endoftext|>" or token_prob is None:
                continue
            try:
                token_probs.append(float(token_prob))
            except (TypeError, ValueError):
                continue

    transcript = re.sub(r"\s+", " ", " ".join(parts)).strip()
    average_confidence = mean(token_probs) if token_probs else None
    return transcript, average_confidence


def list_input_devices() -> list[dict]:
    if pyaudio is None:
        raise RuntimeError("PyAudio is not installed, so microphone recording is unavailable")

    pa = pyaudio.PyAudio()
    try:
        default_info = pa.get_default_input_device_info()
        default_index = int(default_info["index"])
    except Exception:
        default_index = None

    devices: list[dict] = []
    try:
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0) or 0) <= 0:
                continue
            devices.append(
                {
                    "index": int(info["index"]),
                    "name": str(info.get("name") or f"Input {index}"),
                    "max_input_channels": int(info.get("maxInputChannels") or 0),
                    "default_sample_rate": int(float(info.get("defaultSampleRate") or 16000)),
                    "is_default": int(info["index"]) == default_index,
                }
            )
    finally:
        pa.terminate()

    return devices


def record_microphone_fixture(
    *,
    seconds: float = 4.0,
    countdown_seconds: int = 3,
    device_index: Optional[int] = None,
    fixture_name: str = "live_command",
    expected_text: Optional[str] = None,
) -> "WhisperFixture":
    if pyaudio is None:
        raise RuntimeError("PyAudio is not installed, so microphone recording is unavailable")

    record_dir = fixtures_root() / "recorded"
    record_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = record_dir / f"{_slugify(fixture_name)}_{timestamp}.wav"

    pa = pyaudio.PyAudio()
    try:
        if device_index is None:
            device_info = pa.get_default_input_device_info()
            device_index = int(device_info["index"])
        else:
            device_info = pa.get_device_info_by_index(int(device_index))

        sample_rate = int(float(device_info.get("defaultSampleRate") or 16000))
        channels = 1
        chunk_size = 1024

        print(f"Using input device [{device_index}] {device_info.get('name')}")
        if countdown_seconds > 0:
            for remaining in range(int(countdown_seconds), 0, -1):
                print(f"Recording starts in {remaining}...")
                time.sleep(1)
        print(f"Recording for {seconds:.1f} seconds. Speak now.")

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=int(device_index),
            frames_per_buffer=chunk_size,
        )
        try:
            frame_target = max(1, int(sample_rate / chunk_size * float(seconds)))
            frames = [
                stream.read(chunk_size, exception_on_overflow=False)
                for _ in range(frame_target)
            ]
        finally:
            stream.stop_stream()
            stream.close()

        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(frames))
    finally:
        pa.terminate()

    print(f"Saved microphone recording to {output_path}")
    return WhisperFixture(
        name=output_path.stem,
        audio_path=output_path,
        expected_text=expected_text,
        source="live_microphone",
    )


@dataclass
class WhisperFixture:
    name: str
    audio_path: Path
    expected_text: Optional[str] = None
    source: str = "custom"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["audio_path"] = str(self.audio_path)
        return data


@dataclass
class WhisperRunResult:
    model_name: str
    fixture_name: str
    fixture_source: str
    audio_path: Path
    output_json_path: Path
    iteration: int
    elapsed_seconds: float
    audio_duration_seconds: float
    realtime_factor: float
    transcript: str
    expected_text: Optional[str]
    word_error_rate: Optional[float]

    def as_dict(self) -> dict:
        data = asdict(self)
        data["audio_path"] = str(self.audio_path)
        data["output_json_path"] = str(self.output_json_path)
        return data


def run_whisper_cli_once(
    *,
    whisper_cli: Path,
    model_path: Path,
    model_name: str,
    fixture: WhisperFixture,
    iteration: int,
    language: str = DEFAULT_LANGUAGE,
    initial_prompt: Optional[str] = None,
    no_gpu: bool = False,
    threads: Optional[int] = None,
    output_dir: Optional[Path] = None,
) -> WhisperRunResult:
    output_dir = output_dir or output_root()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_slug = f"{model_name.replace('.', '_')}_{fixture.name}_run{iteration}"
    output_base = output_dir / run_slug
    output_json_path = output_base.with_suffix(".json")
    if output_json_path.exists():
        output_json_path.unlink()

    command = [
        str(whisper_cli),
        "-m",
        str(model_path),
        "-f",
        str(fixture.audio_path),
        "-l",
        language,
        "-nt",
        "-np",
        "-ojf",
        "-of",
        str(output_base),
    ]
    if no_gpu:
        command.append("-ng")
    if threads:
        command.extend(["-t", str(threads)])
    if initial_prompt:
        command.extend(["--prompt", initial_prompt, "--carry-initial-prompt"])

    start = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=False, check=False, **_hidden_subprocess_kwargs())
    elapsed = time.perf_counter() - start
    if completed.returncode != 0:
        raise RuntimeError(
            f"whisper.cpp failed for {fixture.audio_path.name}: "
            f"{_decode_subprocess_output(completed.stderr).strip() or _decode_subprocess_output(completed.stdout).strip() or 'unknown error'}"
        )
    if not output_json_path.exists():
        raise RuntimeError(f"whisper.cpp did not produce {output_json_path}")

    duration = wav_duration_seconds(fixture.audio_path)
    transcript = transcript_from_output_json(output_json_path)
    wer = _word_error_rate(fixture.expected_text or "", transcript) if fixture.expected_text else None
    return WhisperRunResult(
        model_name=model_name,
        fixture_name=fixture.name,
        fixture_source=fixture.source,
        audio_path=fixture.audio_path,
        output_json_path=output_json_path,
        iteration=iteration,
        elapsed_seconds=elapsed,
        audio_duration_seconds=duration,
        realtime_factor=(elapsed / duration) if duration > 0 else 0.0,
        transcript=transcript,
        expected_text=fixture.expected_text,
        word_error_rate=wer,
    )


def summarize_runs(runs: Iterable[WhisperRunResult]) -> dict:
    run_list = list(runs)
    if not run_list:
        return {
            "total_runs": 0,
            "average_elapsed_seconds": 0.0,
            "average_audio_duration_seconds": 0.0,
            "average_realtime_factor": 0.0,
            "average_word_error_rate": None,
            "faster_than_realtime_runs": 0,
            "recommendation": "no_data",
        }

    avg_elapsed = mean(item.elapsed_seconds for item in run_list)
    avg_duration = mean(item.audio_duration_seconds for item in run_list)
    avg_rtf = mean(item.realtime_factor for item in run_list)
    wers = [item.word_error_rate for item in run_list if item.word_error_rate is not None]
    avg_wer = mean(wers) if wers else None
    faster_than_realtime_runs = sum(1 for item in run_list if item.realtime_factor < 1.0)

    if avg_rtf <= 0.5 and avg_elapsed <= 1.0 and (avg_wer is None or avg_wer <= 0.25):
        recommendation = "excellent_for_command_input"
    elif avg_rtf <= 1.0 and avg_elapsed <= 2.0 and (avg_wer is None or avg_wer <= 0.40):
        recommendation = "usable_for_command_input"
    else:
        recommendation = "not_ready_for_command_input"

    return {
        "total_runs": len(run_list),
        "average_elapsed_seconds": round(avg_elapsed, 4),
        "average_audio_duration_seconds": round(avg_duration, 4),
        "average_realtime_factor": round(avg_rtf, 4),
        "average_word_error_rate": round(avg_wer, 4) if avg_wer is not None else None,
        "faster_than_realtime_runs": faster_than_realtime_runs,
        "recommendation": recommendation,
    }


def build_suite_report(
    *,
    release_tag: str,
    binary_flavor: str,
    model_names: list[str],
    fixture_profile: str,
    fixtures: list[WhisperFixture],
    iterations: int,
    whisper_cli: Path,
    runs: list[WhisperRunResult],
) -> dict:
    per_model: dict[str, list[WhisperRunResult]] = {}
    for run in runs:
        per_model.setdefault(run.model_name, []).append(run)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "whisper_cpp": {
            "release_tag": release_tag,
            "binary_flavor": binary_flavor,
            "whisper_cli": str(whisper_cli),
        },
        "suite": {
            "models": model_names,
            "fixture_profile": fixture_profile,
            "iterations": iterations,
            "fixtures": [fixture.as_dict() for fixture in fixtures],
        },
        "summary": summarize_runs(runs),
        "per_model_summary": {model_name: summarize_runs(model_runs) for model_name, model_runs in per_model.items()},
        "runs": [run.as_dict() for run in runs],
    }
