from pathlib import Path

from deploy.windows.release_update import (
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


def test_should_check_for_updates_respects_interval(tmp_path: Path):
    assert should_check_for_updates(tmp_path, 12)


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
