from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import desktop_runtime.backend as desktop_backend


def _http_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Any:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method.upper()} {url} failed with {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method.upper()} {url} failed: {exc}") from exc


def _wait_for_api_ready(api_base_url: str, token: str, timeout_seconds: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            profile = _http_json("GET", f"{api_base_url}/api/app/me", token=token, timeout=8.0)
            sessions = _http_json("GET", f"{api_base_url}/api/app/sessions", token=token, timeout=8.0)
            if isinstance(profile, dict) and isinstance(sessions, list):
                return profile, sessions
        except Exception as exc:  # pragma: no cover - best-effort retry path
            last_error = exc
        time.sleep(1.0)
    if last_error:
        raise RuntimeError(f"Desktop API did not become ready: {last_error}") from last_error
    raise RuntimeError("Desktop API did not become ready before the timeout elapsed.")


def _resolve_workspace(
    *,
    bootstrap: dict[str, Any],
    profile: dict[str, Any],
    sessions: list[dict[str, Any]],
    token: str,
    api_base_url: str,
) -> Optional[str]:
    current_session_id = str(profile.get("current_session_id") or "").strip()
    if current_session_id:
        matching = next((item for item in sessions if str(item.get("id") or "").strip() == current_session_id), None)
        workspace = str((matching or {}).get("workspace") or "").strip()
        if workspace:
            return workspace
        try:
            detail = _http_json(
                "GET",
                f"{api_base_url}/api/app/sessions/{current_session_id}",
                token=token,
                timeout=15.0,
            )
            workspace = str((detail or {}).get("workspace") or "").strip()
            if workspace:
                return workspace
        except Exception:
            pass

    setup_state = bootstrap.get("setupState") if isinstance(bootstrap.get("setupState"), dict) else {}
    setup_values = setup_state.get("values") if isinstance(setup_state.get("values"), dict) else {}
    default_workspace = str(setup_values.get("DEFAULT_WORKSPACE") or "").strip()
    if default_workspace:
        return default_workspace
    workspace_root = str(bootstrap.get("workspaceRoot") or "").strip()
    return workspace_root or None


def run_smoke(prompt: str, *, timeout_seconds: float, keep_session: bool = False) -> dict[str, Any]:
    bootstrap = desktop_backend._bootstrap_payload(
        force_launch=True,
        resolve_current_session=False,
    )
    setup_state = bootstrap.get("setupState") if isinstance(bootstrap.get("setupState"), dict) else {}
    runtime_status = bootstrap.get("runtimeStatus") if isinstance(bootstrap.get("runtimeStatus"), dict) else {}
    api_base_url = str(bootstrap.get("apiBaseUrl") or "").strip()
    token = str(bootstrap.get("accessToken") or "").strip()
    if bool(setup_state.get("required")):
        raise RuntimeError("Desktop setup is still required before the chat smoke check can run.")
    if not api_base_url or not token or not bool(runtime_status.get("ok")):
        raise RuntimeError(
            str(runtime_status.get("detail") or "Desktop runtime is not ready for the chat smoke check.")
        )

    profile, sessions = _wait_for_api_ready(api_base_url, token, timeout_seconds)
    restore_session_id = str(profile.get("current_session_id") or "").strip() or None
    workspace = _resolve_workspace(
        bootstrap=bootstrap,
        profile=profile,
        sessions=sessions,
        token=token,
        api_base_url=api_base_url,
    )

    smoke_session_id: Optional[str] = None
    smoke_session_name = f"Smoke Check {time.strftime('%H:%M:%S')}"
    assistant_text = ""
    chat_result: dict[str, Any] | None = None
    created_session: dict[str, Any] | None = None

    try:
        create_payload: dict[str, Any] = {"name": smoke_session_name}
        if workspace:
            create_payload["workspace"] = workspace
        created = _http_json(
            "POST",
            f"{api_base_url}/api/app/sessions",
            token=token,
            payload=create_payload,
            timeout=30.0,
        )
        created_session = (created or {}).get("session") if isinstance(created, dict) else None
        smoke_session_id = str((created_session or {}).get("id") or "").strip() or None
        if not smoke_session_id:
            raise RuntimeError("Smoke chat session was created without a valid session id.")

        started_at = time.monotonic()
        chat_result = _http_json(
            "POST",
            f"{api_base_url}/api/app/chat/send",
            token=token,
            payload={
                "session_id": smoke_session_id,
                "text": prompt,
                "source_format": "app_text",
                "interrupt_policy": "none",
            },
            timeout=max(30.0, timeout_seconds),
        )
        duration_seconds = round(time.monotonic() - started_at, 2)
        assistant_text = str((chat_result or {}).get("assistant_text") or "").strip()
        if not assistant_text:
            raise RuntimeError("Smoke chat completed without assistant output.")
        if "SMOKE_OK" not in assistant_text.upper():
            raise RuntimeError(f"Smoke chat returned an unexpected reply: {assistant_text[:200]}")

        return {
            "ok": True,
            "apiBaseUrl": api_base_url,
            "smokeSessionId": smoke_session_id,
            "smokeSessionName": smoke_session_name,
            "workspace": workspace,
            "durationSeconds": duration_seconds,
            "assistantText": assistant_text,
            "usage": {
                "input_tokens": chat_result.get("input_tokens") if isinstance(chat_result, dict) else None,
                "output_tokens": chat_result.get("output_tokens") if isinstance(chat_result, dict) else None,
                "total_tokens": chat_result.get("total_tokens") if isinstance(chat_result, dict) else None,
            },
        }
    finally:
        cleanup: dict[str, Any] = {}
        if smoke_session_id and not keep_session:
            try:
                cleanup["deleted"] = _http_json(
                    "DELETE",
                    f"{api_base_url}/api/app/sessions/{smoke_session_id}",
                    token=token,
                    timeout=20.0,
                )
            except Exception as exc:
                cleanup["deleteError"] = str(exc)
        if restore_session_id:
            try:
                cleanup["restored"] = _http_json(
                    "POST",
                    f"{api_base_url}/api/app/sessions/{restore_session_id}/activate",
                    token=token,
                    timeout=20.0,
                )
            except Exception as exc:
                cleanup["restoreError"] = str(exc)
        if cleanup:
            sys.stderr.write(json.dumps({"cleanup": cleanup}, ensure_ascii=False) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a live local desktop chat smoke check.")
    parser.add_argument(
        "--prompt",
        default="Reply with exactly SMOKE_OK and nothing else.",
        help="Prompt to send through the desktop app chat endpoint.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Maximum seconds to wait for the local desktop API and the chat response.",
    )
    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="Keep the temporary smoke session instead of deleting it after the run.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_smoke(
            args.prompt,
            timeout_seconds=float(args.timeout_seconds),
            keep_session=bool(args.keep_session),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
