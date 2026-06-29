import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_release_hygiene.py"


def _load_release_hygiene_module():
    spec = importlib.util.spec_from_file_location("check_release_hygiene", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_release_versions_are_aligned():
    module = _load_release_hygiene_module()

    result = module.check_release_versions(REPO_ROOT)

    assert result.errors == []


def test_release_branding_contract_is_explicit():
    module = _load_release_hygiene_module()

    result = module.check_release_branding_contract(REPO_ROOT)

    assert result.errors == []


def test_remote_control_release_defaults_are_broker_ready():
    module = _load_release_hygiene_module()

    result = module.check_remote_control_deployment_defaults(REPO_ROOT)

    assert result.errors == []


def test_remote_control_release_defaults_list_all_model_provider_keys():
    module = _load_release_hygiene_module()
    env_path = REPO_ROOT / "deploy" / "vps" / "linux" / "remote_control.env.example"
    values = module._load_env_file(env_path)

    assert module.REMOTE_CONTROL_PROVIDER_ENV_VARS <= set(values)


def test_release_hygiene_cli_can_skip_dirty_tree_check():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--skip-git-clean-check"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Release hygiene check passed." in result.stdout
