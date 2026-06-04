from mobile_app.backend.auth_store import AppAuthStore


def test_ensure_device_token_reuses_existing_token_for_same_device_key(tmp_path):
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
    assert first["access_token"] == second["access_token"]
    assert store.resolve_access_token(first["access_token"]) is not None


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
