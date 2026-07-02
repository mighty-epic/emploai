from fastapi.testclient import TestClient

from app_backend import app_server
from shared.standalone_policy import cloud_backend_enabled, mobile_connection_enabled, standalone_desktop_enabled


def test_standalone_policy_defaults_to_local_only(monkeypatch):
    monkeypatch.delenv("EMPLOAI_CLOUD_BACKEND_ENABLED", raising=False)
    monkeypatch.delenv("EMPLOAI_MOBILE_CONNECTION_ENABLED", raising=False)
    monkeypatch.delenv("EMPLOAI_STANDALONE_DESKTOP", raising=False)

    assert cloud_backend_enabled() is False
    assert mobile_connection_enabled() is False
    assert standalone_desktop_enabled() is True


def test_standalone_app_disables_cloud_and_mobile_routes_by_default(monkeypatch):
    monkeypatch.delenv("EMPLOAI_CLOUD_BACKEND_ENABLED", raising=False)
    monkeypatch.delenv("EMPLOAI_MOBILE_CONNECTION_ENABLED", raising=False)
    monkeypatch.delenv("EMPLOAI_STANDALONE_DESKTOP", raising=False)

    client = TestClient(app_server.create_app())
    health = client.get("/api/app/health?shallow=1")

    assert health.status_code == 200
    assert health.json()["cloud_backend_enabled"] is False
    assert health.json()["mobile_connection_enabled"] is False
    assert health.json()["standalone_desktop_enabled"] is True
    assert client.post("/api/remote/auth/login", json={}).status_code == 404
    assert client.post("/api/app/pair/start", json={}).status_code == 404


def test_cloud_and_mobile_routes_can_be_reenabled(monkeypatch):
    monkeypatch.setenv("EMPLOAI_CLOUD_BACKEND_ENABLED", "1")
    monkeypatch.setenv("EMPLOAI_MOBILE_CONNECTION_ENABLED", "1")

    client = TestClient(app_server.create_app())
    health = client.get("/api/app/health?shallow=1")

    assert health.status_code == 200
    assert health.json()["cloud_backend_enabled"] is True
    assert health.json()["mobile_connection_enabled"] is True
    assert client.post("/api/remote/auth/login", json={}).status_code != 404
    assert client.post("/api/app/pair/start", json={}).status_code != 404
