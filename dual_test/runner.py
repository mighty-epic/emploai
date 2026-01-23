"""
Simplified Dual Agent Runner for Testing.
Bridge between the test script and the dual-agent architecture.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field

# Add internal path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent.dual_agent.coordinator import DualAgentCoordinator

class DualAgentRunner:
    """
    Simplified wrapper for testing the dual-agent architecture.
    """
    
    def __init__(
        self,
        memory_model: str = "gpt-4o",
        executor_model: str = "gpt-4o-mini"
    ):
        self.memory_model = memory_model
        self.executor_model = executor_model
        
        # The coordinator handles everything
        self.coordinator: Optional[DualAgentCoordinator] = None
        
        # Task state tracking
        self.is_running = False
        self.start_time: Optional[float] = None
        self.current_task: Optional[str] = None

    def _event_handler(self, event_type: str, data: Dict):
        """Standard console logging for events."""
        if event_type == "task_started":
            print(f"\n[TASK STARTED] {data.get('task')}")
        elif event_type == "cycle_start":
            print(f"\n --- Cycle {data.get('cycle')} ---")
        elif event_type == "memory_thought":
            thought = data.get('thought', '')
            print(f"Thought: {thought}")
        elif event_type == "executor_request":
            req = data.get('request', '')
            print(f"Requesting: {req}")
        elif event_type == "executor_response":
            status = "[OK]" if data.get('success') else "[FAIL]"
            summary = data.get('summary', '')
            print(f"Response: {status} {summary}")
        elif event_type == "error":
            print(f"ERROR: {data.get('message')}")
    
    def run(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_cycles: int = 50
    ) -> Dict[str, Any]:
        """Run a task and return the result."""
        self.is_running = True
        self.start_time = time.time()
        self.current_task = task
        
        # Create coordinator
        self.coordinator = DualAgentCoordinator(
            memory_model=self.memory_model,
            executor_model=self.executor_model,
            event_callback=self._event_handler
        )
        
        try:
            # Execute the task
            result = self.coordinator.execute_task(
                task=task,
                start_url=start_url,
                max_cycles=max_cycles
            )
            
            print(f"\n{'='*40}")
            print(f"TASK COMPLETE | Success: {result.success}")
            print(f"Cycles: {result.total_cycles} | Time: {result.execution_time_seconds:.1f}s")
            print(f"Summary: {result.final_summary}")
            print(f"{'='*40}\n")
            
            return {
                "success": result.success,
                "summary": result.final_summary,
                "cycles": result.total_cycles,
                "time_seconds": result.execution_time_seconds
            }
            
        except Exception as exc:
            print(f"\n[FATAL ERROR] {str(exc)}")
            return {"success": False, "summary": str(exc)}
        finally:
            self.is_running = False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        runner = DualAgentRunner()
        runner.run(task)
    else:
        print("Usage: python runner.py 'task description'")
