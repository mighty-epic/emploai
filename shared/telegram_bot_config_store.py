from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.runtime_paths import user_state_root


def _mask_token(token: str) -> str:
    clean = str(token or "").strip()
    if len(clean) <= 10:
        return clean
    return f"{clean[:8]}...{clean[-4:]}"


class TelegramBotConfigStore:
    def __init__(self, *, user_id: int) -> None:
        self.user_id = int(user_id)
        self.base_path = user_state_root(self.user_id)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.path = self.base_path / "telegram-bot-configs.json"

    def _read_payload(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"items": [], "default_bot_config_id": None, "last_emitting_session_by_bot": {}, "sleep_session_by_bot": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"items": [], "default_bot_config_id": None, "last_emitting_session_by_bot": {}, "sleep_session_by_bot": {}}
        if not isinstance(payload, dict):
            return {"items": [], "default_bot_config_id": None, "last_emitting_session_by_bot": {}, "sleep_session_by_bot": {}}
        payload.setdefault("items", [])
        payload.setdefault("default_bot_config_id", None)
        payload.setdefault("last_emitting_session_by_bot", {})
        payload.setdefault("sleep_session_by_bot", {})
        return payload

    def _write_payload(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_configs(self) -> List[Dict[str, Any]]:
        payload = self._read_payload()
        default_id = str(payload.get("default_bot_config_id") or "").strip() or None
        items: List[Dict[str, Any]] = []
        for raw in payload.get("items", []):
            if not isinstance(raw, dict):
                continue
            item = {
                "id": str(raw.get("id") or "").strip(),
                "label": str(raw.get("label") or "Telegram Bot").strip() or "Telegram Bot",
                "bot_token": str(raw.get("bot_token") or "").strip(),
                "is_default": False,
            }
            if not item["id"] or not item["bot_token"]:
                continue
            item["is_default"] = item["id"] == default_id
            items.append(item)
        return items

    def list_public_configs(self) -> List[Dict[str, Any]]:
        items = []
        for item in self.list_configs():
            public_item = dict(item)
            public_item["bot_token"] = _mask_token(public_item["bot_token"])
            items.append(public_item)
        return items

    def get_config(self, bot_config_id: Optional[str]) -> Optional[Dict[str, Any]]:
        target = str(bot_config_id or "").strip()
        if not target:
            return None
        for item in self.list_configs():
            if item["id"] == target:
                return item
        return None

    def default_config(self) -> Optional[Dict[str, Any]]:
        for item in self.list_configs():
            if item.get("is_default"):
                return item
        items = self.list_configs()
        return items[0] if items else None

    def ensure_default_from_env(self, *, bot_token: Optional[str]) -> Optional[Dict[str, Any]]:
        clean_token = str(bot_token or "").strip()
        if not clean_token:
            return self.default_config()
        payload = self._read_payload()
        for raw in payload.get("items", []):
            if isinstance(raw, dict) and str(raw.get("bot_token") or "").strip() == clean_token:
                if not payload.get("default_bot_config_id"):
                    payload["default_bot_config_id"] = str(raw.get("id") or "").strip()
                    self._write_payload(payload)
                return self.default_config()
        item_id = uuid.uuid4().hex[:10]
        payload["items"].append(
            {
                "id": item_id,
                "label": "Default Telegram Bot",
                "bot_token": clean_token,
            }
        )
        payload["default_bot_config_id"] = item_id
        self._write_payload(payload)
        return self.default_config()

    def create_config(self, *, label: str, bot_token: str) -> Dict[str, Any]:
        payload = self._read_payload()
        item_id = uuid.uuid4().hex[:10]
        payload["items"].append(
            {
                "id": item_id,
                "label": str(label or "Telegram Bot").strip() or "Telegram Bot",
                "bot_token": str(bot_token or "").strip(),
            }
        )
        if not payload.get("default_bot_config_id"):
            payload["default_bot_config_id"] = item_id
        self._write_payload(payload)
        return self.get_config(item_id) or {"id": item_id, "label": label, "bot_token": bot_token, "is_default": False}

    def update_config(
        self,
        bot_config_id: str,
        *,
        label: Optional[str] = None,
        bot_token: Optional[str] = None,
        is_default: Optional[bool] = None,
    ) -> Dict[str, Any]:
        payload = self._read_payload()
        target = str(bot_config_id or "").strip()
        found = False
        for raw in payload.get("items", []):
            if not isinstance(raw, dict) or str(raw.get("id") or "").strip() != target:
                continue
            if label is not None:
                raw["label"] = str(label or "").strip() or raw.get("label") or "Telegram Bot"
            if bot_token is not None:
                raw["bot_token"] = str(bot_token or "").strip()
            found = True
            break
        if not found:
            raise KeyError(target)
        if is_default is True:
            payload["default_bot_config_id"] = target
        self._write_payload(payload)
        config = self.get_config(target)
        if not config:
            raise KeyError(target)
        return config

    def delete_config(self, bot_config_id: str) -> None:
        payload = self._read_payload()
        target = str(bot_config_id or "").strip()
        items = [item for item in payload.get("items", []) if isinstance(item, dict) and str(item.get("id") or "").strip() != target]
        payload["items"] = items
        if str(payload.get("default_bot_config_id") or "").strip() == target:
            payload["default_bot_config_id"] = str(items[0].get("id") or "").strip() if items else None
        payload["last_emitting_session_by_bot"] = {
            key: value
            for key, value in dict(payload.get("last_emitting_session_by_bot") or {}).items()
            if key != target
        }
        payload["sleep_session_by_bot"] = {
            key: value
            for key, value in dict(payload.get("sleep_session_by_bot") or {}).items()
            if key != target
        }
        self._write_payload(payload)

    def set_last_emitting_session(self, *, bot_config_id: str, session_id: Optional[str]) -> None:
        payload = self._read_payload()
        mapping = dict(payload.get("last_emitting_session_by_bot") or {})
        if session_id:
            mapping[str(bot_config_id)] = str(session_id)
        else:
            mapping.pop(str(bot_config_id), None)
        payload["last_emitting_session_by_bot"] = mapping
        self._write_payload(payload)

    def get_last_emitting_session(self, bot_config_id: Optional[str]) -> Optional[str]:
        if not bot_config_id:
            return None
        payload = self._read_payload()
        value = dict(payload.get("last_emitting_session_by_bot") or {}).get(str(bot_config_id))
        clean = str(value or "").strip()
        return clean or None

    def set_sleep_session(self, *, bot_config_id: str, session_id: Optional[str]) -> None:
        payload = self._read_payload()
        mapping = dict(payload.get("sleep_session_by_bot") or {})
        if session_id:
            mapping[str(bot_config_id)] = str(session_id)
        else:
            mapping.pop(str(bot_config_id), None)
        payload["sleep_session_by_bot"] = mapping
        self._write_payload(payload)

    def get_sleep_session_by_bot(self) -> Dict[str, str]:
        payload = self._read_payload()
        return {
            str(key): str(value)
            for key, value in dict(payload.get("sleep_session_by_bot") or {}).items()
            if str(key).strip() and str(value).strip()
        }
