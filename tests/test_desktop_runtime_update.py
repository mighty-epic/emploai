import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from desktop_runtime.update import (
    _launch_msi_update,
    AvailableUpdate,
    ReleaseInfo,
    check_for_updates,
    find_available_update,
    find_available_update_from_manifest,
    install_available_update,
    install_latest_update,
    load_release_info,
    should_check_for_updates,
    _normalize_release_version,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, content: bytes):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=1024 * 1024):
        yield self._content


def test_load_release_info_reads_metadata(tmp_path: Path):
    deploy_dir = tmp_path / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text(
        '{"version":"0.1.0-beta.2","release_tag":"v0.1.0-beta.2","msi_version":"0.1.2","channel":"beta","github_repo":"mighty-epic/emploai","primary_asset":"EmploAI.msi","portable_asset":"EmploAI.exe","update_check_interval_hours":12}',
        encoding="utf-8",
    )

    info = load_release_info(tmp_path)
    assert info.version == "0.1.0-beta.2"
    assert info.primary_asset == "EmploAI.msi"
    assert info.update_check_interval_hours == 12


def test_load_release_info_preserves_zero_interval(tmp_path: Path):
    deploy_dir = tmp_path / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text(
        '{"version":"0.1.0-beta.2","release_tag":"v0.1.0-beta.2","msi_version":"0.1.2","channel":"beta","github_repo":"mighty-epic/emploai","primary_asset":"EmploAI.msi","portable_asset":"EmploAI.exe","update_check_interval_hours":0}',
        encoding="utf-8",
    )

    info = load_release_info(tmp_path)
    assert info.update_check_interval_hours == 0


def test_should_check_for_updates_respects_interval(tmp_path: Path):
    assert should_check_for_updates(tmp_path, 12)


def test_should_check_for_updates_always_when_interval_zero(tmp_path: Path):
    assert should_check_for_updates(tmp_path, 0) is True


def test_normalize_release_version_handles_beta_patch_suffix():
    assert _normalize_release_version("0.1.0-beta.14.4") > _normalize_release_version("0.1.0-beta.14.3")
    assert _normalize_release_version("0.1.0-beta.15") > _normalize_release_version("0.1.0-beta.14.4")


def test_find_available_update_prefers_newer_beta_msi(monkeypatch):
    payload = [
        {
            "tag_name": "v0.1.0-beta.2",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-04-14T12:00:00Z",
            "assets": [
                {
                    "name": "EmploAI.msi",
                    "browser_download_url": "https://example.invalid/EmploAI.msi",
                }
            ],
        },
        {
            "tag_name": "v0.1.0-beta.1",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-04-13T12:00:00Z",
            "assets": [
                {
                    "name": "EmploAI.msi",
                    "browser_download_url": "https://example.invalid/older.msi",
                }
            ],
        },
    ]

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    info = ReleaseInfo(
        version="0.1.0-beta.1",
        release_tag="v0.1.0-beta.1",
        msi_version="0.1.1",
        channel="beta",
        github_repo="mighty-epic/emploai",
        primary_asset="EmploAI.msi",
        portable_asset="EmploAI.exe",
        update_check_interval_hours=12,
    )

    update = find_available_update(info)
    assert update is not None
    assert update.tag_name == "v0.1.0-beta.2"
    assert update.asset_name == "EmploAI.msi"


def test_find_available_update_from_manifest_prefers_newer_msi(monkeypatch):
    payload = {
        "channel": "beta",
        "releases": [
            {
                "version": "0.1.0-beta.3",
                "tagName": "v0.1.0-beta.3",
                "assetName": "EmploAI.msi",
                "assetUrl": "https://api.kraitos.app/releases/desktop/EmploAI.msi",
                "publishedAt": "2026-06-16T10:00:00Z",
            },
            {
                "version": "0.1.0-beta.2",
                "tagName": "v0.1.0-beta.2",
                "assetName": "EmploAI.msi",
                "assetUrl": "https://api.kraitos.app/releases/desktop/older.msi",
            },
        ],
    }

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    info = ReleaseInfo(
        version="0.1.0-beta.2",
        release_tag="v0.1.0-beta.2",
        msi_version="0.1.2",
        channel="beta",
        github_repo="mighty-epic/emploai",
        primary_asset="EmploAI.msi",
        portable_asset="EmploAI-portable.zip",
        update_check_interval_hours=12,
        update_manifest_url="https://api.kraitos.app/api/releases/desktop/windows/latest",
    )

    update = find_available_update_from_manifest(info)
    assert update is not None
    assert update.tag_name == "v0.1.0-beta.3"
    assert update.asset_url == "https://api.kraitos.app/releases/desktop/EmploAI.msi"


def test_find_available_update_from_manifest_accepts_versioned_msi_asset(monkeypatch):
    digest = "b" * 64
    payload = {
        "channel": "beta",
        "latest": {
            "version": "0.1.0-beta.14.5",
            "tagName": "v0.1.0-beta.14.5",
            "assetName": "EmploAI-0.1.19.msi",
            "assetUrl": "https://api.kraitos.app/releases/desktop/windows/EmploAI-0.1.19.msi",
            "sha256": digest,
        },
    }

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    info = ReleaseInfo(
        version="0.1.0-beta.14.4",
        release_tag="v0.1.0-beta.14.4",
        msi_version="0.1.18",
        channel="beta",
        github_repo="mighty-epic/emploai",
        primary_asset="EmploAI.msi",
        portable_asset="EmploAI-portable.zip",
        update_check_interval_hours=12,
        update_manifest_url="https://api.kraitos.app/api/releases/desktop/windows/latest",
    )

    update = find_available_update_from_manifest(info)
    assert update is not None
    assert update.asset_name == "EmploAI-0.1.19.msi"
    assert update.asset_url == "https://api.kraitos.app/releases/desktop/windows/EmploAI-0.1.19.msi"
    assert update.sha256 == digest


def test_find_available_update_falls_back_to_github_when_manifest_fails(monkeypatch):
    github_payload = [
        {
            "tag_name": "v0.1.0-beta.4",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-06-16T10:00:00Z",
            "assets": [
                {
                    "name": "EmploAI.msi",
                    "browser_download_url": "https://example.invalid/EmploAI.msi",
                }
            ],
        }
    ]
    calls = []

    def _fake_get(url, *args, **kwargs):
        calls.append(url)
        if "api.kraitos.app" in url:
            raise RuntimeError("manifest unavailable")
        return _FakeResponse(github_payload)

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", _fake_get)

    info = ReleaseInfo(
        version="0.1.0-beta.3",
        release_tag="v0.1.0-beta.3",
        msi_version="0.1.3",
        channel="beta",
        github_repo="mighty-epic/emploai",
        primary_asset="EmploAI.msi",
        portable_asset="EmploAI-portable.zip",
        update_check_interval_hours=12,
        update_manifest_url="https://api.kraitos.app/api/releases/desktop/windows/latest",
    )

    update = find_available_update(info)
    assert update is not None
    assert update.tag_name == "v0.1.0-beta.4"
    assert any("api.kraitos.app" in call for call in calls)
    assert any("api.github.com" in call for call in calls)


def test_launch_msi_update_writes_restart_script(tmp_path: Path, monkeypatch):
    installer = tmp_path / "EmploAI.msi"
    installer.write_text("fake", encoding="utf-8")
    restart_exe = tmp_path / "EmploAI.exe"
    restart_exe.write_text("fake", encoding="utf-8")

    captured = {}

    def _fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.subprocess, "Popen", _fake_popen)
    _launch_msi_update(tmp_path, installer, restart_exe)

    script_path = tmp_path / "updates" / "apply_update_and_restart.cmd"
    assert script_path.exists()
    script_body = script_path.read_text(encoding="utf-8")
    assert 'msiexec.exe /i "' in script_body
    assert str(installer) in script_body
    assert str(restart_exe) in script_body
    assert 'if "%MSI_EXIT%"=="3010" goto relaunch' in script_body
    assert 'if "%MSI_EXIT%"=="1641" goto relaunch' in script_body
    assert captured["args"][0:2] == ["cmd.exe", "/c"]


def test_check_for_updates_returns_serialized_update(monkeypatch, tmp_path: Path):
    deploy_dir = tmp_path / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text(
        '{"version":"0.1.0-beta.1","release_tag":"v0.1.0-beta.1","msi_version":"0.1.1","channel":"beta","github_repo":"mighty-epic/emploai","primary_asset":"EmploAI.msi","portable_asset":"EmploAI-portable.zip","update_check_interval_hours":0}',
        encoding="utf-8",
    )

    payload = [
        {
            "tag_name": "v0.1.0-beta.2",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-04-14T12:00:00Z",
            "assets": [
                {
                    "name": "EmploAI.msi",
                    "browser_download_url": "https://example.invalid/EmploAI.msi",
                }
            ],
        }
    ]

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    result = check_for_updates(tmp_path / "runtime", tmp_path, force=True)
    assert result["ok"] is True
    assert result["checked"] is True
    assert result["updateAvailable"] is True
    assert result["update"]["tagName"] == "v0.1.0-beta.2"


def test_check_for_updates_returns_cached_available_update_during_interval(monkeypatch, tmp_path: Path):
    deploy_dir = tmp_path / "deploy" / "windows"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "release_info.json").write_text(
        '{"version":"0.1.0-beta.1","release_tag":"v0.1.0-beta.1","msi_version":"0.1.1","channel":"beta","github_repo":"mighty-epic/emploai","primary_asset":"EmploAI.msi","portable_asset":"EmploAI-portable.zip","update_check_interval_hours":12}',
        encoding="utf-8",
    )
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "release_state.json").write_text(
        json.dumps(
            {
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
                "last_available_update": {
                    "version": "0.1.0-beta.2",
                    "tagName": "v0.1.0-beta.2",
                    "assetName": "EmploAI.msi",
                    "assetUrl": "https://example.invalid/EmploAI.msi",
                    "publishedAt": "2026-06-19T12:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(
        desktop_update.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should be skipped")),
    )

    result = check_for_updates(runtime_home, tmp_path, force=False)

    assert result["ok"] is True
    assert result["checked"] is False
    assert result["updateAvailable"] is True
    assert result["update"]["tagName"] == "v0.1.0-beta.2"


def test_install_available_update_returns_launch_payload(tmp_path: Path, monkeypatch):
    installer = tmp_path / "downloaded.msi"
    restart_exe = tmp_path / "EmploAI.exe"
    captured = {}

    def _fake_download(_home, _update):
        return installer

    def _fake_launch(_home, installer_path, restart_executable):
        captured["installer_path"] = installer_path
        captured["restart_executable"] = restart_executable

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update, "_download_update_asset", _fake_download)
    monkeypatch.setattr(desktop_update, "_launch_msi_update", _fake_launch)

    result = install_available_update(
        tmp_path,
        AvailableUpdate(
            version="0.1.0b2",
            tag_name="v0.1.0-beta.2",
            asset_name="EmploAI.msi",
            asset_url="https://example.invalid/EmploAI.msi",
            published_at=None,
        ),
        restart_executable=restart_exe,
    )

    assert result["ok"] is True
    assert result["launched"] is True
    assert str(captured["installer_path"]).endswith("downloaded.msi")
    assert captured["restart_executable"] == restart_exe
    assert result["restartExecutable"] == str(restart_exe)


def test_download_update_asset_verifies_sha256(tmp_path: Path, monkeypatch):
    content = b"fake-msi"
    digest = hashlib.sha256(content).hexdigest()

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeStreamResponse(content))

    installer = desktop_update._download_update_asset(
        tmp_path,
        AvailableUpdate(
            version="0.1.0b2",
            tag_name="v0.1.0-beta.2",
            asset_name="EmploAI.msi",
            asset_url="https://example.invalid/EmploAI.msi",
            published_at=None,
            sha256=digest,
        ),
    )

    assert installer.read_bytes() == content


def test_download_update_asset_rejects_sha256_mismatch(tmp_path: Path, monkeypatch):
    content = b"fake-msi"

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update.requests, "get", lambda *args, **kwargs: _FakeStreamResponse(content))

    with pytest.raises(ValueError, match="SHA-256"):
        desktop_update._download_update_asset(
            tmp_path,
            AvailableUpdate(
                version="0.1.0b2",
                tag_name="v0.1.0-beta.2",
                asset_name="EmploAI.msi",
                asset_url="https://example.invalid/EmploAI.msi",
                published_at=None,
                sha256="0" * 64,
            ),
        )

    assert not (tmp_path / "updates" / "EmploAI.msi").exists()


def test_install_latest_update_passes_restart_executable(tmp_path: Path, monkeypatch):
    restart_exe = tmp_path / "install" / "EmploAI.exe"
    update = AvailableUpdate(
        version="0.1.0b3",
        tag_name="v0.1.0-beta.3",
        asset_name="EmploAI.msi",
        asset_url="https://example.invalid/EmploAI.msi",
        published_at=None,
    )
    captured = {}

    import desktop_runtime.update as desktop_update

    monkeypatch.setattr(desktop_update, "find_available_update", lambda _info: update)

    def _fake_install(home, update_arg, *, restart_executable=None):
        captured["home"] = home
        captured["update"] = update_arg
        captured["restart_executable"] = restart_executable
        return {"ok": True, "launched": True}

    monkeypatch.setattr(desktop_update, "install_available_update", _fake_install)

    result = install_latest_update(tmp_path / "runtime", tmp_path, restart_executable=restart_exe)

    assert result["ok"] is True
    assert captured["home"] == tmp_path / "runtime"
    assert captured["update"] is update
    assert captured["restart_executable"] == restart_exe
