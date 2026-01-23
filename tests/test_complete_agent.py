"""
Complete Agent Test Suite
Tests with Step Diff and Adapt Degree matrix using real execution.

Run individual: python tests/test_complete_agent.py browser
Run all: python tests/test_complete_agent.py
"""

from dotenv import load_dotenv
load_dotenv()

import sys
import json
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.unified_agent import UnifiedAgent, TestResult


# ============================================================
# TEST SCENARIOS
# ============================================================

@dataclass
class TestScenario:
    name: str
    step_diff: int
    adapt_degree: int
    task: str
    start_url: str
    mode: str = "browser"
    max_steps: int = 12


SCENARIOS = {
    # ==================== BROWSER TESTS ====================
    
    "wiki_search": TestScenario(
        name="Wikipedia Search",
        step_diff=2,
        adapt_degree=2,
        task="""
        1. Search for 'Python programming' in the search box
        2. Press Enter or click search
        3. Verify you are on the Python article page
        4. Call task_complete when you see the Python article
        """,
        start_url="https://www.wikipedia.org",
        max_steps=10
    ),
    
    "wiki_simple": TestScenario(
        name="Wikipedia Click",
        step_diff=1,
        adapt_degree=1,
        task="""
        Click on the 'English' link to go to English Wikipedia.
        Then verify the URL contains 'en.wikipedia'.
        Call task_complete when done.
        """,
        start_url="https://www.wikipedia.org",
        max_steps=6
    ),
    
    "duckduckgo_search": TestScenario(
        name="DuckDuckGo Search",
        step_diff=2,
        adapt_degree=2,
        task="""
        1. Type 'Selenium Python' in the search box
        2. Press Enter to search
        3. Verify search results appear
        4. Call task_complete with success=true
        """,
        start_url="https://duckduckgo.com",
        max_steps=8
    ),
    
    "github_explore": TestScenario(
        name="GitHub Explore",
        step_diff=1,
        adapt_degree=2,
        task="""
        1. Click on 'Explore' link in the navigation
        2. Verify you are on the explore page (URL contains 'explore')
        3. Call task_complete
        """,
        start_url="https://github.com",
        max_steps=6
    ),
    
    "form_fill": TestScenario(
        name="Form Fill Demo",
        step_diff=3,
        adapt_degree=1,
        task="""
        On this demo form:
        1. Find the first name field and type 'John'
        2. Find the last name field and type 'Doe'
        3. Verify you typed the names correctly
        4. Call task_complete with success=true
        """,
        start_url="https://www.selenium.dev/selenium/web/web-form.html",
        max_steps=10
    ),
    
    "multi_page_nav": TestScenario(
        name="Multi-Page Navigation",
        step_diff=1,
        adapt_degree=3,
        task="""
        Navigate through these pages:
        1. Start at Wikipedia main page
        2. Click 'English' to go to en.wikipedia
        3. Verify URL contains 'en.wikipedia'
        4. Click on any link in the main page content
        5. Verify the URL changed
        6. Call task_complete summarizing where you ended up
        """,
        start_url="https://www.wikipedia.org",
        max_steps=12
    ),
}


# ============================================================
# TEST RUNNER
# ============================================================

class TestRunner:
    def __init__(self):
        self.results: Dict[str, TestResult] = {}
    
    def run_scenario(self, key: str) -> TestResult:
        """Run a single test scenario."""
        if key not in SCENARIOS:
            print(f"Unknown scenario: {key}")
            print(f"Available: {list(SCENARIOS.keys())}")
            return None
        
        scenario = SCENARIOS[key]
        
        print(f"\n{'#'*70}")
        print(f"# TEST: {scenario.name}")
        print(f"# Step Diff: {scenario.step_diff} | Adapt Degree: {scenario.adapt_degree}")
        print(f"{'#'*70}")
        
        agent = UnifiedAgent()
        
        result = agent.run_task(
            task=scenario.task,
            start_url=scenario.start_url,
            mode=scenario.mode,
            max_steps=scenario.max_steps
        )
        
        self.results[key] = result
        return result
    
    def run_all(self) -> Dict[str, TestResult]:
        """Run all test scenarios."""
        print("\n" + "=" * 70)
        print("COMPLETE AGENT TEST SUITE")
        print("=" * 70)
        
        for key in SCENARIOS:
            self.run_scenario(key)
        
        self.print_summary()
        return self.results
    
    def run_quick(self) -> Dict[str, TestResult]:
        """Run quick subset of tests."""
        quick_tests = ["wiki_simple", "duckduckgo_search"]
        
        print("\n" + "=" * 70)
        print("QUICK TEST SUITE")
        print("=" * 70)
        
        for key in quick_tests:
            self.run_scenario(key)
        
        self.print_summary()
        return self.results
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        print(f"\n{'Test':<25} {'SD':>3} {'AD':>3} {'Steps':>6} {'Time':>8} {'Result':<10}")
        print("-" * 60)
        
        passed = 0
        failed = 0
        
        for key, result in self.results.items():
            scenario = SCENARIOS[key]
            status = "PASS" if result.success else "FAIL"
            
            if result.success:
                passed += 1
            else:
                failed += 1
            
            print(f"{scenario.name:<25} {scenario.step_diff:>3} {scenario.adapt_degree:>3} "
                  f"{result.steps:>6} {result.duration_seconds:>7.1f}s {status:<10}")
        
        print("-" * 60)
        print(f"Total: {passed} passed, {failed} failed out of {len(self.results)}")
        
        # Verification summary
        total_verifications = sum(len(r.verification_results) for r in self.results.values())
        passed_verifications = sum(
            sum(1 for v in r.verification_results if v['success'])
            for r in self.results.values()
        )
        
        if total_verifications > 0:
            print(f"Verifications: {passed_verifications}/{total_verifications} passed")


# ============================================================
# MAIN
# ============================================================

def main():
    runner = TestRunner()
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == "quick":
            runner.run_quick()
        elif arg == "all":
            runner.run_all()
        elif arg in SCENARIOS:
            runner.run_scenario(arg)
        else:
            print(f"Unknown argument: {arg}")
            print("\nUsage:")
            print("  python test_complete_agent.py              # Run all tests")
            print("  python test_complete_agent.py quick        # Run quick tests")
            print("  python test_complete_agent.py <scenario>   # Run specific test")
            print(f"\nAvailable scenarios: {list(SCENARIOS.keys())}")
    else:
        runner.run_all()


if __name__ == "__main__":
    main()
