from pathlib import Path

from deploy.windows.release_update import (
    _launch_msi_update,
    ReleaseInfo,
    find_available_update,
    load_release_info,
    should_check_for_updates,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


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

    import deploy.windows.release_update as release_update

    monkeypatch.setattr(release_update.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

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

    import deploy.windows.release_update as release_update

    monkeypatch.setattr(release_update.subprocess, "Popen", _fake_popen)
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
