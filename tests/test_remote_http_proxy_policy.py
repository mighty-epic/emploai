from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException

from app_backend.remote_http_proxy_policy import (
    filter_remote_http_proxy_headers,
    max_base64_chars_for_bytes,
    remote_http_proxy_body_bytes,
    remote_http_proxy_status_code,
    should_proxy_remote_http_request,
)


ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def test_should_proxy_remote_http_request_allows_remote_app_surfaces_only():
    assert should_proxy_remote_http_request("GET", "/api/app/agent/config", allowed_methods=ALLOWED_METHODS)
    assert should_proxy_remote_http_request("POST", "/api/app/chat/send", allowed_methods=ALLOWED_METHODS)
    assert should_proxy_remote_http_request("DELETE", "/api/app/sessions/sess-1", allowed_methods=ALLOWED_METHODS)
    assert should_proxy_remote_http_request("GET", "/api/app/sessions/sess-1/messages", allowed_methods=ALLOWED_METHODS)
    assert should_proxy_remote_http_request("POST", "/api/app/jobs", allowed_methods=ALLOWED_METHODS)

    assert not should_proxy_remote_http_request("TRACE", "/api/app/agent/config", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/health", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/me", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("POST", "/api/app/pair/start", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/devices", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/voice/status", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("POST", "/api/app/sessions", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/sessions/sess-1", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("POST", "/api/app/sessions/sess-1/activate", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/app/jobs", allowed_methods=ALLOWED_METHODS)
    assert not should_proxy_remote_http_request("GET", "/api/fleet/snapshot", allowed_methods=ALLOWED_METHODS)


def test_filter_remote_http_proxy_headers_normalizes_allowlist_and_drops_injection_values():
    headers = filter_remote_http_proxy_headers(
        {
            "Content-Type": "application/json",
            "ACCEPT": "application/json",
            "etag": "ok\r\nx-injected: yes",
            "x-not-allowed": "ignored",
            "content-language": "en\x00us",
        },
        {"content-type", "accept", "etag", "content-language"},
    )

    assert headers == {
        "content-type": "application/json",
        "accept": "application/json",
    }


def test_remote_http_proxy_status_code_rejects_malformed_or_invalid_values():
    assert remote_http_proxy_status_code(201) == 201
    assert remote_http_proxy_status_code("204") == 204
    assert remote_http_proxy_status_code(None) == 502

    with pytest.raises(HTTPException) as malformed:
        remote_http_proxy_status_code("bad")
    assert malformed.value.status_code == 502
    assert "status" in str(malformed.value.detail).lower()

    with pytest.raises(HTTPException) as invalid:
        remote_http_proxy_status_code(99)
    assert invalid.value.status_code == 502
    assert "invalid" in str(invalid.value.detail).lower()


def test_remote_http_proxy_body_bytes_decodes_and_enforces_encoded_and_decoded_limits():
    encoded = base64.b64encode(b"hello").decode("ascii")
    assert remote_http_proxy_body_bytes(encoded, max_response_body_bytes=5) == b"hello"
    assert remote_http_proxy_body_bytes("", max_response_body_bytes=5) == b""
    assert max_base64_chars_for_bytes(5) == 8

    with pytest.raises(HTTPException) as malformed:
        remote_http_proxy_body_bytes("not valid base64 !!!", max_response_body_bytes=64)
    assert malformed.value.status_code == 502
    assert "body" in str(malformed.value.detail).lower()

    with pytest.raises(HTTPException) as encoded_too_large:
        remote_http_proxy_body_bytes(base64.b64encode(b"abcdef").decode("ascii"), max_response_body_bytes=3)
    assert encoded_too_large.value.status_code == 502
    assert "too large" in str(encoded_too_large.value.detail).lower()

    with pytest.raises(HTTPException) as decoded_too_large:
        remote_http_proxy_body_bytes(base64.b64encode(b"abcd").decode("ascii"), max_response_body_bytes=3)
    assert decoded_too_large.value.status_code == 502
    assert "too large" in str(decoded_too_large.value.detail).lower()
