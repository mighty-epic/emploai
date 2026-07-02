import importlib


def test_desktop_runtime_imports_from_preferred_package_name():
    backend = importlib.import_module("desktop_runtime.backend")
    config = importlib.import_module("desktop_runtime.config")

    assert callable(backend.main)
    assert callable(config.runtime_home)
    assert backend._self_command()[1:3] == ["-m", "desktop_runtime.backend"]


def test_legacy_deploy_windows_runtime_import_paths_alias_preferred_modules():
    assert importlib.import_module("deploy.windows.release_backend") is importlib.import_module("desktop_runtime.backend")
    assert importlib.import_module("deploy.windows.release_runtime") is importlib.import_module("desktop_runtime.config")
    assert importlib.import_module("deploy.windows.release_update") is importlib.import_module("desktop_runtime.update")
