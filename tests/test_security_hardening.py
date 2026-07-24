from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app_backend import app_server
from app_backend import app_server_auth
from app_backend.network_boundary import TrustedAppNetworkMiddleware, trusted_app_client_host
from shared import atomic_io, private_paths
from desktop_runtime.backend import DesktopRuntimeConfig


ROOT = Path(__file__).resolve().parents[1]


def test_app_network_boundary_allows_only_loopback_and_yggdrasil():
    assert trusted_app_client_host("127.0.0.1") is True
    assert trusted_app_client_host("::1") is True
    assert trusted_app_client_host("::ffff:127.0.0.1") is True
    assert trusted_app_client_host("200::1234") is True
    assert trusted_app_client_host("300::1234") is True
    assert trusted_app_client_host("192.168.1.50") is False
    assert trusted_app_client_host("8.8.8.8") is False
    assert trusted_app_client_host("fd00::1") is False
    assert trusted_app_client_host("not-an-address") is False


def test_ipv6_wildcard_runtime_uses_csp_compatible_loopback_url():
    config = DesktopRuntimeConfig(
        enabled=True,
        host="::",
        port=8787,
        auto_start=True,
        attach_timeout_seconds=30,
        restart_attach_timeout_seconds=20,
        workspace=".",
    )

    assert config.api_base_url == "http://localhost:8787"


def test_app_network_boundary_rejects_lan_http_before_routes():
    downstream_called = False
    sent: list[dict] = []

    async def downstream(_scope, _receive, _send):
        nonlocal downstream_called
        downstream_called = True

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = TrustedAppNetworkMiddleware(downstream)
    asyncio.run(
        middleware(
            {"type": "http", "client": ("192.168.1.50", 55000)},
            receive,
            send,
        )
    )

    assert downstream_called is False
    assert sent[0]["status"] == 403


def test_paired_computer_token_is_rejected_by_general_http_auth(monkeypatch):
    monkeypatch.setattr(
        app_server,
        "_get_auth_store",
        lambda: SimpleNamespace(resolve_access_token=lambda _token: None),
    )
    monkeypatch.setattr(
        app_server,
        "_get_remote_control_store",
        lambda: SimpleNamespace(
            resolve_session_token=lambda _token: {
                "auth_kind": "remote_session",
                "actor_kind": "desktop",
                "user_id": 0,
            }
        ),
    )

    with pytest.raises(HTTPException) as raised:
        app_server_auth._resolve_token("Bearer paired-computer-secret")

    assert raised.value.status_code == 403


def test_websocket_auth_prefers_authorization_header(monkeypatch):
    resolved: list[str] = []

    def resolve(token):
        resolved.append(str(token))
        return {"user_id": 0}

    monkeypatch.setattr(app_server, "_resolve_ws_token", resolve)
    websocket = SimpleNamespace(
        headers={"authorization": "Bearer header-secret"},
        query_params={"token": "legacy-query-secret"},
    )

    result = asyncio.run(app_server_auth._resolve_ws_token_or_close(websocket))

    assert result == {"user_id": 0}
    assert resolved == ["header-secret"]


def test_health_and_api_responses_do_not_leak_or_cache_diagnostics():
    response = TestClient(app_server.create_app()).get("/api/app/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "process_id" not in response.json()
    assert "runtime_home" not in response.json()
    assert "remote_control_routing" not in response.json()


def test_atomic_private_write_hardens_temp_and_target(tmp_path: Path, monkeypatch):
    hardened: list[Path] = []
    monkeypatch.setattr(
        atomic_io,
        "harden_private_path",
        lambda path, _mode, **_kwargs: hardened.append(Path(path)) or True,
    )
    target = tmp_path / "secret.json"

    atomic_io.atomic_write_json(target, {"token": "secret"}, private=True)

    assert target in hardened
    assert any(path != target and path.suffix == ".tmp" for path in hardened)


def test_windows_private_acl_removes_inheritance_and_grants_current_user(tmp_path: Path, monkeypatch):
    target = tmp_path / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    commands: list[list[str]] = []
    private_paths._HARDENED_WINDOWS_PATHS.clear()
    monkeypatch.setattr(private_paths, "_WINDOWS", True)
    monkeypatch.setattr(private_paths, "_windows_account_name", lambda: "desktop\\user")
    monkeypatch.setattr(
        private_paths.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(list(command)) or SimpleNamespace(returncode=0),
    )

    assert private_paths.harden_private_path(target, 0o600, is_directory=False) is True

    assert commands
    assert commands[0][:3] == ["icacls", str(target), "/inheritance:r"]
    assert "desktop\\user:F" in commands[0]
    assert "*S-1-5-18:F" in commands[0]


def test_paired_websocket_secret_is_not_placed_in_url():
    source = (ROOT / "app_backend" / "remote_desktop_client.py").read_text(encoding="utf-8")

    assert "ws/remote/desktop?token=" not in source
    assert 'additional_headers={"Authorization": f"Bearer {remote_token}"}' in source


def test_desktop_renderer_security_contract_is_explicit():
    source = (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8")

    assert "sandbox: true" in source
    assert "Content-Security-Policy" in source
    assert "setPermissionRequestHandler" in source
    assert "Executable and script files cannot be launched" in source
    assert "parsed.hostname === 'renderer'" in source
