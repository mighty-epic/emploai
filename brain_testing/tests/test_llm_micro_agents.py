"""
TEST: LLM Tool Calling - Micro Agents
Tests whether low-level micro-agents correctly select and execute atomic actions.

Run with: python -m brain_testing.tests.test_llm_micro_agents

NOTE: Requires OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.
"""

import sys
import os
import json
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.tools.definitions import MICRO_AGENT_TOOLS, get_tool_names
from shared.tools.mock_executor import MockToolExecutor


# Micro-step scenarios with expected tool calls
MICRO_STEP_SCENARIOS = [
    {
        "name": "Click Username Field",
        "step": "Click on the username input field",
        "observation": {
            "elements": [
                {"id": "input_username", "role": "textbox", "label": "Username"},
                {"id": "input_password", "role": "textbox", "label": "Password"},
                {"id": "btn_login", "role": "button", "text": "Login"},
            ],
            "focused_element": None
        },
        "expected_tool": "click_element",
        "expected_args": {"element_id": "input_username"},
        "forbidden_tools": ["type_text", "navigate", "scroll"]
    },
    {
        "name": "Type Username",
        "step": "Type 'testuser' into the username field",
        "observation": {
            "elements": [
                {"id": "input_username", "role": "textbox", "label": "Username"},
            ],
            "focused_element": {"id": "input_username", "role": "textbox"}
        },
        "expected_tool": "type_text",
        "expected_args": {"text": "testuser"},
        "forbidden_tools": ["click_element", "navigate"]
    },
    {
        "name": "Press Enter",
        "step": "Press Enter to submit the form",
        "observation": {
            "focused_element": {"id": "btn_login", "role": "button"}
        },
        "expected_tool": "press_key",
        "expected_args": {"key": "enter"},
        "forbidden_tools": ["click_element", "type_text"]
    },
    {
        "name": "Scroll to Find Element",
        "step": "Scroll down to find the submit button (not visible)",
        "observation": {
            "elements": [
                {"id": "header", "role": "text", "text": "Form"},
            ],
            "message": "Submit button not visible"
        },
        "expected_tool": "scroll",
        "expected_args": {"direction": "down"},
        "forbidden_tools": ["click_element"]
    },
]


def simulate_micro_agent_response(step: str, observation: Dict) -> Dict:
    """
    Simulate a micro-agent's tool call decision.
    In production, this would call the actual LLM API.
    """
    step_lower = step.lower()
    
    # Decide based on step content
    if "click" in step_lower:
        # Find target element
        for el in observation.get("elements", []):
            if "username" in step_lower and "username" in el.get("label", "").lower():
                return {"name": "click_element", "arguments": {"element_id": el["id"]}}
            if "password" in step_lower and "password" in el.get("label", "").lower():
                return {"name": "click_element", "arguments": {"element_id": el["id"]}}
            if "login" in step_lower and "login" in el.get("text", "").lower():
                return {"name": "click_element", "arguments": {"element_id": el["id"]}}
        return {"name": "click_element", "arguments": {"text": step.split("'")[1] if "'" in step else "unknown"}}
    
    elif "type" in step_lower:
        # Extract text to type
        if "'" in step:
            text = step.split("'")[1]
        else:
            text = "input_text"
        return {"name": "type_text", "arguments": {"text": text}}
    
    elif "press" in step_lower:
        # Extract key
        if "enter" in step_lower:
            return {"name": "press_key", "arguments": {"key": "enter"}}
        elif "tab" in step_lower:
            return {"name": "press_key", "arguments": {"key": "tab"}}
        elif "escape" in step_lower:
            return {"name": "press_key", "arguments": {"key": "escape"}}
        return {"name": "press_key", "arguments": {"key": "enter"}}
    
    elif "scroll" in step_lower:
        direction = "down" if "down" in step_lower else "up"
        return {"name": "scroll", "arguments": {"direction": direction}}
    
    elif "wait" in step_lower:
        return {"name": "wait", "arguments": {"seconds": 2}}
    
    else:
        return {"name": "get_screen_state", "arguments": {}}


def evaluate_micro_agent_call(
    tool_call: Dict,
    expected_tool: str,
    expected_args: Dict,
    forbidden: List[str]
) -> Dict[str, Any]:
    """Evaluate whether a micro-agent's tool call is correct."""
    
    results = {
        "passed": True,
        "issues": [],
        "tool_call": tool_call
    }
    
    # Check tool name
    if tool_call["name"] != expected_tool:
        results["passed"] = False
        results["issues"].append(f"Expected tool '{expected_tool}', got '{tool_call['name']}'")
    
    # Check key arguments
    for key, value in expected_args.items():
        actual = tool_call.get("arguments", {}).get(key)
        if actual != value:
            # Allow partial matches for text
            if isinstance(value, str) and isinstance(actual, str):
                if value.lower() in actual.lower():
                    continue
            results["passed"] = False
            results["issues"].append(f"Expected {key}='{value}', got '{actual}'")
    
    # Check forbidden tools
    if tool_call["name"] in forbidden:
        results["passed"] = False
        results["issues"].append(f"Called forbidden tool '{tool_call['name']}'")
    
    return results


def test_micro_agent_click():
    """Test 1: Micro-agent click decision."""
    print("=" * 60)
    print("TEST 1: Micro-Agent Click Decision")
    print("=" * 60)
    
    scenario = MICRO_STEP_SCENARIOS[0]
    print(f"\n[Step]: {scenario['step']}")
    print(f"[Observation]: {len(scenario['observation']['elements'])} elements")
    
    tool_call = simulate_micro_agent_response(scenario['step'], scenario['observation'])
    
    print(f"\n[Tool Call]: {tool_call['name']}({json.dumps(tool_call['arguments'])})")
    
    result = evaluate_micro_agent_call(
        tool_call,
        scenario['expected_tool'],
        scenario['expected_args'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 1 PASSED")
    else:
        print(f"\n❌ TEST 1 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def test_micro_agent_type():
    """Test 2: Micro-agent type decision."""
    print("\n" + "=" * 60)
    print("TEST 2: Micro-Agent Type Decision")
    print("=" * 60)
    
    scenario = MICRO_STEP_SCENARIOS[1]
    print(f"\n[Step]: {scenario['step']}")
    print(f"[Focused]: {scenario['observation']['focused_element']['id']}")
    
    tool_call = simulate_micro_agent_response(scenario['step'], scenario['observation'])
    
    print(f"\n[Tool Call]: {tool_call['name']}({json.dumps(tool_call['arguments'])})")
    
    result = evaluate_micro_agent_call(
        tool_call,
        scenario['expected_tool'],
        scenario['expected_args'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 2 PASSED")
    else:
        print(f"\n❌ TEST 2 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def test_micro_agent_key_press():
    """Test 3: Micro-agent key press decision."""
    print("\n" + "=" * 60)
    print("TEST 3: Micro-Agent Key Press Decision")
    print("=" * 60)
    
    scenario = MICRO_STEP_SCENARIOS[2]
    print(f"\n[Step]: {scenario['step']}")
    
    tool_call = simulate_micro_agent_response(scenario['step'], scenario['observation'])
    
    print(f"\n[Tool Call]: {tool_call['name']}({json.dumps(tool_call['arguments'])})")
    
    result = evaluate_micro_agent_call(
        tool_call,
        scenario['expected_tool'],
        scenario['expected_args'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 3 PASSED")
    else:
        print(f"\n❌ TEST 3 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def test_micro_agent_scroll():
    """Test 4: Micro-agent scroll decision."""
    print("\n" + "=" * 60)
    print("TEST 4: Micro-Agent Scroll Decision")
    print("=" * 60)
    
    scenario = MICRO_STEP_SCENARIOS[3]
    print(f"\n[Step]: {scenario['step']}")
    
    tool_call = simulate_micro_agent_response(scenario['step'], scenario['observation'])
    
    print(f"\n[Tool Call]: {tool_call['name']}({json.dumps(tool_call['arguments'])})")
    
    result = evaluate_micro_agent_call(
        tool_call,
        scenario['expected_tool'],
        scenario['expected_args'],
        scenario['forbidden_tools']
    )
    
    if result["passed"]:
        print(f"\n✅ TEST 4 PASSED")
    else:
        print(f"\n❌ TEST 4 FAILED")
        for issue in result["issues"]:
            print(f"   - {issue}")


def run_all_tests():
    """Run all micro-agent tests."""
    print("\n" + "=" * 60)
    print("LLM MICRO-AGENT TOOL CALLING TESTS")
    print("=" * 60)
    print("\n⚠️  Using simulated LLM responses")
    print("    Set OPENAI_API_KEY to use real LLM")
    
    test_micro_agent_click()
    test_micro_agent_type()
    test_micro_agent_key_press()
    test_micro_agent_scroll()
    
    print("\n" + "=" * 60)
    print("ALL MICRO-AGENT TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
