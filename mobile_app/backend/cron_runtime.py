from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from single_agent.cron_scheduler import get_scheduler
from telegram_bot.cron_runner import run_cron_job_via_unified_flow
from telegram_bot.telegram_session_state import TelegramSession

_CRON_RUNTIME_SESSION: Optional[TelegramSession] = None


def _workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def get_cron_runtime_session() -> TelegramSession:
    global _CRON_RUNTIME_SESSION
    if _CRON_RUNTIME_SESSION is None:
        _CRON_RUNTIME_SESSION = TelegramSession(user_id=0, workspace=_workspace())
    return _CRON_RUNTIME_SESSION


async def cron_announcement_callback(message: str) -> None:
    session = get_cron_runtime_session()
    session.chat_history.append(
        {
            "role": "system",
            "content": message,
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
    session = get_cron_runtime_session()

    result = await run_cron_job_via_unified_flow(
        session,
        prompt,
        scheduled_job_id=job_id,
    )

    if job and job.owner_user_id:
        try:
            owner_session = TelegramSession(user_id=int(job.owner_user_id), workspace=_workspace())
            owner_session.chat_history.append(
                {
                    "role": "assistant",
                    "content": result,
                    "timestamp": session.chat_history[-1].get("timestamp"),
                    "scheduled_job": True,
                    "scheduled_job_id": job_id,
                    "channel": "system",
                    "source_format": "scheduled_job_result",
                    "display_label": "Scheduled Job",
                }
            )
            owner_session.save_session()
        except Exception:
            pass


async def ensure_global_cron_scheduler_started() -> None:
    scheduler = get_scheduler(
        spawn_callback=cron_spawn_callback,
        announcement_callback=cron_announcement_callback,
    )
    await scheduler.start()
