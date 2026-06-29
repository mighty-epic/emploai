from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from mobile_app.backend.session_bridge import AppSessionBridge
from single_agent.cron_scheduler import get_scheduler
from shared.artifact_store import ChatArtifactStore
from shared.proactive_runtime import append_event
from shared.runtime_paths import default_workspace_root

if TYPE_CHECKING:
    from telegram_bot.telegram_session_state import TelegramSession

_CRON_RUNTIME_SESSIONS: dict[int, TelegramSession] = {}


def _append_scheduled_history(session: object, *, content: str, job_id: str, job_name: str, role: str = "assistant") -> None:
    history = getattr(session, "chat_history", None)
    if not isinstance(history, list):
        return
    history.append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "scheduled_job": True,
            "scheduled_job_id": job_id,
            "scheduled_job_name": job_name,
        }
    )
    save = getattr(session, "save_session", None)
    if callable(save):
        save()


def _telegram_session_cls():
    from telegram_bot.telegram_session_state import TelegramSession

    return TelegramSession


def _run_cron_job_via_unified_flow():
    from telegram_bot.cron_runner import run_cron_job_via_unified_flow

    return run_cron_job_via_unified_flow


def _workspace() -> Path:
    configured_workspace = default_workspace_root()
    if configured_workspace is not None:
        return configured_workspace
    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
    if runtime_home:
        return Path(runtime_home).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def get_cron_runtime_session(user_id: int = 0) -> TelegramSession:
    normalized_user_id = int(user_id or 0)
    session = _CRON_RUNTIME_SESSIONS.get(normalized_user_id)
    if session is None:
        session = _telegram_session_cls()(
            user_id=normalized_user_id,
            workspace=_workspace(),
            create_new_session_on_init=False,
        )
        _CRON_RUNTIME_SESSIONS[normalized_user_id] = session
    return session


async def cron_announcement_callback(message: str) -> None:
    append_event(
        user_id=0,
        kind="announcement",
        content=message,
        status="running",
        event_type="automation_announcement",
        event_source="schedule",
        importance="normal",
    )


async def cron_spawn_callback(job_id: str, prompt: str) -> None:
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    owner_user_id = int(job.owner_user_id) if job and job.owner_user_id is not None else 0
    bridge = AppSessionBridge(user_id=owner_user_id, workspace=_workspace())
    target_session_id = str(getattr(job, "origin_session_id", "") or "").strip()
    if target_session_id:
        session = bridge.orchestrator.get_worker(target_session_id)
    else:
        session = get_cron_runtime_session(owner_user_id)
        target_session_id = str(getattr(getattr(session, "session", None), "id", "") or "").strip()
    target_session = bridge.get_session(target_session_id) if target_session_id else None
    bot_config_id = str(getattr(job, "origin_telegram_bot_config_id", "") or "").strip() or getattr(target_session, "telegram_bot_config_id", None)
    bot_config = bridge.orchestrator.telegram_bots.get_config(bot_config_id) if bot_config_id else None
    bot_label = str(bot_config.get("label") or "").strip() if bot_config else None

    if job and job.owner_user_id:
        _append_scheduled_history(
            session,
            content=f"Scheduled job running: {job.name}",
            job_id=job_id,
            job_name=job.name,
        )
        append_event(
            user_id=owner_user_id,
            kind="announcement",
            content=f"Scheduled job running: {job.name}",
            session_id=target_session_id or None,
            session_name=getattr(target_session, "name", None),
            automation_id=job_id,
            automation_name=job.name,
            status="running",
            event_type="automation_started",
            event_source="schedule",
            importance="normal",
            metadata={
                "automation_id": job_id,
                "prompt": prompt,
                "telegram_bot_config_id": bot_config_id or None,
                "telegram_bot_label": bot_label or None,
            },
        )
        if target_session_id:
            ChatArtifactStore(user_id=owner_user_id, session_id=target_session_id).create_text_artifact(
                artifact_kind="cron_output",
                title=f"Cron announcement: {job.name}",
                text=f"Scheduled job running: {job.name}",
                source_kind="cron",
                payload_file_name=f"cron-announcement-{job_id}.txt",
                summary_text=f"Scheduled job running: {job.name}",
                preview_text=f"Scheduled job running: {job.name}",
                search_text=f"{job.name}\n{prompt}",
                source_command=job.name,
                file_path=None,
                workspace=getattr(target_session, "workspace", None),
                metadata={
                    "job_id": job_id,
                    "job_name": job.name,
                    "prompt": prompt,
                    "status": "running",
                },
            )

    history_count_before_result = len(getattr(session, "chat_history", []) or [])
    result = await _run_cron_job_via_unified_flow()(
        session,
        prompt,
        scheduled_job_id=job_id,
    )

    if job and job.owner_user_id:
        if len(getattr(session, "chat_history", []) or []) <= history_count_before_result:
            _append_scheduled_history(
                session,
                content=result,
                job_id=job_id,
                job_name=job.name if job else "Scheduled job",
            )
        append_event(
            user_id=owner_user_id,
            kind="result",
            content=result,
            session_id=target_session_id or None,
            session_name=getattr(target_session, "name", None),
            automation_id=job_id,
            automation_name=job.name if job else None,
            status="completed",
            event_type="automation_completed",
            event_source="schedule",
            importance="important",
            metadata={
                "automation_id": job_id,
                "telegram_bot_config_id": bot_config_id or None,
                "telegram_bot_label": bot_label or None,
            },
        )
        if target_session_id:
            ChatArtifactStore(user_id=owner_user_id, session_id=target_session_id).create_text_artifact(
                artifact_kind="cron_output",
                title=f"Cron result: {job.name}",
                text=result,
                source_kind="cron",
                payload_file_name=f"cron-result-{job_id}.txt",
                summary_text=result,
                preview_text=result[:2400],
                search_text=f"{job.name}\n{prompt}\n{result}",
                source_command=job.name,
                workspace=getattr(target_session, "workspace", None),
                metadata={
                    "job_id": job_id,
                    "job_name": job.name,
                    "prompt": prompt,
                    "status": "completed",
                },
            )


async def ensure_global_cron_scheduler_started() -> None:
    scheduler = get_scheduler(
        spawn_callback=cron_spawn_callback,
        announcement_callback=cron_announcement_callback,
    )
    await scheduler.start()
