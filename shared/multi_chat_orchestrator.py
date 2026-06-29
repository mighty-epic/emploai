from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.models.session import Session
from cli.session_manager import SessionManager
from shared.runtime_paths import user_state_root
from shared.telegram_bot_config_store import TelegramBotConfigStore
from shared.tool_packs import (
    PACK_INTERACTIVE_DESKTOP,
    PACK_WORKSPACE_WRITE,
    default_enabled_tool_packs,
    enabled_pack_requires_interactive,
    enabled_pack_requires_workspace_write,
    normalize_enabled_tool_packs,
)


@dataclass
class RunningWorkerState:
    session_id: str
    workspace: str
    enabled_tool_packs: List[str] = field(default_factory=list)
    active_tool_packs: List[str] = field(default_factory=list)
    telegram_bot_config_id: Optional[str] = None
    origin_channel: Optional[str] = None
    fleet_identity_id: Optional[str] = None
    fleet_identity_role: Optional[str] = None
    fleet_worker_id: Optional[str] = None


@dataclass
class TurnLease:
    session_id: str
    worker: Any
    acquired: bool = False
    busy: bool = False
    active_tool_packs: List[str] = field(default_factory=list)
    lock_status: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class UserMultiChatOrchestrator:
    def __init__(self, *, user_id: int, workspace: Path) -> None:
        self.user_id = int(user_id)
        self.workspace = workspace
        self.base_path = user_state_root(self.user_id)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.session_manager = SessionManager(base_path=self.base_path)
        self.telegram_bots = TelegramBotConfigStore(user_id=self.user_id)
        self.settings_path = self.base_path / "multi-chat-orchestrator.json"
        self._lock = asyncio.Lock()
        self._workers: Dict[str, Any] = {}
        self._running: Dict[str, RunningWorkerState] = {}
        self._interactive_owner_session_id: Optional[str] = None
        self._workspace_write_owner_by_workspace: Dict[str, str] = {}
        self._settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            return {
                "max_concurrent_chats": 4,
                "headless_mode_enabled": False,
            }
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("max_concurrent_chats", 4)
        payload.setdefault("headless_mode_enabled", False)
        return payload

    def _save_settings(self) -> None:
        self.settings_path.write_text(json.dumps(self._settings, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def max_concurrent_chats(self) -> int:
        try:
            return max(1, int(self._settings.get("max_concurrent_chats", 4) or 4))
        except Exception:
            return 4

    @property
    def headless_mode_enabled(self) -> bool:
        return bool(self._settings.get("headless_mode_enabled", False))

    def _origin_requires_sleep_chat(self, origin_channel: Optional[str]) -> bool:
        origin = str(origin_channel or "").strip().lower()
        return origin in {"", "telegram"}

    def _session_allowed_in_headless(self, session: Session) -> bool:
        bot_config_id = self._resolved_bot_config_id_for_session(session)
        if not bot_config_id:
            return False
        sleep_session_by_bot = self.telegram_bots.get_sleep_session_by_bot()
        designated_sleep_session_id = str(sleep_session_by_bot.get(str(bot_config_id)) or "").strip()
        return bool(designated_sleep_session_id and designated_sleep_session_id == str(session.id))

    def configure_headless(
        self,
        *,
        enabled: Optional[bool] = None,
        default_max_concurrent_chats: Optional[int] = None,
        default_sleep_session_by_bot: Optional[Dict[str, Optional[str]]] = None,
    ) -> Dict[str, Any]:
        if enabled is not None:
            self._settings["headless_mode_enabled"] = bool(enabled)
        if default_max_concurrent_chats is not None:
            self._settings["max_concurrent_chats"] = max(1, int(default_max_concurrent_chats))
        self._save_settings()
        if default_sleep_session_by_bot is not None:
            for bot_id, session_id in dict(default_sleep_session_by_bot).items():
                self.telegram_bots.set_sleep_session(bot_config_id=str(bot_id), session_id=str(session_id or "").strip() or None)
        if self.headless_mode_enabled:
            for session_id in list(self._running):
                state = self._running.get(session_id)
                if state and not self._origin_requires_sleep_chat(state.origin_channel):
                    continue
                worker = self._workers.get(session_id)
                if worker is None or self._session_allowed_in_headless(worker.session):
                    continue
                setattr(worker, "should_interrupt", True)
        return self.runtime_status_view()

    def _session_workspace(self, session: Session) -> str:
        try:
            return str(Path(session.workspace or self.workspace).expanduser().resolve())
        except Exception:
            return str(self.workspace)

    def _worker_module(self):
        from telegram_bot import telegram_session_state as module

        return module

    def _build_worker(self, session_id: str) -> Any:
        module = self._worker_module()
        session = self.session_manager.load_session(session_id, set_current=False)
        worker = module.TelegramSession(
            user_id=self.user_id,
            workspace=Path(session.workspace or self.workspace),
            create_new_session_on_init=False,
        )
        if getattr(module, "_telegram_application", None) is not None and getattr(module, "_telegram_loop", None) is not None:
            worker.bind_telegram_runtime(module._telegram_application, module._telegram_loop)
        worker.load_session_by_id(session_id, set_current=False)
        worker.enabled_tool_packs = normalize_enabled_tool_packs(getattr(session, "enabled_tool_packs", []) or default_enabled_tool_packs())
        if not worker.enabled_tool_packs:
            worker.enabled_tool_packs = default_enabled_tool_packs()
        worker.telegram_bot_config_id = getattr(session, "telegram_bot_config_id", None)
        worker.headless_eligible = bool(getattr(session, "headless_eligible", False))
        return worker

    def get_worker(self, session_id: str) -> Any:
        worker = self._workers.get(session_id)
        if worker is None:
            worker = self._build_worker(session_id)
            self._workers[session_id] = worker
        return worker

    def _default_bot_config_id(self) -> Optional[str]:
        config = self.telegram_bots.default_config()
        return str(config.get("id") or "").strip() if config else None

    def _resolved_bot_config_id_for_session(self, session: Session) -> Optional[str]:
        target_id = str(getattr(session, "telegram_bot_config_id", "") or "").strip()
        if target_id:
            config = self.telegram_bots.get_config(target_id)
            if config:
                return target_id
        return self._default_bot_config_id()

    def _session_summary_live_fields(self, session: Session) -> Dict[str, Any]:
        enabled_packs = normalize_enabled_tool_packs(getattr(session, "enabled_tool_packs", []) or default_enabled_tool_packs())
        if not enabled_packs:
            enabled_packs = default_enabled_tool_packs()
        lock_status = self.lock_status_for_session_obj(session)
        is_running = str(session.id) in self._running
        return {
            "is_running": is_running,
            "run_state": "running" if is_running else "idle",
            "enabled_tool_packs": enabled_packs,
            "available_tool_packs": self.available_tool_packs_for_session_obj(session),
            "lock_status": lock_status,
            "telegram_bot_config_id": getattr(session, "telegram_bot_config_id", None) or self._default_bot_config_id(),
            "headless_eligible": bool(getattr(session, "headless_eligible", False)),
        }

    def _managed_fleet_identity_id(self, session: Session) -> Optional[str]:
        role = str(getattr(session, "fleet_identity_role", "") or "").strip().lower()
        identity_id = str(getattr(session, "fleet_identity_id", "") or "").strip()
        worker_id = str(getattr(session, "fleet_worker_id", "") or "").strip()
        if role == "worker" or worker_id:
            return identity_id or worker_id
        return None

    def available_tool_packs_for_session_obj(self, session: Session) -> List[str]:
        enabled = normalize_enabled_tool_packs(getattr(session, "enabled_tool_packs", []) or default_enabled_tool_packs())
        if not enabled:
            enabled = default_enabled_tool_packs()
        if not self._running:
            return list(enabled)
        available: List[str] = []
        workspace = self._session_workspace(session)
        interactive_owner = self._interactive_owner_session_id
        workspace_write_owner = self._workspace_write_owner_by_workspace.get(workspace)
        for pack_id in enabled:
            if pack_id == PACK_INTERACTIVE_DESKTOP and interactive_owner and interactive_owner != session.id:
                continue
            if pack_id == PACK_WORKSPACE_WRITE and workspace_write_owner and workspace_write_owner != session.id:
                continue
            available.append(pack_id)
        return available

    def lock_status_for_session_obj(self, session: Session) -> Dict[str, Any]:
        enabled = normalize_enabled_tool_packs(getattr(session, "enabled_tool_packs", []) or default_enabled_tool_packs())
        if not enabled:
            enabled = default_enabled_tool_packs()
        disabled_reasons: Dict[str, str] = {}
        workspace = self._session_workspace(session)
        interactive_owner = self._interactive_owner_session_id
        workspace_write_owner = self._workspace_write_owner_by_workspace.get(workspace)
        if PACK_INTERACTIVE_DESKTOP in enabled and interactive_owner and interactive_owner != session.id:
            disabled_reasons[PACK_INTERACTIVE_DESKTOP] = f"Interactive tools are locked by chat {interactive_owner}"
        if PACK_WORKSPACE_WRITE in enabled and workspace_write_owner and workspace_write_owner != session.id:
            disabled_reasons[PACK_WORKSPACE_WRITE] = f"Workspace write tools are locked by chat {workspace_write_owner}"
        return {
            "interactive_owner_session_id": interactive_owner,
            "workspace_write_owner_by_workspace": dict(self._workspace_write_owner_by_workspace),
            "disabled_pack_reasons": disabled_reasons,
        }

    def resolve_telegram_bot_for_session(self, session: Session) -> Optional[Dict[str, Any]]:
        target_id = str(getattr(session, "telegram_bot_config_id", "") or "").strip()
        if target_id:
            config = self.telegram_bots.get_config(target_id)
            if config:
                return config
        return self.telegram_bots.default_config()

    def mark_last_emitting_session(self, *, session_id: str, bot_config_id: Optional[str]) -> None:
        target_id = str(bot_config_id or "").strip()
        if not target_id:
            return
        self.telegram_bots.set_last_emitting_session(bot_config_id=target_id, session_id=session_id)

    def resolve_session_for_inbound_bot(self, *, bot_config_id: Optional[str], focused_session_id: Optional[str]) -> Optional[str]:
        target_id = str(bot_config_id or "").strip()
        if not target_id:
            return focused_session_id
        last_emitting = self.telegram_bots.get_last_emitting_session(target_id)
        if last_emitting:
            return last_emitting

        focused = str(focused_session_id or "").strip()
        if focused:
            try:
                focused_session = self.session_manager.load_session(focused, set_current=False)
                if self._resolved_bot_config_id_for_session(focused_session) == target_id:
                    return focused
            except Exception:
                pass

        for summary in self.session_manager.list_sessions():
            session_id = str(getattr(summary, "id", "") or "").strip()
            if not session_id:
                continue
            try:
                session = self.session_manager.load_session(session_id, set_current=False)
            except Exception:
                continue
            if self._resolved_bot_config_id_for_session(session) == target_id:
                return session_id
        return focused_session_id

    async def prepare_turn(self, session_id: str, *, origin_channel: Optional[str] = "telegram") -> TurnLease:
        async with self._lock:
            worker = self.get_worker(session_id)
            if worker.is_processing:
                return TurnLease(
                    session_id=session_id,
                    worker=worker,
                    acquired=False,
                    busy=True,
                    active_tool_packs=list(getattr(worker, "_active_tool_packs_for_current_run", []) or []),
                    lock_status=self.lock_status_for_session_obj(worker.session),
                )

            managed_identity_id = self._managed_fleet_identity_id(worker.session)
            if managed_identity_id:
                for running_session_id, state in self._running.items():
                    if running_session_id == session_id:
                        continue
                    if str(state.fleet_identity_id or state.fleet_worker_id or "") == managed_identity_id:
                        return TurnLease(
                            session_id=session_id,
                            worker=worker,
                            acquired=False,
                            busy=True,
                            error="This managed worker already has an active run. Queue the task or stop the current run first.",
                            lock_status=self.lock_status_for_session_obj(worker.session),
                        )

            if session_id not in self._running and len(self._running) >= self.max_concurrent_chats:
                return TurnLease(
                    session_id=session_id,
                    worker=worker,
                    acquired=False,
                    busy=True,
                    error=f"Only {self.max_concurrent_chats} chats can run at once right now.",
                    lock_status=self.lock_status_for_session_obj(worker.session),
                )

            available_tool_packs = self.available_tool_packs_for_session_obj(worker.session)
            lock_status = self.lock_status_for_session_obj(worker.session)
            disabled_pack_reasons = dict(lock_status.get("disabled_pack_reasons") or {})
            if disabled_pack_reasons:
                return TurnLease(
                    session_id=session_id,
                    worker=worker,
                    acquired=False,
                    busy=True,
                    error="Required tool resources are locked by another active chat. Queue this work or stop the conflicting run first.",
                    lock_status=lock_status,
                )
            restrict_to_sleep_chat = self.headless_mode_enabled and self._origin_requires_sleep_chat(origin_channel)
            if restrict_to_sleep_chat:
                bot_config_id = self._resolved_bot_config_id_for_session(worker.session)
                if not self._session_allowed_in_headless(worker.session):
                    return TurnLease(
                        session_id=session_id,
                        worker=worker,
                        acquired=False,
                        busy=True,
                        error="Sleep mode only allows designated Telegram sleep chats to run.",
                        lock_status=self.lock_status_for_session_obj(worker.session),
                    )
                if bot_config_id and bot_config_id != self._default_bot_config_id():
                    available_tool_packs = [pack_id for pack_id in available_tool_packs if pack_id != PACK_INTERACTIVE_DESKTOP]
            worker._active_tool_packs_for_current_run = list(available_tool_packs)
            worker.current_turn_allowed_tool_names = None
            if session_id not in self._running:
                state = RunningWorkerState(
                    session_id=session_id,
                    workspace=self._session_workspace(worker.session),
                    enabled_tool_packs=list(worker.enabled_tool_packs),
                    active_tool_packs=list(available_tool_packs),
                    telegram_bot_config_id=worker.telegram_bot_config_id,
                    origin_channel=origin_channel,
                    fleet_identity_id=str(getattr(worker.session, "fleet_identity_id", "") or "").strip() or None,
                    fleet_identity_role=str(getattr(worker.session, "fleet_identity_role", "") or "").strip() or None,
                    fleet_worker_id=str(getattr(worker.session, "fleet_worker_id", "") or "").strip() or None,
                )
                self._running[session_id] = state
                if enabled_pack_requires_interactive(available_tool_packs) and not self._interactive_owner_session_id:
                    self._interactive_owner_session_id = session_id
                if enabled_pack_requires_workspace_write(available_tool_packs):
                    workspace = self._session_workspace(worker.session)
                    self._workspace_write_owner_by_workspace.setdefault(workspace, session_id)

            return TurnLease(
                session_id=session_id,
                worker=worker,
                acquired=True,
                active_tool_packs=list(available_tool_packs),
                lock_status=self.lock_status_for_session_obj(worker.session),
            )

    async def complete_turn(self, lease: TurnLease) -> None:
        if not lease.acquired:
            return
        async with self._lock:
            self._release_running_state(lease.session_id, worker=lease.worker)

    def _release_running_state(self, session_id: str, *, worker: Any = None) -> bool:
        state = self._running.pop(session_id, None)
        if state and self._interactive_owner_session_id == session_id:
            self._interactive_owner_session_id = None
        if state:
            for workspace, owner_session_id in list(self._workspace_write_owner_by_workspace.items()):
                if owner_session_id == session_id:
                    self._workspace_write_owner_by_workspace.pop(workspace, None)
        target_worker = worker if worker is not None else self._workers.get(session_id)
        if target_worker is not None:
            target_worker._active_tool_packs_for_current_run = []
        return state is not None

    async def force_release_turn(self, session_id: str, *, worker: Any = None) -> bool:
        async with self._lock:
            return self._release_running_state(str(session_id), worker=worker)

    def list_running_workers(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for state in self._running.values():
            rows.append(
                {
                    "session_id": state.session_id,
                    "is_running": True,
                    "run_state": "running",
                    "workspace": state.workspace,
                    "enabled_tool_packs": list(state.enabled_tool_packs),
                    "active_tool_packs": list(state.active_tool_packs),
                    "telegram_bot_config_id": state.telegram_bot_config_id,
                    "fleet_identity_id": state.fleet_identity_id,
                    "fleet_identity_role": state.fleet_identity_role,
                    "fleet_worker_id": state.fleet_worker_id,
                }
            )
        rows.sort(key=lambda item: item["session_id"])
        return rows

    def runtime_status_view(self) -> Dict[str, Any]:
        return {
            "max_concurrent_chats": self.max_concurrent_chats,
            "running_sessions": self.list_running_workers(),
            "locks": {
                "interactive_owner_session_id": self._interactive_owner_session_id,
                "workspace_write_owner_by_workspace": dict(self._workspace_write_owner_by_workspace),
            },
            "headless_mode_enabled": self.headless_mode_enabled,
            "default_sleep_session_by_bot": self.telegram_bots.get_sleep_session_by_bot(),
        }

    def update_session_tool_packs(self, session_id: str, enabled_tool_packs: List[str]) -> Session:
        session = self.session_manager.load_session(session_id, set_current=False)
        session.enabled_tool_packs = normalize_enabled_tool_packs(enabled_tool_packs)
        self.session_manager.save_session(session)
        worker = self._workers.get(session_id)
        if worker and not worker.is_processing:
            next_enabled = list(session.enabled_tool_packs or default_enabled_tool_packs())
            worker.enabled_tool_packs = next_enabled
            if getattr(worker, "session", None) is not None:
                worker.session.enabled_tool_packs = list(next_enabled)
        return session

    def update_session_bot_assignment(self, session_id: str, telegram_bot_config_id: Optional[str]) -> Session:
        session = self.session_manager.load_session(session_id, set_current=False)
        clean = str(telegram_bot_config_id or "").strip() or None
        if clean and not self.telegram_bots.get_config(clean):
            raise KeyError(clean)
        session.telegram_bot_config_id = clean
        self.session_manager.save_session(session)
        worker = self._workers.get(session_id)
        if worker and not worker.is_processing:
            worker.telegram_bot_config_id = clean
            if getattr(worker, "session", None) is not None:
                worker.session.telegram_bot_config_id = clean
        return session

    def update_session_headless_eligible(self, session_id: str, headless_eligible: bool) -> Session:
        session = self.session_manager.load_session(session_id, set_current=False)
        session.headless_eligible = bool(headless_eligible)
        self.session_manager.save_session(session)
        worker = self._workers.get(session_id)
        if worker and not worker.is_processing:
            worker.headless_eligible = bool(headless_eligible)
            if getattr(worker, "session", None) is not None:
                worker.session.headless_eligible = bool(headless_eligible)
        return session

    def update_session_security_permission_mode(self, session_id: str, security_permission_mode: str) -> Session:
        from shared.security_policy import normalize_permission_mode

        session = self.session_manager.load_session(session_id, set_current=False)
        session.security_permission_mode = normalize_permission_mode(security_permission_mode)
        self.session_manager.save_session(session)
        worker = self._workers.get(session_id)
        if worker and not worker.is_processing and getattr(worker, "session", None) is not None:
            worker.session.security_permission_mode = session.security_permission_mode
            if getattr(worker, "tool_executor", None) is not None:
                workspace_for_security = str(getattr(worker.session, "workspace", "") or "")
                worker.tool_executor.security_context_provider = lambda: {
                    "permission_mode": getattr(worker.session, "security_permission_mode", "standard"),
                    "workspace_path": workspace_for_security,
                    "workspace_binding_status": getattr(worker.session, "workspace_binding_status", None),
                    "workspace_write_enabled": (
                        None
                        if not workspace_for_security
                        else Path(workspace_for_security).expanduser().exists()
                    ),
                    "surface": "app",
                    "session_id": getattr(worker.session, "id", None),
                    "identity_id": getattr(worker.session, "fleet_identity_id", None),
                }
        return session


_ORCHESTRATORS: Dict[int, UserMultiChatOrchestrator] = {}


def get_user_orchestrator(*, user_id: int, workspace: Path) -> UserMultiChatOrchestrator:
    orchestrator = _ORCHESTRATORS.get(int(user_id))
    if orchestrator is None:
        orchestrator = UserMultiChatOrchestrator(user_id=int(user_id), workspace=workspace)
        _ORCHESTRATORS[int(user_id)] = orchestrator
    return orchestrator
