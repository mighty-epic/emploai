#!/usr/bin/env python3
"""Manual smoke test for the Chrome extension bridge on the VPS.

Usage:
  1. Stop the bot service temporarily so this script can bind port 8765:
       systemctl stop emploai-agent.service
  2. Activate the venv:
       source /opt/emploai/venv/bin/activate
  3. Run the smoke test:
       python deploy/legacy_vps/linux/browser_bridge_smoke.py --url https://open.spotify.com
  4. Start the bot again when done:
       systemctl start emploai-agent.service
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_agent_runtime.extension_tool import ExtensionTool  # noqa: E402


def _print_block(title: str, payload) -> None:
    print(f"\n== {title} ==")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the EmploAI Chrome extension bridge.")
    parser.add_argument("--url", default="https://open.spotify.com", help="URL to open in the bridge-owned tab.")
    parser.add_argument("--port", type=int, default=8765, help="Bridge server port.")
    parser.add_argument("--connect-timeout", type=float, default=15.0, help="Seconds to wait for the extension to connect.")
    parser.add_argument("--min-elements", type=int, default=1, help="Fail if snapshot returns fewer interactive elements.")
    args = parser.parse_args()

    tool = ExtensionTool(port=args.port)
    tool.start_server()

    try:
        connected = tool.run_sync(tool._wait_for_connection(timeout=args.connect_timeout))
        if not connected:
            _print_block(
                "connection",
                "Extension did not connect. Open Chrome on the VPS, load the unpacked extension, and keep the popup/service worker alive.",
            )
            return 2

        _print_block("status", tool.get_status())

        tabs = tool.list_tabs()
        _print_block("tabs_before", tabs)

        navigation = tool.navigate(args.url)
        _print_block("navigate", navigation)
        if navigation.get("error"):
            return 3

        tab_id = navigation.get("tab_id")
        state = tool.get_page_info(tab_id)
        _print_block("state", state)

        snapshot = tool.snapshot(tab_id)
        _print_block(
            "snapshot",
            {
                "title": snapshot.get("title"),
                "url": snapshot.get("url"),
                "interactive_count": snapshot.get("interactive_count"),
                "focused_ref": snapshot.get("focused_ref"),
                "formatted": snapshot.get("formatted"),
                "sample_elements": (snapshot.get("elements") or [])[:10],
            },
        )

        screenshot = tool.screenshot(tab_id)
        _print_block(
            "screenshot",
            {
                "title": screenshot.get("title"),
                "url": screenshot.get("url"),
                "image_captured": screenshot.get("image_captured"),
                "image_base64_chars": len(screenshot.get("image_base64") or ""),
            },
        )

        if (snapshot.get("interactive_count") or 0) < args.min_elements:
            _print_block(
                "result",
                f"FAIL: snapshot returned {snapshot.get('interactive_count', 0)} interactive elements on {args.url}",
            )
            return 4

        _print_block("result", "PASS: browser bridge is returning interactive elements in the live VPS environment.")
        return 0
    finally:
        time.sleep(0.2)
        tool.shutdown_server()


if __name__ == "__main__":
    raise SystemExit(main())
