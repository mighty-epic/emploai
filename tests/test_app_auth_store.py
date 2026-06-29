import json

from mobile_app.backend.auth_store import AppAuthStore


def test_ensure_device_token_reuses_device_without_persisting_plaintext_token(tmp_path):
    store = AppAuthStore(root_path=tmp_path)

    first = store.ensure_device_token(
        user_id=42,
        device_name="Desktop",
        device_platform="desktop-electron",
        token_ttl_seconds=3600,
        device_key="desktop-local",
    )
    second = store.ensure_device_token(
        user_id=42,
        device_name="Desktop",
        device_platform="desktop-electron",
        token_ttl_seconds=3600,
        device_key="desktop-local",
    )

    assert first["device_id"] == second["device_id"]
    assert first["access_token"] != second["access_token"]
    assert store.resolve_access_token(first["access_token"]) is not None
    assert store.resolve_access_token(second["access_token"]) is not None

    raw_store = json.loads((tmp_path / "app_auth_store.json").read_text(encoding="utf-8"))
    assert first["access_token"] not in json.dumps(raw_store)
    assert second["access_token"] not in json.dumps(raw_store)
    assert all("token_value" not in token for token in raw_store["tokens"].values())


def test_resolve_access_token_reloads_token_created_by_another_store(tmp_path):
    daemon_store = AppAuthStore(root_path=tmp_path)
    helper_store = AppAuthStore(root_path=tmp_path)

    issued = helper_store.ensure_device_token(
        user_id=42,
        device_name="Desktop",
        device_platform="desktop-electron",
        token_ttl_seconds=3600,
        device_key="desktop-local",
    )

    resolved = daemon_store.resolve_access_token(issued["access_token"])

    assert resolved is not None
    assert resolved["user_id"] == 42
    assert resolved["device_id"] == issued["device_id"]


def test_ensure_device_token_caps_active_tokens_per_device(tmp_path):
    store = AppAuthStore(root_path=tmp_path)

    issued = [
        store.ensure_device_token(
            user_id=42,
            device_name="Desktop",
            device_platform="desktop-electron",
            token_ttl_seconds=3600,
            device_key="desktop-local",
        )
        for _ in range(25)
    ]

    raw_store = json.loads((tmp_path / "app_auth_store.json").read_text(encoding="utf-8"))
    assert len(raw_store["tokens"]) == 20
    assert store.resolve_access_token(issued[-1]["access_token"]) is not None
    assert store.resolve_access_token(issued[0]["access_token"]) is None


def test_resolve_access_token_tolerates_last_used_save_lock(tmp_path, monkeypatch):
    store = AppAuthStore(root_path=tmp_path)
    issued = store.ensure_device_token(
        user_id=42,
        device_name="Desktop",
        device_platform="desktop-electron",
        token_ttl_seconds=3600,
        device_key="desktop-local",
    )

    device = store._data["devices"][issued["device_id"]]
    token = next(
        token_data
        for token_data in store._data["tokens"].values()
        if token_data["device_id"] == issued["device_id"]
    )
    device["last_used_at"] = 0
    token["last_used_at"] = 0

    def locked_save():
        raise PermissionError("locked")

    monkeypatch.setattr(store, "_save", locked_save)

    resolved = store.resolve_access_token(issued["access_token"])

    assert resolved is not None
    assert resolved["user_id"] == 42
