from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.runtime_paths import user_state_root


class CronFeedStore:
    def __init__(self, *, user_id: int) -> None:
        self.user_id = int(user_id)
        self.base_path = user_state_root(self.user_id)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.path = self.base_path / "cron-feed.json"

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"items": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}
        if not isinstance(payload, dict):
            return {"items": []}
        payload.setdefault("items", [])
        return payload

    def _write(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append(
        self,
        *,
        kind: str,
        content: str,
        session_id: Optional[str] = None,
        session_name: Optional[str] = None,
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        telegram_bot_config_id: Optional[str] = None,
        telegram_bot_label: Optional[str] = None,
        status: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self._read()
        item = {
            "id": uuid.uuid4().hex,
            "timestamp": timestamp or datetime.now().isoformat(),
            "kind": kind,
            "content": content,
            "session_id": session_id,
            "session_name": session_name,
            "job_id": job_id,
            "job_name": job_name,
            "telegram_bot_config_id": telegram_bot_config_id,
            "telegram_bot_label": telegram_bot_label,
            "status": status,
        }
        items = list(payload.get("items", []))
        items.append(item)
        payload["items"] = items[-800:]
        self._write(payload)
        return item

    def list_items(self) -> List[Dict[str, Any]]:
        payload = self._read()
        items = list(payload.get("items", []))
        items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return items
