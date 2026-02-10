"""
Enhanced Skills Integration - Auto-trigger and seamless integration
Similar to Moltbot's skills system
"""

import re
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class SkillTrigger:
    """Defines when a skill should be auto-triggered."""
    pattern: str  # Regex pattern to match user message
    skill_name: str
    confidence: float = 1.0  # How confident we are this should trigger
    
    def matches(self, text: str) -> bool:
        """Check if this trigger matches the given text."""
        return bool(re.search(self.pattern, text, re.IGNORECASE))


class SkillMatcher:
    """
    Matches user messages to skills that should be triggered.
    Uses pattern matching and keyword detection.
    """
    
    def __init__(self):
        self.triggers: List[SkillTrigger] = []
        self._init_default_triggers()
    
    def _init_default_triggers(self):
        """Initialize common skill trigger patterns."""
        # Example triggers - these would normally be loaded from skill metadata
        self.triggers = [
            # Skill creation
            SkillTrigger(
                pattern=r'\b(create|make|write|build)\s+(a\s+)?(new\s+)?skill\b',
                skill_name='skill-creator',
                confidence=0.9
            ),
            # Skill finding
            SkillTrigger(
                pattern=r'\b(find|search|look\s+for|is\s+there)\s+(a\s+)?skill\b',
                skill_name='find-skills',
                confidence=0.9
            ),
            # File operations
            SkillTrigger(
                pattern=r'\b(read|write|edit|update|modify)\s+(the\s+)?file\b',
                skill_name='file-ops',
                confidence=0.8
            ),
            # Web search
            SkillTrigger(
                pattern=r'\b(search|google|look\s+up|find\s+info)\s+(for|about)\b',
                skill_name='web-search',
                confidence=0.7
            ),
        ]
    
    def add_trigger(self, trigger: SkillTrigger):
        """Add a new trigger pattern."""
        self.triggers.append(trigger)
        logger.info(f"Added trigger for skill: {trigger.skill_name}")
    
    def find_matching_skills(self, text: str, min_confidence: float = 0.5) -> List[str]:
        """Find all skills that match the given text."""
        matches = []
        for trigger in self.triggers:
            if trigger.matches(text) and trigger.confidence >= min_confidence:
                matches.append(trigger.skill_name)
        
        return list(set(matches))  # Remove duplicates
    
    def should_auto_trigger(self, text: str, skill_name: str) -> bool:
        """Check if a specific skill should auto-trigger for this text."""
        for trigger in self.triggers:
            if trigger.skill_name == skill_name and trigger.matches(text):
                return True
        return False


class EnhancedSkillsManager:
    """
    Enhanced skills manager with auto-triggering and better integration.
    Wraps the existing SkillRegistry with additional features.
    """
    
    def __init__(self, skill_registry: Any):
        """
        Initialize with existing skill registry.
        
        Args:
            skill_registry: The SkillRegistry instance from skills.py
        """
        self.registry = skill_registry
        self.matcher = SkillMatcher()
        self.auto_trigger_enabled = True
        self.notification_enabled = True
        
        # Load skill metadata to build triggers
        self._load_skill_triggers()
    
    def _load_skill_triggers(self):
        """Load trigger patterns from skill metadata."""
        # This would read from skill SKILL.md files to find trigger patterns
        # For now, using defaults from SkillMatcher
        logger.info("Loaded skill trigger patterns")
    
    def analyze_message(self, message: str) -> Dict[str, Any]:
        """
        Analyze a message to determine which skills might be relevant.
        
        Returns:
            {
                'suggested_skills': List[str],
                'auto_trigger': List[str],
                'confidence': Dict[str, float]
            }
        """
        if not self.auto_trigger_enabled:
            return {
                'suggested_skills': [],
                'auto_trigger': [],
                'confidence': {}
            }
        
        matching_skills = self.matcher.find_matching_skills(message)
        
        return {
            'suggested_skills': matching_skills,
            'auto_trigger': matching_skills,  # For now, auto-trigger all matches
            'confidence': {skill: 0.8 for skill in matching_skills}  # Placeholder
        }
    
    def execute_skill(
        self,
        skill_name: str,
        context: str,
        callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Execute a skill with the given context.
        
        Args:
            skill_name: Name of the skill to execute
            context: Context/message to pass to the skill
            callback: Optional callback for notifications
        
        Returns:
            Execution result with status and output
        """
        try:
            # Notify user if enabled
            if self.notification_enabled and callback:
                callback(f"🔧 Triggering skill: {skill_name}")
            
            # Execute via registry
            # This is a placeholder - actual execution depends on SkillRegistry API
            result = {
                'status': 'success',
                'skill': skill_name,
                'output': f"Skill {skill_name} would be executed here"
            }
            
            logger.info(f"Executed skill: {skill_name}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing skill {skill_name}: {e}")
            return {
                'status': 'error',
                'skill': skill_name,
                'error': str(e)
            }
    
    def get_skill_suggestions(self, context: str) -> List[Dict[str, Any]]:
        """
        Get skill suggestions based on context.
        Returns list of suggestions with metadata.
        """
        analysis = self.analyze_message(context)
        
        suggestions = []
        for skill_name in analysis['suggested_skills']:
            # Get skill info from registry if available
            skill_info = {
                'name': skill_name,
                'confidence': analysis['confidence'].get(skill_name, 0.0),
                'auto_trigger': skill_name in analysis['auto_trigger']
            }
            suggestions.append(skill_info)
        
        return suggestions
    
    def format_skill_notification(self, skill_name: str, action: str = "triggered") -> str:
        """Format a skill notification message."""
        emoji_map = {
            'skill-creator': '🛠️',
            'find-skills': '🔍',
            'file-ops': '📁',
            'web-search': '🌐'
        }
        
        emoji = emoji_map.get(skill_name, '⚡')
        return f"{emoji} Skill {action}: **{skill_name}**"
    
    def enable_auto_trigger(self, enabled: bool = True):
        """Enable or disable auto-triggering."""
        self.auto_trigger_enabled = enabled
        logger.info(f"Auto-trigger {'enabled' if enabled else 'disabled'}")
    
    def enable_notifications(self, enabled: bool = True):
        """Enable or disable skill notifications."""
        self.notification_enabled = enabled
        logger.info(f"Skill notifications {'enabled' if enabled else 'disabled'}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get skill system statistics."""
        return {
            'total_triggers': len(self.matcher.triggers),
            'auto_trigger_enabled': self.auto_trigger_enabled,
            'notifications_enabled': self.notification_enabled,
            'available_skills': len(self.registry.gating.list_available_skills()) if hasattr(self.registry, 'gating') else 0
        }


# Integration helper
def enhance_skill_registry(skill_registry: Any) -> EnhancedSkillsManager:
    """
    Wrap an existing skill registry with enhanced features.
    
    Args:
        skill_registry: Existing SkillRegistry instance
    
    Returns:
        EnhancedSkillsManager wrapping the registry
    """
    return EnhancedSkillsManager(skill_registry)
