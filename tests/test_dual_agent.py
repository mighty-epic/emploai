"""
Test: Dual Agent Architecture
Tests the Memory Agent + Executor Agent coordination.

Run with: python -m tests.test_dual_agent
"""

from dotenv import load_dotenv
load_dotenv()

import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.dual_agent import DualAgentCoordinator, MemoryAgent, ExecutorAgent
from agent.dual_agent.coordinator import run_dual_agent_task
from agent.dual_agent.schemas import (
    ExecutorRequest, RequestType, ObserveRequest, ActionRequest,
    ObservationMethod, ActionType
)


def test_schema_creation():
    """Test 1: Verify schema objects work correctly."""
    print("=" * 60)
    print("TEST 1: Schema Creation")
    print("=" * 60)
    
    # Test ObserveRequest
    observe_req = ExecutorRequest(
        request_type=RequestType.OBSERVE,
        observe=ObserveRequest(
            method=ObservationMethod.BROWSER,
            focus_area="search results"
        )
    )
    prompt = observe_req.to_prompt()
    print(f"Observe request prompt: {prompt}")
    assert "OBSERVE" in prompt
    assert "browser" in prompt
    
    # Test ActionRequest
    action_req = ExecutorRequest(
        request_type=RequestType.ACTION,
        action=ActionRequest(
            action_type=ActionType.CLICK,
            target="Search button"
        )
    )
    prompt = action_req.to_prompt()
    print(f"Action request prompt: {prompt}")
    assert "ACTION" in prompt
    assert "Click" in prompt
    
    print("✅ TEST 1 PASSED - Schemas work correctly\n")


def test_memory_agent_initialization():
    """Test 2: Verify Memory Agent initializes correctly."""
    print("=" * 60)
    print("TEST 2: Memory Agent Initialization")
    print("=" * 60)
    
    agent = MemoryAgent(model="gpt-4o-mini")  # Use mini for testing
    agent.initialize_task("Test task: open browser and search")
    
    assert agent.context is not None
    assert agent.context.task == "Test task: open browser and search"
    assert len(agent.context.step_list) == 0  # Not decomposed yet
    assert len(agent.context.action_history) == 0
    
    summary = agent.get_context_summary()
    print(f"Context summary:\n{summary}")
    
    print("✅ TEST 2 PASSED - Memory Agent initializes correctly\n")


def test_executor_agent_initialization():
    """Test 3: Verify Executor Agent initializes correctly."""
    print("=" * 60)
    print("TEST 3: Executor Agent Initialization")  
    print("=" * 60)
    
    agent = ExecutorAgent(model="gpt-4o-mini")
    
    # Should not have browser by default
    assert agent.driver is None
    
    # Test that screenshot dir is created
    assert agent.screenshot_dir.exists()
    
    print("✅ TEST 3 PASSED - Executor Agent initializes correctly\n")


def test_coordinator_initialization():
    """Test 4: Verify Coordinator initializes correctly."""
    print("=" * 60)
    print("TEST 4: Coordinator Initialization")
    print("=" * 60)
    
    coordinator = DualAgentCoordinator(
        memory_model="gpt-4o-mini",
        executor_model="gpt-4o-mini"
    )
    
    assert coordinator.memory_agent is not None
    assert coordinator.executor_agent is not None
    assert coordinator.log_dir.exists()
    
    print("✅ TEST 4 PASSED - Coordinator initializes correctly\n")


def test_simple_browser_task():
    """Test 5: Execute a simple browser task."""
    print("=" * 60)
    print("TEST 5: Simple Browser Task")
    print("=" * 60)
    
    # This test actually calls the LLMs
    result = run_dual_agent_task(
        task="Navigate to Google and verify the page loaded",
        start_url="https://www.google.com",
        memory_model="gpt-4o-mini",
        executor_model="gpt-4o-mini",
        max_cycles=10,
        verbose=True
    )
    
    print(f"\nResult: {result}")
    print(f"Success: {result.success}")
    print(f"Cycles used: {result.total_cycles}")
    print(f"Time: {result.execution_time_seconds:.1f}s")
    
    if result.success:
        print("✅ TEST 5 PASSED - Simple browser task completed\n")
    else:
        print("⚠️ TEST 5 - Task may not have succeeded (check logs)\n")
    
    return result


def test_memory_agent_decomposition():
    """Test 6: Test Memory Agent's task decomposition."""
    print("=" * 60)
    print("TEST 6: Task Decomposition (LLM Call)")
    print("=" * 60)
    
    agent = MemoryAgent(model="gpt-4o-mini")
    agent.initialize_task("Open Spotify and play a song")
    
    # First think cycle should decompose
    thought, request, is_complete = agent.think_and_act()
    
    print(f"Thought: {thought}")
    print(f"Request: {request}")
    print(f"Is complete: {is_complete}")
    print(f"Steps after decomposition: {len(agent.context.step_list)}")
    
    for step in agent.context.step_list:
        print(f"  Step {step.step_number}: {step.description} [{step.status}]")
    
    if len(agent.context.step_list) > 0:
        print("✅ TEST 6 PASSED - Task decomposed successfully\n")
    else:
        print("⚠️ TEST 6 - No steps created (may need another cycle)\n")


def run_all_tests(include_llm_tests: bool = True):
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DUAL AGENT ARCHITECTURE TESTS")
    print("=" * 60 + "\n")
    
    # Always run these (no LLM calls)
    test_schema_creation()
    test_memory_agent_initialization()
    test_executor_agent_initialization()
    test_coordinator_initialization()
    
    if include_llm_tests:
        print("\n--- LLM Integration Tests (requires API keys) ---\n")
        test_memory_agent_decomposition()
        test_simple_browser_task()
    else:
        print("\n--- Skipping LLM tests (include_llm_tests=False) ---\n")
    
    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM integration tests")
    parser.add_argument("--test", type=str, help="Run specific test (schema, memory, executor, coordinator, browser, decompose)")
    args = parser.parse_args()
    
    if args.test:
        test_map = {
            "schema": test_schema_creation,
            "memory": test_memory_agent_initialization,
            "executor": test_executor_agent_initialization,
            "coordinator": test_coordinator_initialization,
            "browser": test_simple_browser_task,
            "decompose": test_memory_agent_decomposition
        }
        if args.test in test_map:
            test_map[args.test]()
        else:
            print(f"Unknown test: {args.test}")
            print(f"Available: {list(test_map.keys())}")
    else:
        run_all_tests(include_llm_tests=not args.no_llm)
