from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from single_agent.cron_scheduler import get_scheduler

if TYPE_CHECKING:
    from telegram_bot.telegram_session_state import TelegramSession

_CRON_RUNTIME_SESSIONS: dict[int, TelegramSession] = {}


def _telegram_session_cls():
    from telegram_bot.telegram_session_state import TelegramSession

    return TelegramSession


def _run_cron_job_via_unified_flow():
    from telegram_bot.cron_runner import run_cron_job_via_unified_flow

    return run_cron_job_via_unified_flow


def _workspace() -> Path:
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
    session = get_cron_runtime_session()
    session.chat_history.append(
        {
            "role": "system",
            "content": message,
            "timestamp": datetime.now().isoformat(),
            "scheduled_job": True,
            "channel": "system",
            "source_format": "scheduled_job_announcement",
            "display_label": "Scheduled Job",
        }
    )
    session.save_session()


async def cron_spawn_callback(job_id: str, prompt: str) -> None:
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    owner_user_id = int(job.owner_user_id) if job and job.owner_user_id is not None else 0
    session = get_cron_runtime_session(owner_user_id)

    if job and job.owner_user_id:
        try:
            session.chat_history.append(
                {
                    "role": "system",
                    "content": f"Scheduled job running: {job.name}",
                    "timestamp": datetime.now().isoformat(),
                    "scheduled_job": True,
                    "scheduled_job_id": job_id,
                    "scheduled_job_name": job.name,
                    "channel": "system",
                    "source_format": "scheduled_job_announcement",
                    "display_label": "Scheduled Job",
                }
            )
            session.save_session()
        except Exception:
            pass

    result = await _run_cron_job_via_unified_flow()(
        session,
        prompt,
        scheduled_job_id=job_id,
    )

    if job and job.owner_user_id:
        try:
            session.chat_history.append(
                {
                    "role": "assistant",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                    "scheduled_job": True,
                    "scheduled_job_id": job_id,
                    "scheduled_job_name": job.name if job else None,
                    "channel": "system",
                    "source_format": "scheduled_job_result",
                    "display_label": "Scheduled Job",
                }
            )
            session.save_session()
        except Exception:
            pass


async def ensure_global_cron_scheduler_started() -> None:
    scheduler = get_scheduler(
        spawn_callback=cron_spawn_callback,
        announcement_callback=cron_announcement_callback,
    )
    await scheduler.start()
