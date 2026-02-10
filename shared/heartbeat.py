"""
Heartbeat System - Proactive background checks
Similar to Moltbot's heartbeat polling
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatState:
    """Track heartbeat check history."""
    last_checks: Dict[str, float] = field(default_factory=dict)  # task_name -> timestamp
    last_heartbeat: Optional[float] = None
    check_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'last_checks': self.last_checks,
            'last_heartbeat': self.last_heartbeat,
            'check_count': self.check_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HeartbeatState':
        return cls(
            last_checks=data.get('last_checks', {}),
            last_heartbeat=data.get('last_heartbeat'),
            check_count=data.get('check_count', 0)
        )


class HeartbeatManager:
    """
    Manages proactive heartbeat checks.
    
    Polls HEARTBEAT.md for tasks to perform periodically.
    Can send notifications to user when something needs attention.
    """
    
    DEFAULT_PROMPT = (
        "Read HEARTBEAT.md if it exists. Follow it strictly. "
        "Do not infer or repeat old tasks from prior chats. "
        "If nothing needs attention, reply HEARTBEAT_OK."
    )
    
    def __init__(
        self,
        workspace: Path,
        interval_seconds: int = 1800,  # 30 minutes default
        announcement_callback: Optional[Callable[[str], None]] = None,
        agent_callback: Optional[Callable[[str], str]] = None
    ):
        """
        Initialize heartbeat manager.
        
        Args:
            workspace: Path to workspace containing HEARTBEAT.md
            interval_seconds: How often to check (default 30 min)
            announcement_callback: Function to announce results to user
            agent_callback: Function to run agent with prompt, returns response
        """
        self.workspace = Path(workspace)
        self.interval_seconds = interval_seconds
        self.announcement_callback = announcement_callback
        self.agent_callback = agent_callback
        
        self.state_file = self.workspace / "memory" / "heartbeat-state.json"
        self.state = self._load_state()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.enabled = False
    
    def _load_state(self) -> HeartbeatState:
        """Load heartbeat state from disk."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding='utf-8'))
                return HeartbeatState.from_dict(data)
            except Exception as e:
                logger.error(f"Error loading heartbeat state: {e}")
        
        return HeartbeatState()
    
    def _save_state(self):
        """Save heartbeat state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(
                json.dumps(self.state.to_dict(), indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"Error saving heartbeat state: {e}")
    
    def mark_check(self, task_name: str):
        """Mark a task as checked."""
        self.state.last_checks[task_name] = datetime.now().timestamp()
        self._save_state()
    
    def should_check(self, task_name: str, min_interval_seconds: int) -> bool:
        """Check if enough time has passed since last check."""
        last_check = self.state.last_checks.get(task_name)
        if last_check is None:
            return True
        
        elapsed = datetime.now().timestamp() - last_check
        return elapsed >= min_interval_seconds
    
    async def _heartbeat_loop(self):
        """Main heartbeat loop."""
        logger.info(f"Heartbeat loop started (interval: {self.interval_seconds}s)")
        
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                
                if not self._running:
                    break
                
                logger.debug("Heartbeat check triggered")
                await self._perform_heartbeat()
                
            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled")
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                # Continue loop even on error
    
    async def _perform_heartbeat(self):
        """Perform a single heartbeat check."""
        self.state.check_count += 1
        self.state.last_heartbeat = datetime.now().timestamp()
        self._save_state()
        
        # Read HEARTBEAT.md
        heartbeat_file = self.workspace / "HEARTBEAT.md"
        if not heartbeat_file.exists():
            logger.debug("No HEARTBEAT.md found, skipping check")
            return
        
        heartbeat_content = heartbeat_file.read_text(encoding='utf-8').strip()
        
        # Check if empty or only comments
        lines = [l.strip() for l in heartbeat_content.split('\n') if l.strip() and not l.strip().startswith('#')]
        if not lines:
            logger.debug("HEARTBEAT.md is empty or only has comments, skipping")
            return
        
        # Run agent with heartbeat prompt
        if self.agent_callback:
            try:
                logger.info("Running heartbeat agent callback")
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.agent_callback,
                    self.DEFAULT_PROMPT
                )
                
                # Check if response is just HEARTBEAT_OK
                if response and response.strip().upper() == "HEARTBEAT_OK":
                    logger.debug("Heartbeat: Nothing needs attention")
                    return
                
                # Something needs attention - announce it
                if response and self.announcement_callback:
                    logger.info("Heartbeat: Announcing result to user")
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        self.announcement_callback,
                        f"🔔 **Heartbeat Alert**\n\n{response}"
                    )
            except Exception as e:
                logger.error(f"Error in heartbeat agent callback: {e}")
        else:
            logger.warning("No agent callback configured for heartbeat")
    
    def start(self):
        """Start the heartbeat loop."""
        if self._running:
            logger.warning("Heartbeat already running")
            return
        
        self._running = True
        self.enabled = True
        
        # Create the background task
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._heartbeat_loop())
        
        logger.info("Heartbeat started")
    
    def stop(self):
        """Stop the heartbeat loop."""
        if not self._running:
            return
        
        self._running = False
        self.enabled = False
        
        if self._task:
            self._task.cancel()
            self._task = None
        
        logger.info("Heartbeat stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get heartbeat status."""
        return {
            'enabled': self.enabled,
            'running': self._running,
            'interval_seconds': self.interval_seconds,
            'check_count': self.state.check_count,
            'last_heartbeat': datetime.fromtimestamp(self.state.last_heartbeat).isoformat() if self.state.last_heartbeat else None,
            'last_checks': {
                task: datetime.fromtimestamp(ts).isoformat()
                for task, ts in self.state.last_checks.items()
            }
        }
    
    def set_interval(self, seconds: int):
        """Change the heartbeat interval."""
        old_interval = self.interval_seconds
        self.interval_seconds = seconds
        logger.info(f"Heartbeat interval changed: {old_interval}s -> {seconds}s")
        
        # Restart if running
        if self._running:
            self.stop()
            self.start()


# Global instance
_heartbeat_managers: Dict[str, HeartbeatManager] = {}


def get_heartbeat_manager(
    workspace: Path,
    interval_seconds: int = 1800,
    announcement_callback: Optional[Callable[[str], None]] = None,
    agent_callback: Optional[Callable[[str], str]] = None
) -> HeartbeatManager:
    """Get or create a heartbeat manager for a workspace."""
    key = str(workspace.resolve())
    if key not in _heartbeat_managers:
        _heartbeat_managers[key] = HeartbeatManager(
            workspace,
            interval_seconds,
            announcement_callback,
            agent_callback
        )
    return _heartbeat_managers[key]
