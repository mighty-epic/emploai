from __future__ import annotations

import argparse
import os

import uvicorn

from app_backend.app_server import create_app
from app_backend.remote_control_runtime import assert_remote_control_routing_supported


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the EmploAI remote control plane backend.")
    parser.add_argument("--host", default=os.getenv("EMPLOAI_REMOTE_CONTROL_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("EMPLOAI_REMOTE_CONTROL_PORT", str(DEFAULT_PORT))))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    assert_remote_control_routing_supported()
    uvicorn.run(
        create_app(),
        host=str(args.host or DEFAULT_HOST),
        port=int(args.port or DEFAULT_PORT),
        log_level=os.getenv("EMPLOAI_REMOTE_CONTROL_LOG_LEVEL", "info").lower(),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("EMPLOAI_REMOTE_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
