import importlib


def test_app_backend_imports_from_new_package_name():
    module = importlib.import_module("app_backend")

    assert callable(module.create_app)
    assert callable(module.start_embedded_app_server_if_enabled)


def test_legacy_mobile_backend_import_path_is_compatible():
    legacy = importlib.import_module("mobile_app.backend")
    legacy_submodule = importlib.import_module("mobile_app.backend.auth_store")

    assert callable(legacy.create_app)
    assert legacy_submodule.AppAuthStore.__name__ == "AppAuthStore"
    assert "app_backend" in str(legacy_submodule.__file__)


def test_legacy_app_backend_desktop_runtime_module_is_compatible():
    preferred = importlib.import_module("app_backend.local_runtime_server")
    legacy = importlib.import_module("app_backend.desktop_runtime")

    assert callable(preferred.run_desktop_runtime_server)
    assert legacy.run_desktop_runtime_server is preferred.run_desktop_runtime_server
    assert callable(legacy.main)
