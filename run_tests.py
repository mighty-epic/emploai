"""Small pytest runner for common EmploAI contributor checks.

Usage:
  python run_tests.py                 # Fast local desktop sanity suite
  python run_tests.py quick           # Same as default
  python run_tests.py desktop         # Desktop runtime/config/provider checks
  python run_tests.py local-first     # Standalone and Fleet transport checks
  python run_tests.py legacy          # Preserved compatibility package checks
  python run_tests.py brain           # Older brain/LLM tests
  python run_tests.py integration     # Older integration tests
  python run_tests.py all             # Full pytest suite
  python run_tests.py quick -- -vv    # Pass extra args to pytest
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

TEST_GROUPS: dict[str, list[str]] = {
    "quick": [
        "tests/test_desktop_launch_contract.py",
        "tests/test_app_backend_package.py",
        "tests/test_desktop_runtime_package.py",
        "tests/test_local_agent_runtime_package.py",
        "tests/test_runtime_support_package.py",
        "tests/test_legacy_agent_orchestration_package.py",
    ],
    "desktop": [
        "tests/test_desktop_launch_contract.py",
        "tests/test_desktop_runtime_package.py",
        "tests/test_desktop_runtime_config.py",
        "tests/test_desktop_model_providers.py",
        "tests/test_model_registry_latest.py",
    ],
    "local-first": [
        "tests/test_standalone_policy.py",
        "tests/test_fleet_yggdrasil.py",
        "tests/test_desktop_launch_contract.py",
    ],
    "legacy": [
        "tests/test_app_backend_package.py",
        "tests/test_desktop_runtime_package.py",
        "tests/test_local_agent_runtime_package.py",
        "tests/test_runtime_support_package.py",
        "tests/test_legacy_agent_orchestration_package.py",
    ],
    "brain": [
        "tests/brain_testing/tests/test_mad_decomposition.py",
        "tests/brain_testing/tests/test_maker_voting.py",
        "tests/brain_testing/tests/test_llm_orchestrator.py",
        "tests/brain_testing/tests/test_llm_micro_agents.py",
        "tests/brain_testing/tests/test_llm_e2e_flow.py",
    ],
    "integration": [
        "tests/test_integration_obs_brain.py",
        "tests/test_integration_brain_hands.py",
        "tests/test_full_system.py",
    ],
    "all": ["tests"],
}


def parse_args(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        separator = argv.index("--")
        group_args = argv[:separator]
        pytest_args = argv[separator + 1 :]
    else:
        group_args = argv
        pytest_args = []

    parser = argparse.ArgumentParser(description="Run common EmploAI pytest groups.")
    parser.add_argument(
        "groups",
        nargs="*",
        choices=sorted(TEST_GROUPS),
        help="Named test group(s) to run. Defaults to quick.",
    )
    parsed = parser.parse_args(group_args)
    return parsed.groups or ["quick"], pytest_args


def resolve_targets(groups: list[str]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for target in TEST_GROUPS[group]:
            if target not in seen:
                targets.append(target)
                seen.add(target)
    return targets


def main(argv: list[str] | None = None) -> int:
    groups, pytest_args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    targets = resolve_targets(groups)

    missing = [target for target in targets if target != "tests" and not (ROOT / target).exists()]
    if missing:
        print("Missing test targets:")
        for target in missing:
            print(f"  - {target}")
        return 2

    command = [sys.executable, "-m", "pytest", *targets, *pytest_args]
    print("Running:", " ".join(command), flush=True)
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
