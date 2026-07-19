from __future__ import annotations

import json
import heapq
import math
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import shared_state_root, user_state_root
from shared.security_policy import redact_text


CONTEXT_INDEX_DB_FILENAME = "manager_context_index.sqlite3"
CONTEXT_SETTINGS_FILENAME = "manager_context_inspection.json"
MAX_CONTEXT_TOKENS = 8_000
CONTEXT_RADIUS = 5
_INDEX_LOCKS: Dict[int, threading.RLock] = {}
_MODEL_LOCK = threading.Lock()
_EMBEDDING_RUNTIME: Optional[tuple[Any, Any, Any]] = None


def _lock_for(user_id: int) -> threading.RLock:
    return _INDEX_LOCKS.setdefault(int(user_id), threading.RLock())


def context_settings_path(user_id: int) -> Path:
    return (user_state_root(user_id) / CONTEXT_SETTINGS_FILENAME).resolve()


def context_index_path(user_id: int) -> Path:
    return (user_state_root(user_id) / CONTEXT_INDEX_DB_FILENAME).resolve()


def context_inspection_setting(user_id: int) -> Dict[str, Any]:
    path = context_settings_path(user_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return {
        "enabled": bool(payload.get("enabled", False)),
        "enabled_since": float(payload.get("enabled_since") or 0.0) or None,
        "updated_at": float(payload.get("updated_at") or 0.0) or None,
        "computer_id": str(payload.get("computer_id") or "").strip() or None,
        "computer_name": str(payload.get("computer_name") or "").strip() or None,
        "index_path": str(context_index_path(user_id)),
        "semantic_pack_available": _semantic_pack_available(),
        "lexical_fallback": True,
    }


def set_context_inspection_enabled(
    user_id: int,
    enabled: bool,
    *,
    computer_id: Optional[str] = None,
    computer_name: Optional[str] = None,
) -> Dict[str, Any]:
    previous = context_inspection_setting(user_id)
    now = time.time()
    payload = {
        "enabled": bool(enabled),
        "enabled_since": (
            previous.get("enabled_since")
            if bool(enabled) and previous.get("enabled")
            else now if enabled else None
        ),
        "updated_at": now,
        "computer_id": str(computer_id or previous.get("computer_id") or "").strip() or None,
        "computer_name": str(computer_name or previous.get("computer_name") or "").strip() or None,
    }
    path = context_settings_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)
    if enabled:
        _ensure_schema(user_id)
    return context_inspection_setting(user_id)


def index_persisted_session(session: Any) -> int:
    user_id = getattr(session, "account_user_id", None)
    if user_id is None:
        return 0
    setting = context_inspection_setting(int(user_id))
    if not setting["enabled"]:
        return 0
    eligible_since = float(setting.get("enabled_since") or time.time())
    records: list[Dict[str, Any]] = []
    session_id = str(getattr(session, "id", "") or "").strip()
    identity_id = str(getattr(session, "fleet_identity_id", "") or "").strip() or None
    identity_role = str(getattr(session, "fleet_identity_role", "") or "manager").strip().lower()
    identity_label = str(getattr(session, "name", "") or identity_role.title())
    history = list(getattr(session, "chat_history", []) or [])
    for ordinal, message in enumerate(history):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        created_at = str(message.get("timestamp") or "").strip()
        if _timestamp(created_at) < eligible_since:
            continue
        stable_id = str(message.get("stable_message_id") or "").strip()
        if not stable_id:
            continue
        content = _redacted_content(message.get("content"))
        if not content:
            continue
        records.append(
            _record(
                stable_id=stable_id,
                session_id=session_id,
                computer_id=setting.get("computer_id"),
                computer_name=setting.get("computer_name"),
                identity_id=identity_id,
                identity_label=identity_label,
                identity_role=identity_role,
                item_role=role,
                item_kind="message",
                ordinal=ordinal * 2,
                created_at=created_at,
                content=content,
            )
        )
    for ordinal, event in enumerate(list(getattr(session, "event_timeline", []) or [])):
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind") or "").strip().lower()
        if kind not in {"tool", "evidence", "artifact", "runtime"}:
            continue
        created_at = str(event.get("timestamp") or "").strip()
        if _timestamp(created_at) < eligible_since:
            continue
        stable_id = str(event.get("id") or "").strip()
        if not stable_id:
            continue
        content = _redacted_content(f"{event.get('title') or kind}: {event.get('content') or ''}")
        if not content:
            continue
        records.append(
            _record(
                stable_id=stable_id,
                session_id=session_id,
                computer_id=setting.get("computer_id"),
                computer_name=setting.get("computer_name"),
                identity_id=identity_id,
                identity_label=identity_label,
                identity_role=identity_role,
                item_role="tool",
                item_kind=kind,
                ordinal=(len(history) + ordinal) * 2 + 1,
                created_at=created_at,
                content=content,
            )
        )
    return _insert_records(int(user_id), records)


def search_context_index(user_id: int, query: str, *, limit: int = 20) -> Dict[str, Any]:
    setting = context_inspection_setting(user_id)
    if not setting["enabled"]:
        raise PermissionError("Manager context inspection is disabled")
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("query is required")
    _ensure_schema(user_id)
    match_query = _fts_query(clean_query)
    with _connect(user_id) as conn:
        rows = conn.execute(
            """
            SELECT i.*, bm25(context_fts) AS lexical_rank,
                   snippet(context_fts, 0, '[', ']', ' … ', 24) AS snippet
            FROM context_fts
            JOIN indexed_items i ON i.stable_id = context_fts.stable_id
            WHERE context_fts MATCH ?
            ORDER BY lexical_rank ASC
            LIMIT ?
            """,
            (match_query, max(1, min(int(limit or 20), 100))),
        ).fetchall()
    results = [_search_result(row) for row in rows]
    semantic_used = False
    if _semantic_pack_available():
        try:
            semantic_results = _semantic_candidates(user_id, clean_query, limit=limit)
            merged = {str(item["message_id"]): item for item in results}
            for item in semantic_results:
                message_id = str(item["message_id"])
                if message_id in merged:
                    lexical_score = float(merged[message_id].get("score") or 0.0)
                    merged[message_id].update(item)
                    merged[message_id]["score"] = lexical_score + float(item.get("semantic_score") or 0.0)
                else:
                    merged[message_id] = item
            results = sorted(merged.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)
            semantic_used = bool(semantic_results)
        except Exception:
            semantic_used = False
    return {
        "query": clean_query,
        "results": results[: max(1, min(int(limit or 20), 100))],
        "count": min(len(results), max(1, min(int(limit or 20), 100))),
        "semantic_used": semantic_used,
        "lexical_fallback": not semantic_used,
    }


def context_window(
    user_id: int,
    message_id: str,
    *,
    direction: str = "around",
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    setting = context_inspection_setting(user_id)
    if not setting["enabled"]:
        raise PermissionError("Manager context inspection is disabled")
    target_id = str(cursor or message_id or "").strip()
    if not target_id:
        raise ValueError("message_id is required")
    with _connect(user_id) as conn:
        target = conn.execute("SELECT * FROM indexed_items WHERE stable_id = ?", (target_id,)).fetchone()
        if not target:
            raise KeyError("Indexed message was not found")
        rows = conn.execute(
            "SELECT * FROM indexed_items WHERE session_id = ? ORDER BY ordinal ASC, created_at ASC, stable_id ASC",
            (target["session_id"],),
        ).fetchall()
    index = next(i for i, row in enumerate(rows) if row["stable_id"] == target_id)
    if direction == "previous":
        start, end = max(0, index - (CONTEXT_RADIUS * 2 + 1)), index + 1
    elif direction == "next":
        start, end = index, min(len(rows), index + CONTEXT_RADIUS * 2 + 2)
    else:
        start, end = max(0, index - CONTEXT_RADIUS), min(len(rows), index + CONTEXT_RADIUS + 1)
    selected = _cap_context_tokens(rows[start:end])
    return {
        "message_id": str(message_id or target_id),
        "cursor": target_id,
        "items": [_context_item(row) for row in selected],
        "previous_cursor": rows[start - 1]["stable_id"] if start > 0 else None,
        "next_cursor": rows[end]["stable_id"] if end < len(rows) else None,
        "token_cap": MAX_CONTEXT_TOKENS,
        "truncated": len(selected) < end - start,
    }


def vectorize_all_eligible_indexes() -> int:
    total = 0
    for path in shared_state_root().glob(f"user_*/{CONTEXT_INDEX_DB_FILENAME}"):
        match = re.match(r"user_(\d+)$", path.parent.name)
        if match:
            total += vectorize_index(int(match.group(1)))
    return total


def vectorize_index(user_id: int) -> int:
    if not _semantic_pack_available():
        return 0
    with _connect(user_id) as conn:
        rows = conn.execute(
            "SELECT stable_id, content FROM indexed_items WHERE embedding IS NULL ORDER BY indexed_at ASC"
        ).fetchall()
        updated = 0
        for row in rows:
            vector = _embed(str(row["content"] or ""))
            conn.execute("UPDATE indexed_items SET embedding = ? WHERE stable_id = ?", (vector.tobytes(), row["stable_id"]))
            updated += 1
        conn.commit()
    return updated


def _record(**kwargs: Any) -> Dict[str, Any]:
    return kwargs


def _insert_records(user_id: int, records: Iterable[Dict[str, Any]]) -> int:
    records = list(records)
    if not records:
        return 0
    _ensure_schema(user_id)
    inserted = 0
    with _lock_for(user_id), _connect(user_id) as conn:
        for record in records:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO indexed_items(
                    stable_id, session_id, computer_id, computer_name, identity_id, identity_label,
                    identity_role, item_role, item_kind, ordinal, created_at, content, indexed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["stable_id"], record["session_id"], record["computer_id"], record["computer_name"],
                    record["identity_id"], record["identity_label"], record["identity_role"], record["item_role"],
                    record["item_kind"], record["ordinal"], record["created_at"], record["content"], time.time(),
                ),
            )
            if cursor.rowcount:
                conn.execute(
                    "INSERT INTO context_fts(content, stable_id) VALUES(?, ?)",
                    (record["content"], record["stable_id"]),
                )
                inserted += 1
        conn.commit()
    if inserted and _semantic_pack_available():
        try:
            vectorize_index(user_id)
        except Exception:
            pass
    return inserted


def _ensure_schema(user_id: int) -> None:
    path = context_index_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(user_id), _connect(user_id) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS indexed_items(
                stable_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                computer_id TEXT,
                computer_name TEXT,
                identity_id TEXT,
                identity_label TEXT,
                identity_role TEXT NOT NULL,
                item_role TEXT NOT NULL,
                item_kind TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                created_at TEXT,
                content TEXT NOT NULL,
                embedding BLOB,
                indexed_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_context_session_ordinal ON indexed_items(session_id, ordinal);
            CREATE VIRTUAL TABLE IF NOT EXISTS context_fts USING fts5(content, stable_id UNINDEXED);
            """
        )


def _connect(user_id: int) -> sqlite3.Connection:
    conn = sqlite3.connect(context_index_path(user_id), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _redacted_content(value: Any) -> str:
    text = redact_text(str(value or "")).strip()
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1: [REDACTED]", text)
    return text[:20_000]


def _timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)
    return " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:20]) or '""'


def _search_result(row: sqlite3.Row) -> Dict[str, Any]:
    rank = float(row["lexical_rank"] or 0.0)
    return {
        "message_id": row["stable_id"],
        "computer_id": row["computer_id"],
        "computer_name": row["computer_name"],
        "identity_id": row["identity_id"],
        "identity_label": row["identity_label"],
        "session_id": row["session_id"],
        "identity_role": row["identity_role"],
        "item_role": row["item_role"],
        "item_kind": row["item_kind"],
        "snippet": str(row["snippet"] or row["content"] or "")[:1200],
        "score": -rank,
    }


def _context_item(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "message_id": row["stable_id"],
        "computer_id": row["computer_id"],
        "computer_name": row["computer_name"],
        "identity_id": row["identity_id"],
        "identity_label": row["identity_label"],
        "session_id": row["session_id"],
        "identity_role": row["identity_role"],
        "role": row["item_role"],
        "kind": row["item_kind"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def _cap_context_tokens(rows: Iterable[sqlite3.Row]) -> list[sqlite3.Row]:
    selected = []
    tokens = 0
    for row in rows:
        estimate = max(1, math.ceil(len(str(row["content"] or "")) / 4))
        if selected and tokens + estimate > MAX_CONTEXT_TOKENS:
            break
        selected.append(row)
        tokens += estimate
    return selected


def _semantic_pack_available() -> bool:
    try:
        from app_backend.runtime_pack_registry import runtime_pack_status, CONTEXT_INDEX_ENGLISH_PACK_ID

        return bool(runtime_pack_status(CONTEXT_INDEX_ENGLISH_PACK_ID).get("available"))
    except Exception:
        return False


def _embedding_runtime() -> tuple[Any, Any, Any]:
    global _EMBEDDING_RUNTIME
    with _MODEL_LOCK:
        if _EMBEDDING_RUNTIME is None:
            import numpy as np
            from transformers import AutoModel, AutoTokenizer
            from app_backend.runtime_pack_registry import context_index_pack_root

            root = context_index_pack_root()
            tokenizer = AutoTokenizer.from_pretrained(str(root), local_files_only=True)
            model = AutoModel.from_pretrained(str(root), local_files_only=True)
            model.eval()
            _EMBEDDING_RUNTIME = (tokenizer, model, np)
        return _EMBEDDING_RUNTIME


def _embed(text: str) -> Any:
    tokenizer, model, np = _embedding_runtime()
    import torch

    encoded = tokenizer([text], padding=True, truncation=True, max_length=256, return_tensors="pt")
    with torch.no_grad():
        output = model(**encoded).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).expand(output.size()).float()
        vector = (output * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        vector = torch.nn.functional.normalize(vector, p=2, dim=1)[0].cpu().numpy().astype("float32")
    return np.asarray(vector, dtype=np.float32)


def _semantic_candidates(user_id: int, query: str, *, limit: int) -> list[Dict[str, Any]]:
    _, _, np = _embedding_runtime()
    query_vector = _embed(query)
    keep = max(20, min(int(limit or 20) * 4, 400))
    ranked: list[tuple[float, str, sqlite3.Row]] = []
    with _connect(user_id) as conn:
        rows = conn.execute("SELECT * FROM indexed_items WHERE embedding IS NOT NULL")
        for row in rows:
            blob = row["embedding"]
            if not blob:
                continue
            vector = np.frombuffer(blob, dtype=np.float32)
            semantic = float(np.dot(query_vector, vector))
            candidate = (semantic, str(row["stable_id"]), row)
            if len(ranked) < keep:
                heapq.heappush(ranked, candidate)
            elif candidate[:2] > ranked[0][:2]:
                heapq.heapreplace(ranked, candidate)
    results = []
    for semantic, _stable_id, row in sorted(ranked, reverse=True):
        item = _context_item(row)
        results.append(
            {
                "message_id": item["message_id"],
                "computer_id": item["computer_id"],
                "computer_name": item["computer_name"],
                "identity_id": item["identity_id"],
                "identity_label": item["identity_label"],
                "session_id": item["session_id"],
                "identity_role": item["identity_role"],
                "item_role": item["role"],
                "item_kind": item["kind"],
                "snippet": str(item["content"] or "")[:1200],
                "semantic_score": semantic,
                "score": semantic,
            }
        )
    return results
