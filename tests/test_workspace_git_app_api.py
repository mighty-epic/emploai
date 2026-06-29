import shutil
import subprocess

from fastapi.testclient import TestClient

from mobile_app.backend import app_server


def _client(monkeypatch):
    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 1})
    return TestClient(app_server.create_app())


def test_workspace_git_endpoint_rejects_missing_path(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/app/workspace/git", headers={"Authorization": "Bearer local"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing workspace path"


def test_workspace_git_endpoint_reports_non_repo_cleanly(tmp_path, monkeypatch):
    client = _client(monkeypatch)
    response = client.get(
        "/api/app/workspace/git",
        params={"path": str(tmp_path)},
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requestedPath"] == str(tmp_path)
    assert payload["resolvedPath"]
    assert payload["isGitRepo"] is False
    assert payload["repoRoot"] is None
    assert payload["branches"] == []


def test_workspace_git_checkout_switches_existing_branch(tmp_path, monkeypatch):
    if not shutil.which("git"):
        return

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "branch", "feature/mobile"], cwd=tmp_path, check=True)

    client = _client(monkeypatch)
    before = client.get(
        "/api/app/workspace/git",
        params={"path": str(tmp_path)},
        headers={"Authorization": "Bearer local"},
    )
    assert before.status_code == 200
    assert before.json()["isGitRepo"] is True
    assert "feature/mobile" in before.json()["branches"]

    switched = client.post(
        "/api/app/workspace/git/checkout",
        json={"path": str(tmp_path), "branch": "feature/mobile"},
        headers={"Authorization": "Bearer local"},
    )

    assert switched.status_code == 200
    assert switched.json()["isGitRepo"] is True
    assert switched.json()["currentBranch"] == "feature/mobile"
    assert switched.json()["error"] is None


def test_workspace_git_endpoint_rejects_direct_remote_session(monkeypatch):
    calls = []

    def fail_if_called(path):
        calls.append(path)
        raise AssertionError("remote sessions must not run git commands on the cloud backend")

    monkeypatch.setattr(
        app_server,
        "_resolve_token",
        lambda _authorization: {"auth_kind": "remote_session", "actor_kind": "desktop", "user_id": 1},
    )
    monkeypatch.setattr(app_server, "_workspace_git_state", fail_if_called)
    client = TestClient(app_server.create_app())

    response = client.get(
        "/api/app/workspace/git",
        params={"path": "C:/work/app"},
        headers={"Authorization": "Bearer remote"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]
    assert calls == []


def test_workspace_git_checkout_is_rate_limited(tmp_path, monkeypatch):
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = _client(monkeypatch)
    payload = {"path": str(tmp_path), "branch": "feature/mobile"}

    statuses = [
        client.post(
            "/api/app/workspace/git/checkout",
            json=payload,
            headers={"Authorization": "Bearer local"},
        ).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/app/workspace/git/checkout",
        json=payload,
        headers={"Authorization": "Bearer local"},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429
