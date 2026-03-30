from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

from cli.models.session import Session
from cli.session_manager import SessionManager
from single_agent.cron_scheduler import get_scheduler
from telegram_bot.telegram_session_state import TelegramSession


@dataclass
class AppRuntimeContext:
    user_id: int
    workspace: Path
    session_manager: SessionManager


_APP_SESSIONS: Dict[int, TelegramSession] = {}


class AppSessionBridge:
    """Additive bridge for the mobile app channel.

    This intentionally reuses the existing session store so app and Telegram can
    operate over shared session history. It does not change Telegram behavior.
    """

    def __init__(self, *, user_id: int, workspace: Path):
        self.user_id = user_id
        self.workspace = workspace
        self.base_path = Path.home() / ".agentshell" / f"user_{self.user_id}"
        self.session_manager = SessionManager(base_path=self.base_path)

    def list_sessions(self) -> List[Session]:
        sessions = []
        for summary in self.session_manager.list_sessions():
            try:
                sessions.append(self.session_manager.load_session(summary.id))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_current_session(self) -> Optional[Session]:
        current_id = self.session_manager.get_current_session_id()
        if not current_id:
            return None
        try:
            return self.session_manager.load_session(current_id)
        except Exception:
            return None

    def get_session(self, session_id: str) -> Session:
        return self.session_manager.load_session(session_id)

    def create_session(self, name: Optional[str] = None) -> Session:
        return self.session_manager.create_session(
            name=name,
            workspace=self.workspace,
            agent_mode="auto",
        )

    def get_or_create_runtime_session(self) -> TelegramSession:
        runtime = _APP_SESSIONS.get(self.user_id)
        if runtime is None:
            runtime = TelegramSession(user_id=self.user_id, workspace=self.workspace)
            _APP_SESSIONS[self.user_id] = runtime
        return runtime

    def load_runtime_session(self, session_id: Optional[str] = None) -> TelegramSession:
        runtime = self.get_or_create_runtime_session()
        if session_id:
            runtime.load_session_by_id(session_id)
        else:
            current_id = self.session_manager.get_current_session_id()
            if current_id:
                runtime.load_session_by_id(current_id)
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
        session = self.session_manager.load_session(session_id)
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
            "agent_mode": session.agent_mode,
            "workspace": session.workspace,
            "messages": [self.build_message_view(m) for m in session.chat_history],
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        scheduler = get_scheduler()
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
