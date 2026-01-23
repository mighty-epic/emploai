"""
TEST: LLM Tool Calling - Orchestrator
Tests whether the high-level LLM correctly decomposes tasks and calls tools.

Run with: python -m brain_testing.tests.test_llm_orchestrator

NOTE: Requires OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.
"""

import sys
import os
import json
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.tools.definitions import ORCHESTRATOR_ALL_TOOLS, get_tool_names
from shared.tools.mock_executor import MockToolExecutor


# Test scenarios with expected tool sequences
TEST_SCENARIOS = [
    {
        "name": "Login Task Decomposition",
        "task": "Log in to the website with username 'testuser' and password 'testpass123'",
        "expected_first_tools": ["get_screen_state", "decompose_task"],
        "expected_contains": ["issue_micro_step"],
        "forbidden_tools": [],  # Tools that should NOT be called
    },
    {
        "name": "Verify Login Success",
        "task": "Verify that login was successful by checking for dashboard",
        "expected_first_tools": ["get_screen_state", "verify_state"],
        "expected_contains": ["verify_state"],
        "forbidden_tools": ["click_element", "type_text"],
    },
    {
        "name": "Handle Unexpected Modal",
        "task": "A CAPTCHA appeared unexpectedly. Adapt the plan.",
        "expected_first_tools": ["adapt_plan", "request_human_help"],
        "expected_contains": [],
        "forbidden_tools": [],
    },
]


def create_orchestrator_prompt(task: str, observation: Dict) -> str:
    """Create the system prompt for the orchestrator."""
    return f"""You are the Orchestrator agent in an agentic automation system.

Your role is to:
1. Understand high-level tasks
2. Observe the current screen state
3. Decompose tasks into atomic steps
4. Issue micro-steps to low-level agents
5. Verify progress after each step
6. Adapt the plan when unexpected situations occur

Current observation:
{json.dumps(observation, indent=2)}

Task: {task}

Use the available tools to accomplish this task. Always observe the screen state first before deciding on actions."""


def simulate_llm_response(task: str, tools: List[Dict]) -> List[Dict]:
    """
    Simulate LLM tool calls for testing.
    In production, this would call the actual LLM API.
    """
    # Simulated responses based on task content
    task_lower = task.lower()
    
    tool_calls = []
    
    if "log in" in task_lower or "login" in task_lower:
        tool_calls = [
            {"name": "get_screen_state", "arguments": {}},
            {"name": "decompose_task", "arguments": {"task": task}},
            {"name": "issue_micro_step", "arguments": {
                "step_description": "Click username field",
                "expected_outcome": "Username field is focused"
            }},
        ]
    elif "verify" in task_lower:
        tool_calls = [
            {"name": "get_screen_state", "arguments": {}},
            {"name": "verify_state", "arguments": {"url_contains": "dashboard"}},
        ]
    elif "captcha" in task_lower or "unexpected" in task_lower:
        tool_calls = [
            {"name": "adapt_plan", "arguments": {"reason": "CAPTCHA detected"}},
            {"name": "request_human_help", "arguments": {"reason": "CAPTCHA requires human intervention"}},
        ]
    else:
        tool_calls = [
            {"name": "get_screen_state", "arguments": {}},
        ]
    
    return tool_calls


def evaluate_tool_calls(
    tool_calls: List[Dict],
    expected_first: List[str],
    expected_contains: List[str],
    forbidden: List[str]
) -> Dict[str, Any]:
    """Evaluate whether tool calls match expectations."""
    
    called_names = [tc["name"] for tc in tool_calls]
    
    results = {
        "passed": True,
        "issues": [],
        "tool_calls": called_names
    }
    
    # Check first tools
    if expected_first:
        first_call = called_names[0] if called_names else None
        if first_call not in expected_first:
            results["passed"] = False
            results["issues"].append(f"First call should be one of {expected_first}, got {first_call}")
    
    # Check expected tools are present
    for expected in expected_contains:
        if expected not in called_names:
            results["passed"] = False
            results["issues"].append(f"Expected tool '{expected}' was not called")
    
    # Check forbidden tools
    for forbidden_tool in forbidden:
        if forbidden_tool in called_names:
            results["passed"] = False
            results["issues"].append(f"Forbidden tool '{forbidden_tool}' was called")
    
    return results


def test_orchestrator_decomposition():
    """Test 1: Orchestrator task decomposition."""
    print("=" * 60)
    print("TEST 1: Orchestrator Task Decomposition")
    print("=" * 60)
    
    executor = MockToolExecutor()
    observation = executor.execute("get_screen_state", {})
    
    scenario = TEST_SCENARIOS[0]
    print(f"\n[Scenario]: {scenario['name']}")
    print(f"[Task]: {scenario['task']}")
    
    # Simulate LLM response
    tool_calls = simulate_llm_response(scenario['task'], ORCHESTRATOR_ALL_TOOLS)
    
    print(f"\n[Tool Calls Made]:")
    for i, tc in enumerate(tool_calls):
        print(f"  {i+1}. {tc['name']}({json.dumps(tc['arguments'])})")
    
    # Evaluate
    result = evaluate_tool_calls(
        tool_calls,
        scenario['expected_first_tools'],
        scenario['expected_contains'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 1 PASSED")
    else:
        print(f"\n❌ TEST 1 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def test_orchestrator_verification():
    """Test 2: Orchestrator state verification."""
    print("\n" + "=" * 60)
    print("TEST 2: Orchestrator State Verification")
    print("=" * 60)
    
    scenario = TEST_SCENARIOS[1]
    print(f"\n[Scenario]: {scenario['name']}")
    print(f"[Task]: {scenario['task']}")
    
    tool_calls = simulate_llm_response(scenario['task'], ORCHESTRATOR_ALL_TOOLS)
    
    print(f"\n[Tool Calls Made]:")
    for i, tc in enumerate(tool_calls):
        print(f"  {i+1}. {tc['name']}({json.dumps(tc['arguments'])})")
    
    result = evaluate_tool_calls(
        tool_calls,
        scenario['expected_first_tools'],
        scenario['expected_contains'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 2 PASSED")
    else:
        print(f"\n❌ TEST 2 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def test_orchestrator_adaptation():
    """Test 3: Orchestrator plan adaptation."""
    print("\n" + "=" * 60)
    print("TEST 3: Orchestrator Plan Adaptation")
    print("=" * 60)
    
    scenario = TEST_SCENARIOS[2]
    print(f"\n[Scenario]: {scenario['name']}")
    print(f"[Task]: {scenario['task']}")
    
    tool_calls = simulate_llm_response(scenario['task'], ORCHESTRATOR_ALL_TOOLS)
    
    print(f"\n[Tool Calls Made]:")
    for i, tc in enumerate(tool_calls):
        print(f"  {i+1}. {tc['name']}({json.dumps(tc['arguments'])})")
    
    result = evaluate_tool_calls(
        tool_calls,
        scenario['expected_first_tools'],
        scenario['expected_contains'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 3 PASSED")
    else:
        print(f"\n❌ TEST 3 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def run_all_tests():
    """Run all orchestrator tests."""
    print("\n" + "=" * 60)
    print("LLM ORCHESTRATOR TOOL CALLING TESTS")
    print("=" * 60)
    print("\n⚠️  Using simulated LLM responses")
    print("    Set OPENAI_API_KEY to use real LLM")
    
    test_orchestrator_decomposition()
    test_orchestrator_verification()
    test_orchestrator_adaptation()
    
    print("\n" + "=" * 60)
    print("ALL ORCHESTRATOR TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
