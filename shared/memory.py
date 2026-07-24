"""
Memory System - Persistent memory with semantic search
Similar to Moltbot's MEMORY.md + daily logs architecture
"""

import json
import os
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

from shared.local_fact_memory import LocalFactStore
from shared.memory_safety import (
    MemorySafetyError,
    assert_safe_memory_text,
    atomic_write_text,
    backup_file,
    strip_placeholder_lines,
)

logger = logging.getLogger(__name__)


_DEFAULT_MEMORY_TEMPLATE = """# MEMORY.md - Long-Term Memory

## User Preferences

*(Add user preferences here)*

## Key Events

*(Important events and decisions)*

## Lessons Learned

*(Things to remember for future interactions)*

## Context

*(General context about the user, projects, etc.)*
"""


def _scope_token(prefix: str, value: str) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def resolve_memory_root(
    workspace: Path,
    *,
    company_id: Optional[str] = None,
    identity_id: Optional[str] = None,
) -> Path:
    """Resolve the durable memory store root.

    Desktop/runtime builds set EMPLOAI_HOME to a packaged runtime home. When
    present, memory should live there instead of following an arbitrary file
    workspace or repo checkout. Company sessions are additionally isolated by
    immutable Company and identity IDs so one employee cannot recall another
    Company's or another employee's private durable memory.
    """
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = Path(workspace).expanduser().resolve()
    clean_company_id = str(company_id or "").strip()
    if not clean_company_id:
        return root
    clean_identity_id = str(identity_id or "").strip() or "unassigned"
    return (
        root
        / "company_agent_memory"
        / _scope_token("company", clean_company_id)
        / "identities"
        / _scope_token("identity", clean_identity_id)
    )


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
    
    def __init__(
        self,
        workspace: Path,
        *,
        company_id: Optional[str] = None,
        identity_id: Optional[str] = None,
    ):
        self.company_id = str(company_id or "").strip() or None
        self.identity_id = str(identity_id or "").strip() or None
        self.workspace = resolve_memory_root(
            Path(workspace),
            company_id=self.company_id,
            identity_id=self.identity_id,
        )
        self.memory_dir = self.workspace / "memory"
        self.memory_file = self.workspace / "MEMORY.md"
        self.backup_dir = self.memory_dir / "backups"
        self.fact_store = LocalFactStore(self.memory_dir / "facts.sqlite")
        
        # Create directories if needed
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize MEMORY.md if doesn't exist
        if not self.memory_file.exists():
            self._init_memory_file()
    
    def _init_memory_file(self):
        """Create initial MEMORY.md structure."""
        atomic_write_text(self.memory_file, _DEFAULT_MEMORY_TEMPLATE)
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
        assert_safe_memory_text(content, context="MEMORY.md")
        backup_file(self.memory_file, self.backup_dir, label="memory")
        atomic_write_text(self.memory_file, content)
        logger.info("Updated MEMORY.md")

    def apply_operations(self, operations: List[Dict[str, Any]], *, max_chars: int = 120_000) -> Dict[str, Any]:
        """Apply add/replace/remove operations to MEMORY.md as one safe write.

        Supported operation shapes:
        - {"action": "add", "section": "Context", "content": "- Durable fact"}
        - {"action": "replace", "old_text": "...", "new_text": "..."}
        - {"action": "remove", "content": "..."}
        """
        if not operations:
            return {"changed": False, "operations": [], "message": "No memory operations supplied"}

        current = self.read_memory()
        next_content = current
        results: list[dict[str, Any]] = []

        for index, raw in enumerate(operations):
            if not isinstance(raw, dict):
                raise ValueError(f"Memory operation {index + 1} must be an object")
            action = str(raw.get("action") or "").strip().lower()
            if action == "add":
                section = str(raw.get("section") or "Context").strip() or "Context"
                content = str(raw.get("content") or "").strip()
                if not content:
                    raise ValueError(f"Memory operation {index + 1} add content is required")
                assert_safe_memory_text(content, context="memory add operation")
                updated, added = self._append_to_memory_content(next_content, section, content)
                next_content = updated
                results.append({"action": "add", "section": section, "changed": added})
            elif action == "replace":
                old_text = str(raw.get("old_text") or "")
                new_text = str(raw.get("new_text") or "")
                if not old_text:
                    raise ValueError(f"Memory operation {index + 1} old_text is required")
                assert_safe_memory_text(new_text, context="memory replace operation")
                if old_text not in next_content:
                    raise ValueError(f"Memory operation {index + 1} could not find old_text")
                next_content = next_content.replace(old_text, new_text, 1)
                results.append({"action": "replace", "changed": True})
            elif action == "remove":
                content = str(raw.get("content") or "")
                if not content:
                    raise ValueError(f"Memory operation {index + 1} remove content is required")
                if content not in next_content:
                    results.append({"action": "remove", "changed": False})
                    continue
                next_content = next_content.replace(content, "", 1)
                results.append({"action": "remove", "changed": True})
            else:
                raise ValueError(f"Unsupported memory operation action: {action or '<missing>'}")

        if len(next_content) > max_chars:
            raise ValueError(f"MEMORY.md would exceed the local memory budget of {max_chars} characters")

        changed = next_content != current
        if changed:
            self.update_memory(next_content)

        return {
            "changed": changed,
            "operations": results,
            "memory_file": str(self.memory_file),
        }

    def append_to_memory(self, section: str, content: str) -> bool:
        """
        Append content to a specific section in MEMORY.md.
        Creates section if it doesn't exist.
        """
        content = content.strip()
        if not content:
            return False

        current = self.read_memory()
        new_content, changed = self._append_to_memory_content(current, section, content)
        if not changed:
            return False

        self.update_memory(new_content)
        try:
            self.fact_store.add_fact(content.lstrip("- ").strip(), category=section, source="memory_md")
        except (MemorySafetyError, ValueError):
            raise
        except Exception:
            logger.debug("Failed to mirror MEMORY.md entry into local fact store", exc_info=True)
        return True

    @staticmethod
    def _append_to_memory_content(current: str, section: str, content: str) -> tuple[str, bool]:
        """Return updated MEMORY.md content for a section append."""
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
                return current, False
            
            new_content = before + section_content + f"\n{content}\n" + rest
        else:
            # Add new section at end
            new_content = current.rstrip() + f"\n\n## {section}\n\n{content}\n"

        return new_content, True

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

        filtered_lines = strip_placeholder_lines(memory_content.splitlines())

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

        # Search structured local facts.
        try:
            for fact in self.fact_store.search(query, limit=max_results):
                results.append({
                    'source': 'local-facts.sqlite',
                    'line': fact.get('id'),
                    'content': fact.get('content', ''),
                    'score': float(fact.get('score', 0.0)),
                })
        except Exception:
            logger.debug("Local fact memory search failed", exc_info=True)
        
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
        fact_chars: int = 1600,
    ) -> str:
        """Build combined long-term + recent memory context for prompt injection."""
        parts = []

        long_term = self.get_long_term_context(max_chars=long_term_chars)
        if long_term:
            parts.append(f"## Long-Term Memory\n\n{long_term}")

        try:
            facts = self.fact_store.build_prompt_context(max_chars=fact_chars)
        except Exception:
            logger.debug("Local fact memory prompt context failed", exc_info=True)
            facts = ""
        if facts:
            parts.append(f"## Local Fact Memory\n\n{facts}")

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
            'workspace': str(self.workspace),
            'fact_store_exists': self.fact_store.db_path.exists(),
            'fact_count': len(self.fact_store.list_facts(limit=10_000)) if self.fact_store.db_path.exists() else 0,
        }


# Global instance (initialized per workspace)
_memory_managers: Dict[str, MemoryManager] = {}


def get_memory_manager(
    workspace: Path,
    *,
    company_id: Optional[str] = None,
    identity_id: Optional[str] = None,
) -> MemoryManager:
    """Get or create a memory manager for a workspace."""
    key = str(
        resolve_memory_root(
            Path(workspace),
            company_id=company_id,
            identity_id=identity_id,
        )
    )
    if key not in _memory_managers:
        _memory_managers[key] = MemoryManager(
            workspace,
            company_id=company_id,
            identity_id=identity_id,
        )
    return _memory_managers[key]


def migrate_legacy_memory_to_company(
    workspace: Path,
    *,
    company_id: str,
    identity_id: str,
) -> Dict[str, Any]:
    """Copy the one pre-Company memory store to its confirmed manager once.

    The operation is intentionally one-way and idempotent. It never copies
    memory to a worker or to a second Company, and it leaves the legacy source
    intact until the user has completed the broader Company migration.
    """

    clean_company_id = str(company_id or "").strip()
    clean_identity_id = str(identity_id or "").strip()
    if not clean_company_id or not clean_identity_id:
        raise ValueError("Company and identity IDs are required for memory migration.")

    legacy_root = resolve_memory_root(Path(workspace))
    marker_path = legacy_root / "memory" / "company-memory-migration.json"
    if marker_path.exists():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = {}
        return {
            "migrated": False,
            "reason": "already_migrated",
            "company_id": str(marker.get("company_id") or ""),
            "identity_id": str(marker.get("identity_id") or ""),
        }

    target = get_memory_manager(
        workspace,
        company_id=clean_company_id,
        identity_id=clean_identity_id,
    )
    copied: List[str] = []
    legacy_memory_file = legacy_root / "MEMORY.md"
    if legacy_memory_file.exists():
        try:
            source_text = legacy_memory_file.read_text(encoding="utf-8")
            target_text = target.read_memory()
        except OSError:
            source_text = ""
            target_text = ""
        if source_text.strip() and (
            not target_text.strip()
            or target_text.strip() == _DEFAULT_MEMORY_TEMPLATE.strip()
        ):
            target.update_memory(source_text)
            copied.append("MEMORY.md")

    legacy_memory_dir = legacy_root / "memory"
    if legacy_memory_dir.is_dir():
        for log_path in sorted(legacy_memory_dir.glob("*.md")):
            destination = target.memory_dir / log_path.name
            if destination.exists():
                continue
            try:
                atomic_write_text(
                    destination,
                    log_path.read_text(encoding="utf-8"),
                )
            except OSError:
                continue
            copied.append(f"memory/{log_path.name}")

    legacy_facts = LocalFactStore(legacy_memory_dir / "facts.sqlite")
    for fact in legacy_facts.list_facts(limit=10_000):
        target.fact_store.add_fact(
            str(fact.get("content") or ""),
            category=str(fact.get("category") or "general"),
            tags=list(fact.get("tags") or []),
            trust=float(fact.get("trust") or 0.7),
            source=str(fact.get("source") or "legacy_memory"),
        )
    fact_count = len(legacy_facts.list_facts(limit=10_000))
    if fact_count:
        copied.append(f"{fact_count} structured fact(s)")

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        marker_path,
        json.dumps(
            {
                "company_id": clean_company_id,
                "identity_id": clean_identity_id,
                "migrated_at": datetime.now().astimezone().isoformat(),
                "copied": copied,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return {
        "migrated": True,
        "company_id": clean_company_id,
        "identity_id": clean_identity_id,
        "copied": copied,
    }


def delete_company_memory(
    workspace: Path,
    *,
    company_id: str,
) -> Dict[str, Any]:
    """Remove one deleted Company's identity-memory subtree only."""

    clean_company_id = str(company_id or "").strip()
    if not clean_company_id:
        raise ValueError("A company ID is required for memory deletion.")
    base_root = resolve_memory_root(Path(workspace))
    company_root = (
        base_root
        / "company_agent_memory"
        / _scope_token("company", clean_company_id)
    ).resolve()
    allowed_root = (base_root / "company_agent_memory").resolve()
    if allowed_root not in company_root.parents:
        raise ValueError("The Company memory path failed its deletion safety check.")
    existed = company_root.exists()
    if existed:
        shutil.rmtree(company_root)
    prefix = str(company_root)
    for key in list(_memory_managers):
        try:
            cached_path = str(Path(key).resolve())
        except OSError:
            cached_path = str(key)
        if cached_path == prefix or cached_path.startswith(prefix + os.sep):
            _memory_managers.pop(key, None)
    return {
        "company_id": clean_company_id,
        "deleted": existed,
    }
