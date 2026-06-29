import json

from fastapi.testclient import TestClient

from mobile_app.backend import app_server


_VALID_SHA256 = "a" * 64


def test_desktop_release_manifest_endpoint_reads_configured_file(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "https://api.kraitos.app/releases/desktop/windows/EmploAI.msi",
                    "sha256": _VALID_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 200
    assert response.json()["latest"]["tagName"] == "v0.1.0-beta.14.4"


def test_desktop_release_manifest_endpoint_rejects_unsafe_asset_url(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "http://evil.example/releases/desktop/windows/EmploAI.msi",
                    "sha256": _VALID_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 500
    assert "unsafe asset url" in response.json()["detail"].lower()


def test_desktop_release_manifest_endpoint_rejects_asset_url_name_mismatch(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "https://api.kraitos.app/releases/desktop/windows/Other.msi",
                    "sha256": _VALID_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 500
    assert "does not match" in response.json()["detail"].lower()


def test_desktop_release_manifest_endpoint_requires_sha256(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "https://api.kraitos.app/releases/desktop/windows/EmploAI.msi",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 500
    assert "sha-256" in response.json()["detail"].lower()


def test_desktop_release_manifest_endpoint_rejects_unsupported_asset_type(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.exe",
                    "assetUrl": "https://api.kraitos.app/releases/desktop/windows/EmploAI.exe",
                    "sha256": _VALID_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 500
    assert "asset type" in response.json()["detail"].lower()


def test_desktop_release_manifest_endpoint_accepts_configured_release_host(tmp_path, monkeypatch):
    manifest_path = tmp_path / "desktop_windows_release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "channel": "beta",
                "latest": {
                    "version": "0.1.0-beta.14.4",
                    "tagName": "v0.1.0-beta.14.4",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "https://downloads.example.com/releases/desktop/windows/EmploAI.msi",
                    "sha256": _VALID_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_ALLOWED_HOSTS", "downloads.example.com")

    response = TestClient(app_server.create_app()).get("/api/releases/desktop/windows/latest")

    assert response.status_code == 200
    assert response.json()["latest"]["assetUrl"] == "https://downloads.example.com/releases/desktop/windows/EmploAI.msi"


def test_desktop_release_asset_endpoint_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_ASSET_DIR", str(tmp_path))

    response = TestClient(app_server.create_app()).get("/releases/desktop/windows/..%2Fsecret.msi")

    assert response.status_code == 404


def test_desktop_release_asset_endpoint_serves_msi(tmp_path, monkeypatch):
    asset = tmp_path / "EmploAI.msi"
    asset.write_bytes(b"fake-msi")
    monkeypatch.setenv("EMPLOAI_DESKTOP_RELEASE_ASSET_DIR", str(tmp_path))

    response = TestClient(app_server.create_app()).get("/releases/desktop/windows/EmploAI.msi")

    assert response.status_code == 200
    assert response.content == b"fake-msi"
