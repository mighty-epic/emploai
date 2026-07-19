from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app_backend import app_server
from app_backend.local_profile_policy import sanitize_user_profile
from app_backend.remote_control_store import RemoteControlPlaneStore
from shared.fleet_connection import (
    FLEET_CONNECTION_FILENAME,
    LEGACY_ACCOUNT_SESSION_FILENAME,
    load_fleet_connection,
)
from shared.standalone_policy import (
    cloud_backend_enabled,
    mobile_connection_enabled,
    standalone_desktop_enabled,
)


ROOT = Path(__file__).resolve().parents[1]


def test_local_profile_sanitizer_keeps_bounded_profile_data():
    profile = sanitize_user_profile(
        {
            "preferences": {"verbose_mode": True},
            "metadata": {f"field_{index}": index for index in range(150)},
        }
    )

    assert profile["preferences"]["verbose_mode"] is True
    assert len(profile["metadata"]) == 100


def test_hosted_modes_cannot_be_enabled_by_environment(monkeypatch):
    monkeypatch.setenv("EMPLOAI_CLOUD_BACKEND_ENABLED", "1")
    monkeypatch.setenv("EMPLOAI_MOBILE_CONNECTION_ENABLED", "1")
    monkeypatch.setenv("EMPLOAI_STANDALONE_DESKTOP", "0")

    assert cloud_backend_enabled() is False
    assert mobile_connection_enabled() is False
    assert standalone_desktop_enabled() is True


def test_account_and_mobile_routes_are_not_mounted():
    paths = {str(route.path) for route in app_server.create_app().routes}

    assert not any(path.startswith("/api/remote/auth") for path in paths)
    assert not any(path.startswith("/api/remote/account") for path in paths)
    assert not any(path.startswith("/api/remote/pair") for path in paths)
    assert not any(path.startswith("/api/app/pair") for path in paths)
    assert "/ws/remote/mobile" not in paths
    assert "/ws/remote/desktop" in paths
    assert "/api/fleet/enrollments" in paths
    assert "/api/fleet/enrollments/complete" in paths
    assert "/api/fleet/delegations/route" in paths
    assert "/api/fleet/context-inspection" in paths
    assert "/api/fleet/context/search" in paths
    assert "/api/runtime-packs" in paths
    assert "/api/runtime-packs/{pack_id}/install" in paths


def test_fleet_store_exposes_no_account_login_or_mobile_pairing(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    for method_name in (
        "register_user",
        "login",
        "begin_signup_otp",
        "begin_login_otp",
        "create_oauth_login_request",
        "create_pairing",
        "complete_pairing",
        "repair_mobile_pairing",
        "upsert_user_secrets",
        "reveal_user_secrets",
    ):
        assert not hasattr(store, method_name)


def test_desktop_does_not_expose_account_ipc():
    main_source = (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8")
    preload_source = (ROOT / "desktop_app" / "preload.js").read_text(encoding="utf-8")

    assert "ipcMain.handle('emploai:remote-auth:" not in main_source
    assert "ipcRenderer.invoke('emploai:remote-auth:" not in preload_source
    assert "login:" not in preload_source.split("remoteAuth:", 1)[1].split("fleet:", 1)[0]


def test_active_runtime_has_no_hosted_account_bootstrap():
    runtime_source = (ROOT / "app_backend" / "runtime.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "app_backend" / "remote_desktop_client.py").read_text(encoding="utf-8")
    backend_source = (ROOT / "desktop_runtime" / "backend.py").read_text(encoding="utf-8")
    artifact_source = (ROOT / "shared" / "artifact_store.py").read_text(encoding="utf-8")

    for source in (runtime_source, worker_source, backend_source, artifact_source):
        assert "api.kraitos.app" not in source
        assert "/api/remote/auth" not in source
        assert "/api/remote/account" not in source
    assert "desktop_runtime import cloud" not in backend_source
    assert "CloudObjectStore" not in artifact_source


def test_production_clients_contain_no_hosted_account_requests():
    sources = [
        (ROOT / "desktop_app" / "main.js").read_text(encoding="utf-8"),
        (ROOT / "desktop_app" / "preload.js").read_text(encoding="utf-8"),
        (ROOT / "desktop_app" / "remote_control_services.js").read_text(encoding="utf-8"),
        (ROOT / "desktop_app" / "renderer_client" / "src" / "lib" / "appApi.ts").read_text(encoding="utf-8"),
    ]
    forbidden = (
        "/api/remote/auth",
        "/api/remote/account",
        "/api/remote/pair",
        "ipcRenderer.invoke('emploai:remote-auth:",
        "ipcMain.handle('emploai:remote-auth:",
    )

    for source in sources:
        for marker in forbidden:
            assert marker not in source


def test_legacy_session_migration_accepts_only_yggdrasil(tmp_path: Path):
    legacy_path = tmp_path / LEGACY_ACCOUNT_SESSION_FILENAME
    legacy_path.write_text(
        json.dumps(
            {
                "apiBaseUrl": "https://api.kraitos.app",
                "sessionToken": "hosted-token",
                "desktop": {"desktop_id": "hosted-desktop"},
            }
        ),
        encoding="utf-8",
    )

    assert load_fleet_connection(tmp_path) == {}
    assert legacy_path.exists()
    assert not (tmp_path / FLEET_CONNECTION_FILENAME).exists()

    legacy_path.write_text(
        json.dumps(
            {
                "apiBaseUrl": "http://[200::abcd]:8787",
                "sessionToken": "fleet-token",
                "desktop": {"desktop_id": "fleet-desktop"},
                "transport": {"kind": "yggdrasil"},
            }
        ),
        encoding="utf-8",
    )
    connection = load_fleet_connection(tmp_path)

    assert connection["sessionToken"] == "fleet-token"
    assert connection["transport"]["kind"] == "yggdrasil"
    assert not legacy_path.exists()
    assert (tmp_path / FLEET_CONNECTION_FILENAME).exists()


def test_desktop_fleet_service_rejects_non_local_backend_without_network(tmp_path: Path):
    service_path = ROOT / "desktop_app" / "remote_control_services.js"
    script = r"""
const { createRemoteControlServices } = require(process.argv[1]);
let fetchCalls = 0;
const services = createRemoteControlServices({
  net: { fetch() { fetchCalls += 1; throw new Error('network must not run'); } },
  shell: {},
  safeStorage: { isEncryptionAvailable: () => false },
  resolveRuntimeHome: () => process.argv[2],
  saveSetup: async () => ({}),
  getBootstrapCache: () => ({ apiBaseUrl: 'https://api.kraitos.app', accessToken: 'token' }),
});
services.fleetSnapshot().then(
  () => process.exit(2),
  (error) => {
    if (!String(error.message || error).includes('only permits the local EmploAI backend')) process.exit(3);
    if (fetchCalls !== 0) process.exit(4);
  },
);
"""
    result = subprocess.run(
        ["node", "-e", script, str(service_path), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_desktop_fleet_snapshot_refreshes_stale_local_session_once(tmp_path: Path):
    service_path = ROOT / "desktop_app" / "remote_control_services.js"
    script = r"""
const { createRemoteControlServices } = require(process.argv[1]);
let currentToken = 'stale-token';
let refreshCalls = 0;
let fetchCalls = 0;
const services = createRemoteControlServices({
  net: {
    async fetch(_url, options) {
      fetchCalls += 1;
      const authorization = options?.headers?.Authorization || '';
      if (authorization === 'Bearer stale-token') {
        return new Response(JSON.stringify({ detail: 'Local runtime session expired.' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ workers: [], tasks: [], reports: [], desktops: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  },
  shell: {},
  safeStorage: { isEncryptionAvailable: () => false },
  resolveRuntimeHome: () => process.argv[2],
  saveSetup: async () => ({}),
  getBootstrapCache: () => ({ apiBaseUrl: 'http://[::1]:8787', accessToken: currentToken }),
  refreshBootstrapCache: async () => {
    refreshCalls += 1;
    currentToken = 'fresh-token';
  },
});
services.fleetSnapshot().then(
  (snapshot) => {
    if (!Array.isArray(snapshot.workers)) process.exit(2);
    if (refreshCalls !== 1 || fetchCalls !== 2) process.exit(3);
  },
  (error) => {
    console.error(error);
    process.exit(4);
  },
);
"""
    result = subprocess.run(
        ["node", "-e", script, str(service_path), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
