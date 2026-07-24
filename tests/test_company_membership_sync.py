from __future__ import annotations

import asyncio

import pytest

from app_backend import remote_desktop_client
from app_backend.company_store import CompanyStore
from shared.fleet_connection import load_fleet_connection, write_fleet_connection


def _protect(payload, *, purpose):
    return {
        "storage": "test-vault",
        "purpose": purpose,
        "payload": dict(payload),
    }


def _unprotect(envelope, *, purpose):
    assert envelope["purpose"] == purpose
    return dict(envelope["payload"])


def _store(path):
    return CompanyStore(
        root_path=path,
        protect_payload=_protect,
        unprotect_payload=_unprotect,
    )


def test_paired_host_persists_only_newer_matching_signed_membership(
    monkeypatch,
    tmp_path,
):
    root_store = _store(tmp_path / "root")
    company = root_store.create_root_company(
        computer_id="root-computer",
        computer_name="Root PC",
        display_name="Root Company",
    )
    first_bundle = root_store.register_child_membership(
        company_id=company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="child-computer",
        child_computer_name="Child PC",
    )
    child_home = tmp_path / "child-home"
    write_fleet_connection(
        home=child_home,
        payload={
            "apiBaseUrl": "http://[200::1]:8787",
            "managerUrl": "http://[200::1]:8787",
            "sessionToken": "paired-session",
            "desktop": {
                "desktop_id": "child-computer",
                "display_name": "Child PC",
            },
            "transport": {"kind": "yggdrasil"},
            "companyMembership": first_bundle,
        },
    )
    root_store.update_company(
        company_id=company["company_id"],
        manifest_updates={"purpose": "Current purpose"},
    )
    latest_bundle = root_store.issue_child_membership_bundle(
        company_id=company["company_id"],
        child_computer_id="child-computer",
    )
    monkeypatch.setattr(
        remote_desktop_client,
        "runtime_home",
        lambda: child_home,
    )

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_company_membership_sync",
            payload={"bundle": latest_bundle},
            local_api_base_url="",
            local_token="",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )
    assert result["updated"] is True
    assert (
        load_fleet_connection(child_home)["companyMembership"]["signature"]
        == latest_bundle["signature"]
    )

    with pytest.raises(PermissionError, match="older"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="fleet_company_membership_sync",
                payload={"bundle": first_bundle},
                local_api_base_url="",
                local_token="",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )
