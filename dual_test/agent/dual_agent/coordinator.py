"""
Dual Agent Coordinator
Manages communication between Memory Agent and Executor Agent.
"""

from dotenv import load_dotenv
load_dotenv()

import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

from .memory_agent import MemoryAgent
from .executor_agent import ExecutorAgent
from .schemas import ExecutorRequest, ExecutorResponse, RequestType

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class ExecutionLog:
    """Log entry for execution history."""
    cycle: int
    thought: str
    request: Optional[str]
    response_summary: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskResult:
    """Result of task execution."""
    task: str
    success: bool
    total_cycles: int
    execution_time_seconds: float
    final_summary: str
    execution_log: list = field(default_factory=list)


class DualAgentCoordinator:
    """
    Coordinates the Memory Agent and Executor Agent.
    Manages the task execution loop.
    """
    
    def __init__(
        self,
        memory_model: str = "gpt-4o",
        executor_model: str = "gpt-4o-mini",
        headless: bool = False,
        log_dir: str = "test_outputs/dual_agent_logs",
        event_callback: Optional[Callable] = None
    ):
        self.memory_agent = MemoryAgent(model=memory_model)
        self.executor_agent = ExecutorAgent(model=executor_model)
        self.headless = headless
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback
        
        # Browser instance
        self.driver = None
        
        # Execution tracking
        self.execution_log: list = []
        self.current_cycle = 0
        
        # Pause/Cancel state
        self.is_paused = False
        self.pause_requested = False
        self.cancel_requested = False
    
    def get_memory_agent(self) -> MemoryAgent:
        """Get the memory agent for mid-task conversation."""
        return self.memory_agent
    
    def request_pause(self):
        """Request the coordinator to pause at the next safe point."""
        self.pause_requested = True
        self._emit("pause_requested", {})
    
    def request_cancel(self):
        """Request the coordinator to cancel the task completely."""
        self.cancel_requested = True
        self._emit("cancel_requested", {})
    
    def resume(self):
        """Resume execution after a pause."""
        self.is_paused = False
        self.pause_requested = False
        self._emit("resumed", {})
    
    def _emit(self, event_type: str, data: Dict):
        """Emit event to callback if registered."""
        if self.event_callback:
            self.event_callback(event_type, data)
        
        # Also print for debugging
        print(f"[{event_type}] {json.dumps(data, indent=2, default=str)[:500]}")
    
    def start_browser(self, url: Optional[str] = None):
        """Start browser for web tasks."""
        if not SELENIUM_AVAILABLE:
            self._emit("error", {"message": "Selenium not available"})
            return
        
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_window_size(1280, 900)
        
        if url:
            self.driver.get(url)
        
        # Share browser with executor
        self.executor_agent.set_browser(self.driver)
        
        self._emit("browser_started", {"url": url})
    
    def stop_browser(self):
        """Stop browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def execute_task(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_cycles: int = 50
    ) -> TaskResult:
        """
        Execute a task using the dual-agent architecture.
        
        Args:
            task: The task to complete
            start_url: Optional URL to start browser at (for web tasks)
            max_cycles: Maximum number of think-act cycles
        
        Returns:
            TaskResult with execution details
        """
        start_time = time.time()
        self.execution_log = []
        self.current_cycle = 0
        
        self._emit("task_started", {"task": task, "start_url": start_url})
        
        # Start browser if URL provided
        if start_url:
            self.start_browser(start_url)
        
        # Initialize task in Memory Agent
        self.memory_agent.initialize_task(task)
        
        try:
            # Main execution loop
            is_complete = False
            final_summary = ""
            
            while self.current_cycle < max_cycles and not is_complete and not self.is_paused and not self.cancel_requested:
                # Check for pause/cancel request before starting cycle
                if self.cancel_requested:
                    self._emit("cancelled", {"cycle": self.current_cycle})
                    break
                if self.pause_requested:
                    self.is_paused = True
                    self._emit("paused", {"cycle": self.current_cycle, "reason": "User requested pause"})
                    break
                
                self.current_cycle += 1
                
                self._emit("cycle_start", {"cycle": self.current_cycle})
                
                # Memory Agent thinks and decides
                thought, request, is_complete = self.memory_agent.think_and_act()
                
                self._emit("memory_thought", {
                    "cycle": self.current_cycle,
                    "thought": thought[:500],
                    "has_request": request is not None,
                    "is_complete": is_complete
                })
                
                if is_complete:
                    final_summary = thought
                    break
                
                # If there's a request, send to Executor
                response_summary = "No request"
                if request:
                    self._emit("executor_request", {
                        "cycle": self.current_cycle,
                        "request": request.to_prompt()
                    })
                    
                    # Executor executes (fresh each time)
                    response = self.executor_agent.execute(request)
                    
                    response_summary = self._summarize_response(response)
                    
                    self._emit("executor_response", {
                        "cycle": self.current_cycle,
                        "success": not response.impossible and (
                            (response.observation and response.observation.success) or
                            (response.action and response.action.success)
                        ),
                        "summary": response_summary
                    })
                    
                    # Feed response back to Memory Agent
                    self.memory_agent.receive_executor_response(request, response, thought)
                
                # Log this cycle
                self.execution_log.append(ExecutionLog(
                    cycle=self.current_cycle,
                    thought=thought,
                    request=request.to_prompt() if request else None,
                    response_summary=response_summary
                ))
                
                # Check for pause/cancel request after cycle completes
                if self.cancel_requested:
                    self._emit("cancelled", {"cycle": self.current_cycle})
                    break
                if self.pause_requested:
                    self.is_paused = True
                    self._emit("paused", {"cycle": self.current_cycle, "reason": "User requested pause"})
                    break
                
                # Small delay to prevent rate limiting
                time.sleep(0.5)
            
            # Check if cancelled
            if self.cancel_requested:
                return TaskResult(
                    task=task,
                    success=False,
                    total_cycles=self.current_cycle,
                    execution_time_seconds=time.time() - start_time,
                    final_summary="[CANCELLED] Task cancelled by user.",
                    execution_log=[vars(log) for log in self.execution_log]
                )

            # Check if paused
            if self.is_paused:
                return TaskResult(
                    task=task,
                    success=False,  # Not complete
                    total_cycles=self.current_cycle,
                    execution_time_seconds=time.time() - start_time,
                    final_summary="[PAUSED] Task paused by user. Use /continue to resume.",
                    execution_log=[vars(log) for log in self.execution_log]
                )
            
            # Check if we hit max cycles
            if self.current_cycle >= max_cycles and not is_complete:
                final_summary = f"Task incomplete after {max_cycles} cycles"
            
            # Calculate result
            success = is_complete and "success" in final_summary.lower()
            
            return TaskResult(
                task=task,
                success=success,
                total_cycles=self.current_cycle,
                execution_time_seconds=time.time() - start_time,
                final_summary=final_summary,
                execution_log=[vars(log) for log in self.execution_log]
            )
            
        except Exception as e:
            self._emit("error", {"message": str(e)})
            return TaskResult(
                task=task,
                success=False,
                total_cycles=self.current_cycle,
                execution_time_seconds=time.time() - start_time,
                final_summary=f"Error: {str(e)}",
                execution_log=[vars(log) for log in self.execution_log]
            )
        
        finally:
            # Don't stop browser if paused - we might resume
            if start_url and not self.is_paused:
                self.stop_browser()
    
    def continue_task(self, max_cycles: int = 50) -> TaskResult:
        """
        Continue a paused task from where it left off.
        
        Args:
            max_cycles: Maximum additional cycles to run
            
        Returns:
            TaskResult with execution details
        """
        if not self.is_paused:
            return TaskResult(
                task="",
                success=False,
                total_cycles=0,
                execution_time_seconds=0,
                final_summary="No paused task to continue.",
                execution_log=[]
            )
        
        if not self.memory_agent.context:
            return TaskResult(
                task="",
                success=False,
                total_cycles=0,
                execution_time_seconds=0,
                final_summary="No task context available.",
                execution_log=[]
            )
        
        # Resume execution
        self.resume()
        task = self.memory_agent.context.task
        start_time = time.time()
        start_cycle = self.current_cycle
        
        self._emit("task_resumed", {"task": task, "cycle": self.current_cycle})
        
        try:
            is_complete = False
            final_summary = ""
            
            while self.current_cycle < start_cycle + max_cycles and not is_complete and not self.is_paused and not self.cancel_requested:
                if self.cancel_requested:
                    self._emit("cancelled", {"cycle": self.current_cycle})
                    break
                if self.pause_requested:
                    self.is_paused = True
                    self._emit("paused", {"cycle": self.current_cycle, "reason": "User requested pause"})
                    break
                
                self.current_cycle += 1
                
                self._emit("cycle_start", {"cycle": self.current_cycle})
                
                thought, request, is_complete = self.memory_agent.think_and_act()
                
                self._emit("memory_thought", {
                    "cycle": self.current_cycle,
                    "thought": thought[:500],
                    "has_request": request is not None,
                    "is_complete": is_complete
                })
                
                if is_complete:
                    final_summary = thought
                    break
                
                response_summary = "No request"
                if request:
                    self._emit("executor_request", {
                        "cycle": self.current_cycle,
                        "request": request.to_prompt()
                    })
                    
                    response = self.executor_agent.execute(request)
                    response_summary = self._summarize_response(response)
                    
                    self._emit("executor_response", {
                        "cycle": self.current_cycle,
                        "success": not response.impossible and (
                            (response.observation and response.observation.success) or
                            (response.action and response.action.success)
                        ),
                        "summary": response_summary
                    })
                    
                    self.memory_agent.receive_executor_response(request, response, thought)
                
                self.execution_log.append(ExecutionLog(
                    cycle=self.current_cycle,
                    thought=thought,
                    request=request.to_prompt() if request else None,
                    response_summary=response_summary
                ))
                
                if self.cancel_requested:
                    self._emit("cancelled", {"cycle": self.current_cycle})
                    break
                if self.pause_requested:
                    self.is_paused = True
                    self._emit("paused", {"cycle": self.current_cycle, "reason": "User requested pause"})
                    break
                
                time.sleep(0.5)
            
            if self.cancel_requested:
                return TaskResult(
                    task=task,
                    success=False,
                    total_cycles=self.current_cycle,
                    execution_time_seconds=time.time() - start_time,
                    final_summary="[CANCELLED] Task cancelled by user.",
                    execution_log=[vars(log) for log in self.execution_log]
                )
            
            if self.is_paused:
                return TaskResult(
                    task=task,
                    success=False,
                    total_cycles=self.current_cycle,
                    execution_time_seconds=time.time() - start_time,
                    final_summary="[PAUSED] Task paused by user. Use /continue to resume.",
                    execution_log=[vars(log) for log in self.execution_log]
                )
            
            if self.current_cycle >= start_cycle + max_cycles and not is_complete:
                final_summary = f"Task incomplete after {max_cycles} additional cycles"
            
            success = is_complete and "success" in final_summary.lower()
            
            return TaskResult(
                task=task,
                success=success,
                total_cycles=self.current_cycle,
                execution_time_seconds=time.time() - start_time,
                final_summary=final_summary,
                execution_log=[vars(log) for log in self.execution_log]
            )
            
        except Exception as e:
            self._emit("error", {"message": str(e)})
            return TaskResult(
                task=task,
                success=False,
                total_cycles=self.current_cycle,
                execution_time_seconds=time.time() - start_time,
                final_summary=f"Error: {str(e)}",
                execution_log=[vars(log) for log in self.execution_log]
            )
    
    def _summarize_response(self, response: ExecutorResponse) -> str:
        """Summarize executor response for logging."""
        if response.impossible:
            return f"IMPOSSIBLE: {response.impossible_reason}"
        
        if response.observation:
            obs = response.observation
            if obs.success:
                return f"Observed: {obs.screen_title}, {len(obs.key_elements)} elements"
            return f"Observation failed: {obs.error}"
        
        if response.action:
            act = response.action
            if act.success:
                return f"Action succeeded: {act.action_taken}"
            return f"Action failed: {act.failure_reason}"
        
        return "Unknown response"
    
    def save_log(self, filename: Optional[str] = None):
        """Save execution log to file."""
        if not filename:
            filename = f"dual_agent_log_{int(time.time())}.json"
        
        filepath = self.log_dir / filename
        
        with open(filepath, "w") as f:
            json.dump({
                "execution_log": [vars(log) for log in self.execution_log],
                "context_summary": self.memory_agent.get_context_summary()
            }, f, indent=2, default=str)
        
        return str(filepath)


# ============================================================
# Convenience function for testing
# ============================================================

def run_dual_agent_task(
    task: str,
    start_url: Optional[str] = None,
    memory_model: str = "gpt-4o",
    executor_model: str = "gpt-4o-mini",
    max_cycles: int = 50,
    verbose: bool = True
) -> TaskResult:
    """
    Convenience function to run a task with the dual-agent architecture.
    
    Args:
        task: Task description
        start_url: Optional starting URL for browser tasks
        memory_model: LLM model for Memory Agent
        executor_model: LLM model for Executor Agent
        max_cycles: Maximum execution cycles
        verbose: Print progress
    
    Returns:
        TaskResult
    """
    def event_handler(event_type: str, data: Dict):
        if verbose:
            if event_type == "memory_thought":
                print(f"\n[Cycle {data['cycle']}] Memory Agent thinking...")
                print(f"  Thought: {data['thought'][:100]}...")
            elif event_type == "executor_request":
                print(f"  -> Request: {data['request']}")
            elif event_type == "executor_response":
                status = "[OK]" if data['success'] else "[FAIL]"
                print(f"  <- Response: {status} {data['summary']}")
    
    coordinator = DualAgentCoordinator(
        memory_model=memory_model,
        executor_model=executor_model,
        event_callback=event_handler if verbose else None
    )
    
    result = coordinator.execute_task(
        task=task,
        start_url=start_url,
        max_cycles=max_cycles
    )
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Task: {result.task}")
        print(f"Success: {result.success}")
        print(f"Cycles: {result.total_cycles}")
        print(f"Time: {result.execution_time_seconds:.1f}s")
        print(f"Summary: {result.final_summary}")
    
    return result
