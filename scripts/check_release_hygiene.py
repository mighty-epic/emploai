"""Release hygiene checks for EmploAI/Kraitos deliverables."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_REMOTE_CONTROL_ROUTING_MODES = {"single_process", "sqlite_broker"}
REMOTE_CONTROL_PROVIDER_ENV_VARS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
}


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _root_package_version(lock_data: dict[str, Any]) -> str | None:
    root_package = lock_data.get("packages", {}).get("")
    if isinstance(root_package, dict):
        value = root_package.get("version")
        return str(value) if value is not None else None
    return None


def _check_equal(errors: list[str], label: str, actual: Any, expected: str) -> None:
    if actual != expected:
        errors.append(f"{label} is {actual!r}; expected {expected!r}.")


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_release_versions(repo_root: Path = REPO_ROOT) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    release_info = _load_json(repo_root / "deploy" / "windows" / "release_info.json")
    mobile_package = _load_json(repo_root / "mobile_app" / "client" / "package.json")
    mobile_lock = _load_json(repo_root / "mobile_app" / "client" / "package-lock.json")
    app_config = _load_json(repo_root / "mobile_app" / "client" / "app.json")
    desktop_package = _load_json(repo_root / "desktop_app" / "package.json")
    desktop_lock = _load_json(repo_root / "desktop_app" / "package-lock.json")

    expected_version = str(release_info.get("version") or "").strip()
    if not expected_version:
        errors.append("deploy/windows/release_info.json must define a non-empty version.")
        return CheckResult(errors=errors, warnings=warnings)

    expected_tag = f"v{expected_version}"
    _check_equal(errors, "deploy/windows/release_info.json release_tag", release_info.get("release_tag"), expected_tag)

    expo = app_config.get("expo") or {}
    mobile_release = (expo.get("extra") or {}).get("mobileRelease") or {}

    _check_equal(errors, "mobile package version", mobile_package.get("version"), expected_version)
    _check_equal(errors, "mobile package-lock version", mobile_lock.get("version"), expected_version)
    _check_equal(errors, "mobile package-lock root package version", _root_package_version(mobile_lock), expected_version)
    _check_equal(errors, "Expo app version", expo.get("version"), expected_version)
    _check_equal(errors, "Expo mobileRelease.version", mobile_release.get("version"), expected_version)
    _check_equal(errors, "Expo mobileRelease.desktopCompatibility", mobile_release.get("desktopCompatibility"), expected_version)
    _check_equal(errors, "desktop package version", desktop_package.get("version"), expected_version)
    _check_equal(errors, "desktop package-lock version", desktop_lock.get("version"), expected_version)
    _check_equal(errors, "desktop package-lock root package version", _root_package_version(desktop_lock), expected_version)

    return CheckResult(errors=errors, warnings=warnings)


def check_release_branding_contract(repo_root: Path = REPO_ROOT) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    release_info = _load_json(repo_root / "deploy" / "windows" / "release_info.json")
    mobile_package = _load_json(repo_root / "mobile_app" / "client" / "package.json")
    mobile_lock = _load_json(repo_root / "mobile_app" / "client" / "package-lock.json")
    app_config = _load_json(repo_root / "mobile_app" / "client" / "app.json")
    desktop_package = _load_json(repo_root / "desktop_app" / "package.json")
    desktop_lock = _load_json(repo_root / "desktop_app" / "package-lock.json")
    wix_source = (repo_root / "deploy" / "windows" / "EmploAI.wxs").read_text(encoding="utf-8")

    expo = app_config.get("expo") or {}
    mobile_release = (expo.get("extra") or {}).get("mobileRelease") or {}
    expo_scheme = expo.get("scheme") if isinstance(expo.get("scheme"), list) else []

    _check_equal(errors, "mobile package name", mobile_package.get("name"), "kraitos-mobile")
    _check_equal(errors, "mobile package-lock name", mobile_lock.get("name"), "kraitos-mobile")
    _check_equal(errors, "mobile package-lock root package name", (mobile_lock.get("packages") or {}).get("", {}).get("name"), "kraitos-mobile")
    _check_equal(errors, "Expo app display name", expo.get("name"), "Kraitos")
    _check_equal(errors, "Expo slug", expo.get("slug"), "emploai-app")
    _check_equal(errors, "Expo Android package", (expo.get("android") or {}).get("package"), "app.kraitos.mobile")
    _check_equal(errors, "Expo mobileRelease.apiBaseUrl", mobile_release.get("apiBaseUrl"), "https://api.kraitos.app")
    for scheme in ("kraitos", "emploai"):
        if scheme not in expo_scheme:
            errors.append(f"Expo scheme list must include {scheme!r}.")

    _check_equal(errors, "desktop package name", desktop_package.get("name"), "emploai-desktop-shell")
    _check_equal(errors, "desktop package-lock name", desktop_lock.get("name"), "emploai-desktop-shell")
    _check_equal(errors, "desktop package-lock root package name", (desktop_lock.get("packages") or {}).get("", {}).get("name"), "emploai-desktop-shell")
    _check_equal(errors, "desktop release GitHub repo", release_info.get("github_repo"), "mighty-epic/emploai-releases")
    _check_equal(errors, "desktop primary asset", release_info.get("primary_asset"), "EmploAI.msi")
    _check_equal(errors, "desktop portable asset", release_info.get("portable_asset"), "EmploAI-portable.zip")
    if not str(release_info.get("update_manifest_url") or "").startswith("https://api.kraitos.app/"):
        errors.append("Desktop update manifest URL must stay under https://api.kraitos.app/.")

    for snippet in (
        'Name="EmploAI Beta"',
        'Description="EmploAI Windows beta installer"',
        'Value="[INSTALLDIR]EmploAI.exe"',
        'Description="Launch EmploAI Beta"',
    ):
        if snippet not in wix_source:
            errors.append(f"Windows installer branding is missing {snippet!r}.")

    return CheckResult(errors=errors, warnings=warnings)


def check_remote_control_deployment_defaults(repo_root: Path = REPO_ROOT) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    env_path = repo_root / "deploy" / "vps" / "linux" / "remote_control.env.example"
    values = _load_env_file(env_path)

    routing_mode = values.get("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE")
    if routing_mode not in SUPPORTED_REMOTE_CONTROL_ROUTING_MODES:
        errors.append(
            "deploy/vps/linux/remote_control.env.example sets an unsupported "
            f"EMPLOAI_REMOTE_CONTROL_ROUTING_MODE={routing_mode!r}; expected one of "
            f"{sorted(SUPPORTED_REMOTE_CONTROL_ROUTING_MODES)}."
        )
    if routing_mode != "sqlite_broker":
        errors.append(
            "deploy/vps/linux/remote_control.env.example must default "
            "EMPLOAI_REMOTE_CONTROL_ROUTING_MODE to 'sqlite_broker' so public deployments are broker-ready."
        )

    unsafe_bypass = str(values.get("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS") or "").lower()
    if unsafe_bypass not in {"", "0", "false", "no", "off"}:
        errors.append(
            "deploy/vps/linux/remote_control.env.example must not enable "
            "EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS for public release deployments."
        )

    missing_provider_keys = sorted(key for key in REMOTE_CONTROL_PROVIDER_ENV_VARS if key not in values)
    if missing_provider_keys:
        errors.append(
            "deploy/vps/linux/remote_control.env.example is missing provider env vars: "
            + ", ".join(missing_provider_keys)
        )

    return CheckResult(errors=errors, warnings=warnings)


def check_git_clean(repo_root: Path = REPO_ROOT) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        warnings.append("No .git directory found; skipping clean-tree check.")
        return CheckResult(errors=errors, warnings=warnings)

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )
    if status.returncode != 0:
        errors.append(f"git status failed: {status.stderr.strip() or status.stdout.strip()}")
        return CheckResult(errors=errors, warnings=warnings)

    dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
    if dirty_lines:
        preview = "\n".join(dirty_lines[:20])
        suffix = "" if len(dirty_lines) <= 20 else f"\n... and {len(dirty_lines) - 20} more paths"
        errors.append(
            "Refusing to build a release from a dirty worktree. Commit, stash, or intentionally bypass "
            f"this gate outside release automation.\n{preview}{suffix}"
        )
    return CheckResult(errors=errors, warnings=warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-git-clean-check", action="store_true", help="Only validate release metadata.")
    args = parser.parse_args(argv)

    checks = [
        check_release_versions(REPO_ROOT),
        check_release_branding_contract(REPO_ROOT),
        check_remote_control_deployment_defaults(REPO_ROOT),
    ]
    if not args.skip_git_clean_check:
        checks.append(check_git_clean(REPO_ROOT))

    errors = [error for check in checks for error in check.errors]
    warnings = [warning for check in checks for warning in check.warnings]

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        print("Release hygiene check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Release hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
