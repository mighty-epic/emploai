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

