"""
Spawn Tool - Sub-agent spawning capability for parallel task execution.
Inspired by Moltbot's sessions-spawn-tool.ts
Enables "Parallel Researcher" flow - spawn background tasks while continuing main chat.
"""

import asyncio
import uuid
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SubAgentStatus(Enum):
    """Status of a sub-agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class SubAgentTask:
    """Represents a spawned sub-agent task."""
    id: str
    prompt: str
    status: SubAgentStatus
    created_at: float
    headless: bool = True
    max_turns: int = 20
    result: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[float] = None
    turns_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "prompt": self.prompt[:100] + "..." if len(self.prompt) > 100 else self.prompt,
            "status": self.status.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "headless": self.headless,
            "max_turns": self.max_turns,
            "result": self.result[:500] + "..." if self.result and len(self.result) > 500 else self.result,
            "error": self.error,
            "completed_at": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            "turns_used": self.turns_used
        }


class SpawnTool:
    """
    Tool for spawning sub-agents to run tasks in parallel.
    Similar to Moltbot's sessions-spawn-tool.ts
    """
    
    def __init__(
        self,
        agent_factory: Optional[Callable[[bool], Any]] = None,
        announcement_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize spawn tool.
        
        Args:
            agent_factory: Function that creates agent instance (headless: bool) -> agent
            announcement_callback: Function for sending announcements
        """
        self.agent_factory = agent_factory
        self.announcement_callback = announcement_callback
        
        self.tasks: Dict[str, SubAgentTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def spawn(
        self,
        prompt: str,
        headless: bool = True,
        max_turns: int = 20,
        announce_on_complete: bool = True
    ) -> str:
        """
        Spawn a sub-agent to run a task in the background.
        
        Args:
            prompt: The task prompt for the sub-agent
            headless: Whether to run in headless mode (default True)
            max_turns: Maximum turns for the sub-agent
            announce_on_complete: Whether to announce when complete
        
        Returns:
            Task ID for tracking
        """
        task_id = f"sub-{str(uuid.uuid4())[:6]}"
        
        task = SubAgentTask(
            id=task_id,
            prompt=prompt,
            status=SubAgentStatus.PENDING,
            created_at=time.time(),
            headless=headless,
            max_turns=max_turns
        )
        
        self.tasks[task_id] = task
        
        # Start the task
        asyncio.create_task(
            self._run_sub_agent(task, announce_on_complete)
        )
        
        return task_id
    
    async def _run_sub_agent(
        self,
        task: SubAgentTask,
        announce: bool = True
    ) -> None:
        """Run the sub-agent in background."""
        task.status = SubAgentStatus.RUNNING
        
        try:
            if not self.agent_factory:
                raise RuntimeError("No agent factory configured")
            
            # Create agent instance (headless mode)
            agent = self.agent_factory(task.headless)
            
            # Run the task (this would be blocking, so we run in thread)
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: agent.run(task.prompt, max_turns=task.max_turns)
            )
            
            task.result = result
            task.status = SubAgentStatus.COMPLETED
            task.completed_at = time.time()
            
            # Announce completion
            if announce and self.announcement_callback:
                await self.announcement_callback(
                    f"🤖 **Sub-Agent Report [{task.id}]**\n\n{result[:1000]}"
                )
        
        except Exception as e:
            task.status = SubAgentStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            
            if announce and self.announcement_callback:
                await self.announcement_callback(
                    f"❌ **Sub-Agent Failed [{task.id}]**\n\n{str(e)}"
                )
    
    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def list_tasks(
        self,
        status: Optional[SubAgentStatus] = None
    ) -> List[SubAgentTask]:
        """List all tasks, optionally filtered by status."""
        if status:
            return [t for t in self.tasks.values() if t.status == status]
        return list(self.tasks.values())
    
    def stop_task(self, task_id: str) -> bool:
        """Stop a running task."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        if task.status == SubAgentStatus.RUNNING:
            task.status = SubAgentStatus.STOPPED
            
            # Cancel the async task if still running
            if task_id in self._running_tasks:
                self._running_tasks[task_id].cancel()
            
            return True
        
        return False

    def stop_all_tasks(self) -> int:
        """Stop all running sub-agent tasks."""
        stopped = 0
        for task_id, task in list(self.tasks.items()):
            if task.status != SubAgentStatus.RUNNING:
                continue
            task.status = SubAgentStatus.STOPPED
            task.completed_at = time.time()
            running_task = self._running_tasks.get(task_id)
            if running_task:
                running_task.cancel()
            stopped += 1
        return stopped
    
    def cleanup_completed(self, max_age_hours: float = 24) -> int:
        """Remove old completed tasks."""
        now = time.time()
        to_remove = []
        
        for task_id, task in self.tasks.items():
            if task.status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED, SubAgentStatus.STOPPED):
                if task.completed_at and (now - task.completed_at) > (max_age_hours * 3600):
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
        
        return len(to_remove)
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall spawn tool status."""
        return {
            "total_tasks": len(self.tasks),
            "running": len([t for t in self.tasks.values() if t.status == SubAgentStatus.RUNNING]),
            "completed": len([t for t in self.tasks.values() if t.status == SubAgentStatus.COMPLETED]),
            "failed": len([t for t in self.tasks.values() if t.status == SubAgentStatus.FAILED]),
            "tasks": [t.to_dict() for t in list(self.tasks.values())[-10:]]  # Last 10
        }


# Tool definitions for agent integration
SPAWN_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "spawn_sub_agent",
            "description": "Spawn a sub-agent to complete a task in parallel. The sub-agent runs in the background while you continue the main conversation. Results are announced when ready.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task for the sub-agent to complete (e.g., 'Read docs for FastAPI and summarize Middleware section')"
                    },
                    "headless": {
                        "type": "boolean",
                        "default": True,
                        "description": "Run in headless mode (no visible browser). Recommended for background tasks."
                    },
                    "max_turns": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum turns for the sub-agent"
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_sub_agents",
            "description": "List all spawned sub-agents and their current status.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sub_agent_result",
            "description": "Get the full result of a completed sub-agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The sub-agent task ID"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_sub_agent",
            "description": "Stop a running sub-agent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The sub-agent task ID to stop"}
                },
                "required": ["task_id"]
            }
        }
    }
]


# Global spawn tool instance
_global_spawn_tool: Optional[SpawnTool] = None


def get_spawn_tool(
    agent_factory: Optional[Callable[[bool], Any]] = None,
    announcement_callback: Optional[Callable[[str], None]] = None
) -> SpawnTool:
    """Get or create the global spawn tool instance."""
    global _global_spawn_tool
    if _global_spawn_tool is None:
        _global_spawn_tool = SpawnTool(
            agent_factory=agent_factory,
            announcement_callback=announcement_callback
        )
    return _global_spawn_tool


def create_spawn_tool(
    agent_factory: Optional[Callable[[bool], Any]] = None,
    announcement_callback: Optional[Callable[[str], None]] = None
) -> SpawnTool:
    """Create a new spawn tool instance (not global)."""
    return SpawnTool(
        agent_factory=agent_factory,
        announcement_callback=announcement_callback
    )
