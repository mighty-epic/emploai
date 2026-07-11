from __future__ import annotations

import json

import pytest

from shared import fleet_yggdrasil
from shared.fleet_connection import FLEET_CONNECTION_FILENAME


def test_yggdrasil_pairing_token_round_trips_ipv6_manager_url():
    manager_url = fleet_yggdrasil.manager_url_for_yggdrasil("0200::abcd", 8787)
    payload = fleet_yggdrasil.build_pairing_payload(
        manager_url=manager_url,
        manager_yggdrasil_ip="0200::abcd",
        manager_public_key="abc123",
        enrollment_token="fw_test_token",
        expires_in_seconds=120,
        display_name="Worker One",
    )

    token = fleet_yggdrasil.encode_pairing_token(payload)
    decoded = fleet_yggdrasil.decode_pairing_token(token)

    assert token.startswith(fleet_yggdrasil.PAIRING_TOKEN_PREFIX)
    assert decoded["transport"] == "yggdrasil"
    assert decoded["manager_url"] == "http://[200::abcd]:8787"
    assert decoded["manager_yggdrasil_ip"] == "200::abcd"
    assert decoded["enrollment_token"] == "fw_test_token"


def test_yggdrasil_pairing_token_rejects_non_yggdrasil_url():
    payload = {
        "version": 1,
        "transport": "yggdrasil",
        "manager_url": "http://127.0.0.1:8787",
        "enrollment_token": "fw_bad",
    }

    with pytest.raises(ValueError, match="Yggdrasil manager URL"):
        fleet_yggdrasil.decode_pairing_token(fleet_yggdrasil.encode_pairing_token(payload))


def test_parse_yggdrasil_self_accepts_json_and_text_shapes():
    parsed_json = fleet_yggdrasil.parse_yggdrasil_self(
        json.dumps({"response": {"address": "0200::1234", "box_pub_key": "a" * 64}})
    )
    parsed_text = fleet_yggdrasil.parse_yggdrasil_self(
        "IPv6 address: 0200::5678\nPublic key: " + ("b" * 64)
    )

    assert parsed_json == {"address": "200::1234", "public_key": "a" * 64}
    assert parsed_text == {"address": "200::5678", "public_key": "b" * 64}


def test_select_release_asset_matches_windows_x64_msi():
    asset = fleet_yggdrasil.select_release_asset(
        [
            {"name": "yggdrasil-0.5.14-arm64.msi", "browser_download_url": "https://example/arm64.msi"},
            {"name": "yggdrasil-0.5.14-x64.msi", "browser_download_url": "https://example/x64.msi"},
        ],
        pattern="x64.msi",
    )

    assert asset["browser_download_url"] == "https://example/x64.msi"


def test_update_yggdrasil_peers_config_replaces_empty_peer_block():
    updated, changed = fleet_yggdrasil.update_yggdrasil_peers_config(
        "Peers: []\nIfName: auto\n",
        ["tls://peer-one.example:1234", "quic://peer-two.example:1234"],
    )

    assert changed is True
    assert "Peers: [" in updated
    assert "tls://peer-one.example:1234" in updated
    assert "quic://peer-two.example:1234" in updated
    assert "IfName: auto" in updated


def test_update_yggdrasil_peers_config_is_idempotent_when_peers_exist():
    config = "Peers: [\n  tls://peer-one.example:1234\n]\n"

    updated, changed = fleet_yggdrasil.update_yggdrasil_peers_config(
        config,
        ["tls://peer-one.example:1234"],
    )

    assert changed is False
    assert updated == config


def test_complete_worker_enrollment_writes_local_fleet_connection(tmp_path, monkeypatch):
    manager_url = fleet_yggdrasil.manager_url_for_yggdrasil("0200::abcd", 8787)
    payload = fleet_yggdrasil.build_pairing_payload(
        manager_url=manager_url,
        manager_yggdrasil_ip="0200::abcd",
        enrollment_token="fw_join",
        expires_in_seconds=120,
    )
    token = fleet_yggdrasil.encode_pairing_token(payload)
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {
            "session_token": "session-token",
            "user_id": 1,
            "desktop": {"desktop_id": "dsk_worker"},
            "worker": {"worker_id": "wrk_worker"},
        }

    monkeypatch.setattr(fleet_yggdrasil, "request_json", fake_request_json)

    completed = fleet_yggdrasil.complete_worker_enrollment(
        pairing_token=token,
        home=tmp_path,
        device_name="Worker",
        device_platform="desktop",
        device_key="worker-key",
    )

    assert completed["session_token"] == "session-token"
    assert calls[0]["url"] == f"{manager_url}/api/fleet/enrollments/complete"
    assert calls[0]["payload"]["enrollment_token"] == "fw_join"
    session = json.loads((tmp_path / FLEET_CONNECTION_FILENAME).read_text(encoding="utf-8"))
    assert session["apiBaseUrl"] == manager_url
    assert session["sessionToken"] == "session-token"
    assert session["transport"]["kind"] == "yggdrasil"
