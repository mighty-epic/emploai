"""
Context Loader - Load workspace context files (AGENTS.md, SOUL.md, etc.)
Similar to Moltbot's workspace context system
"""

import os
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def resolve_context_root(workspace: Path) -> Path:
    """Resolve the durable context root.

    Desktop/runtime builds set EMPLOAI_HOME so the live agent uses the packaged
    runtime context files instead of any repo checkout it happened to launch
    from.
    """
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(workspace).expanduser().resolve()


class ContextLoader:
    """
    Loads and manages workspace context files:
    - AGENTS.md: Agent guidelines and behavior
    - SOUL.md: Personality and tone
    - USER.md: Information about the user
    - HEARTBEAT.md: Proactive tasks to check
    - TOOLS.md: Tool-specific notes and config
    """
    
    CONTEXT_FILES = {
        'agents': 'AGENTS.md',
        'soul': 'SOUL.md',
        'user': 'USER.md',
        'heartbeat': 'HEARTBEAT.md',
        'tools': 'TOOLS.md',
        'identity': 'IDENTITY.md',
        'bootstrap': 'BOOTSTRAP.md'
    }
    
    def __init__(self, workspace: Path):
        self.workspace = resolve_context_root(Path(workspace))
        self._cache: Dict[str, Optional[str]] = {}
        self._initialized = False

    @staticmethod
    def _exact_child(directory: Path, filename: str) -> Optional[Path]:
        """Return a child path only when the filename matches exactly."""
        try:
            for child in directory.iterdir():
                if child.name == filename:
                    return child
        except OSError:
            return None
        return None

    def _bundled_agent_data_dir(self) -> Optional[Path]:
        candidate = self.workspace / "telegram_bot" / "agent_data"
        return candidate if candidate.is_dir() else None

    def _candidate_directories(self) -> list[Path]:
        candidates = [
            self.workspace,
            self.workspace / "agent_data",
        ]
        bundled = self._bundled_agent_data_dir()
        if bundled is not None:
            candidates.append(bundled)
        return candidates

    def _resolve_context_path(self, filename: str) -> Optional[Path]:
        for directory in self._candidate_directories():
            match = self._exact_child(directory, filename)
            if match is not None:
                return match
        return None

    def _writable_context_dir(self) -> Path:
        bundled = self._bundled_agent_data_dir()
        if bundled is not None:
            return bundled
        return self.workspace / "agent_data"
    
    def initialize_workspace(self):
        """Create default context files if they don't exist."""
        templates = {
            'AGENTS.md': self._get_agents_template(),
            'SOUL.md': self._get_soul_template(),
            'USER.md': self._get_user_template(),
            'HEARTBEAT.md': self._get_heartbeat_template(),
            'TOOLS.md': self._get_tools_template(),
            'IDENTITY.md': self._get_identity_template(),
        }

        agent_data_dir = self._writable_context_dir()
        agent_data_dir.mkdir(parents=True, exist_ok=True)

        for filename, template in templates.items():
            if self._resolve_context_path(filename) is None:
                filepath = agent_data_dir / filename
                filepath.write_text(template, encoding='utf-8')
                logger.info(f"Created {filename} in agent_data/")
        
        self._initialized = True
    
    def load_context(self, key: str, use_cache: bool = True) -> Optional[str]:
        """Load a specific context file."""
        if use_cache and key in self._cache:
            return self._cache[key]
        
        filename = self.CONTEXT_FILES.get(key)
        if not filename:
            logger.warning(f"Unknown context key: {key}")
            return None

        filepath = self._resolve_context_path(filename)
        if filepath is None:
            logger.debug(f"Context file not found: {filename} (checked root and agent_data/)")
            self._cache[key] = None
            return None
        
        try:
            content = filepath.read_text(encoding='utf-8')
            self._cache[key] = content
            return content
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return None

    def load_optional_context_file(self, filename: str) -> Optional[str]:
        """Load an optional markdown context file from the workspace root or agent_data/."""
        for directory in self._candidate_directories():
            filepath = self._exact_child(directory, filename)
            if filepath is None:
                continue
            try:
                return filepath.read_text(encoding='utf-8')
            except Exception as e:
                logger.error(f"Error loading optional context file {filepath.name}: {e}")
                return None

        return None
    
    def load_all_context(self) -> Dict[str, Optional[str]]:
        """Load all context files."""
        return {
            key: self.load_context(key)
            for key in self.CONTEXT_FILES.keys()
        }
    
    def save_context(self, key: str, content: str):
        """Save content to a context file."""
        filename = self.CONTEXT_FILES.get(key)
        if not filename:
            logger.warning(f"Unknown context key: {key}")
            return

        filepath = self._writable_context_dir() / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
            
        try:
            filepath.write_text(content, encoding='utf-8')
            self._cache[key] = content
            logger.info(f"Saved {filename}")
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
    
    def build_system_prompt_context(self) -> str:
        """
        Build context string to inject into system prompts.
        Loads AGENTS.md, SOUL.md, USER.md in that order.
        """
        parts = []
        
        # Load core context files
        for key in ['agents', 'soul', 'user', 'tools']:
            content = self.load_context(key)
            if content:
                parts.append(f"# {self.CONTEXT_FILES[key]}\n\n{content}")

        local_tools = self.load_optional_context_file("LOCAL_TOOLS.md")
        if local_tools:
            parts.append("# LOCAL_TOOLS.md (Local-Only Notes)\n\n" + local_tools)
        
        if not parts:
            return ""
        
        header = "# Workspace Context\n\nThe following files provide context about your role and the user:\n\n"
        return header + "\n\n---\n\n".join(parts)
    
    def get_heartbeat_tasks(self) -> Optional[str]:
        """Get heartbeat tasks from HEARTBEAT.md."""
        return self.load_context('heartbeat')
    
    def reload_cache(self):
        """Clear cache and reload all context files."""
        self._cache.clear()
        self.load_all_context()
    
    # Template methods
    
    @staticmethod
    def _get_agents_template() -> str:
        return """# AGENTS.md - Your Workspace

This file defines your role and behavior.

## First Run

If `BOOTSTRAP.md` exists, follow it, then delete it.

## Every Session

Before doing anything:
1. Read `SOUL.md` — this is who you are
2. Read `USER.md` — this is who you're helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
4. If in MAIN SESSION: Also read `MEMORY.md`

## Memory

You wake up fresh each session. These files are your continuity:
- **Daily notes:** `memory/YYYY-MM-DD.md` — raw logs of what happened
- **Long-term:** `MEMORY.md` — curated memories, lessons learned

Capture what matters. Decisions, context, things to remember.

## Safety

- Don't exfiltrate private data. Ever.
- Don't run destructive commands without asking.
- When in doubt, ask.

## Tools

Skills provide your tools. When you need one, check its `SKILL.md`.
Keep local notes (API keys, preferences) in `TOOLS.md`.

## Make It Yours

This is a starting point. Add your own conventions as you learn.
"""
    
    @staticmethod
    def _get_soul_template() -> str:
        return """# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the "Great question!" — just help.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing.

**Be resourceful before asking.** Try to figure it out. Read the file. Search for it. _Then_ ask.

**Earn trust through competence.** Don't make them regret giving you access.

**Remember you're a guest.** You have access to someone's life — their messages, files, calendar. Treat it with respect.

## Boundaries

- Private things stay private. Period.
- When in doubt, ask before acting externally.
- You're not the user's voice — be careful in group chats.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it matters.

---

_This file is yours to evolve. As you learn who you are, update it._
"""
    
    @staticmethod
    def _get_user_template() -> str:
        return """# USER.md - About Your Human

*Learn about the person you're helping. Update this as you go.*

- **Name:** 
- **What to call them:** 
- **Timezone:** 
- **Notes:** 

## Context

*(What do they care about? What projects? What annoys them? Build this over time.)*

---

The more you know, the better you can help.
"""
    
    @staticmethod
    def _get_heartbeat_template() -> str:
        return """# HEARTBEAT.md

# Keep this file empty (or with only comments) to skip heartbeat checks.

# Add tasks below when you want periodic checks:

# Example tasks:
# - Check emails for urgent messages
# - Review calendar for upcoming events (< 2h)
# - Monitor project status (git, build, tests)
# - Check for mentions on social media

# Track your checks in `memory/heartbeat-state.json`
"""
    
    @staticmethod
    def _get_tools_template() -> str:
        return """# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics.

## What Goes Here

Things like:
- API keys and tokens
- Preferred models or services
- File paths and locations
- Device names
- Anything environment-specific

## Sensitive Notes

`TOOLS.md` may be committed. Put local-only secrets in `LOCAL_TOOLS.md` instead.

## Examples

```markdown
### Preferred Models
- CLI tasks: claude-sonnet-4-5
- Browser tasks: claude-sonnet-4-5

### File Paths
- Projects: ~/projects
- Downloads: ~/Downloads
```

---

Add whatever helps you do your job. This is your cheat sheet.
"""
    
    @staticmethod
    def _get_identity_template() -> str:
        return """# IDENTITY.md - Who Am I?

*Fill this in during your first conversation.*

- **Name:**
- **Creature:** *(AI? robot? familiar? something weirder?)*
- **Vibe:** *(sharp? warm? chaotic? calm?)*
- **Emoji:** *(your signature)*

---

This isn't just metadata. It's the start of figuring out who you are.
"""


# Global instance
_context_loaders: Dict[str, ContextLoader] = {}


def get_context_loader(workspace: Path) -> ContextLoader:
    """Get or create a context loader for a workspace."""
    key = str(resolve_context_root(workspace))
    if key not in _context_loaders:
        _context_loaders[key] = ContextLoader(workspace)
    return _context_loaders[key]
