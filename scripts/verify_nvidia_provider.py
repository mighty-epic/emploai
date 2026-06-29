"""Verify EmploAI's NVIDIA NIM provider wiring against the live API.

The NVIDIA model catalog endpoint is public, so catalog checks catch registry
drift but do not prove a user key works. The chat smoke call below is the
authenticated proof and runs only when a key is available, or when requested
with --require-key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.tui_constants import NVIDIA_MODEL_IDS  # noqa: E402
from shared.model_defaults import NVIDIA_DEFAULT_MODEL  # noqa: E402


NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODELS_URL = f"{NVIDIA_BASE_URL}/models"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env")


def fetch_live_model_ids(timeout: float = 30.0) -> list[str]:
    request = urllib.request.Request(
        NVIDIA_MODELS_URL,
        headers={"Accept": "application/json", "User-Agent": "emploai-nvidia-provider-smoke"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("NVIDIA model catalog response did not contain a data list")

    model_ids: list[str] = []
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            model_ids.append(str(row["id"]))
        elif isinstance(row, str):
            model_ids.append(row)
    return sorted(set(model_ids))


def registry_missing_from_catalog(live_model_ids: Sequence[str]) -> list[str]:
    live = set(live_model_ids)
    return sorted(model_id for model_id in NVIDIA_MODEL_IDS if model_id not in live)


def run_chat_smoke(api_key: str, *, model: str, prompt: str, stream: bool, timeout: float) -> str:
    client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=24,
        temperature=0,
        stream=stream,
    )

    if not stream:
        return (response.choices[0].message.content or "").strip()

    chunks: list[str] = []
    for chunk in response:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            chunks.append(content)
    return "".join(chunks).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=NVIDIA_DEFAULT_MODEL, help="NVIDIA model ID to smoke test.")
    parser.add_argument("--prompt", default="Reply with only: ok", help="Prompt for the authenticated chat smoke.")
    parser.add_argument("--stream", action="store_true", help="Use streaming chat completions for the smoke call.")
    parser.add_argument("--skip-chat", action="store_true", help="Only verify catalog/registry wiring.")
    parser.add_argument("--require-key", action="store_true", help="Fail when NVIDIA_API_KEY is not configured.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_dotenv()

    if args.model not in NVIDIA_MODEL_IDS:
        print(f"ERROR: {args.model!r} is not registered in NVIDIA_MODEL_IDS.")
        return 1

    try:
        live_model_ids = fetch_live_model_ids(timeout=args.timeout)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: failed to fetch NVIDIA model catalog: {exc}")
        return 1

    missing = registry_missing_from_catalog(live_model_ids)
    if missing:
        print("ERROR: registered NVIDIA models missing from the live catalog:")
        for model_id in missing:
            print(f"  - {model_id}")
        return 1

    print(f"NVIDIA catalog OK: {len(NVIDIA_MODEL_IDS)} registered chooser models are live.")

    if args.model not in live_model_ids:
        print(f"ERROR: selected model {args.model!r} is not in the live NVIDIA catalog.")
        return 1

    if args.skip_chat:
        print("Authenticated chat smoke skipped by --skip-chat.")
        return 0

    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        print("NVIDIA_API_KEY is not configured; authenticated chat smoke skipped.")
        return 2 if args.require_key else 0

    try:
        content = run_chat_smoke(
            api_key,
            model=args.model,
            prompt=args.prompt,
            stream=args.stream,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"ERROR: authenticated NVIDIA chat smoke failed: {exc}")
        return 1

    preview = content[:120] if content else "(empty response)"
    print(f"Authenticated NVIDIA chat OK with {args.model}: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
