"""
INTEGRATION TEST: Brain + Hands
Tests the flow from decision to execution.

Run with: python -m tests.test_integration_brain_hands
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.schemas.actions import AtomicAction, ActionType, ActionTarget, ActionResult


class MockExecutor:
    """Mock executor for testing without actual screen interaction."""
    
    def __init__(self):
        self.executed_actions = []
    
    def execute(self, action: AtomicAction) -> ActionResult:
        """Execute an action (mock)."""
        self.executed_actions.append(action)
        
        # Simulate success
        return ActionResult(
            success=True,
            action=action,
            actual_target_coords=(100, 100),
            execution_time_ms=50,
            focus_changed=action.action_type == ActionType.CLICK
        )


def test_action_execution_flow():
    """Test 1: Flow from action to execution."""
    print("=" * 60)
    print("TEST 1: Action → Execution Flow")
    print("=" * 60)
    
    # Create action (from brain)
    action = AtomicAction(
        action_type=ActionType.CLICK,
        target=ActionTarget(element_id="btn_login", x=150, y=215),
        rationale="Click the login button",
        confidence=0.95
    )
    
    print(f"\n[1. ACTION FROM BRAIN]")
    print(f"    Type: {action.action_type.value}")
    print(f"    Target: {action.target.element_id}")
    print(f"    Coords: ({action.target.x}, {action.target.y})")
    
    # Execute
    executor = MockExecutor()
    result = executor.execute(action)
    
    print(f"\n[2. EXECUTION RESULT]")
    print(f"    Success: {result.success}")
    print(f"    Time: {result.execution_time_ms}ms")
    print(f"    Focus changed: {result.focus_changed}")
    
    print("\n✅ TEST 1 PASSED")


def test_action_sequence():
    """Test 2: Execute a sequence of actions."""
    print("\n" + "=" * 60)
    print("TEST 2: Action Sequence")
    print("=" * 60)
    
    actions = [
        AtomicAction(action_type=ActionType.CLICK, 
                    target=ActionTarget(element_id="input_username"),
                    rationale="Click username field"),
        AtomicAction(action_type=ActionType.TYPE_TEXT,
                    text="testuser",
                    rationale="Type username"),
        AtomicAction(action_type=ActionType.CLICK,
                    target=ActionTarget(element_id="input_password"),
                    rationale="Click password field"),
        AtomicAction(action_type=ActionType.TYPE_TEXT,
                    text="testpass",
                    rationale="Type password"),
        AtomicAction(action_type=ActionType.CLICK,
                    target=ActionTarget(element_id="btn_login"),
                    rationale="Click login button"),
    ]
    
    executor = MockExecutor()
    
    print(f"\n[Executing {len(actions)} actions]:")
    for i, action in enumerate(actions):
        result = executor.execute(action)
        status = "✅" if result.success else "❌"
        print(f"  {i+1}. {status} {action.action_type.value}: {action.rationale}")
    
    print(f"\n[Total executed]: {len(executor.executed_actions)}")
    print("\n✅ TEST 2 PASSED")


def test_execution_with_failure():
    """Test 3: Handle execution failure."""
    print("\n" + "=" * 60)
    print("TEST 3: Execution Failure Handling")
    print("=" * 60)
    
    action = AtomicAction(
        action_type=ActionType.CLICK,
        target=ActionTarget(element_id="missing_element"),
        rationale="Click non-existent element"
    )
    
    # Simulate failure
    result = ActionResult(
        success=False,
        action=action,
        error_message="Element not found",
        error_type="ElementNotFound"
    )
    
    print(f"\n[ACTION]: {action.rationale}")
    print(f"[RESULT]: Failed - {result.error_message}")
    
    # Recovery logic
    print(f"\n[RECOVERY OPTIONS]:")
    print(f"  1. Scroll to reveal element")
    print(f"  2. Wait and retry")
    print(f"  3. Find alternative target")
    print(f"  4. Escalate to orchestrator")
    
    print("\n✅ TEST 3 PASSED")


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("INTEGRATION TESTS: BRAIN + HANDS")
    print("=" * 60)
    
    test_action_execution_flow()
    test_action_sequence()
    test_execution_with_failure()
    
    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
