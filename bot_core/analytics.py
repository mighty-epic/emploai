"""
Analytics and Insights for Telegram Agent
Tracks usage, skills, tokens, and provides insights
"""

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter


logger = logging.getLogger(__name__)


def _default_storage_path() -> Path:
    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
    if runtime_home:
        return Path(runtime_home).expanduser().resolve() / "data" / "analytics.json"
    return Path(__file__).parent / "data" / "analytics.json"


@dataclass
class UsageEvent:
    """A single usage event."""
    timestamp: str
    user_id: int
    event_type: str  # 'message', 'command', 'skill_triggered', 'tool_used'
    details: Dict[str, Any]
    tokens_input: int = 0
    tokens_output: int = 0
    skill_name: Optional[str] = None
    command_name: Optional[str] = None
    duration_seconds: float = 0.0


class AnalyticsTracker:
    """
    Tracks usage analytics for the Telegram agent.
    
    Tracks:
    - Message counts and frequency
    - Token usage over time
    - Skill usage statistics
    - Command usage patterns
    - Response times
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize analytics tracker.
        
        Args:
            storage_path: Path to store analytics data
        """
        if storage_path is None:
            storage_path = _default_storage_path()
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.events: List[UsageEvent] = []
        self._load_data()
        
        logger.info(f"AnalyticsTracker initialized with {len(self.events)} events")
    
    def _load_data(self):
        """Load existing analytics data."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.events = [UsageEvent(**e) for e in data.get('events', [])]
            except Exception as e:
                logger.error(f"Error loading analytics: {e}")
                self.events = []
    
    def _save_data(self):
        """Save analytics data to disk."""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump({
                    'events': [asdict(e) for e in self.events],
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving analytics: {e}")
    
    def track_message(self, user_id: int, message_length: int, 
                     has_attachment: bool = False):
        """Track a user message."""
        event = UsageEvent(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            event_type='message',
            details={'length': message_length, 'has_attachment': has_attachment}
        )
        self.events.append(event)
        self._save_data()
    
    def track_command(self, user_id: int, command: str, success: bool = True):
        """Track a command execution."""
        event = UsageEvent(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            event_type='command',
            command_name=command,
            details={'success': success}
        )
        self.events.append(event)
        self._save_data()
    
    def track_skill_triggered(self, user_id: int, skill_name: str, 
                             message: str):
        """Track when a skill is triggered."""
        event = UsageEvent(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            event_type='skill_triggered',
            skill_name=skill_name,
            details={'triggered_by': message[:100]}
        )
        self.events.append(event)
        self._save_data()
    
    def track_llm_request(self, user_id: int, model: str, 
                         tokens_input: int, tokens_output: int,
                         duration_seconds: float):
        """Track an LLM request with token usage."""
        event = UsageEvent(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            event_type='llm_request',
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            duration_seconds=duration_seconds,
            details={'model': model}
        )
        self.events.append(event)
        self._save_data()
    
    def track_tool_used(self, user_id: int, tool_name: str, 
                       success: bool = True):
        """Track a tool usage."""
        event = UsageEvent(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            event_type='tool_used',
            details={'tool': tool_name, 'success': success}
        )
        self.events.append(event)
        self._save_data()
    
    def get_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get analytics summary for the specified period.
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Dict with summary statistics
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_events = [
            e for e in self.events 
            if datetime.fromisoformat(e.timestamp) > cutoff
        ]
        
        # Calculate metrics
        total_messages = sum(1 for e in recent_events if e.event_type == 'message')
        total_commands = sum(1 for e in recent_events if e.event_type == 'command')
        total_tokens = sum(
            e.tokens_input + e.tokens_output 
            for e in recent_events 
            if e.event_type == 'llm_request'
        )
        
        # Skill usage
        skill_counts: Counter[str] = Counter()
        for e in recent_events:
            if e.skill_name:
                skill_counts[e.skill_name] += 1
        
        # Command usage
        command_counts: Counter[str] = Counter()
        for e in recent_events:
            if e.command_name:
                command_counts[e.command_name] += 1
        
        # Model usage
        model_tokens = defaultdict(lambda: {'input': 0, 'output': 0})
        for e in recent_events:
            if e.event_type == 'llm_request' and e.details.get('model'):
                model = e.details['model']
                model_tokens[model]['input'] += e.tokens_input
                model_tokens[model]['output'] += e.tokens_output
        
        # Daily breakdown
        daily_counts = defaultdict(int)
        for e in recent_events:
            date = datetime.fromisoformat(e.timestamp).date().isoformat()
            daily_counts[date] += 1
        
        return {
            'period_days': days,
            'total_events': len(recent_events),
            'total_messages': total_messages,
            'total_commands': total_commands,
            'total_tokens': total_tokens,
            'avg_tokens_per_message': total_tokens / max(total_messages, 1),
            'top_skills': dict(skill_counts.most_common(5)),
            'top_commands': dict(command_counts.most_common(5)),
            'model_usage': dict(model_tokens),
            'daily_activity': dict(sorted(daily_counts.items())),
        }
    
    def get_user_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get stats for a specific user."""
        cutoff = datetime.now() - timedelta(days=days)
        user_events = [
            e for e in self.events 
            if e.user_id == user_id and datetime.fromisoformat(e.timestamp) > cutoff
        ]
        
        total_tokens = sum(
            e.tokens_input + e.tokens_output 
            for e in user_events 
            if e.event_type == 'llm_request'
        )
        
        return {
            'user_id': user_id,
            'period_days': days,
            'total_messages': sum(1 for e in user_events if e.event_type == 'message'),
            'total_commands': sum(1 for e in user_events if e.event_type == 'command'),
            'total_tokens': total_tokens,
            'skills_used': list(set(e.skill_name for e in user_events if e.skill_name)),
        }
    
    def format_summary_for_telegram(self, days: int = 7) -> str:
        """Format summary for Telegram display."""
        summary = self.get_summary(days)
        
        lines = [
            f"📊 *Analytics Summary (Last {days} Days)*\n",
            f"• Messages: {summary['total_messages']}",
            f"• Commands: {summary['total_commands']}",
            f"• Total Tokens: {summary['total_tokens']:,}",
            f"• Avg Tokens/Message: {summary['avg_tokens_per_message']:.0f}",
            "",
            "📚 *Most Used Skills:*"
        ]
        
        for skill, count in summary['top_skills'].items():
            lines.append(f"  • {skill}: {count} times")
        
        if not summary['top_skills']:
            lines.append("  No skills used")
        
        lines.extend(["", "⌨️ *Most Used Commands:*"])
        for cmd, count in summary['top_commands'].items():
            lines.append(f"  • /{cmd}: {count} times")
        
        if not summary['top_commands']:
            lines.append("  No commands used")
        
        lines.extend(["", "🤖 *Model Usage:*"])
        for model, tokens in summary['model_usage'].items():
            total = tokens['input'] + tokens['output']
            lines.append(f"  • {model}: {total:,} tokens")
        
        return "\n".join(lines)


# Global analytics tracker
_global_tracker: Optional[AnalyticsTracker] = None


def get_analytics_tracker(storage_path: Optional[Path] = None) -> AnalyticsTracker:
    """Get or create the global analytics tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = AnalyticsTracker(storage_path)
    return _global_tracker
