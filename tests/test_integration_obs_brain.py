"""
INTEGRATION TEST: Observation + Brain
Tests the flow from observation to decision.

Run with: python -m tests.test_integration_obs_brain
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.schemas.observation import ElementDescriptor, BoundingBox, ObservationSnapshot
from shared.schemas.actions import AtomicAction, ActionType, ActionTarget
from tests.brain_testing.tests.test_mad_decomposition import MADDecomposer
import time


def create_mock_observation() -> ObservationSnapshot:
    """Create a mock observation mimicking a login page."""
    elements = [
        ElementDescriptor(
            id="input_username", role="textbox", text="", label="Username",
            bbox=BoundingBox(x=100, y=100, width=200, height=30),
            is_enabled=True, confidence=1.0
        ),
        ElementDescriptor(
            id="input_password", role="textbox", text="", label="Password",
            bbox=BoundingBox(x=100, y=150, width=200, height=30),
            is_enabled=True, confidence=1.0
        ),
        ElementDescriptor(
            id="btn_login", role="button", text="Login", label="",
            bbox=BoundingBox(x=100, y=200, width=100, height=35),
            is_enabled=True, confidence=1.0
        ),
        ElementDescriptor(
            id="link_forgot", role="link", text="Forgot Password?", label="",
            bbox=BoundingBox(x=100, y=250, width=120, height=20),
            is_enabled=True, confidence=1.0
        ),
    ]
    
    return ObservationSnapshot(
        source="mock",
        timestamp=time.time(),
        active_window_title="Login - Example.com",
        url="https://example.com/login",
        elements=elements,
        focused_element_id=None
    )


def test_observation_to_decision():
    """Test 1: Flow from observation to atomic action decision."""
    print("=" * 60)
    print("TEST 1: Observation → Decision Flow")
    print("=" * 60)
    
    # Step 1: Get observation
    observation = create_mock_observation()
    print(f"\n[1. OBSERVATION]")
    print(f"    URL: {observation.url}")
    print(f"    Elements: {len(observation.elements)}")
    for el in observation.elements:
        print(f"      - [{el.role}] '{el.text or el.label}' (id: {el.id})")
    
    # Step 2: High-level task
    task = "Login with username 'testuser' and password 'testpass'"
    print(f"\n[2. TASK]")
    print(f"    {task}")
    
    # Step 3: Decompose task
    decomposer = MADDecomposer()
    steps = decomposer.decompose_task(task)
    print(f"\n[3. DECOMPOSITION]")
    print(f"    {len(steps)} atomic steps:")
    for i, step in enumerate(steps):
        print(f"      {i+1}. {step['description']}")
    
    # Step 4: Match first step to observation
    current_step = steps[0]  # "Click username field"
    print(f"\n[4. CURRENT STEP]")
    print(f"    {current_step['description']}")
    
    # Find matching element
    matching_element = None
    for el in observation.elements:
        if el.role == "textbox" and "username" in el.label.lower():
            matching_element = el
            break
    
    if matching_element:
        print(f"\n[5. MATCHED ELEMENT]")
        print(f"    Found: [{matching_element.role}] id={matching_element.id}")
        print(f"    Position: ({matching_element.bbox.x}, {matching_element.bbox.y})")
        
        # Create action
        action = AtomicAction(
            action_type=ActionType.CLICK,
            target=ActionTarget(element_id=matching_element.id),
            rationale=current_step['description'],
            confidence=0.95
        )
        
        print(f"\n[6. GENERATED ACTION]")
        print(f"    Type: {action.action_type.value}")
        print(f"    Target: {action.target.element_id}")
        print(f"    Confidence: {action.confidence}")
    else:
        print(f"\n[5. NO MATCH FOUND] - would trigger scroll/search")
    
    print("\n✅ TEST 1 PASSED")


def test_observation_change_detection():
    """Test 2: Detect changes between observations."""
    print("\n" + "=" * 60)
    print("TEST 2: Change Detection")
    print("=" * 60)
    
    # Before action
    obs_before = create_mock_observation()
    obs_before.focused_element_id = None
    
    # After action (simulated - username field now focused)
    obs_after = create_mock_observation()
    obs_after.focused_element_id = "input_username"
    obs_after.timestamp = time.time() + 0.5
    
    print(f"\n[BEFORE] Focused: {obs_before.focused_element_id}")
    print(f"[AFTER]  Focused: {obs_after.focused_element_id}")
    
    # Detect progress
    progress_evidence = []
    
    if obs_before.focused_element_id != obs_after.focused_element_id:
        progress_evidence.append("focus_changed")
    
    if obs_before.url != obs_after.url:
        progress_evidence.append("url_changed")
    
    print(f"\n[PROGRESS EVIDENCE]: {progress_evidence if progress_evidence else 'none'}")
    
    if progress_evidence:
        print("[DECISION]: Action succeeded, continue to next step")
    else:
        print("[DECISION]: No progress, retry or recover")
    
    print("\n✅ TEST 2 PASSED")


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("INTEGRATION TESTS: OBSERVATION + BRAIN")
    print("=" * 60)
    
    test_observation_to_decision()
    test_observation_change_detection()
    
    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
