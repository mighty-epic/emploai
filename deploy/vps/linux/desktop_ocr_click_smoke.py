#!/usr/bin/env python3
"""Live VPS smoke test for Linux desktop OCR + click on the X11 virtual desktop.

This test does not use Selenium or the extension bridge. It validates the actual
Linux desktop path the Telegram bot uses on the VPS:
- screenshot capture
- OCR extraction
- physical click via xdotool

Usage:
  source /opt/emploai/venv/bin/activate
  DISPLAY=:99 python deploy/vps/linux/desktop_ocr_click_smoke.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telegram_bot.linux import desktop_tools  # noqa: E402


def _print_block(title: str, payload) -> None:
    print(f"\n== {title} ==")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload)


def _create_smoke_html() -> Path:
    smoke_dir = Path(tempfile.gettempdir()) / "emploai-desktop-smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    html_path = smoke_dir / "index.html"
    html_path.write_text(
        """<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>EmploAI Desktop Smoke</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 40px; background: #f7f4ea; color: #202020; }
      h1 { font-size: 40px; margin-bottom: 12px; }
      p { font-size: 24px; }
      button {
        margin-top: 36px;
        font-size: 30px;
        padding: 18px 32px;
        border: 0;
        border-radius: 14px;
        background: #1f6f5f;
        color: white;
        cursor: pointer;
      }
      #status { margin-top: 32px; font-weight: bold; color: #7a2600; }
    </style>
  </head>
  <body>
    <h1>EmploAI OCR Click Smoke Test</h1>
    <p>Find the button text and click it using OCR coordinates.</p>
    <button id="target" onclick="document.getElementById('status').textContent='CLICK CONFIRMED'">
      EMPLO SMOKE TARGET
    </button>
    <p id="status">WAITING FOR CLICK</p>
  </body>
</html>
""",
        encoding="utf-8",
    )
    return html_path


def _find_element(elements: list[dict], required_terms: list[str]) -> dict | None:
    for element in elements:
        text = str(element.get("text", "")).lower()
        if all(term in text for term in required_terms):
            return element
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Linux OCR + click on the live VPS desktop.")
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":99"), help="X11 display to target.")
    parser.add_argument("--chrome-binary", default="google-chrome", help="Chrome binary to launch.")
    parser.add_argument("--load-seconds", type=float, default=4.0, help="Seconds to wait for Chrome to paint.")
    parser.add_argument("--keep-open", action="store_true", help="Leave the smoke-test window open after the run.")
    args = parser.parse_args()

    os.environ["DISPLAY"] = args.display

    html_path = _create_smoke_html()
    profile_dir = Path(tempfile.gettempdir()) / "emploai-desktop-smoke-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    app_url = html_path.resolve().as_uri()

    chrome_args = [
        args.chrome_binary,
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--new-window",
        f"--user-data-dir={profile_dir}",
        f"--app={app_url}",
        "--window-size=1280,960",
        "--window-position=0,0",
    ]

    _print_block("launch", {"display": args.display, "command": chrome_args})
    process = subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(args.load_seconds)

    describe_result = desktop_tools._execute_describe_screen(None, {})
    _print_block(
        "describe_screen",
        {
            "image_captured": describe_result.get("image_captured"),
            "metadata": describe_result.get("metadata"),
            "image_base64_chars": len(describe_result.get("image_base64", "")),
        },
    )

    windows = desktop_tools._execute_observe_desktop(None, {})
    _print_block("observe_desktop", windows)

    ocr_before = desktop_tools._execute_ocr_screen(None, {})
    _print_block(
        "ocr_before",
        {
            "variant": ocr_before.get("variant"),
            "total_elements": ocr_before.get("total_elements"),
            "sample_elements": (ocr_before.get("elements") or [])[:10],
            "plain_text": (ocr_before.get("plain_text") or "")[:400],
        },
    )

    target = _find_element(ocr_before.get("elements") or [], ["emplo", "smoke", "target"])
    if not target:
        _print_block("result", "FAIL: OCR did not find the target button text on the live desktop.")
        if not args.keep_open:
            process.terminate()
        return 2

    click_result = desktop_tools._execute_click(None, {"x": target["x"], "y": target["y"]})
    _print_block("click", click_result)
    time.sleep(1.5)

    ocr_after = desktop_tools._execute_ocr_screen(None, {})
    _print_block(
        "ocr_after",
        {
            "variant": ocr_after.get("variant"),
            "total_elements": ocr_after.get("total_elements"),
            "sample_elements": (ocr_after.get("elements") or [])[:10],
            "plain_text": (ocr_after.get("plain_text") or "")[:400],
        },
    )

    plain_text_after = (ocr_after.get("plain_text") or "").lower()
    if "click confirmed" not in plain_text_after:
        _print_block(
            "result",
            "FAIL: OCR click ran, but the page did not show the expected 'CLICK CONFIRMED' state.",
        )
        if not args.keep_open:
            process.terminate()
        return 3

    _print_block("result", "PASS: live desktop OCR found the target and xdotool click changed the page state.")

    if not args.keep_open:
        process.terminate()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
