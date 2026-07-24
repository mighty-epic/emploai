from __future__ import annotations

import pytest

from app_backend import remote_desktop_client


@pytest.mark.asyncio
async def test_connection_loss_stops_only_affected_company_tasks(monkeypatch):
    calls = []

    async def fake_request_json(
        _client,
        *,
        method,
        url,
        token,
        json_body=None,
        company_id=None,
    ):
        calls.append(
            {
                "method": method,
                "url": url,
                "token": token,
                "company_id": company_id,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(
        remote_desktop_client,
        "_request_json",
        fake_request_json,
    )
    remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
    remote_desktop_client.FLEET_ACTIVE_TASK_COMPANIES.clear()
    remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()
    remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.update(
        {
            "task-a": "session a",
            "task-b": "session-b",
        }
    )
    remote_desktop_client.FLEET_ACTIVE_TASK_COMPANIES.update(
        {
            "task-a": "company-a",
            "task-b": "company-b",
        }
    )
    credentials = remote_desktop_client.LocalRuntimeCredentials(
        api_base_url="http://127.0.0.1:9999",
        access_token="local-token",
    )

    try:
        await remote_desktop_client._stop_company_tasks_after_connection_loss(
            credentials,
            company_id="company-a",
        )

        assert len(calls) == 1
        assert calls[0]["method"] == "POST"
        assert calls[0]["company_id"] == "company-a"
        assert calls[0]["url"].endswith(
            "/api/app/agent/control/stop?session_id=session+a"
        )
        assert "task-a" in remote_desktop_client.FLEET_STOP_REQUESTED_TASKS
        assert "task-b" not in remote_desktop_client.FLEET_STOP_REQUESTED_TASKS
    finally:
        remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
        remote_desktop_client.FLEET_ACTIVE_TASK_COMPANIES.clear()
        remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()
