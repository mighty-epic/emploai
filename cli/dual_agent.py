"""
CLI Dual Agent Runner
Bridge between the TUI and the dual-agent architecture.
Provides all automation capabilities to the terminal interface.
"""

from dotenv import load_dotenv
load_dotenv()

import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.dual_agent.coordinator import DualAgentCoordinator
from agent.dual_agent.memory_agent import MemoryAgent
from agent.dual_agent.executor_agent import ExecutorAgent
from agent.dual_agent.schemas import (
    ExecutorRequest, ExecutorResponse, RequestType,
    ObserveRequest, ActionRequest, ObservationMethod, ActionType
)


@dataclass
class TaskEvent:
    """Event emitted during task execution."""
    event_type: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class DualAgentRunner:
    """
    CLI-friendly wrapper for the dual-agent architecture.
    Provides streaming output and all automation capabilities.
    """
    
    def __init__(
        self,
        memory_model: str = "gpt-4o",
        executor_model: str = "gpt-4o-mini",
        log_callback: Optional[Callable[[str], None]] = None,
        detail_callback: Optional[Callable[[str], None]] = None
    ):
        self.memory_model = memory_model
        self.executor_model = executor_model
        self.log_callback = log_callback
        self.detail_callback = detail_callback
        self.events: list[TaskEvent] = []
        
        # The coordinator handles everything
        self.coordinator: Optional[DualAgentCoordinator] = None
        
        # Task state tracking
        self.is_running = False
        self.start_time: Optional[float] = None
        self.current_task: Optional[str] = None
    
    @property
    def is_paused(self) -> bool:
        """Check if the task is currently paused."""
        return self.coordinator is not None and self.coordinator.is_paused
    
    @property
    def pause_requested(self) -> bool:
        """Check if a pause has been requested but not yet active."""
        return self.coordinator is not None and self.coordinator.pause_requested
    
    @property
    def cancel_requested(self) -> bool:
        """Check if a cancellation has been requested."""
        return self.coordinator is not None and self.coordinator.cancel_requested
    
    def request_pause(self):
        """Request the running task to pause at the next safe point."""
        if self.coordinator:
            self.coordinator.request_pause()
            self._log("[PAUSE] Pause requested. Will pause after current cycle...")
    
    def request_cancel(self):
        """Request the running task to cancel completely."""
        if self.coordinator:
            if self.coordinator.cancel_requested:
                return # Already cancelling
                
            self.coordinator.request_cancel()
            self._log("[CANCEL] Cancel requested. Stopping task...")
            # If already paused, we need to manually clean up as no loop is running to catch it
            if self.is_paused:
                self.coordinator.is_paused = False
                self.is_running = False
                self.start_time = None
                self._log("[CANCEL] Task was paused, now cancelled and cleaned up.")
                if self.coordinator.driver:
                    self.coordinator.stop_browser()
    
    def chat_with_memory(self, message: str) -> str:
        """
        Chat with the Memory Agent during a pause.
        
        Args:
            message: User's message
            
        Returns:
            Memory Agent's response
        """
        if not self.coordinator:
            return "No task is currently active."
        
        if not self.is_paused:
            return "Task is not paused. Use Esc+Esc to pause first."
        
        memory_agent = self.coordinator.get_memory_agent()
        response = memory_agent.chat_with_user(message)
        
        # Also inject as instruction for when we resume
        memory_agent.inject_user_instruction(message)
        
        return response
    
    def continue_task(self, max_cycles: int = 50) -> Dict[str, Any]:
        """
        Continue a paused task.
        
        Args:
            max_cycles: Maximum additional cycles to run
            
        Returns:
            Result dictionary
        """
        if not self.coordinator:
            return {"success": False, "summary": "No task to continue."}
        
        if not self.is_paused:
            return {"success": False, "summary": "Task is not paused."}
        
        self._log("\n" + "="*60)
        self._log("RESUMING DUAL-AGENT TASK")
        self._log("="*60 + "\n")
        
        self.is_running = True
        
        try:
            result = self.coordinator.continue_task(max_cycles=max_cycles)
            
            self._log("\n" + "="*60)
            if result.final_summary.startswith("[PAUSED]"):
                self._log("TASK PAUSED")
            else:
                self._log("TASK COMPLETE")
            self._log("="*60)
            self._log(f"Success: {result.success}")
            self._log(f"Cycles: {result.total_cycles}")
            self._log(f"Time: {result.execution_time_seconds:.1f}s")
            self._log(f"Summary: {result.final_summary}")
            self._log("="*60 + "\n")
            
            return {
                "success": result.success,
                "summary": result.final_summary,
                "cycles": result.total_cycles,
                "time_seconds": result.execution_time_seconds,
                "paused": self.is_paused,
                "events": [{"type": e.event_type, "data": e.data} for e in self.events],
                "log": result.execution_log
            }
            
        except Exception as exc:
            self._log(f"\n[FATAL ERROR] {str(exc)}")
            return {
                "success": False,
                "summary": f"Error: {str(exc)}",
                "cycles": 0,
                "time_seconds": 0,
                "paused": False,
                "events": [{"type": ev.event_type, "data": ev.data} for ev in self.events],
                "log": []
            }
        finally:
            if not self.is_paused:
                self.is_running = False
    
    def _log(self, message: str):
        """Log a message (to main log)."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def _log_detail(self, message: str):
        """Log a detailed message (to agent details log)."""
        if self.detail_callback:
            self.detail_callback(message)
        else:
            # Fallback to main log if no detail callback, but with a prefix
            self._log(f"  [Detail] {message}")
    
    def _event_handler(self, event_type: str, data: Dict):
        """Handle events from the coordinator."""
        event = TaskEvent(event_type=event_type, data=data)
        self.events.append(event)
        
        # Format for terminal output
        if event_type == "task_started":
            self._log(f"[TASK] Starting: {data.get('task', '')}")
        elif event_type == "cycle_start":
            self._log(f"\n[Cycle {data.get('cycle', '?')}]")
        elif event_type == "memory_thought":
            thought = data.get('thought', '')
            self._log(f"  Memory Agent thinking...")
            self._log_detail(f"[Cycle {data.get('cycle', '')}] Thought: {thought}\n")
        elif event_type == "executor_request":
            req = data.get('request', '')
            self._log(f"  -> Executor action: {req[:50]}...")
            self._log_detail(f"  -> Request: {req}\n")
        elif event_type == "executor_response":
            status = "[OK]" if data.get('success') else "[FAIL]"
            summary = data.get('summary', '')
            self._log(f"  <- {status} {summary[:50]}...")
            self._log_detail(f"  <- {status} {summary}\n")
        elif event_type == "error":
            self._log(f"[ERROR] {data.get('message', '')}")
    
    def run(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_cycles: int = 50
    ) -> Dict[str, Any]:
        """
        Run a task with the dual-agent architecture.
        
        Args:
            task: The task to complete (natural language)
            start_url: Optional URL for browser tasks
            max_cycles: Maximum execution cycles
        
        Returns:
            Result dictionary with success, summary, and details
        """
        self.events = []
        self.is_running = True
        self.start_time = time.time()
        self.current_task = task
        
        # Detect if this is a browser task
        browser_keywords = ['browser', 'website', 'web page', 'navigate', 'url', 'http', 'www', 'google', 'search online']
        is_browser_task = any(kw in task.lower() for kw in browser_keywords) or start_url is not None
        
        self._log(f"\n{'='*60}")
        self._log(f"DUAL-AGENT TASK EXECUTION")
        self._log(f"{'='*60}")
        self._log(f"Task: {task}")
        self._log(f"Mode: {'Browser' if is_browser_task else 'Desktop'}")
        if start_url:
            self._log(f"URL: {start_url}")
        self._log(f"Max cycles: {max_cycles}")
        self._log(f"{'='*60}\n")
        
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
            
            # Format result
            self._log(f"\n{'='*60}")
            if result.final_summary.startswith("[PAUSED]"):
                self._log(f"TASK PAUSED")
            else:
                self._log(f"TASK COMPLETE")
            self._log(f"{'='*60}")
            self._log(f"Success: {result.success}")
            self._log(f"Cycles: {result.total_cycles}")
            self._log(f"Time: {result.execution_time_seconds:.1f}s")
            self._log(f"Summary: {result.final_summary}")
            self._log(f"{'='*60}\n")
            
            return {
                "success": result.success,
                "summary": result.final_summary,
                "cycles": result.total_cycles,
                "time_seconds": result.execution_time_seconds,
                "paused": self.is_paused,
                "events": [{"type": e.event_type, "data": e.data} for e in self.events],
                "log": result.execution_log
            }
            
        except Exception as exc:
            self._log(f"\n[FATAL ERROR] {str(exc)}")
            return {
                "success": False,
                "summary": f"Error: {str(exc)}",
                "cycles": 0,
                "time_seconds": 0,
                "paused": False,
                "events": [{"type": ev.event_type, "data": ev.data} for ev in self.events],
                "log": []
            }
        finally:
            if not self.is_paused:
                self.is_running = False
                self.start_time = None
    
    def run_browser_task(self, task: str, url: str, max_cycles: int = 50) -> Dict[str, Any]:
        """Convenience method for browser tasks."""
        return self.run(task=task, start_url=url, max_cycles=max_cycles)
    
    def run_desktop_task(self, task: str, max_cycles: int = 50) -> Dict[str, Any]:
        """Convenience method for desktop automation tasks."""
        return self.run(task=task, start_url=None, max_cycles=max_cycles)


# ============================================================
# Quick Actions for Common Tasks
# ============================================================

class QuickActions:
    """
    Pre-defined quick actions for common automation tasks.
    These provide shortcuts for the CLI.
    """
    
    def __init__(self, runner: Optional[DualAgentRunner] = None):
        self.runner = runner or DualAgentRunner()
    
    def search_google(self, query: str) -> Dict[str, Any]:
        """Search Google for a query."""
        return self.runner.run_browser_task(
            task=f"Search Google for '{query}' and report the first 3 results",
            url="https://www.google.com"
        )
    
    def open_application(self, app_name: str) -> Dict[str, Any]:
        """Open a desktop application."""
        return self.runner.run_desktop_task(
            task=f"Open the {app_name} application and confirm it's open"
        )
    
    def type_in_app(self, app_name: str, text: str) -> Dict[str, Any]:
        """Type text into a focused application."""
        return self.runner.run_desktop_task(
            task=f"Focus {app_name}, then type the following text: {text}"
        )
    
    def take_screenshot(self) -> Dict[str, Any]:
        """Take a screenshot of the current screen."""
        return self.runner.run_desktop_task(
            task="Take a screenshot of the current screen and save it"
        )
    
    def describe_screen(self) -> Dict[str, Any]:
        """Describe what's currently visible on screen."""
        return self.runner.run_desktop_task(
            task="Observe the current screen and describe what you see"
        )


# ============================================================
# CLI Entry Point
# ============================================================

def main():
    """CLI entry point for running dual-agent tasks."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dual-Agent Task Runner")
    parser.add_argument("task", nargs="?", help="Task to execute")
    parser.add_argument("--url", help="Starting URL for browser tasks")
    parser.add_argument("--max-cycles", type=int, default=50, help="Maximum execution cycles")
    parser.add_argument("--memory-model", default="gpt-4o", help="LLM for Memory Agent")
    parser.add_argument("--executor-model", default="gpt-4o-mini", help="LLM for Executor Agent")
    parser.add_argument("--quick", choices=["google", "screenshot", "describe"], help="Quick action")
    parser.add_argument("--query", help="Query for quick actions like google search")
    
    args = parser.parse_args()
    
    runner = DualAgentRunner(
        memory_model=args.memory_model,
        executor_model=args.executor_model
    )
    
    # Quick actions
    if args.quick:
        quick = QuickActions(runner)
        if args.quick == "google":
            if not args.query:
                print("Error: --query required for google search")
                return
            result = quick.search_google(args.query)
        elif args.quick == "screenshot":
            result = quick.take_screenshot()
        elif args.quick == "describe":
            result = quick.describe_screen()
        return
    
    # Regular task
    if not args.task:
        print("Error: No task provided")
        print("Usage: python -m cli.dual_agent 'your task here'")
        print("       python -m cli.dual_agent --quick google --query 'search term'")
        return
    
    result = runner.run(
        task=args.task,
        start_url=args.url,
        max_cycles=args.max_cycles
    )
    
    # Return exit code based on success
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
