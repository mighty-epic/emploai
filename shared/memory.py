"""
Memory System - Persistent memory with semantic search
Similar to Moltbot's MEMORY.md + daily logs architecture
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


def resolve_memory_root(workspace: Path) -> Path:
    """Resolve the durable memory store root.

    Desktop/runtime builds set EMPLOAI_HOME to a packaged runtime home. When
    present, memory should live there instead of following an arbitrary file
    workspace or repo checkout.
    """
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(workspace).expanduser().resolve()


@dataclass
class MemoryEntry:
    """Single memory entry with metadata."""
    content: str
    timestamp: datetime
    source: str  # "user", "agent", "system"
    importance: int = 1  # 1-5 scale
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class MemoryManager:
    """
    Manages persistent memory similar to Moltbot:
    - MEMORY.md: Curated long-term memory
    - memory/YYYY-MM-DD.md: Daily conversation logs
    - Semantic search capability
    """
    
    def __init__(self, workspace: Path):
        self.workspace = resolve_memory_root(Path(workspace))
        self.memory_dir = self.workspace / "memory"
        self.memory_file = self.workspace / "MEMORY.md"
        
        # Create directories if needed
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize MEMORY.md if doesn't exist
        if not self.memory_file.exists():
            self._init_memory_file()
    
    def _init_memory_file(self):
        """Create initial MEMORY.md structure."""
        template = """# MEMORY.md - Long-Term Memory

## User Preferences

*(Add user preferences here)*

## Key Events

*(Important events and decisions)*

## Lessons Learned

*(Things to remember for future interactions)*

## Context

*(General context about the user, projects, etc.)*
"""
        self.memory_file.write_text(template, encoding='utf-8')
        logger.info(f"Initialized MEMORY.md at {self.memory_file}")
    
    def get_daily_log_path(self, date: Optional[datetime] = None) -> Path:
        """Get path to daily log file."""
        if date is None:
            date = datetime.now()
        filename = f"{date.strftime('%Y-%m-%d')}.md"
        return self.memory_dir / filename
    
    def append_to_daily_log(self, content: str, source: str = "user", session_id: Optional[str] = None):
        """Append entry to today's daily log."""
        log_path = self.get_daily_log_path()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Create file with header if it doesn't exist
        if not log_path.exists():
            header = f"# {datetime.now().strftime('%Y-%m-%d')} - Daily Log\n\n"
            log_path.write_text(header, encoding='utf-8')
        
        # Append entry
        sid_tag = f" [SID: {session_id}]" if session_id else ""
        entry = f"## [{timestamp}]{sid_tag} {source.title()}\n{content}\n\n"
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(entry)
        
        logger.debug(f"Appended to daily log: {log_path}")
    
    def read_memory(self) -> str:
        """Read the curated long-term memory."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding='utf-8')
        return ""
    
    def update_memory(self, content: str):
        """Update the long-term memory file."""
        self.memory_file.write_text(content, encoding='utf-8')
        logger.info("Updated MEMORY.md")

    def append_to_memory(self, section: str, content: str) -> bool:
        """
        Append content to a specific section in MEMORY.md.
        Creates section if it doesn't exist.
        """
        content = content.strip()
        if not content:
            return False

        current = self.read_memory()
        
        # Find section
        section_header = f"## {section}"
        if section_header in current:
            # Append to existing section
            parts = current.split(section_header)
            before = parts[0] + section_header
            after_parts = parts[1].split("\n## ", 1)
            section_content = after_parts[0]
            rest = "\n## " + after_parts[1] if len(after_parts) > 1 else ""

            if content in section_content:
                logger.debug("Skipped duplicate memory entry for section %s", section)
                return False
            
            new_content = before + section_content + f"\n{content}\n" + rest
        else:
            # Add new section at end
            new_content = current.rstrip() + f"\n\n## {section}\n\n{content}\n"
        
        self.update_memory(new_content)
        return True

    @staticmethod
    def _trim_context_block(text: str, max_chars: int) -> str:
        text = text.strip()
        if max_chars <= 0 or len(text) <= max_chars:
            return text

        marker = "\n... (truncated) ...\n"
        head = max(0, (max_chars - len(marker)) // 2)
        tail = max(0, max_chars - len(marker) - head)
        return text[:head].rstrip() + marker + text[-tail:].lstrip()

    def get_long_term_context(self, max_chars: int = 4000) -> str:
        """Get the curated long-term memory block for prompt injection."""
        memory_content = self.read_memory()
        if not memory_content:
            return ""

        filtered_lines = []
        for line in memory_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("*(") and stripped.endswith(")*"):
                continue
            filtered_lines.append(line)

        filtered = "\n".join(filtered_lines).strip()
        if not filtered or filtered == "# MEMORY.md - Long-Term Memory":
            return ""

        return self._trim_context_block(filtered, max_chars)
    
    def search_memory(self, query: str, max_results: int = 5, session_id: Optional[str] = None) -> List[Dict]:
        """
        Simple keyword-based search across MEMORY.md and recent daily logs.
        """
        results = []
        query_lower = query.lower()
        
        # Search MEMORY.md (Long-term memory is currently shared/not isolated by SID tag)
        memory_content = self.read_memory()
        if memory_content:
            lines = memory_content.split('\n')
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Get context (3 lines before and after)
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    context = '\n'.join(lines[start:end])
                    
                    results.append({
                        'source': 'MEMORY.md',
                        'line': i + 1,
                        'content': context,
                        'score': 1.0
                    })
        
        # Search recent daily logs (last 7 days)
        for days_back in range(7):
            from datetime import timedelta
            date = datetime.now() - timedelta(days=days_back)
            log_path = self.get_daily_log_path(date)
            
            if log_path.exists():
                log_content = log_path.read_text(encoding='utf-8')
                
                # Split content into blocks by entry header
                blocks = log_content.split("## [")
                for block_text in blocks:
                    if not block_text.strip():
                        continue
                    
                    full_block = "## [" + block_text
                    
                    # session_id check
                    if session_id:
                        tag = f"[SID: {session_id}]"
                        if tag not in full_block.split("\n")[0]:
                            continue

                    if query_lower in full_block.lower():
                        results.append({
                            'source': str(log_path.name),
                            'content': full_block,
                            'score': 0.8 - (days_back * 0.1)
                        })
        
        # Sort by score and limit
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:max_results]
    
    def get_recent_context(self, days: int = 2, max_chars: int = 2000, session_id: Optional[str] = None) -> str:
        """
        Get recent conversation context from daily logs.
        If session_id is provided, only include entries from that session.
        """
        context_parts = []
        total_chars = 0
        
        from datetime import timedelta
        for days_back in range(days):
            date = datetime.now() - timedelta(days=days_back)
            log_path = self.get_daily_log_path(date)
            
            if log_path.exists():
                content = log_path.read_text(encoding='utf-8')
                
                # Filter by session_id if requested
                if session_id:
                    # Entries start with "## [timestamp] [SID: id] ..."
                    # If an entry doesn't have the SID tag, or has a different one, skip it
                    filtered_blocks = []
                    blocks = content.split("## [")
                    for block in blocks:
                        if not block.strip():
                            continue
                        
                        # Re-add the header delimiter
                        full_block = "## [" + block
                        
                        # Search for the session tag
                        tag = f"[SID: {session_id}]"
                        if tag in full_block.split("\n")[0]:
                           filtered_blocks.append(full_block)
                    
                    content = "\n\n".join(filtered_blocks)
                
                if not content.strip():
                    continue

                if total_chars + len(content) > max_chars:
                    # Truncate to fit
                    remaining = max_chars - total_chars
                    content = content[:remaining] + "\n... (truncated)"
                
                context_parts.append(f"## {log_path.stem}\n{content}")
                total_chars += len(content)
                
                if total_chars >= max_chars:
                    break
        
        return "\n\n".join(context_parts)

    def build_prompt_context(
        self,
        *,
        session_id: Optional[str] = None,
        long_term_chars: int = 4000,
        recent_days: int = 7,
        recent_chars: int = 3000,
    ) -> str:
        """Build combined long-term + recent memory context for prompt injection."""
        parts = []

        long_term = self.get_long_term_context(max_chars=long_term_chars)
        if long_term:
            parts.append(f"## Long-Term Memory\n\n{long_term}")

        recent = self.get_recent_context(
            days=recent_days,
            max_chars=recent_chars,
            session_id=session_id,
        )
        if recent:
            parts.append(f"## Recent Context from Memory\n\n{recent}")

        return "\n\n".join(parts)
    
    def export_memory_summary(self) -> Dict:
        """Export memory statistics and summary."""
        daily_logs = list(self.memory_dir.glob("*.md"))
        
        return {
            'memory_file_exists': self.memory_file.exists(),
            'memory_file_size': self.memory_file.stat().st_size if self.memory_file.exists() else 0,
            'daily_log_count': len(daily_logs),
            'oldest_log': min(daily_logs).stem if daily_logs else None,
            'newest_log': max(daily_logs).stem if daily_logs else None,
            'workspace': str(self.workspace)
        }


# Global instance (initialized per workspace)
_memory_managers: Dict[str, MemoryManager] = {}


def get_memory_manager(workspace: Path) -> MemoryManager:
    """Get or create a memory manager for a workspace."""
    key = str(resolve_memory_root(Path(workspace)))
    if key not in _memory_managers:
        _memory_managers[key] = MemoryManager(workspace)
    return _memory_managers[key]
