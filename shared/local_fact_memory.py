"""Local SQLite fact memory for EmploAI.

This is a small local-first structured recall layer. It complements the
human-editable MEMORY.md file without requiring a cloud memory service.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from shared.memory_safety import assert_safe_memory_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_tags(tags: Optional[Iterable[str] | str]) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        raw = tags.split(",")
    else:
        raw = list(tags)
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        tag = str(item or "").strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result[:24]


class LocalFactStore:
    """A tiny local SQLite fact store with trust-weighted keyword search."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL DEFAULT 'general',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    trust REAL NOT NULL DEFAULT 0.7,
                    source TEXT NOT NULL DEFAULT 'memory',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fact_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_id INTEGER NOT NULL,
                    helpful INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(fact_id) REFERENCES facts(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_trust ON facts(trust)")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        try:
            data["tags"] = json.loads(data.pop("tags_json") or "[]")
        except Exception:
            data["tags"] = []
        return data

    def add_fact(
        self,
        content: str,
        *,
        category: str = "general",
        tags: Optional[Iterable[str] | str] = None,
        trust: float = 0.7,
        source: str = "memory",
    ) -> Dict[str, Any]:
        content = str(content or "").strip()
        if not content:
            raise ValueError("Fact content is required")
        assert_safe_memory_text(content, context="local fact")
        category = str(category or "general").strip().lower()[:64] or "general"
        trust = max(0.0, min(1.0, float(trust)))
        tags_json = json.dumps(_normalise_tags(tags), ensure_ascii=False)
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM facts WHERE content = ?", (content,)).fetchone()
            if existing:
                current_trust = float(existing["trust"])
                merged_trust = max(current_trust, trust)
                conn.execute(
                    """
                    UPDATE facts
                    SET category = ?, tags_json = ?, trust = ?, source = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (category, tags_json, merged_trust, source[:64], now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM facts WHERE id = ?", (existing["id"],)).fetchone()
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO facts (content, category, tags_json, trust, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (content, category, tags_json, trust, source[:64], now, now),
                )
                row = conn.execute("SELECT * FROM facts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_dict(row)

    def search(self, query: str, *, limit: int = 8, min_trust: float = 0.2) -> List[Dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        terms = [term.lower() for term in query.split() if len(term.strip()) >= 2]
        if not terms:
            terms = [query.lower()]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE trust >= ? ORDER BY trust DESC, updated_at DESC LIMIT 250",
                (max(0.0, min(1.0, float(min_trust))),),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            fact = self._row_to_dict(row)
            haystack = f"{fact.get('content', '')} {fact.get('category', '')} {' '.join(fact.get('tags', []))}".lower()
            hits = sum(1 for term in terms if term in haystack)
            if hits <= 0:
                continue
            fact["score"] = round(float(fact.get("trust", 0.0)) + hits, 3)
            results.append(fact)
        results.sort(key=lambda item: (item.get("score", 0), item.get("trust", 0)), reverse=True)
        return results[: max(1, int(limit))]

    def list_facts(
        self,
        *,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM facts WHERE trust >= ?"
        params: list[Any] = [max(0.0, min(1.0, float(min_trust)))]
        if category:
            sql += " AND category = ?"
            params.append(str(category).strip().lower())
        sql += " ORDER BY trust DESC, updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            return [self._row_to_dict(row) for row in conn.execute(sql, params).fetchall()]

    def record_feedback(self, fact_id: int, *, helpful: bool) -> Dict[str, Any]:
        delta = 0.08 if helpful else -0.14
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM facts WHERE id = ?", (int(fact_id),)).fetchone()
            if not row:
                raise KeyError(f"Fact not found: {fact_id}")
            next_trust = max(0.0, min(1.0, float(row["trust"]) + delta))
            conn.execute(
                "UPDATE facts SET trust = ?, updated_at = ? WHERE id = ?",
                (next_trust, now, int(fact_id)),
            )
            conn.execute(
                "INSERT INTO fact_feedback (fact_id, helpful, created_at) VALUES (?, ?, ?)",
                (int(fact_id), 1 if helpful else 0, now),
            )
            updated = conn.execute("SELECT * FROM facts WHERE id = ?", (int(fact_id),)).fetchone()
        return self._row_to_dict(updated)

    def remove_fact(self, fact_id: int) -> bool:
        """Delete a fact by id."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM facts WHERE id = ?", (int(fact_id),))
        return cursor.rowcount > 0

    def build_prompt_context(self, *, max_chars: int = 1600, min_trust: float = 0.55) -> str:
        facts = self.list_facts(min_trust=min_trust, limit=24)
        lines: list[str] = []
        for fact in facts:
            tag_text = f" [{', '.join(fact['tags'])}]" if fact.get("tags") else ""
            lines.append(f"- ({fact['category']}, trust {float(fact['trust']):.2f}) {fact['content']}{tag_text}")
        text = "\n".join(lines).strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 22)].rstrip() + "\n... (truncated)"
