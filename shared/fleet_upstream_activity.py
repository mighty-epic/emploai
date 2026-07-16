from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


FLEET_ACTIVITY_FILENAME = "fleet_upstream_activity.sqlite3"
REQUEST_KINDS = {"question", "approval", "blocked"}
REQUEST_DECISIONS = {"approved", "denied", "replied"}


def _utc_iso(value: Optional[float]) -> Optional[str]:
    if not value:
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value)) if value not in {None, ""} else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _database_path(home: Path) -> Path:
    path = Path(home).expanduser().resolve() / FLEET_ACTIVITY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(home: Path) -> sqlite3.Connection:
    path = _database_path(home)
    connection = sqlite3.connect(str(path), timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS fleet_upstream_activity (
            activity_id TEXT PRIMARY KEY,
            activity_kind TEXT NOT NULL,
            direction TEXT NOT NULL,
            identity_id TEXT,
            identity_label TEXT,
            request_kind TEXT,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            response TEXT,
            report TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fleet_upstream_activity_updated
            ON fleet_upstream_activity(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fleet_upstream_activity_outbox
            ON fleet_upstream_activity(activity_kind, status, created_at);
        """
    )
    connection.commit()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return connection


def _activity_view(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "activity_id": str(row["activity_id"]),
        "activity_kind": str(row["activity_kind"]),
        "direction": str(row["direction"]),
        "identity_id": row["identity_id"],
        "identity_label": row["identity_label"],
        "request_kind": row["request_kind"],
        "message": str(row["message"] or ""),
        "status": str(row["status"] or ""),
        "response": row["response"],
        "report": _json_loads(row["report"], {}),
        "created_at": _utc_iso(row["created_at"]),
        "updated_at": _utc_iso(row["updated_at"]),
    }


def activity_snapshot(home: Path, *, limit: int = 200) -> Dict[str, Any]:
    with _connect(home) as connection:
        rows = connection.execute(
            "SELECT * FROM fleet_upstream_activity ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(500, int(limit or 200))),),
        ).fetchall()
    return {"schema_version": 1, "items": [_activity_view(row) for row in rows]}


def queue_upstream_request(
    home: Path,
    *,
    request_kind: str,
    identity_id: Optional[str],
    identity_label: Optional[str],
    message: str,
) -> Dict[str, Any]:
    clean_kind = str(request_kind or "").strip().lower()
    clean_message = str(message or "").strip()
    if clean_kind not in REQUEST_KINDS:
        raise ValueError("request_kind must be question, approval, or blocked")
    if not clean_message:
        raise ValueError("message is required")
    request_id = f"fur_{secrets.token_hex(8)}"
    now = time.time()
    with _connect(home) as connection:
        connection.execute(
            """
            INSERT INTO fleet_upstream_activity(
                activity_id, activity_kind, direction, identity_id, identity_label,
                request_kind, message, status, response, report, created_at, updated_at
            ) VALUES(?, 'request', 'up', ?, ?, ?, ?, 'queued', NULL, '{}', ?, ?)
            """,
            (
                request_id,
                str(identity_id or "").strip()[:128] or None,
                str(identity_label or "").strip()[:160] or None,
                clean_kind,
                clean_message[:8000],
                now,
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM fleet_upstream_activity WHERE activity_id = ?",
            (request_id,),
        ).fetchone()
    return _activity_view(row)


def pending_upstream_requests(home: Path, *, limit: int = 25) -> List[Dict[str, Any]]:
    with _connect(home) as connection:
        rows = connection.execute(
            """
            SELECT * FROM fleet_upstream_activity
            WHERE activity_kind = 'request' AND direction = 'up' AND status = 'queued'
            ORDER BY created_at ASC LIMIT ?
            """,
            (max(1, min(100, int(limit or 25))),),
        ).fetchall()
    return [_activity_view(row) for row in rows]


def mark_upstream_request_sent(home: Path, request_id: str) -> Dict[str, Any]:
    now = time.time()
    with _connect(home) as connection:
        connection.execute(
            """
            UPDATE fleet_upstream_activity SET status = 'sent', updated_at = ?
            WHERE activity_id = ? AND activity_kind = 'request' AND status = 'queued'
            """,
            (now, str(request_id or "").strip()),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM fleet_upstream_activity WHERE activity_id = ?",
            (str(request_id or "").strip(),),
        ).fetchone()
    if not row:
        raise KeyError("Unknown upstream request")
    return _activity_view(row)


def record_upstream_request_decision(
    home: Path,
    *,
    request_id: str,
    decision: str,
    response: Optional[str] = None,
) -> Dict[str, Any]:
    clean_decision = str(decision or "").strip().lower()
    if clean_decision not in REQUEST_DECISIONS:
        raise ValueError("decision must be approved, denied, or replied")
    now = time.time()
    with _connect(home) as connection:
        cursor = connection.execute(
            """
            UPDATE fleet_upstream_activity SET status = ?, response = ?, updated_at = ?
            WHERE activity_id = ? AND activity_kind = 'request'
            """,
            (
                clean_decision,
                str(response or "").strip()[:8000] or None,
                now,
                str(request_id or "").strip(),
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError("Unknown upstream request")
        connection.commit()
        row = connection.execute(
            "SELECT * FROM fleet_upstream_activity WHERE activity_id = ?",
            (str(request_id or "").strip(),),
        ).fetchone()
    return _activity_view(row)


def record_incoming_delegation(
    home: Path,
    *,
    delegation_id: str,
    message: str,
    identity_id: Optional[str] = None,
    identity_label: Optional[str] = None,
    status: str = "running",
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    clean_id = str(delegation_id or "").strip()
    clean_message = str(message or "").strip()
    if not clean_id or not clean_message:
        raise ValueError("delegation_id and message are required")
    clean_status = str(status or "running").strip().lower()
    if clean_status not in {"queued", "running", "completed", "failed", "stopped", "canceled"}:
        clean_status = "failed"
    now = time.time()
    with _connect(home) as connection:
        connection.execute(
            """
            INSERT INTO fleet_upstream_activity(
                activity_id, activity_kind, direction, identity_id, identity_label,
                request_kind, message, status, response, report, created_at, updated_at
            ) VALUES(?, 'delegation', 'down', ?, ?, NULL, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                identity_id = COALESCE(excluded.identity_id, fleet_upstream_activity.identity_id),
                identity_label = COALESCE(excluded.identity_label, fleet_upstream_activity.identity_label),
                message = excluded.message,
                status = excluded.status,
                report = excluded.report,
                updated_at = excluded.updated_at
            """,
            (
                clean_id,
                str(identity_id or "").strip()[:128] or None,
                str(identity_label or "").strip()[:160] or None,
                clean_message[:8000],
                clean_status,
                _json_dumps(report or {}),
                now,
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM fleet_upstream_activity WHERE activity_id = ?",
            (clean_id,),
        ).fetchone()
    return _activity_view(row)
