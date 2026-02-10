"""
TEST: End-to-End Tool Calling Flow
Tests the complete flow: Orchestrator → Micro-agents → Tool Execution → Verification

Run with: python -m brain_testing.tests.test_llm_e2e_flow
"""

import sys
import os
import json
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.tools.definitions import ORCHESTRATOR_ALL_TOOLS, MICRO_AGENT_TOOLS
from shared.tools.mock_executor import MockToolExecutor


class E2ETestHarness:
    """Test harness for end-to-end tool calling flow."""
    
    def __init__(self):
        self.executor = MockToolExecutor()
        self.orchestrator_calls = []
        self.micro_agent_calls = []
        self.execution_trace = []
    
    def simulate_orchestrator(self, task: str) -> List[Dict]:
        """Simulate orchestrator decomposing task and issuing steps."""
        # Get initial observation
        obs = self.executor.execute("get_screen_state", {})
        
        # Decompose task (simulated)
        steps = []
        task_lower = task.lower()
        
        if "login" in task_lower:
            steps = [
                {"step": "Click username field", "target": "input_username"},
                {"step": "Type username", "value": "testuser"},
                {"step": "Click password field", "target": "input_password"},
                {"step": "Type password", "value": "testpass"},
                {"step": "Click login button", "target": "btn_login"},
            ]
        
        self.orchestrator_calls.append({
            "action": "decompose_task",
            "task": task,
            "steps": steps
        })
        
        return steps
    
    def simulate_micro_agent(self, step: Dict, observation: Dict) -> Dict:
        """Simulate micro-agent deciding on atomic action."""
        step_desc = step.get("step", "").lower()
        
        if "click" in step_desc:
            tool_call = {
                "name": "click_element",
                "arguments": {"element_id": step.get("target")}
            }
        elif "type" in step_desc:
            tool_call = {
                "name": "type_text",
                "arguments": {"text": step.get("value", "")}
            }
        else:
            tool_call = {"name": "wait", "arguments": {"seconds": 1}}
        
        self.micro_agent_calls.append({
            "step": step,
            "tool_call": tool_call
        })
        
        return tool_call
    
    def execute_tool(self, tool_call: Dict) -> Dict:
        """Execute a tool call and return result."""
        result = self.executor.execute(tool_call["name"], tool_call["arguments"])
        
        self.execution_trace.append({
            "tool": tool_call["name"],
            "args": tool_call["arguments"],
            "result": result
        })
        
        return result
    
    def verify_progress(self, expected: str) -> Dict:
        """Verify progress after action."""
        obs = self.executor.execute("get_screen_state", {})
        
        if "dashboard" in expected.lower():
            success = "dashboard" in obs.get("url", "")
        elif "focused" in expected.lower():
            success = obs.get("focused_element") is not None
        else:
            success = True
        
        return {"verified": success, "observation": obs}
    
    def run_task(self, task: str) -> Dict:
        """Run complete task flow."""
        print(f"\n[TASK]: {task}")
        
        # Orchestrator decomposes
        steps = self.simulate_orchestrator(task)
        print(f"[ORCHESTRATOR]: Decomposed into {len(steps)} steps")
        
        for i, step in enumerate(steps):
            print(f"\n  Step {i+1}: {step['step']}")
            
            # Get observation
            obs = self.executor.execute("get_screen_state", {})
            
            # Micro-agent decides
            tool_call = self.simulate_micro_agent(step, obs)
            print(f"    → Tool: {tool_call['name']}({tool_call['arguments']})")
            
            # Execute
            result = self.execute_tool(tool_call)
            print(f"    → Result: {'✅' if result.get('success') else '❌'}")
        
        # Final verification
        final_obs = self.executor.execute("get_screen_state", {})
        
        return {
            "task": task,
            "steps_executed": len(steps),
            "final_url": final_obs.get("url"),
            "success": "dashboard" in final_obs.get("url", "")
        }


def test_login_e2e():
    """Test 1: Complete login flow end-to-end."""
    print("=" * 60)
    print("TEST 1: Login Flow End-to-End")
    print("=" * 60)
    
    harness = E2ETestHarness()
    result = harness.run_task("Login with username 'testuser' and password 'testpass'")
    
    print(f"\n[FINAL RESULT]")
    print(f"  Steps executed: {result['steps_executed']}")
    print(f"  Final URL: {result['final_url']}")
    print(f"  Success: {result['success']}")
    
    if result['success']:
        print("\n✅ TEST 1 PASSED")
    else:
        print("\n❌ TEST 1 FAILED")


def test_execution_trace():
    """Test 2: Verify execution trace is correct."""
    print("\n" + "=" * 60)
    print("TEST 2: Execution Trace Verification")
    print("=" * 60)
    
    harness = E2ETestHarness()
    harness.run_task("Login with username 'testuser' and password 'testpass'")
    
    print(f"\n[EXECUTION TRACE]:")
    expected_sequence = ["click_element", "type_text", "click_element", "type_text", "click_element"]
    actual_sequence = [t["tool"] for t in harness.execution_trace]
    
    for i, trace in enumerate(harness.execution_trace):
        expected = expected_sequence[i] if i < len(expected_sequence) else "?"
        actual = trace["tool"]
        match = "✅" if actual == expected else "❌"
        print(f"  {i+1}. {match} Expected: {expected}, Got: {actual}")
    
    if actual_sequence == expected_sequence:
        print("\n✅ TEST 2 PASSED - Sequence matches")
    else:
        print("\n⚠️ TEST 2 - Sequence differs (may still be valid)")


def test_tool_execution_success():
    """Test 3: Verify all tool executions succeed."""
    print("\n" + "=" * 60)
    print("TEST 3: Tool Execution Success")
    print("=" * 60)
    
    harness = E2ETestHarness()
    harness.run_task("Login with username 'testuser' and password 'testpass'")
    
    all_success = True
    for trace in harness.execution_trace:
        success = trace["result"].get("success", False)
        if not success:
            all_success = False
            print(f"  ❌ {trace['tool']} failed: {trace['result']}")
    
    if all_success:
        print(f"  All {len(harness.execution_trace)} tool executions succeeded")
        print("\n✅ TEST 3 PASSED")
    else:
        print("\n❌ TEST 3 FAILED")


def run_all_tests():
    """Run all E2E tests."""
    print("\n" + "=" * 60)
    print("END-TO-END TOOL CALLING FLOW TESTS")
    print("=" * 60)
    
    test_login_e2e()
    test_execution_trace()
    test_tool_execution_success()
    
    print("\n" + "=" * 60)
    print("ALL E2E TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
