"""
Security utilities for local control surfaces.

Provides authentication, rate limiting, input validation, and audit logging.
"""

import os
import re
import time
import logging
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from typing import Set, Dict, Optional, List, Any
from dataclasses import dataclass, field


# Security logger
security_logger = logging.getLogger("telegram_agent.security")


@dataclass
class RateLimitEntry:
    """Tracks rate limiting for a user."""
    user_id: int
    command: str
    timestamps: List[float] = field(default_factory=list)
    violations: int = 0


class SecurityManager:
    """
    Manages security features for Telegram-compatible control surfaces.
    
    Features:
    - Environment-based authentication
    - Rate limiting per user/command
    - Input validation and sanitization
    - Path traversal protection
    - Audit logging
    """
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        allowed_user_ids: Optional[Set[int]] = None,
        max_requests_per_minute: int = 30,
        max_requests_per_hour: int = 200,
        allowed_paths: Optional[List[str]] = None
    ):
        """
        Initialize security manager.
        
        Args:
            bot_token: Telegram bot token (from env if not provided)
            allowed_user_ids: Set of allowed Telegram user IDs
            max_requests_per_minute: Rate limit per command per minute
            max_requests_per_hour: Rate limit per command per hour
            allowed_paths: List of allowed base paths for file operations
        """
        # Load from environment if not provided
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN not found in environment. "
                "Please set it in your .env file or environment variables."
            )
        
        # Parse allowed user IDs from environment or parameter
        if allowed_user_ids:
            self.allowed_user_ids = allowed_user_ids
        else:
            user_ids_str = os.getenv("ALLOWED_USER_IDS", "")
            if user_ids_str:
                self.allowed_user_ids = {
                    int(uid.strip()) 
                    for uid in user_ids_str.split(",") 
                    if uid.strip().isdigit()
                }
            else:
                # Fallback to single user ID for backwards compatibility
                single_id = os.getenv("ALLOWED_USER_ID")
                if single_id and single_id.isdigit():
                    self.allowed_user_ids = {int(single_id)}
                else:
                    self.allowed_user_ids = set()
        
        if not self.allowed_user_ids:
            security_logger.warning(
                "No allowed user IDs configured. Bot will reject all users. "
                "Set ALLOWED_USER_IDS in environment."
            )
        
        # Rate limiting config
        self.max_requests_per_minute = max_requests_per_minute
        self.max_requests_per_hour = max_requests_per_hour
        
        # Rate limit storage: {(user_id, command): RateLimitEntry}
        self._rate_limits: Dict[tuple, RateLimitEntry] = {}
        self._last_cleanup = time.time()
        
        # Allowed paths for file operations
        default_workspace = Path(os.getenv("DEFAULT_WORKSPACE", Path.cwd()))
        self.allowed_paths = allowed_paths or [str(default_workspace.resolve())]
        
        # Security event log
        self._security_events: List[Dict[str, Any]] = []
        
        security_logger.info(
            f"SecurityManager initialized with {len(self.allowed_user_ids)} allowed users, "
            f"rate limits: {max_requests_per_minute}/min, {max_requests_per_hour}/hour"
        )
    
    def is_user_authorized(self, user_id: int) -> bool:
        """
        Check if a user is authorized to use the bot.
        
        Args:
            user_id: Telegram user ID to check
            
        Returns:
            True if authorized, False otherwise
        """
        is_allowed = user_id in self.allowed_user_ids
        
        if not is_allowed:
            self._log_security_event(
                event_type="unauthorized_access",
                user_id=user_id,
                details="User attempted to access bot without authorization",
                severity="warning"
            )
        
        return is_allowed
    
    def check_rate_limit(self, user_id: int, command: str) -> tuple[bool, Optional[str]]:
        """
        Check if a user has exceeded rate limits for a command.
        
        Args:
            user_id: Telegram user ID
            command: Command being executed
            
        Returns:
            Tuple of (allowed: bool, message: Optional[str])
            If not allowed, message contains the reason.
        """
        key = (user_id, command)
        now = time.time()
        
        # Cleanup old entries periodically (every 5 minutes)
        if now - self._last_cleanup > 300:
            self._cleanup_old_entries()
        
        # Get or create rate limit entry
        if key not in self._rate_limits:
            self._rate_limits[key] = RateLimitEntry(user_id=user_id, command=command)
        
        entry = self._rate_limits[key]
        
        # Remove timestamps older than 1 hour
        cutoff_hour = now - 3600
        entry.timestamps = [ts for ts in entry.timestamps if ts > cutoff_hour]
        
        # Check hourly limit
        if len(entry.timestamps) >= self.max_requests_per_hour:
            self._log_security_event(
                event_type="rate_limit_exceeded",
                user_id=user_id,
                details=f"Hourly rate limit exceeded for command: {command}",
                severity="warning"
            )
            return False, f"Rate limit exceeded: Maximum {self.max_requests_per_hour} requests per hour. Please try again later."
        
        # Check minute limit (last 60 seconds)
        cutoff_minute = now - 60
        recent_requests = sum(1 for ts in entry.timestamps if ts > cutoff_minute)
        
        if recent_requests >= self.max_requests_per_minute:
            self._log_security_event(
                event_type="rate_limit_exceeded",
                user_id=user_id,
                details=f"Per-minute rate limit exceeded for command: {command}",
                severity="warning"
            )
            return False, f"Rate limit exceeded: Maximum {self.max_requests_per_minute} requests per minute. Please slow down."
        
        # Record this request
        entry.timestamps.append(now)
        
        return True, None
    
    def _cleanup_old_entries(self):
        """Remove old rate limit entries to prevent memory growth."""
        now = time.time()
        cutoff = now - 3600  # Keep entries for 1 hour
        
        keys_to_remove = [
            key for key, entry in self._rate_limits.items()
            if not entry.timestamps or all(ts < cutoff for ts in entry.timestamps)
        ]
        
        for key in keys_to_remove:
            del self._rate_limits[key]
        
        self._last_cleanup = now
        security_logger.debug(f"Cleaned up {len(keys_to_remove)} old rate limit entries")
    
    def validate_path(self, path_str: str, user_id: int) -> tuple[bool, Optional[Path], Optional[str]]:
        """
        Validate and sanitize a file path to prevent path traversal attacks.
        
        Args:
            path_str: The path string to validate
            user_id: User ID for logging
            
        Returns:
            Tuple of (valid: bool, resolved_path: Optional[Path], error_message: Optional[str])
        """
        try:
            # Resolve the path
            path = Path(path_str).resolve()
            
            # Check if path is within allowed directories
            path_str_resolved = str(path)
            is_allowed = any(
                path_str_resolved.startswith(allowed_path) 
                for allowed_path in self.allowed_paths
            )
            
            if not is_allowed:
                self._log_security_event(
                    event_type="path_traversal_attempt",
                    user_id=user_id,
                    details=f"Attempted to access path outside allowed directories: {path_str}",
                    severity="warning"
                )
                return False, None, "❌ Access denied: Path is outside allowed workspace directories."
            
            return True, path, None
            
        except Exception as e:
            security_logger.error(f"Path validation error: {e}")
            return False, None, f"❌ Invalid path: {str(e)}"
    
    def sanitize_input(self, text: str, max_length: int = 4000) -> str:
        """
        Sanitize user input to remove potentially dangerous characters.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # Remove control characters except newlines and tabs
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length]
        
        return text
    
    def validate_command_args(self, args: List[str], user_id: int) -> tuple[bool, Optional[str]]:
        """
        Validate command arguments for potentially dangerous content.
        
        Args:
            args: List of command arguments
            user_id: User ID for logging
            
        Returns:
            Tuple of (valid: bool, error_message: Optional[str])
        """
        # Patterns that might indicate command injection
        dangerous_patterns = [
            r'[;&|]\s*\w+',  # Command chaining
            r'`[^`]+`',       # Backtick command substitution
            r'\$\([^)]+\)',   # Command substitution
            r'[<>]',          # Redirection
        ]
        
        for arg in args:
            for pattern in dangerous_patterns:
                if re.search(pattern, arg):
                    self._log_security_event(
                        event_type="suspicious_input",
                        user_id=user_id,
                        details=f"Potentially dangerous pattern detected in input: {arg[:100]}",
                        severity="warning"
                    )
                    return False, "❌ Invalid input: Potentially dangerous characters detected."
        
        return True, None
    
    def _log_security_event(self, event_type: str, user_id: int, details: str, severity: str = "info"):
        """
        Log a security event for audit purposes.
        
        Args:
            event_type: Type of security event
            user_id: User ID associated with the event
            details: Event details
            severity: Event severity (info, warning, error)
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "details": details,
            "severity": severity
        }
        
        self._security_events.append(event)
        
        # Also log to standard logger
        log_message = f"[SECURITY] {event_type} | User: {user_id} | {details}"
        
        if severity == "error":
            security_logger.error(log_message)
        elif severity == "warning":
            security_logger.warning(log_message)
        else:
            security_logger.info(log_message)
    
    def get_security_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent security events for monitoring.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of security events
        """
        return self._security_events[-limit:]
    
    def get_security_summary(self) -> Dict[str, Any]:
        """
        Get a summary of security status.
        
        Returns:
            Dictionary with security metrics
        """
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        
        recent_events = [
            e for e in self._security_events
            if datetime.fromisoformat(e["timestamp"]) > last_24h
        ]
        
        return {
            "allowed_users_count": len(self.allowed_user_ids),
            "rate_limited_users": len(self._rate_limits),
            "security_events_24h": len(recent_events),
            "warning_events_24h": sum(1 for e in recent_events if e["severity"] == "warning"),
            "error_events_24h": sum(1 for e in recent_events if e["severity"] == "error"),
        }


def rate_limited(security_manager: SecurityManager):
    """
    Decorator to apply rate limiting to a command handler.
    
    Usage:
        @rate_limited(security_manager)
        async def my_command(update, context):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context):
            user = update.effective_user
            if not user:
                return
            
            # Check authorization first
            if not security_manager.is_user_authorized(user.id):
                if update.message:
                    await update.message.reply_text("⛔ Unauthorized access.")
                return
            
            # Get command name from function name
            command_name = func.__name__.replace('_command', '').replace('Command', '')
            
            # Check rate limit
            allowed, message = security_manager.check_rate_limit(user.id, command_name)
            if not allowed:
                if update.message:
                    await update.message.reply_text(message)
                return
            
            # Execute the command
            return await func(update, context)
        
        return wrapper
    return decorator


def authorized_only(security_manager: SecurityManager):
    """
    Decorator to restrict command to authorized users only (no rate limiting).
    
    Usage:
        @authorized_only(security_manager)
        async def my_command(update, context):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context):
            user = update.effective_user
            if not user:
                return
            
            # Check authorization
            if not security_manager.is_user_authorized(user.id):
                if update.message:
                    await update.message.reply_text("⛔ Unauthorized access.")
                security_manager._log_security_event(
                    event_type="unauthorized_access",
                    user_id=user.id,
                    details=f"Unauthorized access attempt to command: {func.__name__}",
                    severity="warning"
                )
                return
            
            # Execute the command
            return await func(update, context)
        
        return wrapper
    return decorator
