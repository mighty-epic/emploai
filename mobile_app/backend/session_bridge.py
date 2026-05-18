from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import time

from cli.models.session import Session
from cli.session_manager import SessionManager
from shared.session_timeline import append_timeline_event, create_timeline_event

if TYPE_CHECKING:
    from telegram_bot.telegram_session_state import TelegramSession


def _telegram_session_state_module():
    from telegram_bot import telegram_session_state as module

    return module


def _scheduler():
    from single_agent.cron_scheduler import get_scheduler

    return get_scheduler()


class AppSessionBridge:
    """Additive bridge for the mobile app channel.

    This reuses the Telegram runtime cache so app and Telegram operate over the
    same live session object instead of parallel in-memory runtimes.
    """

    def __init__(self, *, user_id: int, workspace: Path):
        self.user_id = user_id
        self.workspace = workspace
        self.base_path = Path.home() / ".agentshell" / f"user_{self.user_id}"
        self.session_manager = SessionManager(base_path=self.base_path)

    def _load_session(self, session_id: str, *, set_current: bool) -> Session:
        try:
            return self.session_manager.load_session(session_id, set_current=set_current)
        except TypeError:
            return self.session_manager.load_session(session_id)

    def list_sessions(self) -> List[Session]:
        sessions = []
        for summary in self.session_manager.list_sessions():
            try:
                sessions.append(self._load_session(summary.id, set_current=False))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_current_session(self) -> Optional[Session]:
        current_id = self.session_manager.get_current_session_id()
        if not current_id:
            return None
        try:
            return self._load_session(current_id, set_current=False)
        except Exception:
            return None

    def get_session(self, session_id: str) -> Session:
        return self._load_session(session_id, set_current=False)

    def session_file_path(self, session_id: str) -> Path:
        return self.session_manager.sessions_dir / f"{session_id}.json"

    def session_index_path(self) -> Path:
        return self.session_manager.sessions_dir / "index.json"

    def _runtime(self) -> Optional["TelegramSession"]:
        module = _telegram_session_state_module()
        return getattr(module, "user_sessions", {}).get(self.user_id)

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

    def _session_defaults(self, runtime: Optional["TelegramSession"]) -> Dict[str, Any]:
        if runtime:
            planner_model = getattr(runtime, "planner_model", None)
            if planner_model is None:
                planner_model = getattr(runtime, "default_planner_model", None)
            return {
                "workspace": getattr(runtime, "workspace", self.workspace),
                "model": getattr(runtime, "current_model", "claude-haiku-4.5"),
                "variant": getattr(runtime, "current_variant", "standard"),
                "agent_mode": "auto",
                "planner_model": planner_model,
            }

        current = self.get_current_session()
        if current:
            return {
                "workspace": Path(current.workspace) if current.workspace else self.workspace,
                "model": current.model,
                "variant": current.variant,
                "agent_mode": current.agent_mode or "auto",
                "planner_model": current.planner_model,
            }

        return {
            "workspace": self.workspace,
            "model": "claude-haiku-4.5",
            "variant": "standard",
            "agent_mode": "auto",
            "planner_model": None,
        }

    def create_session(self, name: Optional[str] = None, workspace: Optional[Path] = None) -> Session:
        runtime = self._runtime()
        self._assert_runtime_can_switch(runtime)
        self._persist_runtime_before_switch(runtime)

        defaults = self._session_defaults(runtime)
        target_workspace = Path(workspace).expanduser().resolve() if workspace else defaults["workspace"]
        session = self.session_manager.create_session(
            name=name,
            workspace=target_workspace,
            model=defaults["model"],
            variant=defaults["variant"],
            agent_mode=defaults["agent_mode"],
            planner_model=defaults["planner_model"],
        )

        self.session_manager.set_current_session(session.id)
        if runtime:
            runtime.load_session_by_id(session.id)
            return runtime.session
        return self._load_session(session.id, set_current=False)

    def activate_session(self, session_id: str) -> Session:
        session = self._load_session(session_id, set_current=False)
        runtime = self._runtime()
        self._assert_runtime_can_switch(runtime, target_session_id=session_id)
        self._persist_runtime_before_switch(runtime)
        self.session_manager.set_current_session(session_id)
        if runtime:
            runtime.load_session_by_id(session_id)
            return runtime.session
        return session

    def get_or_create_runtime_session(self) -> "TelegramSession":
        module = _telegram_session_state_module()
        return module.get_session(
            self.user_id,
            workspace=self.workspace,
            create_new_session=False,
        )

    def load_runtime_session(self, session_id: Optional[str] = None) -> "TelegramSession":
        runtime = self.get_or_create_runtime_session()
        target_session_id = session_id or self.session_manager.get_current_session_id()
        if target_session_id:
            runtime.load_session_by_id(target_session_id)
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
            ch = item.get("channel")
            if ch and ch not in origin_channels:
                origin_channels.append(ch)
        if session.chat_history:
            latest_preview = str(session.chat_history[-1].get("content", ""))[:140]
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "model": session.model,
            "message_count": len(session.chat_history),
            "workspace": session.workspace,
            "latest_preview": latest_preview,
            "origin_channels": origin_channels,
        }

    def detailed_session_view(self, session: Session) -> Dict[str, Any]:
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "model": session.model,
            "variant": session.variant,
            "planner_model": session.planner_model,
            "agent_mode": session.agent_mode,
            "workspace": session.workspace,
            "messages": [self.build_message_view(m) for m in session.chat_history],
            "timeline_events": [self.build_timeline_event_view(item) for item in session.event_timeline],
            "task_board": self.task_board_view(session),
            "completed_task_boards": self.completed_task_boards_view(session),
        }

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
            "sessions": [self.summarize_session(item) for item in self.list_sessions()],
            "current_session_id": current.id if current else None,
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
            })
        jobs.sort(key=lambda item: (item.get("next_run_at") is None, item.get("next_run_at") or ""))
        return jobs

    def get_job(self, job_id: str) -> Dict[str, Any]:
        for job in self.list_jobs():
            if job.get("id") == job_id:
                return job
        raise KeyError(job_id)

    def list_cron_feed(self) -> List[Dict[str, Any]]:
        jobs_by_id = {job["id"]: job for job in self.list_jobs()}
        feed: List[Dict[str, Any]] = []

        for session in self.list_sessions():
            for index, message in enumerate(session.chat_history):
                if not message.get("scheduled_job"):
                    continue

                source_format = str(message.get("source_format") or "")
                if source_format not in {"scheduled_job_announcement", "scheduled_job_result"}:
                    continue

                job_id = message.get("scheduled_job_id")
                job_meta = jobs_by_id.get(str(job_id)) if job_id else None
                feed.append({
                    "id": f"{session.id}:{index}",
                    "timestamp": message.get("timestamp") or message.get("created_at") or session.updated_at,
                    "kind": "announcement" if source_format == "scheduled_job_announcement" else "result",
                    "content": str(message.get("content", "")),
                    "session_id": session.id,
                    "session_name": session.name,
                    "job_id": str(job_id) if job_id else None,
                    "job_name": (
                        str(message.get("scheduled_job_name"))
                        if message.get("scheduled_job_name")
                        else (job_meta.get("name") if job_meta else None)
                    ),
                })

        feed.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return feed

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
        return payload
