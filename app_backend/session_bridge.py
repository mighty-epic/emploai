from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import time

from cli.models.session import Session, SessionSummary
from cli.session_manager import SessionManager
from shared.artifact_store import ChatArtifactStore
from shared.cron_feed_store import CronFeedStore
from shared.multi_chat_orchestrator import get_user_orchestrator
from shared.model_availability import enabled_providers_from_env
from shared.model_defaults import default_model_pair_for_enabled_providers
from shared.session_timeline import append_timeline_event, create_timeline_event
from shared.runtime_paths import user_state_root
from shared.security_policy import normalize_permission_mode
from shared.tool_packs import default_enabled_tool_packs, normalize_enabled_tool_packs

if TYPE_CHECKING:
    from telegram_bot.telegram_session_state import TelegramSession


user_sessions: dict[int, Any] | None = None
EMPTY_SESSION_PRUNE_GRACE_SECONDS = 10.0


def is_user_visible_timeline_event(event: Dict[str, Any]) -> bool:
    metadata = dict(event.get("metadata") or {})
    visibility = str(metadata.get("visibility") or "").strip().lower()
    title = str(event.get("title") or "").strip().casefold()
    kind = str(event.get("kind") or "").strip().casefold()
    content = str(event.get("content") or "").strip().casefold()
    source_format = str(event.get("source_format") or "").strip().casefold()
    if visibility in {"internal", "debug"} or metadata.get("internal") is True:
        return False
    if source_format in {"app_internal", "internal"}:
        return False
    planner_markers = {
        "candidate_final_preview",
        "auto_continue_count",
        "auto_continue_limit",
        "continuation_instruction",
        "retry_instruction",
        "failed_obligation",
        "evidence_gap",
        "must_use_tool",
    }
    if planner_markers.intersection(metadata.keys()):
        return False
    if "planner verifier" in title or "final quality guard" in title:
        return False
    if "planner verifier" in content or "final quality guard" in content:
        return False
    if "candidate final:" in content and kind == "runtime":
        return False
    if kind in {"planner", "planner_verdict", "auto_continue"}:
        return False
    return True


def _telegram_session_state_module():
    from telegram_bot import telegram_session_state as module

    return module


def get_session(user_id: int, *, workspace: Path | None = None, create_new_session: bool = True):
    module = _telegram_session_state_module()
    return module.get_session(user_id, workspace=workspace, create_new_session=create_new_session)


def _scheduler():
    from local_agent_runtime.cron_scheduler import get_scheduler

    return get_scheduler()


class AppSessionBridge:
    """Additive bridge for the mobile app channel.

    This reuses the Telegram runtime cache so app and Telegram operate over the
    same live session object instead of parallel in-memory runtimes.
    """

    def __init__(self, *, user_id: int, workspace: Path):
        self.user_id = user_id
        self.workspace = workspace
        self.base_path = user_state_root(self.user_id)
        self.session_manager = SessionManager(base_path=self.base_path)
        self.orchestrator = get_user_orchestrator(user_id=self.user_id, workspace=self.workspace)
        self.cron_feed_store = CronFeedStore(user_id=self.user_id)

    def _load_session(self, session_id: str, *, set_current: bool) -> Session:
        try:
            session = self.session_manager.load_session(session_id, set_current=set_current)
        except TypeError:
            session = self.session_manager.load_session(session_id)
        changed = False
        if getattr(session, "account_user_id", None) is None:
            try:
                session.account_user_id = int(self.user_id)
                changed = True
            except Exception:
                pass
        if changed:
            try:
                self.session_manager.save_session(session)
            except Exception:
                pass
        return session

    def _session_age_seconds(self, session: Session) -> float:
        raw_value = str(getattr(session, "updated_at", "") or getattr(session, "created_at", "") or "").strip()
        if not raw_value:
            return EMPTY_SESSION_PRUNE_GRACE_SECONDS + 1.0
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return EMPTY_SESSION_PRUNE_GRACE_SECONDS + 1.0
        now = datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.now()
        return max(0.0, (now - parsed).total_seconds())

    def _session_has_user_visible_content(self, session: Session) -> bool:
        if getattr(session, "chat_history", None):
            return True
        if getattr(session, "event_timeline", None):
            return True
        if getattr(session, "task_history", None):
            return True
        if getattr(session, "active_task_id", None):
            return True
        if bool(getattr(session, "task_board_armed_next_turn", False)):
            return True
        if getattr(session, "active_skills", None):
            return True
        return self._existing_artifact_count(session.id) > 0

    def _existing_artifact_count(self, session_id: str) -> int:
        index_path = user_state_root(self.user_id) / "artifacts" / "chats" / str(session_id or "") / "index.json"
        if not index_path.exists():
            return 0
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        if not isinstance(payload, dict):
            return 0
        items = payload.get("items", [])
        return len(items) if isinstance(items, list) else 0

    def _should_prune_empty_session(self, session: Session) -> bool:
        session_id = str(getattr(session, "id", "") or "")
        if not session_id:
            return False
        if session_id in self.orchestrator._running:
            return False
        runtime = self._runtime()
        if runtime and getattr(runtime, "is_processing", False):
            current_id = None
            if getattr(runtime, "session_manager", None):
                current_id = runtime.session_manager.get_current_session_id()
            if str(current_id or "") == session_id:
                return False
        if self._session_has_user_visible_content(session):
            return False
        return self._session_age_seconds(session) >= EMPTY_SESSION_PRUNE_GRACE_SECONDS

    def prune_empty_sessions(self) -> List[str]:
        pruned: List[str] = []
        runtime = self._runtime()
        runtime_session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "")

        for summary in list(self.session_manager.list_sessions()):
            try:
                session = self._load_session(summary.id, set_current=False)
            except Exception:
                continue
            if not self._should_prune_empty_session(session):
                continue
            self.session_manager.delete_session(session.id)
            self.orchestrator._workers.pop(session.id, None)
            pruned.append(session.id)

        if runtime and runtime_session_id in pruned and not getattr(runtime, "is_processing", False):
            next_current_id = self.session_manager.get_current_session_id()
            if next_current_id:
                try:
                    runtime.load_session_by_id(next_current_id)
                except Exception:
                    next_current_id = None
            if not next_current_id:
                runtime.session = None
                runtime.chat_history = []
                runtime.task_history = []
                runtime.active_task_id = None
                runtime.task_board_armed_next_turn = False
                runtime.active_skills = []
                runtime.last_context_compaction = None

        return pruned

    def list_sessions(self) -> List[Session]:
        self.prune_empty_sessions()
        sessions = []
        for summary in self.session_manager.list_sessions():
            try:
                sessions.append(self._load_session(summary.id, set_current=False))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def list_session_summaries(self) -> List[SessionSummary]:
        self.prune_empty_sessions()
        return list(self.session_manager.list_sessions())

    def _artifact_store(self, session_id: str) -> ChatArtifactStore:
        return ChatArtifactStore(user_id=self.user_id, session_id=session_id)

    def _artifact_meta(self, session_id: str) -> Dict[str, Any]:
        return self._artifact_store(session_id).meta()

    def _session_sort_key(self, session: Optional[Session]) -> tuple[str, int, str]:
        if not session:
            return ("", 0, "")
        return (
            str(getattr(session, "updated_at", "") or ""),
            len(getattr(session, "chat_history", []) or []),
            str(getattr(session, "id", "") or ""),
        )

    def _prefer_authoritative_session(
        self,
        runtime_session: Optional[Session],
        disk_session: Optional[Session],
    ) -> Optional[Session]:
        if runtime_session is None:
            return disk_session
        if disk_session is None:
            return runtime_session
        return disk_session if self._session_sort_key(disk_session) >= self._session_sort_key(runtime_session) else runtime_session

    def get_current_session(self) -> Optional[Session]:
        self.prune_empty_sessions()
        current_id = self.session_manager.get_current_session_id()
        disk_session: Optional[Session] = None
        if current_id:
            try:
                disk_session = self._load_session(current_id, set_current=False)
            except Exception:
                disk_session = None

        runtime = self._runtime()
        if runtime and getattr(runtime, "session", None) is not None and getattr(runtime, "session_manager", None):
            runtime_current_id = runtime.session_manager.get_current_session_id()
            runtime_session_id = getattr(runtime.session, "id", None)
            if runtime_current_id and str(runtime_current_id) == str(runtime_session_id or ""):
                preferred = self._prefer_authoritative_session(runtime.session, disk_session)
                if preferred is disk_session and not getattr(runtime, "is_processing", False):
                    try:
                        runtime.load_session_by_id(str(disk_session.id))
                        return runtime.session
                    except Exception:
                        pass
                return preferred
        return disk_session

    def get_session(self, session_id: str) -> Session:
        disk_session = self._load_session(session_id, set_current=False)
        runtime = self._runtime()
        if runtime and getattr(runtime, "session", None) is not None and getattr(runtime, "session_manager", None):
            runtime_current_id = runtime.session_manager.get_current_session_id()
            runtime_session_id = getattr(runtime.session, "id", None)
            if runtime_current_id and str(runtime_current_id) == str(session_id) and str(runtime_session_id or "") == str(session_id):
                preferred = self._prefer_authoritative_session(runtime.session, disk_session)
                if preferred is disk_session and not getattr(runtime, "is_processing", False):
                    try:
                        runtime.load_session_by_id(str(disk_session.id))
                        return runtime.session
                    except Exception:
                        pass
                return preferred
        return disk_session

    def session_file_path(self, session_id: str) -> Path:
        return self.session_manager.sessions_dir / f"{session_id}.json"

    def session_index_path(self) -> Path:
        return self.session_manager.sessions_dir / "index.json"

    def _runtime(self) -> Optional["TelegramSession"]:
        if isinstance(user_sessions, dict):
            return user_sessions.get(self.user_id)
        module = _telegram_session_state_module()
        return getattr(module, "user_sessions", {}).get(self.user_id)

    def _reload_current_runtime_session_if_idle(self, session_id: str) -> None:
        runtime = self._runtime()
        if not runtime or getattr(runtime, "is_processing", False) or not getattr(runtime, "session_manager", None):
            return
        current_id = runtime.session_manager.get_current_session_id()
        if str(current_id or "") != str(session_id):
            return
        try:
            runtime.load_session_by_id(str(session_id), set_current=False)
        except Exception:
            pass

    def _assert_runtime_can_switch(
        self,
        runtime: Optional["TelegramSession"],
        *,
        target_session_id: Optional[str] = None,
    ) -> None:
        if not runtime or not runtime.is_processing:
            return

        current_id = runtime.session_manager.get_current_session_id() if runtime.session_manager else None
        if target_session_id and str(current_id or "") == str(target_session_id):
            return

        raise RuntimeError("Finish or stop the current task before switching sessions.")

    def _persist_runtime_before_switch(self, runtime: Optional["TelegramSession"]) -> None:
        if not runtime:
            return
        runtime.save_session()

    def _configured_default_workspace(self) -> Optional[Path]:
        configured = str(os.getenv("DEFAULT_WORKSPACE", "") or "").strip()
        if not configured:
            return None
        try:
            workspace = Path(configured).expanduser().resolve()
        except Exception:
            return None
        if not workspace.exists() or not workspace.is_dir():
            return None
        return workspace

    def _runtime_home_workspace(self) -> Optional[Path]:
        runtime_home = str(os.getenv("EMPLOAI_HOME", "") or "").strip()
        if not runtime_home:
            return None
        try:
            return Path(runtime_home).expanduser().resolve()
        except Exception:
            return None

    def _preferred_workspace(self, candidate: Optional[Path]) -> Path:
        configured = self._configured_default_workspace()
        runtime_home = self._runtime_home_workspace()
        if candidate is not None:
            try:
                resolved_candidate = Path(candidate).expanduser().resolve()
            except Exception:
                resolved_candidate = None
            if resolved_candidate is not None:
                if configured is not None and runtime_home is not None and resolved_candidate == runtime_home:
                    return configured
                return resolved_candidate
        if configured is not None and runtime_home is not None:
            try:
                bridge_workspace = self.workspace.expanduser().resolve()
            except Exception:
                bridge_workspace = self.workspace
            if bridge_workspace == runtime_home:
                return configured
        return self.workspace

    def _session_defaults(self, runtime: Optional["TelegramSession"]) -> Dict[str, Any]:
        provider_defaults = default_model_pair_for_enabled_providers(
            enabled_providers_from_env(os.environ, include_local_codex_auth=True)
        )
        if runtime:
            planner_model = getattr(runtime, "planner_model", None)
            return {
                "workspace": self._preferred_workspace(getattr(runtime, "workspace", self.workspace)),
                "model": getattr(runtime, "current_model", "claude-haiku-4.5"),
                "variant": getattr(runtime, "current_variant", "standard"),
                "agent_mode": "auto",
                "planner_model": planner_model,
                "enabled_tool_packs": normalize_enabled_tool_packs(
                    getattr(runtime, "enabled_tool_packs", []) or default_enabled_tool_packs()
                ) or default_enabled_tool_packs(),
                "security_permission_mode": getattr(getattr(runtime, "session", None), "security_permission_mode", "standard"),
                "telegram_bot_config_id": getattr(runtime, "telegram_bot_config_id", None),
                "headless_eligible": bool(getattr(runtime, "headless_eligible", False)),
            }

        current = self.get_current_session()
        if current:
            return {
                "workspace": self._preferred_workspace(Path(current.workspace) if current.workspace else None),
                "model": current.model,
                "variant": current.variant,
                "agent_mode": current.agent_mode or "auto",
                "planner_model": current.planner_model,
                "enabled_tool_packs": normalize_enabled_tool_packs(
                    getattr(current, "enabled_tool_packs", []) or default_enabled_tool_packs()
                ) or default_enabled_tool_packs(),
                "security_permission_mode": getattr(current, "security_permission_mode", "standard"),
                "telegram_bot_config_id": getattr(current, "telegram_bot_config_id", None),
                "headless_eligible": bool(getattr(current, "headless_eligible", False)),
            }

        return {
            "workspace": self._preferred_workspace(None),
            "model": provider_defaults.model,
            "variant": "standard",
            "agent_mode": "auto",
            "planner_model": None,
            "enabled_tool_packs": default_enabled_tool_packs(),
            "security_permission_mode": "standard",
            "telegram_bot_config_id": self.orchestrator._default_bot_config_id(),
            "headless_eligible": False,
        }

    def _workspace_key(self, workspace: Path | str | None) -> str:
        if workspace is None:
            return ""
        try:
            return str(Path(workspace).expanduser().resolve()).casefold()
        except Exception:
            return str(workspace or "").strip().casefold()

    def _permission_mode_for_workspace(self, workspace: Path) -> Optional[str]:
        target_key = self._workspace_key(workspace)
        if not target_key:
            return None
        try:
            summaries = self.session_manager.list_sessions()
        except Exception:
            return None
        for summary in summaries:
            if self._workspace_key(getattr(summary, "workspace", "")) != target_key:
                continue
            permission_mode = str(getattr(summary, "security_permission_mode", "") or "").strip()
            if permission_mode:
                return normalize_permission_mode(permission_mode)
        return None

    def create_session(
        self,
        name: Optional[str] = None,
        workspace: Optional[Path] = None,
        *,
        telegram_bot_config_id: Optional[str] = None,
        enabled_tool_packs: Optional[List[str]] = None,
        security_permission_mode: Optional[str] = None,
        headless_eligible: bool = False,
        workspace_id: Optional[str] = None,
        workspace_binding_status: Optional[str] = None,
        fleet_identity_id: Optional[str] = None,
        fleet_identity_role: Optional[str] = None,
        fleet_worker_id: Optional[str] = None,
        activate: bool = True,
    ) -> Session:
        runtime = self._runtime()
        if activate:
            self._assert_runtime_can_switch(runtime)
            self._persist_runtime_before_switch(runtime)

        defaults = self._session_defaults(runtime)
        target_workspace = Path(workspace).expanduser().resolve() if workspace else defaults["workspace"]
        inherited_permission_mode = (
            normalize_permission_mode(security_permission_mode)
            if security_permission_mode is not None
            else self._permission_mode_for_workspace(target_workspace) or normalize_permission_mode(defaults["security_permission_mode"])
        )
        create_kwargs = {
            "name": name,
            "workspace": target_workspace,
            "model": defaults["model"],
            "variant": defaults["variant"],
            "agent_mode": defaults["agent_mode"],
            "planner_model": defaults["planner_model"],
            "enabled_tool_packs": normalize_enabled_tool_packs(enabled_tool_packs or defaults["enabled_tool_packs"]) or default_enabled_tool_packs(),
            "security_permission_mode": inherited_permission_mode,
            "telegram_bot_config_id": telegram_bot_config_id if telegram_bot_config_id is not None else defaults["telegram_bot_config_id"],
            "headless_eligible": bool(headless_eligible if headless_eligible is not None else defaults["headless_eligible"]),
        }
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id
        if workspace_binding_status is not None:
            create_kwargs["workspace_binding_status"] = workspace_binding_status
        session = self.session_manager.create_session(**create_kwargs)
        try:
            session.account_user_id = int(self.user_id)
        except Exception:
            session.account_user_id = None
        session.fleet_identity_id = str(fleet_identity_id or "").strip() or None
        session.fleet_identity_role = str(fleet_identity_role or "").strip() or None
        session.fleet_worker_id = str(fleet_worker_id or "").strip() or None
        if session.account_user_id is not None or session.fleet_identity_id or session.fleet_identity_role or session.fleet_worker_id:
            self.session_manager.save_session(session)

        if activate:
            self.session_manager.set_current_session(session.id)
            if runtime and not getattr(runtime, "is_processing", False):
                runtime.load_session_by_id(session.id)
                return runtime.session
        return self._load_session(session.id, set_current=False)

    def activate_session(self, session_id: str) -> Session:
        session = self._load_session(session_id, set_current=False)
        runtime = self._runtime()
        self._assert_runtime_can_switch(runtime, target_session_id=session_id)
        self._persist_runtime_before_switch(runtime)
        self.session_manager.set_current_session(session_id)
        if runtime and not getattr(runtime, "is_processing", False):
            runtime.load_session_by_id(session_id)
            return runtime.session
        return session

    def delete_session(self, session_id: str) -> Dict[str, Optional[str]]:
        session = self._load_session(session_id, set_current=False)
        runtime = self._runtime()
        current_id = self.session_manager.get_current_session_id()
        if session_id in self.orchestrator._running:
            raise RuntimeError("Finish or stop the current task before deleting this chat.")

        if runtime and runtime.is_processing and str(current_id or "") == str(session_id):
            raise RuntimeError("Finish or stop the current task before deleting this chat.")

        if runtime and str(current_id or "") == str(session_id):
            self._persist_runtime_before_switch(runtime)

        self.session_manager.delete_session(session.id)
        self.orchestrator._workers.pop(session.id, None)

        next_current_id = self.session_manager.get_current_session_id()
        if next_current_id == session.id:
            next_current_id = None

        if next_current_id:
            try:
                self._load_session(next_current_id, set_current=False)
            except Exception:
                next_current_id = None

        if next_current_id is None:
            remaining_sessions = self.list_sessions()
            next_current_id = remaining_sessions[0].id if remaining_sessions else None

        if next_current_id:
            self.session_manager.set_current_session(next_current_id)
            if runtime:
                runtime.load_session_by_id(next_current_id)
        else:
            self.session_manager.set_current_session(None)
            if runtime:
                runtime.session = None
                runtime.chat_history = []
                runtime.task_history = []
                runtime.active_task_id = None
                runtime.task_board_armed_next_turn = False
                runtime.active_skills = []
                runtime.last_context_compaction = None

        return {
            "deleted_session_id": session.id,
            "current_session_id": next_current_id,
        }

    def rename_session(self, session_id: str, name: str) -> Session:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Chat name is required")
        if len(clean_name) > 160:
            clean_name = clean_name[:160].rstrip()
        session = self._load_session(session_id, set_current=False)
        session.name = clean_name
        self.session_manager.save_session(session)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def get_or_create_runtime_session(self) -> "TelegramSession":
        return get_session(
            self.user_id,
            workspace=self.workspace,
            create_new_session=False,
        )

    def load_runtime_session(self, session_id: Optional[str] = None) -> "TelegramSession":
        runtime = self.get_or_create_runtime_session()
        target_session_id = session_id or self.session_manager.get_current_session_id()
        if target_session_id:
            runtime.load_session_by_id(target_session_id)
        from shared.task_board import recover_stale_task_board

        if recover_stale_task_board(runtime):
            runtime.save_session()
        return runtime

    def append_app_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        source_format: str = "app_text",
        display_label: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Session:
        session = self._load_session(session_id, set_current=False)
        payload: Dict[str, Any] = {
            "role": role,
            "content": content,
            "channel": "app",
            "source_format": source_format,
        }
        if display_label:
            payload["display_label"] = display_label
        if extra:
            payload.update(extra)
        session.chat_history.append(payload)
        self.session_manager.save_session(session)
        return session

    def build_message_view(self, message: Dict[str, Any]) -> Dict[str, Any]:
        channel = message.get("channel")
        source_format = message.get("source_format")
        display_label = message.get("display_label")
        if not display_label:
            if channel == "app" and source_format == "app_voice_transcript":
                display_label = "App Voice"
            elif channel == "app":
                display_label = "App"
            elif channel == "telegram":
                display_label = "Telegram"

        return {
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp"),
            "channel": channel,
            "source_format": source_format,
            "display_label": display_label,
            "run_mode": message.get("run_mode"),
            "raw": message,
        }

    def build_timeline_event_view(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(event.get("id", "")),
            "kind": str(event.get("kind", "note")),
            "title": str(event.get("title", "Event")),
            "content": str(event.get("content", "")),
            "tone": str(event.get("tone", "neutral")),
            "timestamp": event.get("timestamp"),
            "channel": event.get("channel"),
            "source_format": event.get("source_format"),
            "metadata": dict(event.get("metadata") or {}),
        }

    def summarize_session(self, session: Session) -> Dict[str, Any]:
        latest_preview = None
        origin_channels = []
        for item in session.chat_history:
            if bool(item.get("hidden_from_app")):
                continue
            ch = item.get("channel")
            if ch and ch not in origin_channels:
                origin_channels.append(ch)
        visible_history = [item for item in session.chat_history if not bool(item.get("hidden_from_app"))]
        if visible_history:
            latest_preview = str(visible_history[-1].get("content", ""))[:140]
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "model": session.model,
            "variant": session.variant,
            "message_count": len(session.chat_history),
            "workspace": session.workspace,
            "latest_preview": latest_preview,
            "origin_channels": origin_channels,
            "security_permission_mode": getattr(session, "security_permission_mode", "standard"),
            "workspace_id": getattr(session, "workspace_id", None),
            "workspace_binding_status": getattr(session, "workspace_binding_status", None),
            "fleet_identity_id": getattr(session, "fleet_identity_id", None),
            "fleet_identity_role": getattr(session, "fleet_identity_role", None),
            "fleet_worker_id": getattr(session, "fleet_worker_id", None),
            "account_user_id": getattr(session, "account_user_id", None),
            "account_email": getattr(session, "account_email", None),
            "plan_mode": getattr(session, "plan_mode", None),
            "active_goal": getattr(session, "active_goal", None),
            **self._artifact_meta(session.id),
            **self.orchestrator._session_summary_live_fields(session),
        }

    def summarize_session_summary(self, session: SessionSummary) -> Dict[str, Any]:
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "model": session.model,
            "variant": getattr(session, "variant", "standard"),
            "message_count": int(getattr(session, "message_count", 0) or 0),
            "workspace": session.workspace,
            "latest_preview": getattr(session, "latest_preview", None),
            "origin_channels": list(getattr(session, "origin_channels", []) or []),
            "security_permission_mode": getattr(session, "security_permission_mode", "standard"),
            "workspace_id": getattr(session, "workspace_id", None),
            "workspace_binding_status": getattr(session, "workspace_binding_status", None),
            "fleet_identity_id": getattr(session, "fleet_identity_id", None),
            "fleet_identity_role": getattr(session, "fleet_identity_role", None),
            "fleet_worker_id": getattr(session, "fleet_worker_id", None),
            "account_user_id": getattr(session, "account_user_id", None),
            "account_email": getattr(session, "account_email", None),
            "plan_mode": getattr(session, "plan_mode", None),
            "active_goal": getattr(session, "active_goal", None),
            **self._artifact_meta(session.id),
            **self.orchestrator._session_summary_live_fields(session),
        }

    def detailed_session_view(self, session: Session) -> Dict[str, Any]:
        from shared.task_board import recover_stale_task_board

        if recover_stale_task_board(session):
            self.session_manager.save_session(session)
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "model": session.model,
            "variant": session.variant,
            "planner_model": session.planner_model,
            "agent_mode": session.agent_mode,
            "security_permission_mode": getattr(session, "security_permission_mode", "standard"),
            "workspace": session.workspace,
            "workspace_id": getattr(session, "workspace_id", None),
            "workspace_binding_status": getattr(session, "workspace_binding_status", None),
            "messages": [
                self.build_message_view(m)
                for m in session.chat_history
                if not bool(m.get("hidden_from_app"))
            ],
            "timeline_events": [
                self.build_timeline_event_view(item)
                for item in session.event_timeline
                if is_user_visible_timeline_event(item)
            ],
            "task_board": self.task_board_view(session),
            "completed_task_boards": self.completed_task_boards_view(session),
            "task_board_armed_next_turn": bool(getattr(session, "task_board_armed_next_turn", False)),
            "fleet_identity_id": getattr(session, "fleet_identity_id", None),
            "fleet_identity_role": getattr(session, "fleet_identity_role", None),
            "fleet_worker_id": getattr(session, "fleet_worker_id", None),
            "account_user_id": getattr(session, "account_user_id", None),
            "account_email": getattr(session, "account_email", None),
            "plan_mode": getattr(session, "plan_mode", None),
            "active_goal": getattr(session, "active_goal", None),
            **self._artifact_meta(session.id),
            **self.orchestrator._session_summary_live_fields(session),
        }

    def update_session_mode_state(self, session_id: str, action: str, reason: Optional[str] = None) -> Session:
        runtime = self._runtime()
        current_id = None
        if runtime and getattr(runtime, "session_manager", None):
            current_id = runtime.session_manager.get_current_session_id()
        session = runtime.session if runtime and str(current_id or "") == str(session_id) else self._load_session(session_id, set_current=False)

        normalized = str(action or "").strip().lower()
        timestamp = datetime.utcnow().isoformat() + "Z"
        if normalized in {"exit_plan", "dismiss_plan"}:
            state = getattr(session, "plan_mode", None)
            if isinstance(state, dict):
                state = dict(state)
                state["status"] = "dismissed" if normalized == "dismiss_plan" else "exited"
                state["updated_at"] = timestamp
                if reason:
                    state["exit_reason"] = str(reason)
            session.plan_mode = None
        elif normalized == "clear_goal":
            goal = getattr(session, "active_goal", None)
            if isinstance(goal, dict):
                goal = dict(goal)
                goal["status"] = "cleared"
                goal["updated_at"] = timestamp
                goal["cleared_at"] = timestamp
                if reason:
                    goal["summary"] = str(reason)
            session.active_goal = None
        else:
            raise ValueError(f"Unsupported mode action: {action}")

        if runtime and session is runtime.session:
            runtime.save_session()
        else:
            self.session_manager.save_session(session)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def append_timeline_event(
        self,
        *,
        session_id: str,
        kind: str,
        title: str,
        content: str,
        tone: str = "neutral",
        channel: Optional[str] = None,
        source_format: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime = self._runtime()
        current_id = None
        if runtime and getattr(runtime, "session_manager", None):
            current_id = runtime.session_manager.get_current_session_id()

        if runtime and current_id and str(current_id) == str(session_id):
            target_session = runtime.session
            event = append_timeline_event(
                target_session,
                event=create_timeline_event(
                    kind=kind,
                    title=title,
                    content=content,
                    tone=tone,
                    channel=channel,
                    source_format=source_format,
                    metadata=metadata,
                ),
            )
            runtime.save_session()
            return self.build_timeline_event_view(event)

        session = self._load_session(session_id, set_current=False)
        event = append_timeline_event(
            session,
            event=create_timeline_event(
                kind=kind,
                title=title,
                content=content,
                tone=tone,
                channel=channel,
                source_format=source_format,
                metadata=metadata,
            ),
        )
        self.session_manager.save_session(session)
        return self.build_timeline_event_view(event)

    def task_board_view(self, session: Session) -> Optional[Dict[str, Any]]:
        from shared.task_board import get_display_task_board, task_board_view

        return task_board_view(get_display_task_board(session))

    def completed_task_boards_view(self, session: Session) -> List[Dict[str, Any]]:
        from shared.task_board import completed_task_board_views

        return completed_task_board_views(session)

    def build_session_sync_payload(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        current = self.get_current_session()
        return {
            "session": self.detailed_session_view(session),
            "sessions": [self.summarize_session_summary(item) for item in self.list_session_summaries()],
            "current_session_id": current.id if current else None,
            "runtime": self.orchestrator.runtime_status_view(),
        }

    def list_session_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        store = self._artifact_store(session_id)
        return [store.build_summary_view(record) for record in store.list_records(descending=True)]

    def get_session_artifact(self, session_id: str, artifact_id: str) -> Dict[str, Any]:
        store = self._artifact_store(session_id)
        detail = store.build_detail_view(artifact_id)
        if detail is None:
            raise KeyError(artifact_id)
        return detail

    def session_artifact_download_path(self, session_id: str, artifact_id: str) -> Path:
        path = self._artifact_store(session_id).payload_absolute_path(artifact_id)
        if path is None or not path.exists():
            raise KeyError(artifact_id)
        return path

    def list_telegram_bot_configs(self) -> List[Dict[str, Any]]:
        return self.orchestrator.telegram_bots.list_public_configs()

    def create_telegram_bot_config(self, *, label: str, bot_token: str) -> Dict[str, Any]:
        created = self.orchestrator.telegram_bots.create_config(label=label, bot_token=bot_token)
        for item in self.orchestrator.telegram_bots.list_public_configs():
            if item["id"] == created["id"]:
                return item
        public = dict(created)
        public["bot_token"] = ""
        return public

    def update_telegram_bot_config(
        self,
        bot_config_id: str,
        *,
        label: Optional[str] = None,
        bot_token: Optional[str] = None,
        is_default: Optional[bool] = None,
    ) -> Dict[str, Any]:
        self.orchestrator.telegram_bots.update_config(
            bot_config_id,
            label=label,
            bot_token=bot_token,
            is_default=is_default,
        )
        for item in self.orchestrator.telegram_bots.list_public_configs():
            if item["id"] == bot_config_id:
                return item
        raise KeyError(bot_config_id)

    def delete_telegram_bot_config(self, bot_config_id: str) -> Dict[str, Any]:
        self.orchestrator.telegram_bots.delete_config(bot_config_id)
        for session in self.list_sessions():
            if getattr(session, "telegram_bot_config_id", None) == bot_config_id:
                session.telegram_bot_config_id = self.orchestrator._default_bot_config_id()
                self.session_manager.save_session(session)
        return {"ok": True, "id": bot_config_id}

    def update_session_tool_packs(self, session_id: str, enabled_tool_packs: List[str]) -> Session:
        session = self.orchestrator.update_session_tool_packs(session_id, enabled_tool_packs)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def update_session_telegram_bot_config(self, session_id: str, telegram_bot_config_id: Optional[str]) -> Session:
        session = self.orchestrator.update_session_bot_assignment(session_id, telegram_bot_config_id)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def restore_telegram_bot_parenting(self, assignments: Dict[str, str]) -> Dict[str, Any]:
        valid_bot_ids = {
            str(item.get("id") or "").strip()
            for item in self.orchestrator.telegram_bots.list_configs()
            if str(item.get("id") or "").strip()
        }
        if not valid_bot_ids:
            return {"updated": 0, "skipped": len(assignments or {})}

        updated = 0
        skipped = 0
        for session in self.list_sessions():
            session_id = str(getattr(session, "id", "") or "").strip()
            if not session_id:
                continue
            bot_config_id = str(dict(assignments or {}).get(session_id) or "").strip()
            if not bot_config_id or bot_config_id not in valid_bot_ids:
                skipped += 1
                continue
            if str(getattr(session, "telegram_bot_config_id", "") or "") == bot_config_id:
                continue
            session.telegram_bot_config_id = bot_config_id
            self.session_manager.save_session(session)
            self._reload_current_runtime_session_if_idle(session_id)
            updated += 1
        return {"updated": updated, "skipped": skipped}

    def update_session_headless_eligible(self, session_id: str, headless_eligible: bool) -> Session:
        session = self.orchestrator.update_session_headless_eligible(session_id, headless_eligible)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def update_session_security_permission_mode(self, session_id: str, security_permission_mode: str) -> Session:
        session = self.orchestrator.update_session_security_permission_mode(session_id, security_permission_mode)
        self._reload_current_runtime_session_if_idle(session_id)
        return session

    def set_task_board_armed_next_turn(self, session_id: str, armed: bool) -> Dict[str, Any]:
        runtime = self._runtime()
        current_id = runtime.session_manager.get_current_session_id() if runtime and runtime.session_manager else None

        if runtime and str(current_id or "") == str(session_id):
            runtime.task_board_armed_next_turn = bool(armed)
            runtime.save_session()
            return {
                "session_id": session_id,
                "task_board_armed_next_turn": bool(runtime.task_board_armed_next_turn),
            }

        session = self._load_session(session_id, set_current=False)
        session.task_board_armed_next_turn = bool(armed)
        self.session_manager.save_session(session)
        return {
            "session_id": session_id,
            "task_board_armed_next_turn": bool(session.task_board_armed_next_turn),
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        scheduler = _scheduler()
        jobs = []
        for job in scheduler.jobs.values():
            owner_user_id = getattr(job, "owner_user_id", None)
            if owner_user_id not in (None, self.user_id):
                continue
            jobs.append({
                "id": job.id,
                "name": job.name,
                "prompt": job.prompt,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "run_count": job.run_count,
                "error_count": job.error_count,
                "next_run_at": datetime.fromtimestamp(job.next_run).isoformat() if job.next_run else None,
                "last_run_at": datetime.fromtimestamp(job.last_run).isoformat() if job.last_run else None,
                "interval_seconds": job.interval_seconds,
                "due": bool(job.next_run and time.time() >= job.next_run),
                "owner_user_id": owner_user_id,
                "origin_session_id": getattr(job, "origin_session_id", None),
                "origin_telegram_bot_config_id": getattr(job, "origin_telegram_bot_config_id", None),
                "origin_workspace": getattr(job, "origin_workspace", None),
                "origin_model": getattr(job, "origin_model", None),
                "origin_enabled_tool_packs": list(getattr(job, "origin_enabled_tool_packs", []) or []),
                "one_time": bool(getattr(job, "one_time", False)),
            })
        jobs.sort(key=lambda item: (item.get("next_run_at") is None, item.get("next_run_at") or ""))
        return jobs

    def get_job(self, job_id: str) -> Dict[str, Any]:
        for job in self.list_jobs():
            if job.get("id") == job_id:
                return job
        raise KeyError(job_id)

    def list_cron_feed(self) -> List[Dict[str, Any]]:
        return self.cron_feed_store.list_items()

    def attach_pending_file(
        self,
        *,
        runtime: TelegramSession,
        filename: str,
        content_type: Optional[str],
        data: bytes,
        source_format: str = "app_file_upload",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "filename": filename,
            "mime_type": content_type or "application/octet-stream",
            "size": len(data),
            "source": "app_upload",
            "channel": "app",
            "source_format": source_format,
            "uploaded_at": datetime.now().isoformat(),
        }
        if (content_type or "").startswith("image/"):
            import base64
            payload["image_base64"] = base64.b64encode(data).decode("utf-8")
        else:
            try:
                payload["text"] = data.decode("utf-8")
            except UnicodeDecodeError:
                payload["text"] = f"[binary file omitted: {filename}]"
        runtime.pending_files.append(payload)
        runtime.save_session()
        session_id = str(
            getattr(getattr(runtime, "session_manager", None), "get_current_session_id", lambda: None)()
            or getattr(getattr(runtime, "session", None), "id", "")
            or ""
        ).strip()
        if session_id:
            store = self._artifact_store(session_id)
            metadata = {
                "filename": filename,
                "mime_type": payload["mime_type"],
                "size": payload["size"],
                "source_format": source_format,
                "uploaded_at": payload["uploaded_at"],
            }
            if (content_type or "").startswith("image/"):
                store.create_bytes_artifact(
                    artifact_kind="upload",
                    title=f"Upload: {filename}",
                    data=data,
                    mime_type=content_type or "application/octet-stream",
                    source_kind="upload",
                    payload_file_name=filename,
                    summary_text=f"Uploaded image: {filename}",
                    preview_text=f"Uploaded image: {filename}",
                    search_text=json.dumps(metadata, ensure_ascii=False, default=str),
                    workspace=str(getattr(runtime, "workspace", "") or ""),
                    metadata=metadata,
                )
            else:
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = f"[binary upload omitted from inline preview: {filename}]"
                store.create_text_artifact(
                    artifact_kind="upload",
                    title=f"Upload: {filename}",
                    text=text,
                    mime_type=content_type or "application/octet-stream",
                    source_kind="upload",
                    payload_file_name=filename,
                    summary_text=text,
                    preview_text=text[:2400],
                    search_text=json.dumps(metadata, ensure_ascii=False, default=str) + "\n" + text,
                    workspace=str(getattr(runtime, "workspace", "") or ""),
                    metadata=metadata,
                )
        return payload
