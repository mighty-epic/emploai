from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import user_state_root

FIRST_BOT_LABEL = "Telegram bot 1"
MAX_TELEGRAM_BOT_TOKEN_CHARS = 2000
TELEGRAM_BOT_TOKENS_JSON_ENV = "EMPLOAI_TELEGRAM_BOT_TOKENS_JSON"


def _secure_chmod(path: Path, mode: int) -> None:
    try:
        if path.exists():
            os.chmod(path, mode)
    except Exception:
        pass


def _mask_token(token: str) -> str:
    clean = str(token or "").strip()
    if len(clean) <= 10:
        return clean
    return f"{clean[:8]}...{clean[-4:]}"


def _runtime_token_map() -> Dict[str, str]:
    raw = str(os.getenv(TELEGRAM_BOT_TOKENS_JSON_ENV, "") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    tokens: Dict[str, str] = {}
    for raw_id, raw_token in payload.items():
        item_id = str(raw_id or "").strip()
        token = str(raw_token or "").strip()
        if item_id and token and len(token) <= MAX_TELEGRAM_BOT_TOKEN_CHARS:
            tokens[item_id] = token
    return tokens


def _set_runtime_token_map(tokens: Dict[str, str]) -> None:
    clean_tokens = {
        str(item_id): str(token)
        for item_id, token in dict(tokens or {}).items()
        if str(item_id).strip() and str(token).strip() and len(str(token).strip()) <= MAX_TELEGRAM_BOT_TOKEN_CHARS
    }
    if clean_tokens:
        os.environ[TELEGRAM_BOT_TOKENS_JSON_ENV] = json.dumps(clean_tokens, ensure_ascii=False, sort_keys=True)
    else:
        os.environ.pop(TELEGRAM_BOT_TOKENS_JSON_ENV, None)


class TelegramBotConfigStore:
    def __init__(self, *, user_id: int) -> None:
        self.user_id = int(user_id)
        self.base_path = user_state_root(self.user_id)
        self.base_path.mkdir(parents=True, exist_ok=True)
        _secure_chmod(self.base_path, 0o700)
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
        normalized = self._normalize_payload(payload)
        token_map = {
            str(item.get("id") or "").strip(): str(item.get("bot_token") or "").strip()
            for item in normalized.get("items", [])
            if isinstance(item, dict)
            and str(item.get("id") or "").strip()
            and str(item.get("bot_token") or "").strip()
        }
        disk_payload = dict(normalized)
        disk_items: List[Dict[str, Any]] = []
        for raw in normalized.get("items", []):
            if not isinstance(raw, dict):
                continue
            disk_items.append(
                {
                    "id": str(raw.get("id") or "").strip(),
                    "label": str(raw.get("label") or "").strip(),
                }
            )
        disk_payload["items"] = disk_items

        previous_umask: Optional[int] = None
        try:
            previous_umask = os.umask(0o077)
        except Exception:
            previous_umask = None
        try:
            atomic_write_json(self.path, disk_payload)
        finally:
            if previous_umask is not None:
                try:
                    os.umask(previous_umask)
                except Exception:
                    pass
        _secure_chmod(self.path, 0o600)
        _set_runtime_token_map(token_map)

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        default_id = str(payload.get("default_bot_config_id") or "").strip() or None
        runtime_tokens = _runtime_token_map()
        for raw in payload.get("items", []):
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "").strip()
            bot_token = str(raw.get("bot_token") or runtime_tokens.get(item_id) or "").strip()
            if len(bot_token) > MAX_TELEGRAM_BOT_TOKEN_CHARS:
                continue
            if not item_id or not bot_token or item_id in seen_ids:
                continue
            label = str(raw.get("label") or "").strip()[:128]
            if not label or label in {"Telegram Bot", "Default Telegram Bot", "Default Telegram bot"}:
                label = FIRST_BOT_LABEL if not items else f"Telegram bot {len(items) + 1}"
            items.append(
                {
                    "id": item_id,
                    "label": label,
                    "bot_token": bot_token,
                }
            )
            seen_ids.add(item_id)

        if not items:
            payload["items"] = []
            payload["default_bot_config_id"] = None
            payload["last_emitting_session_by_bot"] = {}
            payload["sleep_session_by_bot"] = {}
            return payload

        if default_id and default_id in seen_ids:
            items.sort(key=lambda item: 0 if item["id"] == default_id else 1)
        default_id = items[0]["id"]
        for item in items:
            if item["id"] == default_id and not str(item.get("label") or "").strip():
                item["label"] = FIRST_BOT_LABEL

        payload["items"] = items
        payload["default_bot_config_id"] = default_id
        return payload

    def list_configs(self) -> List[Dict[str, Any]]:
        payload = self._normalize_payload(self._read_payload())
        default_id = str(payload.get("default_bot_config_id") or "").strip() or None
        items: List[Dict[str, Any]] = []
        for raw in payload.get("items", []):
            if not isinstance(raw, dict):
                continue
            item = {
                "id": str(raw.get("id") or "").strip(),
                "label": str(raw.get("label") or "").strip() or (
                    FIRST_BOT_LABEL if str(raw.get("id") or "").strip() == default_id else "Telegram Bot"
                ),
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
        payload = self._normalize_payload(self._read_payload())
        for raw in payload.get("items", []):
            if isinstance(raw, dict) and str(raw.get("bot_token") or "").strip() == clean_token:
                if not payload.get("default_bot_config_id"):
                    payload["default_bot_config_id"] = str(raw.get("id") or "").strip()
                if str(payload.get("default_bot_config_id") or "").strip() == str(raw.get("id") or "").strip():
                    label = str(raw.get("label") or "").strip()
                    if not label or label in {"Telegram Bot", "Default Telegram Bot", "Default Telegram bot"}:
                        raw["label"] = FIRST_BOT_LABEL
                self._write_payload(self._normalize_payload(payload))
                return self.default_config()
        item_id = uuid.uuid4().hex[:10]
        payload["items"].append(
            {
                "id": item_id,
                "label": FIRST_BOT_LABEL,
                "bot_token": clean_token,
            }
        )
        payload["default_bot_config_id"] = item_id
        self._write_payload(self._normalize_payload(payload))
        return self.default_config()

    def replace_configs(
        self,
        items: List[Dict[str, Any]],
        *,
        default_bot_config_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._read_payload()
        next_items: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or raw.get("bot_config_id") or "").strip()
            bot_token = str(raw.get("bot_token") or raw.get("token") or "").strip()
            if not item_id or item_id in seen_ids:
                continue
            if not bot_token or len(bot_token) > MAX_TELEGRAM_BOT_TOKEN_CHARS:
                continue
            label = str(raw.get("label") or "").strip()[:128]
            if not label:
                label = FIRST_BOT_LABEL if index == 0 else f"Telegram bot {len(next_items) + 1}"
            next_items.append(
                {
                    "id": item_id,
                    "label": label,
                    "bot_token": bot_token,
                }
            )
            seen_ids.add(item_id)

        clean_default_id = str(default_bot_config_id or "").strip()
        if not clean_default_id:
            default_candidates = {
                str(raw.get("id") or raw.get("bot_config_id") or "").strip()
                for raw in items
                if isinstance(raw, dict) and bool(raw.get("is_default"))
            }
            for item in next_items:
                if item["id"] in default_candidates:
                    clean_default_id = item["id"]
                    break
        if clean_default_id not in seen_ids:
            clean_default_id = next_items[0]["id"] if next_items else ""

        payload["items"] = next_items
        payload["default_bot_config_id"] = clean_default_id or None
        payload["last_emitting_session_by_bot"] = {
            str(key): str(value)
            for key, value in dict(payload.get("last_emitting_session_by_bot") or {}).items()
            if str(key) in seen_ids and str(value).strip()
        }
        payload["sleep_session_by_bot"] = {
            str(key): str(value)
            for key, value in dict(payload.get("sleep_session_by_bot") or {}).items()
            if str(key) in seen_ids and str(value).strip()
        }
        self._write_payload(self._normalize_payload(payload))
        return self.list_public_configs()

    def create_config(self, *, label: str, bot_token: str) -> Dict[str, Any]:
        clean_token = str(bot_token or "").strip()
        if not clean_token:
            raise ValueError("Telegram bot token is required")
        if len(clean_token) > MAX_TELEGRAM_BOT_TOKEN_CHARS:
            raise ValueError("Telegram bot token is too large")
        payload = self._normalize_payload(self._read_payload())
        item_id = uuid.uuid4().hex[:10]
        label_text = str(label or "").strip()[:128]
        if not label_text:
            label_text = f"Telegram bot {len(payload.get('items', [])) + 1}"
        payload["items"].append(
            {
                "id": item_id,
                "label": label_text,
                "bot_token": clean_token,
            }
        )
        if not payload.get("default_bot_config_id"):
            payload["default_bot_config_id"] = item_id
        self._write_payload(self._normalize_payload(payload))
        return self.get_config(item_id) or {"id": item_id, "label": label_text, "bot_token": clean_token, "is_default": False}

    def update_config(
        self,
        bot_config_id: str,
        *,
        label: Optional[str] = None,
        bot_token: Optional[str] = None,
        is_default: Optional[bool] = None,
    ) -> Dict[str, Any]:
        payload = self._normalize_payload(self._read_payload())
        target = str(bot_config_id or "").strip()
        found = False
        for raw in payload.get("items", []):
            if not isinstance(raw, dict) or str(raw.get("id") or "").strip() != target:
                continue
            if label is not None:
                default_id = str(payload.get("default_bot_config_id") or "").strip()
                fallback = FIRST_BOT_LABEL if target == default_id else "Telegram Bot"
                raw["label"] = str(label or "").strip()[:128] or raw.get("label") or fallback
            if bot_token is not None:
                clean_token = str(bot_token or "").strip()
                if not clean_token:
                    raise ValueError("Telegram bot token is required")
                if len(clean_token) > MAX_TELEGRAM_BOT_TOKEN_CHARS:
                    raise ValueError("Telegram bot token is too large")
                raw["bot_token"] = clean_token
            found = True
            break
        if not found:
            raise KeyError(target)
        if is_default is True:
            payload["default_bot_config_id"] = target
        self._write_payload(self._normalize_payload(payload))
        config = self.get_config(target)
        if not config:
            raise KeyError(target)
        return config

    def delete_config(self, bot_config_id: str) -> None:
        payload = self._normalize_payload(self._read_payload())
        target = str(bot_config_id or "").strip()
        if not target or not any(str(item.get("id") or "").strip() == target for item in payload.get("items", [])):
            raise KeyError(target)
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
        self._write_payload(self._normalize_payload(payload))

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
