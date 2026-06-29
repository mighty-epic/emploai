import asyncio
import warnings

import pytest
from fastapi.testclient import TestClient

from mobile_app.backend import app_server


def _app_with_crashing_route():
    app = app_server.create_app()

    @app.get("/__test__/crash")
    async def crash_route():
        raise RuntimeError("top secret backend detail")

    return app


def test_unhandled_exception_response_hides_traceback_by_default(monkeypatch):
    monkeypatch.delenv(app_server.DEBUG_ERROR_RESPONSES_ENV, raising=False)
    client = TestClient(_app_with_crashing_route(), raise_server_exceptions=False)

    response = client.get("/__test__/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["error_id"]
    assert response.headers["x-emploai-error-id"] == body["error_id"]
    assert "traceback" not in body
    assert "top secret backend detail" not in response.text


def test_unhandled_exception_response_can_include_traceback_for_debug(monkeypatch):
    monkeypatch.setenv(app_server.DEBUG_ERROR_RESPONSES_ENV, "1")
    client = TestClient(_app_with_crashing_route(), raise_server_exceptions=False)

    response = client.get("/__test__/crash")

    assert response.status_code == 500
    body = response.json()
    assert "RuntimeError: top secret backend detail" in body["detail"]
    assert "top secret backend detail" in body["traceback"]
    assert body["error_id"]


def test_app_lifespan_starts_and_stops_background_services(monkeypatch):
    from mobile_app.backend import cron_runtime

    events = []

    async def fake_ensure_global_cron_scheduler_started():
        events.append("scheduler_started")

    async def fake_event_run_reconciler(stop_event):
        events.append("reconciler_started")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            events.append(f"reconciler_cancelled:{stop_event.is_set()}")
            raise

    monkeypatch.setattr(
        cron_runtime,
        "ensure_global_cron_scheduler_started",
        fake_ensure_global_cron_scheduler_started,
    )
    monkeypatch.setattr(app_server, "_event_run_reconciler", fake_event_run_reconciler)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        app = app_server.create_app()

    assert not any("on_event is deprecated" in str(item.message) for item in caught)

    with TestClient(app) as client:
        assert "scheduler_started" in events
        assert isinstance(app.state.event_run_reconciler_stop, asyncio.Event)
        assert isinstance(app.state.event_run_reconciler_task, asyncio.Task)
        response = client.get("/__missing__")
        assert response.status_code == 404

    assert app.state.event_run_reconciler_stop is None
    assert app.state.event_run_reconciler_task is None
    assert any(item == "reconciler_cancelled:True" for item in events)


def test_app_secret_uses_dev_fallback_outside_production(monkeypatch):
    monkeypatch.delenv(app_server.DEPLOYMENT_ENV_ENV, raising=False)
    monkeypatch.delenv(app_server.APP_SECRET_ENV, raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert app_server._secret() == "emploai-dev-secret"


def test_app_secret_fails_closed_in_production_without_configured_secret(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.delenv(app_server.APP_SECRET_ENV, raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match=app_server.APP_SECRET_ENV):
        app_server._secret()


def test_app_secret_uses_configured_secret_in_production(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.setenv(app_server.APP_SECRET_ENV, "configured-production-secret")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert app_server._secret() == "configured-production-secret"


def test_cors_defaults_keep_localhost_outside_production(monkeypatch):
    monkeypatch.delenv(app_server.DEPLOYMENT_ENV_ENV, raising=False)
    monkeypatch.delenv(app_server.CORS_ORIGINS_ENV, raising=False)

    origins = app_server._cors_allow_origins()

    assert "http://localhost:5173" in origins
    assert "https://kraitos.app" in origins


def test_cors_defaults_drop_localhost_in_production(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.delenv(app_server.CORS_ORIGINS_ENV, raising=False)

    origins = app_server._cors_allow_origins()

    assert "https://kraitos.app" in origins
    assert "emploai://renderer" in origins
    assert "http://localhost:5173" not in origins
    assert all(not origin.startswith("http://") for origin in origins)


def test_cors_rejects_unsafe_configured_origins_in_production(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.setenv(app_server.CORS_ORIGINS_ENV, "https://kraitos.app,http://localhost:5173,*")

    with pytest.raises(RuntimeError, match=app_server.CORS_ORIGINS_ENV):
        app_server._cors_allow_origins()


def test_cors_accepts_https_and_desktop_origin_in_production(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.setenv(app_server.CORS_ORIGINS_ENV, "https://mobile.example.com/,emploai://renderer/")

    assert app_server._cors_allow_origins() == ["https://mobile.example.com", "emploai://renderer"]


def test_auth_otp_email_allows_console_outside_production(monkeypatch, caplog):
    monkeypatch.delenv(app_server.DEPLOYMENT_ENV_ENV, raising=False)
    monkeypatch.setenv(app_server.AUTH_EMAIL_BACKEND_ENV, "console")

    asyncio.run(
        app_server._send_remote_auth_otp_email(
            email="person@example.com",
            code="123456",
            purpose="login_verify",
        )
    )

    assert "Auth OTP for person@example.com: 123456" in caplog.text


def test_auth_otp_email_requires_configured_delivery(monkeypatch):
    monkeypatch.delenv(app_server.DEPLOYMENT_ENV_ENV, raising=False)
    monkeypatch.delenv(app_server.AUTH_EMAIL_BACKEND_ENV, raising=False)
    monkeypatch.delenv(app_server.RESEND_API_KEY_ENV, raising=False)

    with pytest.raises(RuntimeError, match="delivery is not configured"):
        asyncio.run(
            app_server._send_remote_auth_otp_email(
                email="person@example.com",
                code="123456",
                purpose="login_verify",
            )
        )


def test_auth_otp_email_uses_resend_when_api_key_is_present(monkeypatch):
    monkeypatch.delenv(app_server.DEPLOYMENT_ENV_ENV, raising=False)
    monkeypatch.delenv(app_server.AUTH_EMAIL_BACKEND_ENV, raising=False)
    monkeypatch.setenv(app_server.RESEND_API_KEY_ENV, "resend-test-key")
    sent_requests = []

    class FakeResponse:
        status_code = 202
        text = ""

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers=None, json=None):
            sent_requests.append({"url": url, "headers": headers or {}, "json": json or {}})
            return FakeResponse()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        app_server._send_remote_auth_otp_email(
            email="person@example.com",
            code="123456",
            purpose="signup_verify",
        )
    )

    assert sent_requests
    assert sent_requests[0]["url"] == "https://api.resend.com/emails"
    assert sent_requests[0]["headers"]["Authorization"] == "Bearer resend-test-key"
    assert sent_requests[0]["json"]["to"] == ["person@example.com"]


def test_auth_otp_email_rejects_console_in_production(monkeypatch):
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.setenv(app_server.AUTH_EMAIL_BACKEND_ENV, "console")
    monkeypatch.delenv(app_server.RESEND_API_KEY_ENV, raising=False)

    with pytest.raises(RuntimeError, match=app_server.AUTH_EMAIL_BACKEND_ENV):
        asyncio.run(
            app_server._send_remote_auth_otp_email(
                email="person@example.com",
                code="123456",
                purpose="login_verify",
            )
        )
