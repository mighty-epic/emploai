from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import shared_state_root
from shared.secure_store import (
    KEYRING_STORAGE,
    WINDOWS_DPAPI_STORAGE,
    SecureStorageUnavailable,
    delete_secure_payload,
    protect_json_payload,
    unprotect_json_payload,
)


CODEX_PROVIDER = "openai-codex"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_ISSUER = "https://auth.openai.com"
CODEX_TOKEN_URL = f"{CODEX_AUTH_ISSUER}/oauth/token"
CODEX_DEVICE_URL = f"{CODEX_AUTH_ISSUER}/codex/device"
CODEX_DEVICE_CALLBACK_URL = f"{CODEX_AUTH_ISSUER}/deviceauth/callback"
CODEX_BACKEND_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_AUTH_FILENAME = "openai-codex-auth.json"
CODEX_PENDING_LOGIN_TTL_SECONDS = 15 * 60
CODEX_REFRESH_SKEW_SECONDS = 120


class CodexAuthError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def codex_auth_path() -> Path:
    configured = os.getenv("EMPLOAI_CODEX_AUTH_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (shared_state_root() / CODEX_AUTH_FILENAME).resolve()


def _read_store() -> Dict[str, Any]:
    path = codex_auth_path()
    backup_path = path.with_suffix(f"{path.suffix}.bak")
    purpose = f"EmploAI OpenAI Codex auth: {path}"
    for candidate in (path, backup_path):
        try:
            record = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        storage = str(record.get("storage") or "").strip()
        try:
            if storage in {WINDOWS_DPAPI_STORAGE, KEYRING_STORAGE}:
                payload = unprotect_json_payload(record, purpose=purpose)
            else:
                # Legacy plaintext stores are accepted only long enough to
                # migrate them into the current user's OS credential vault.
                payload = record
                _write_store(payload)
        except SecureStorageUnavailable:
            continue
        if candidate == backup_path:
            _write_store(payload)
        return payload
    return {}


def _write_store(payload: Mapping[str, Any]) -> None:
    path = codex_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    purpose = f"EmploAI OpenAI Codex auth: {path}"
    try:
        envelope = protect_json_payload(payload, purpose=purpose)
    except SecureStorageUnavailable as exc:
        raise CodexAuthError(str(exc)) from exc
    atomic_write_json(
        path,
        envelope,
        backup_path=path.with_suffix(f"{path.suffix}.bak"),
        sort_keys=True,
    )


def delete_codex_auth() -> Dict[str, Any]:
    path = codex_auth_path()
    purpose = f"EmploAI OpenAI Codex auth: {path}"
    for candidate in (path, path.with_suffix(f"{path.suffix}.bak")):
        try:
            record = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(record, dict):
                delete_secure_payload(record, purpose=purpose)
        except (OSError, json.JSONDecodeError, SecureStorageUnavailable):
            pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    try:
        path.with_suffix(f"{path.suffix}.bak").unlink()
    except FileNotFoundError:
        pass
    return codex_auth_status()


def _json_object(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _tokens(store: Mapping[str, Any]) -> Dict[str, Any]:
    return _json_object(store.get("tokens"))


def _coerce_expires_at(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return None
    return None


def _is_access_token_usable(store: Mapping[str, Any], *, skew_seconds: int = 0) -> bool:
    tokens = _tokens(store)
    if not str(tokens.get("access_token", "") or "").strip():
        return False
    expires_at = _coerce_expires_at(tokens.get("expires_at") or store.get("expires_at"))
    if expires_at is None:
        return True
    return expires_at > (time.time() + max(0, int(skew_seconds)))


def _access_token(store: Mapping[str, Any]) -> str:
    return str(_tokens(store).get("access_token", "") or "").strip()


def _refresh_token(store: Mapping[str, Any]) -> str:
    return str(_tokens(store).get("refresh_token", "") or "").strip()


def _base_url(store: Mapping[str, Any]) -> str:
    return (
        os.getenv("EMPLOAI_CODEX_BASE_URL", "").strip().rstrip("/")
        or str(store.get("base_url") or "").strip().rstrip("/")
        or CODEX_BACKEND_BASE_URL
    )


def _request(
    url: str,
    *,
    method: str = "POST",
    json_body: Optional[Mapping[str, Any]] = None,
    form_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout_seconds: float = 30.0,
) -> Tuple[int, Dict[str, Any], str, Mapping[str, str]]:
    body: Optional[bytes] = None
    request_headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(dict(json_body)).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    if form_body is not None:
        body = urllib.parse.urlencode(dict(form_body)).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request_headers.setdefault("Accept", "application/json")
    request_headers.setdefault("User-Agent", "emploai/1.0")
    request = urllib.request.Request(url=url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200) or 200)
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    payload: Dict[str, Any] = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
            payload = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            payload = {}
    return status, payload, raw, response_headers


def _jwt_claims(token: str) -> Dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_account_id(tokens: Mapping[str, Any]) -> Optional[str]:
    for token_key in ("id_token", "access_token"):
        claims = _jwt_claims(str(tokens.get(token_key, "") or ""))
        if not claims:
            continue
        nested = claims.get("https://api.openai.com/auth")
        candidates = [
            claims.get("chatgpt_account_id"),
            _json_object(nested).get("chatgpt_account_id"),
        ]
        organizations = claims.get("organizations")
        if isinstance(organizations, list) and organizations:
            first = organizations[0]
            if isinstance(first, dict):
                candidates.append(first.get("id"))
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
    return None


def _store_tokens(token_payload: Mapping[str, Any], *, base_url: Optional[str] = None) -> Dict[str, Any]:
    previous = _read_store()
    previous_tokens = _tokens(previous)
    expires_in = int(float(token_payload.get("expires_in") or 3600))
    expires_at = time.time() + max(1, expires_in)
    tokens = {
        "access_token": str(token_payload.get("access_token") or "").strip(),
        "refresh_token": str(token_payload.get("refresh_token") or previous_tokens.get("refresh_token") or "").strip(),
        "id_token": str(token_payload.get("id_token") or previous_tokens.get("id_token") or "").strip(),
        "expires_at": expires_at,
        "expires_in": expires_in,
    }
    if not tokens["access_token"]:
        raise CodexAuthError("OpenAI did not return an access token.")
    store: Dict[str, Any] = {
        "provider": CODEX_PROVIDER,
        "auth_mode": "chatgpt",
        "source": "device-code",
        "base_url": (base_url or _base_url(previous)).rstrip("/"),
        "account_id": _extract_account_id(tokens) or previous.get("account_id"),
        "tokens": tokens,
        "updated_at": _utc_now_iso(),
        "last_refresh": _utc_now_iso(),
    }
    _write_store(store)
    return store


def codex_auth_status(*, include_path: bool = True) -> Dict[str, Any]:
    store = _read_store()
    tokens = _tokens(store)
    expires_at = _coerce_expires_at(tokens.get("expires_at") or store.get("expires_at"))
    configured = bool(_access_token(store) or _refresh_token(store))
    payload: Dict[str, Any] = {
        "provider": CODEX_PROVIDER,
        "configured": configured,
        "signedIn": configured,
        "authMode": "chatgpt",
        "baseUrl": _base_url(store),
        "accountId": str(store.get("account_id") or "").strip() or None,
        "expiresAt": expires_at,
        "expiresAtIso": datetime.fromtimestamp(expires_at, timezone.utc).isoformat().replace("+00:00", "Z") if expires_at else None,
        "hasRefreshToken": bool(_refresh_token(store)),
        "accessTokenUsable": _is_access_token_usable(store),
        "pendingDeviceLogin": bool(_json_object(store.get("pending_device_login"))),
    }
    if include_path:
        payload["authPath"] = str(codex_auth_path())
    return payload


def is_codex_auth_configured() -> bool:
    store = _read_store()
    return bool(_access_token(store) or _refresh_token(store))


def begin_codex_device_login() -> Dict[str, Any]:
    status, payload, raw, _headers = _request(
        f"{CODEX_AUTH_ISSUER}/api/accounts/deviceauth/usercode",
        json_body={"client_id": CODEX_OAUTH_CLIENT_ID},
        timeout_seconds=20,
    )
    if status != 200:
        detail = payload.get("error_description") or payload.get("error") or raw or f"HTTP {status}"
        raise CodexAuthError(f"Could not start ChatGPT sign-in: {detail}")
    user_code = str(payload.get("user_code") or "").strip()
    device_auth_id = str(payload.get("device_auth_id") or "").strip()
    if not user_code or not device_auth_id:
        raise CodexAuthError("OpenAI device sign-in response did not include a user code.")
    try:
        interval_seconds = max(3, int(float(payload.get("interval") or 5)))
    except (TypeError, ValueError):
        interval_seconds = 5
    pending = {
        "device_auth_id": device_auth_id,
        "user_code": user_code,
        "verification_uri": CODEX_DEVICE_URL,
        "interval_seconds": interval_seconds,
        "expires_at": time.time() + CODEX_PENDING_LOGIN_TTL_SECONDS,
        "started_at": _utc_now_iso(),
    }
    store = _read_store()
    store["pending_device_login"] = pending
    _write_store(store)
    return {
        "ok": True,
        "provider": CODEX_PROVIDER,
        "verification_uri": CODEX_DEVICE_URL,
        "verificationUri": CODEX_DEVICE_URL,
        "user_code": user_code,
        "userCode": user_code,
        "interval_seconds": interval_seconds,
        "intervalSeconds": interval_seconds,
        "expires_at": pending["expires_at"],
        "expiresAt": pending["expires_at"],
        "authPath": str(codex_auth_path()),
    }


def poll_codex_device_login() -> Dict[str, Any]:
    store = _read_store()
    pending = _json_object(store.get("pending_device_login"))
    if not pending:
        return {"ok": False, "state": "missing", "detail": "No ChatGPT sign-in is pending."}
    if _coerce_expires_at(pending.get("expires_at")) and float(pending["expires_at"]) <= time.time():
        store.pop("pending_device_login", None)
        _write_store(store)
        return {"ok": False, "state": "expired", "detail": "ChatGPT sign-in expired. Start sign-in again."}

    status, payload, raw, _headers = _request(
        f"{CODEX_AUTH_ISSUER}/api/accounts/deviceauth/token",
        json_body={
            "device_auth_id": str(pending.get("device_auth_id") or ""),
            "user_code": str(pending.get("user_code") or ""),
        },
        timeout_seconds=20,
    )
    if status in {403, 404}:
        return {
            "ok": False,
            "state": "pending",
            "verification_uri": CODEX_DEVICE_URL,
            "verificationUri": CODEX_DEVICE_URL,
            "user_code": str(pending.get("user_code") or ""),
            "userCode": str(pending.get("user_code") or ""),
            "interval_seconds": int(pending.get("interval_seconds") or 5),
            "intervalSeconds": int(pending.get("interval_seconds") or 5),
        }
    if status != 200:
        detail = payload.get("error_description") or payload.get("error") or raw or f"HTTP {status}"
        raise CodexAuthError(f"ChatGPT sign-in polling failed: {detail}")

    authorization_code = str(payload.get("authorization_code") or "").strip()
    code_verifier = str(payload.get("code_verifier") or "").strip()
    if not authorization_code or not code_verifier:
        raise CodexAuthError("OpenAI device sign-in response was missing the authorization code.")

    token_status, token_payload, token_raw, _token_headers = _request(
        CODEX_TOKEN_URL,
        form_body={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": CODEX_DEVICE_CALLBACK_URL,
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout_seconds=20,
    )
    if token_status != 200:
        detail = token_payload.get("error_description") or token_payload.get("error") or token_raw or f"HTTP {token_status}"
        raise CodexAuthError(f"ChatGPT token exchange failed: {detail}")
    saved = _store_tokens(token_payload)
    saved.pop("pending_device_login", None)
    _write_store(saved)
    status_payload = codex_auth_status()
    status_payload.update({"ok": True, "state": "connected"})
    return status_payload


def refresh_codex_auth_if_needed(*, force: bool = False) -> Dict[str, Any]:
    store = _read_store()
    if not force and _is_access_token_usable(store, skew_seconds=CODEX_REFRESH_SKEW_SECONDS):
        return store
    refresh_token = _refresh_token(store)
    if not refresh_token:
        if _is_access_token_usable(store):
            return store
        raise CodexAuthError("ChatGPT sign-in has expired. Sign in again from Settings.")
    status, payload, raw, _headers = _request(
        CODEX_TOKEN_URL,
        form_body={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_OAUTH_CLIENT_ID,
        },
        timeout_seconds=30,
    )
    if status != 200:
        detail = payload.get("error_description") or payload.get("error") or raw or f"HTTP {status}"
        raise CodexAuthError(f"Could not refresh ChatGPT sign-in: {detail}")
    return _store_tokens(payload, base_url=_base_url(store))


def _namespace(value: Any) -> Any:
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    if isinstance(value, dict):
        ns = SimpleNamespace()
        for key, item in value.items():
            setattr(ns, str(key), _namespace(item))
        return ns
    return value


def _response_output_text(payload: Mapping[str, Any]) -> str:
    text = str(payload.get("output_text") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()


def _response_namespace(payload: Mapping[str, Any]) -> Any:
    data = dict(payload)
    data.setdefault("output_text", _response_output_text(data))
    return _namespace(data)


def _codex_headers(store: Mapping[str, Any]) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_access_token(store)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "emploai/1.0",
        "originator": "emploai",
    }
    account_id = str(store.get("account_id") or "").strip()
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _parse_sse_events(lines: Iterable[bytes]) -> Iterator[Any]:
    event_name = ""
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if not data_lines:
                event_name = ""
                continue
            data_text = "\n".join(data_lines).strip()
            current_event = event_name
            event_name = ""
            data_lines = []
            if not data_text or data_text == "[DONE]":
                continue
            try:
                payload = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                if current_event and not payload.get("type"):
                    payload["type"] = current_event
                yield _namespace(payload)
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())


class _CodexResponsesEndpoint:
    def create(self, **kwargs: Any) -> Any:
        store = refresh_codex_auth_if_needed()
        base_url = _base_url(store)
        url = f"{base_url}/responses"
        payload = {key: value for key, value in dict(kwargs).items() if value is not None}
        payload["store"] = False
        stream = bool(payload.get("stream"))
        accept = "text/event-stream" if stream else "application/json"
        headers = _codex_headers(store)
        headers["Accept"] = accept
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        if stream:
            return self._stream(request)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise CodexAuthError(raw.strip() or f"ChatGPT Codex request failed with HTTP {exc.code}") from exc
        parsed = json.loads(raw) if raw.strip() else {}
        if not isinstance(parsed, dict):
            parsed = {"output_text": str(parsed or "")}
        return _response_namespace(parsed)

    @staticmethod
    def _stream(request: urllib.request.Request) -> Iterator[Any]:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                yield from _parse_sse_events(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise CodexAuthError(raw.strip() or f"ChatGPT Codex stream failed with HTTP {exc.code}") from exc


class OpenAICodexClient:
    def __init__(self) -> None:
        self.responses = _CodexResponsesEndpoint()


def create_codex_client() -> OpenAICodexClient:
    return OpenAICodexClient()
