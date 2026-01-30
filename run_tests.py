"""
TEST RUNNER
Runs all tests for the agentic system.

Usage:
  python run_tests.py              # Run all tests
  python run_tests.py brain        # Run brain tests only
  python run_tests.py llm          # Run LLM tests only
  python run_tests.py integration  # Run integration tests only
"""

import sys
import subprocess


def run_test(module_path: str, name: str):
    """Run a test module."""
    print(f"\n{'='*60}")
    print(f"RUNNING: {name}")
    print('='*60)
    
    result = subprocess.run(
        [sys.executable, "-m", module_path],
        capture_output=False
    )
    return result.returncode == 0


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    
    tests = {
        "brain": [
            ("brain_testing.tests.test_mad_decomposition", "MAD Decomposition"),
            ("brain_testing.tests.test_maker_voting", "MAKER Voting"),
        ],
        "llm": [
            ("brain_testing.tests.test_llm_orchestrator", "LLM Orchestrator"),
            ("brain_testing.tests.test_llm_micro_agents", "LLM Micro-Agents"),
            ("brain_testing.tests.test_llm_e2e_flow", "LLM E2E Flow"),
        ],
        "integration": [
            ("tests.test_integration_obs_brain", "Observation + Brain"),
            ("tests.test_integration_brain_hands", "Brain + Hands"),
            ("tests.test_full_system", "Full System"),
        ],
    }
    
    to_run = []
    if "all" in args:
        for group in tests.values():
            to_run.extend(group)
    else:
        for arg in args:
            if arg in tests:
                to_run.extend(tests[arg])
    
    print("\n" + "="*60)
    print("AGENTIC SYSTEM TEST SUITE")
    print("="*60)
    print(f"\nTests to run: {len(to_run)}")
    
    results = []
    for module, name in to_run:
        success = run_test(module, name)
        results.append((name, success))
    
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    for name, success in results:
        icon = "✅" if success else "❌"
        print(f"  {icon} {name}")
    
    print(f"\nTotal: {passed}/{total} passed")


if __name__ == "__main__":
    main()
