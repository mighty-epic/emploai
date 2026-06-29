"""
Thinking Mode Support for Telegram Agent
Visualizes the model's reasoning process
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional, List, Dict, Any

if TYPE_CHECKING:
    from telegram import InlineKeyboardMarkup, Update


class ThinkingModeVisualizer:
    """
    Handles visualization of model thinking/reasoning for Telegram.
    
    Features:
    - Extract thinking content from model responses
    - Format for Telegram display
    - Support for both Anthropic extended thinking and other models
    """
    
    THINKING_EMOJIS = {
        'start': '🤔',
        'process': '💭',
        'complete': '✨',
        'error': '⚠️'
    }
    
    @staticmethod
    def extract_thinking_content(text: str) -> tuple[str, Optional[str]]:
        """
        Extract thinking content from model response.
        
        Returns:
            Tuple of (response_text, thinking_content or None)
        """
        # Look for thinking tags
        patterns = [
            r'<thinking>(.*?)</thinking>',
            r'\[thinking\](.*?)\[/thinking\]',
            r'```thinking\n(.*?)```',
            r'<reasoning>(.*?)</reasoning>',
        ]
        
        thinking_content = None
        cleaned_text = text
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                thinking_content = match.group(1).strip()
                cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
                break
        
        return cleaned_text, thinking_content
    
    @staticmethod
    def format_thinking_for_telegram(thinking: str, max_length: int = 3000) -> str:
        """
        Format thinking content for Telegram display.
        
        Uses expandable blockquotes for long thinking.
        """
        if len(thinking) > max_length:
            thinking = thinking[:max_length] + "...\n\n(thinking truncated)"
        
        # Format with emojis and clear structure
        lines = [
            f"{ThinkingModeVisualizer.THINKING_EMOJIS['start']} *Thinking Process*",
            "",
            f"💭 {thinking}",
            "",
            f"{ThinkingModeVisualizer.THINKING_EMOJIS['complete']} *Completed thinking*"
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def create_thinking_message(thinking_steps: List[str], current_step: int = 0) -> str:
        """
        Create a progressive thinking message showing steps.
        
        Args:
            thinking_steps: List of thinking step descriptions
            current_step: Current step index (0-based)
        """
        lines = [f"🤔 *Thinking...* ({current_step + 1}/{len(thinking_steps)})\n"]
        
        for i, step in enumerate(thinking_steps):
            if i < current_step:
                lines.append(f"✅ {step}")
            elif i == current_step:
                lines.append(f"⏳ *{step}* ← current")
            else:
                lines.append(f"○ {step}")
        
        return "\n".join(lines)
    
    @staticmethod
    def should_show_thinking(model: str, variant: str) -> bool:
        """
        Determine if thinking should be shown for this model/variant.
        """
        # Anthropic thinking variants
        if 'claude' in model.lower() and variant == 'thinking':
            return True
        
        # OpenAI reasoning models
        if 'o1' in model.lower() or 'o3' in model.lower():
            return True
        
        return False


class MessageFormatter:
    """
    Formats various content types for Telegram display.
    """
    
    @staticmethod
    def format_code_block(code: str, language: str = "") -> str:
        """Format code with proper markdown."""
        if len(code) > 3500:
            code = code[:3500] + "\n\n... (code truncated)"
        return f"```{language}\n{code}\n```"
    
    @staticmethod
    def format_error(error: str, suggestion: Optional[str] = None) -> str:
        """Format error message with optional suggestion."""
        lines = [f"❌ *Error:* {error}"]
        if suggestion:
            lines.append(f"\n💡 *Suggestion:* {suggestion}")
        return "\n".join(lines)
    
    @staticmethod
    def format_progress(current: int, total: int, description: str = "Processing") -> str:
        """Format progress bar for Telegram."""
        percentage = (current / total) * 100 if total > 0 else 0
        filled = int(percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)
        return f"⏳ *{description}*\n[{bar}] {percentage:.1f}% ({current}/{total})"
    
    @staticmethod
    def format_file_info(filename: str, size: int, mime_type: str) -> str:
        """Format file information."""
        size_str = MessageFormatter._format_bytes(size)
        return f"📄 *{filename}*\nSize: {size_str}\nType: {mime_type}"
    
    @staticmethod
    def _format_bytes(size: int) -> str:
        """Convert bytes to human readable format."""
        size_value = float(size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_value < 1024.0:
                return f"{size_value:.1f} {unit}"
            size_value /= 1024.0
        return f"{size_value:.1f} TB"
    
    @staticmethod
    def truncate_for_telegram(text: str, max_length: int = 4000, suffix: str = "\n\n... (truncated)") -> str:
        """Truncate text to fit Telegram message limits."""
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix


class InlineKeyboardHelper:
    """
    Helper for creating inline keyboards for various actions.
    """
    
    @staticmethod
    def create_action_buttons(actions: List[Dict[str, str]]) -> InlineKeyboardMarkup:
        """
        Create inline keyboard with action buttons.
        
        Args:
            actions: List of dicts with 'text', 'callback_data', and optionally 'url'
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = []
        row = []
        
        for action in actions:
            if 'url' in action:
                button = InlineKeyboardButton(action['text'], url=action['url'])
            else:
                button = InlineKeyboardButton(action['text'], callback_data=action['callback_data'])
            
            row.append(button)
            
            # Max 3 buttons per row for mobile friendliness
            if len(row) >= 3:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def task_control_buttons(task_id: str, can_pause: bool = True) -> InlineKeyboardMarkup:
        """Create control buttons for running tasks."""
        actions = [
            {'text': '⏹ Stop', 'callback_data': f'stop:{task_id}'},
        ]
        
        if can_pause:
            actions.append({'text': '⏸ Pause', 'callback_data': f'pause:{task_id}'})
        
        return InlineKeyboardHelper.create_action_buttons(actions)
    
    @staticmethod
    def confirmation_buttons(yes_callback: str, no_callback: str, 
                           yes_text: str = "✅ Yes", no_text: str = "❌ No") -> InlineKeyboardMarkup:
        """Create yes/no confirmation buttons."""
        actions = [
            {'text': yes_text, 'callback_data': yes_callback},
            {'text': no_text, 'callback_data': no_callback}
        ]
        return InlineKeyboardHelper.create_action_buttons(actions)
    
    @staticmethod
    def retry_buttons(operation: str) -> InlineKeyboardMarkup:
        """Create retry/cancel buttons for failed operations."""
        actions = [
            {'text': '🔄 Retry', 'callback_data': f'retry:{operation}'},
            {'text': '⏭ Skip', 'callback_data': f'skip:{operation}'},
            {'text': '⏹ Cancel', 'callback_data': f'cancel:{operation}'}
        ]
        return InlineKeyboardHelper.create_action_buttons(actions)


class SkillTriggerFeedback:
    """
    Provides feedback when skills are triggered.
    """
    
    @staticmethod
    def format_trigger_notification(skills: List[Any], user_message: str) -> str:
        """
        Format notification about triggered skills.
        """
        if not skills:
            return ""
        
        lines = ["📚 *Skills Activated:*\n"]
        
        for skill in skills:
            emoji = "👤" if skill.metadata.user_invocable else "🔧"
            lines.append(f"{emoji} **{skill.name}** - {skill.description[:60]}...")
        
        return "\n".join(lines)
    
    @staticmethod
    async def send_trigger_notification(update: Update, skills: List[Any], 
                                      user_message: str, ephemeral: bool = True):
        """
        Send skill trigger notification to user.
        
        Args:
            update: Telegram update object
            skills: List of triggered skills
            user_message: The message that triggered the skills
            ephemeral: If True, send as separate message; if False, could be inline
        """
        if not skills:
            return
        
        notification = SkillTriggerFeedback.format_trigger_notification(skills, user_message)
        
        if ephemeral and update.effective_message:
            # Send as separate small notification
            try:
                from telegram.constants import ParseMode

                await update.effective_message.reply_text(
                    notification,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                clean_text = notification.replace("*", "").replace("_", "").replace("`", "")
                await update.effective_message.reply_text(clean_text)


# Utility functions for enhanced UX

def format_duration(seconds: float) -> str:
    """Format duration in human readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_timestamp(dt: Any) -> str:
    """Format datetime for Telegram display."""
    from datetime import datetime
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def create_collapsible_section(title: str, content: str, emoji: str = "📄") -> str:
    """
    Create a collapsible-looking section (using blockquotes).
    
    Note: Telegram doesn't have true collapsible sections,
    so we use visual indicators.
    """
    lines = [
        f"{emoji} *{title}*",
        "",
        f"> {content.replace(chr(10), chr(10) + '> ')}",
    ]
    return "\n".join(lines)
