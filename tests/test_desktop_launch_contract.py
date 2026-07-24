import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_package_scripts_are_the_desktop_launch_contract():
    package = json.loads(_read("package.json"))
    scripts = package["scripts"]

    assert scripts["start"] == "powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/desktop/start.ps1"
    assert scripts["start:fast"] == "powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/desktop/start.ps1 -Fast"
    assert scripts["setup"] == "powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/desktop/setup.ps1"
    assert scripts["check"] == "npm run desktop:check"
    assert scripts["desktop:check"] == "powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/desktop/start.ps1 -CheckOnly"


def test_root_windows_wrappers_delegate_to_desktop_scripts_and_preserve_errors():
    start_bat = _read("start-desktop.bat")
    setup_bat = _read("setup-desktop.bat")

    assert 'cd /d "%~dp0"' in start_bat
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\desktop\\start.ps1" %*' in start_bat
    assert "EmploAI failed to start" in start_bat
    assert "exit /b %EXIT_CODE%" in start_bat

    assert 'cd /d "%~dp0"' in setup_bat
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\desktop\\setup.ps1" %*' in setup_bat
    assert "EmploAI setup failed" in setup_bat
    assert "exit /b %EXIT_CODE%" in setup_bat


def test_start_script_repairs_missing_core_python_dependencies_unless_disabled():
    start_script = _read("scripts/desktop/start.ps1")

    assert '$RequirementsPath = Join-Path $RepoRoot "requirements.txt"' in start_script
    assert "function Ensure-CorePythonDependencies" in start_script
    assert "Invoke-PythonRuntime @(\"-m\", \"pip\", \"install\", \"-r\", $RequirementsPath)" in start_script
    assert "if ($NoInstall)" in start_script
    assert "omit -NoInstall so startup can install them" in start_script
    assert "Ensure-CorePythonDependencies" in start_script


def test_setup_and_start_scripts_use_the_same_python_override_env_var():
    start_script = _read("scripts/desktop/start.ps1")
    setup_script = _read("scripts/desktop/setup.ps1")

    assert "EMPLOAI_DESKTOP_PYTHON" in start_script
    assert "EMPLOAI_DESKTOP_PYTHON" in setup_script
    assert "Invoke-PythonRuntime" in start_script
    assert "Invoke-PythonRuntime" in setup_script


def test_start_script_detaches_electron_without_a_persistent_npm_wrapper():
    start_script = _read("scripts/desktop/start.ps1")

    assert "function Start-DesktopShell" in start_script
    assert "node_modules\\electron\\dist\\electron.exe" in start_script
    assert "Start-Process" in start_script
    assert '-ArgumentList "."' in start_script
    assert "desktop_shell.pid.json" in start_script
    assert "Desktop shell is already running" in start_script
    assert "desktop_shell_stderr.log" in start_script
    assert 'Invoke-NpmInDirectory $DesktopAppDir @("run", "start:electron")' not in start_script


def test_powershell_desktop_launch_scripts_parse_when_powershell_is_available():
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is not available on PATH")

    command = (
        "$null = [scriptblock]::Create((Get-Content -Raw 'start.ps1')); "
        "$null = [scriptblock]::Create((Get-Content -Raw 'scripts/desktop/start.ps1')); "
        "$null = [scriptblock]::Create((Get-Content -Raw 'scripts/desktop/setup.ps1')); "
        "'desktop_launch_scripts_parse_ok'"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-Command", command],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "desktop_launch_scripts_parse_ok" in result.stdout
