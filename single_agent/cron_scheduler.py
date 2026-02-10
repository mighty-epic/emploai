"""
Cron Scheduler - Recurring task scheduler for agents.
Inspired by Moltbot's server-cron.ts and CronService.
Stores jobs in jobs.json, runs headless agents on schedule.
"""

import os
import json
import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
import threading


@dataclass
class CronJob:
    """Represents a scheduled job."""
    id: str
    name: str
    prompt: str
    schedule: str  # Cron expression or natural language
    next_run: float  # Unix timestamp
    interval_seconds: int  # For simple intervals
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    run_count: int = 0
    error_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CronJob':
        """Create from dictionary."""
        return cls(**data)


class CronScheduler:
    """
    Cron scheduler for running headless agent tasks on a schedule.
    Similar to Moltbot's CronService.
    """
    
    def __init__(
        self,
        job_store: str = "jobs.json",
        check_interval: int = 60,
        spawn_callback: Optional[Callable[[str, str], None]] = None,
        announcement_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the cron scheduler.
        
        Args:
            job_store: Path to JSON file for job persistence
            check_interval: Seconds between job checks
            spawn_callback: Function to call when spawning a job (job_id, prompt)
            announcement_callback: Function to call for announcements
        """
        self.job_store = Path(job_store)
        self.check_interval = check_interval
        self.spawn_callback = spawn_callback
        self.announcement_callback = announcement_callback
        
        self.jobs: Dict[str, CronJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Load existing jobs
        self._load_jobs()
    
    def _load_jobs(self) -> None:
        """Load jobs from disk."""
        if self.job_store.exists():
            try:
                with open(self.job_store, 'r') as f:
                    data = json.load(f)
                    for job_data in data.get('jobs', []):
                        job = CronJob.from_dict(job_data)
                        self.jobs[job.id] = job
                print(f"[Cron] Loaded {len(self.jobs)} jobs from {self.job_store}")
            except Exception as e:
                print(f"[Cron] Error loading jobs: {e}")
    
    def _save_jobs(self) -> None:
        """Save jobs to disk."""
        try:
            data = {
                'jobs': [job.to_dict() for job in self.jobs.values()],
                'saved_at': time.time()
            }
            with open(self.job_store, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Cron] Error saving jobs: {e}")
    
    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        print("[Cron] Scheduler started")
    
    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[Cron] Scheduler stopped")
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks for due jobs."""
        while self._running:
            try:
                await self._check_jobs()
            except Exception as e:
                print(f"[Cron] Error in scheduler loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.check_interval)
    
    async def _check_jobs(self) -> None:
        """Check for and execute due jobs."""
        now = time.time()
        
        async with self._lock:
            for job in self.jobs.values():
                if not job.enabled:
                    continue
                
                if now >= job.next_run:
                    # Job is due - execute it
                    await self._execute_job(job)
                    
                    # Update next run time
                    job.last_run = now
                    job.run_count += 1
                    job.next_run = now + job.interval_seconds
        
        # Save after any changes
        self._save_jobs()
    
    async def _execute_job(self, job: CronJob) -> None:
        """Execute a scheduled job."""
        print(f"[Cron] Executing job '{job.name}' (ID: {job.id})")
        
        try:
            # Announce if callback provided
            if self.announcement_callback:
                await self.announcement_callback(f"🌞 **Scheduled Job Starting**: {job.name}")
            
            # Spawn the agent via callback
            if self.spawn_callback:
                await self.spawn_callback(job.id, job.prompt)
            else:
                print(f"[Cron] No spawn callback set for job {job.id}")
        
        except Exception as e:
            print(f"[Cron] Error executing job {job.id}: {e}")
            job.error_count += 1
    
    def add_job(
        self,
        name: str,
        prompt: str,
        interval_seconds: int,
        enabled: bool = True
    ) -> str:
        """
        Add a new recurring job.
        
        Args:
            name: Human-readable job name
            prompt: The task prompt for the agent
            interval_seconds: How often to run (in seconds)
            enabled: Whether job is initially enabled
        
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())[:8]
        
        job = CronJob(
            id=job_id,
            name=name,
            prompt=prompt,
            schedule=f"every {interval_seconds}s",
            next_run=time.time(),  # Run immediately on next check
            interval_seconds=interval_seconds,
            enabled=enabled
        )
        
        async def _add():
            async with self._lock:
                self.jobs[job_id] = job
                self._save_jobs()
        
        # Run in event loop if available, else run directly
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_add())
        except RuntimeError:
            # No event loop running
            self.jobs[job_id] = job
            self._save_jobs()
        
        print(f"[Cron] Added job '{name}' (ID: {job_id}, interval: {interval_seconds}s)")
        return job_id
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs()
            print(f"[Cron] Removed job {job_id}")
            return True
        return False
    
    def enable_job(self, job_id: str) -> bool:
        """Enable a job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = True
            self._save_jobs()
            return True
        return False
    
    def disable_job(self, job_id: str) -> bool:
        """Disable a job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = False
            self._save_jobs()
            return True
        return False
    
    def get_job(self, job_id: str) -> Optional[CronJob]:
        """Get a job by ID."""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[CronJob]:
        """List all jobs."""
        return list(self.jobs.values())
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        now = time.time()
        return {
            "running": self._running,
            "total_jobs": len(self.jobs),
            "enabled_jobs": sum(1 for j in self.jobs.values() if j.enabled),
            "next_check_in": self.check_interval,
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "next_run": datetime.fromtimestamp(j.next_run).isoformat() if j.next_run else None,
                    "last_run": datetime.fromtimestamp(j.last_run).isoformat() if j.last_run else None,
                    "run_count": j.run_count,
                    "due": j.next_run and now >= j.next_run
                }
                for j in self.jobs.values()
            ]
        }
    
    def run_job_now(self, job_id: str) -> bool:
        """Manually trigger a job to run immediately."""
        job = self.jobs.get(job_id)
        if not job:
            return False
        
        # Set next_run to now (will be picked up on next check)
        job.next_run = time.time()
        self._save_jobs()
        return True


# Natural language parsing for common schedules
def parse_schedule(schedule_text: str) -> Optional[int]:
    """
    Parse natural language schedule to interval in seconds.
    
    Examples:
        "every 1 minute" -> 60
        "every 5 minutes" -> 300
        "every 1 hour" -> 3600
        "every day at 08:00" -> 86400 (next 08:00)
    """
    text = schedule_text.lower().strip()
    
    # Parse "every N minutes/hours/seconds"
    if text.startswith("every "):
        parts = text[6:].split()
        if len(parts) >= 2:
            try:
                num = int(parts[0])
                unit = parts[1].rstrip('s')  # Remove trailing 's'
                
                if unit == "minute":
                    return num * 60
                elif unit == "hour":
                    return num * 3600
                elif unit == "day":
                    return num * 86400
                elif unit == "second":
                    return num
            except ValueError:
                pass
    
    # Parse "every day at HH:MM"
    if "every day at " in text:
        # For simplicity, return 1 day interval
        # In production, you'd calculate seconds until next occurrence
        return 86400
    
    return None


# Tool definitions for agent integration
CRON_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_job",
            "description": "Schedule a recurring task to run automatically. Jobs are persisted and survive restarts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Human-readable name for the job"},
                    "prompt": {"type": "string", "description": "The task to execute (e.g., 'Check news.ycombinator.com for top AI launch')"},
                    "schedule": {"type": "string", "description": "Schedule expression like 'every 1 hour', 'every 5 minutes', 'every day at 08:00'"}
                },
                "required": ["name", "prompt", "schedule"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_jobs",
            "description": "List all scheduled recurring jobs with their status.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_scheduled_job",
            "description": "Remove a scheduled job by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job ID to remove"}
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enable_job",
            "description": "Enable a previously disabled job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"}
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "disable_job",
            "description": "Disable a job without removing it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"}
                },
                "required": ["job_id"]
            }
        }
    }
]


# Global scheduler instance (singleton pattern)
_global_scheduler: Optional[CronScheduler] = None


def get_scheduler(
    job_store: str = "jobs.json",
    spawn_callback: Optional[Callable[[str, str], None]] = None,
    announcement_callback: Optional[Callable[[str], None]] = None
) -> CronScheduler:
    """Get or create the global scheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = CronScheduler(
            job_store=job_store,
            spawn_callback=spawn_callback,
            announcement_callback=announcement_callback
        )
    return _global_scheduler


def create_scheduler(
    job_store: str = "jobs.json",
    spawn_callback: Optional[Callable[[str, str], None]] = None,
    announcement_callback: Optional[Callable[[str], None]] = None
) -> CronScheduler:
    """Create a new scheduler instance (not global)."""
    return CronScheduler(
        job_store=job_store,
        spawn_callback=spawn_callback,
        announcement_callback=announcement_callback
    )
