"""Task, scheduling, and automation command handlers."""

from __future__ import annotations

import asyncio
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from local_agent_runtime.cron_scheduler import parse_schedule
from shared.channel_events import publish_status_update
from shared.channel_sync import get_channel_sync_hub
from shared.task_board import (
    archive_active_task_board,
    completed_task_board_views,
    format_task_board_for_user,
    get_active_task_board,
    get_display_task_board,
    request_task_board_reassessment,
    task_board_view,
)


def _confirmation_store():
    from app_backend.remote_control_store import RemoteControlPlaneStore

    return RemoteControlPlaneStore()


def _session_sync_user_id(session, fallback_user_id: int) -> int:
    raw = getattr(session, "sync_user_id", None)
    return int(raw) if raw is not None else int(fallback_user_id)


def _publish_confirmation_sync(user_id: int, confirmation: dict) -> None:
    get_channel_sync_hub().publish(
        user_id=int(user_id),
        event={
            "type": "confirmation_changed",
            "session_id": confirmation.get("origin_chat_id"),
            "origin_channel": "telegram",
            "payload": {"confirmation": confirmation},
        },
    )


def build_task_command_handlers(
    *,
    security_manager,
    rate_limited,
    get_session,
    track_command_usage,
    safe_reply,
):
    @rate_limited(security_manager)
    async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disabled legacy resume command kept only for backwards compatibility."""
        await safe_reply(
            update,
            "⚠️ `/continue` is disabled.\n\n"
            "The current Telegram flow no longer creates resumable paused tasks. "
            "Use a normal message to steer the active run or `/pause` and `/stop` for run control.",
        )

    @rate_limited(security_manager)
    async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pause the running task."""
        user = update.effective_user

        session = get_session(user.id)

        agent_to_pause = None
        if session.unified_agent and session.unified_agent.current_task:
            agent_to_pause = session.unified_agent
        elif session.refined_agent and session.refined_agent.current_task:
            agent_to_pause = session.refined_agent
        elif session.single_agent and session.single_agent.current_task:
            agent_to_pause = session.single_agent

        if not agent_to_pause:
            await safe_reply(update, "No task is currently running.")
            return

        agent_to_pause.pause()
        await safe_reply(update, f"⏸️ Pause requested: {agent_to_pause.current_task}")

    @rate_limited(security_manager)
    async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the running task immediately."""
        user = update.effective_user

        session = get_session(user.id)

        stopped = False
        archived_board = None
        current_session_id = session.session_manager.get_current_session_id() if session.session_manager else None
        async with session.lock:
            if session.unified_agent and session.unified_agent.current_task:
                session.unified_agent.stop()
                stopped = True

            if session.single_agent and session.single_agent.current_task:
                session.single_agent.stop()
                stopped = True

            if session.refined_agent and session.refined_agent.current_task:
                session.refined_agent.stop()
                stopped = True

            if stopped:
                session.is_processing = False
                session.should_interrupt = True
                archived_board = archive_active_task_board(
                    session,
                    status="interrupted",
                    summary="The current managed task was stopped by the user.",
                )
                session.save_session()

        if stopped:
            state_user_id = _session_sync_user_id(session, user.id)
            publish_status_update(
                user_id=state_user_id,
                session_id=current_session_id,
                origin_channel="telegram",
                message="ready",
                run_state="idle",
            )
            if archived_board:
                get_channel_sync_hub().publish(
                    user_id=state_user_id,
                    event={
                        "type": "task_board",
                        "session_id": current_session_id,
                        "origin_channel": "telegram",
                        "payload": {
                            "board": task_board_view(get_active_task_board(session)),
                            "completed_task_boards": completed_task_board_views(session),
                            "summary": archived_board.get("completion_summary")
                            or archived_board.get("progress_summary")
                            or archived_board.get("latest_summary")
                            or "The current managed task was stopped by the user.",
                        },
                    },
                )
            await safe_reply(update, "⏹️ **Stopped.**")
        else:
            await safe_reply(update, "❌ No task is currently running.")

    @rate_limited(security_manager)
    async def spawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Spawn a sub-agent to run a task in parallel."""
        user = update.effective_user

        session = get_session(user.id)

        if not context.args:
            await safe_reply(
                update,
                "**Usage:** /spawn <task description>\n\n"
                "Spawn a sub-agent to complete a task in the background.\n"
                "Example: `/spawn Read the FastAPI docs and summarize the Middleware section`\n\n"
                "The sub-agent runs in parallel while you continue chatting.",
            )
            return

        prompt = " ".join(context.args)

        if not session.refined_agent:
            loop = asyncio.get_running_loop()
            session.init_single_agent(context.application, loop)

        try:
            task_id = await session.spawn_tool.spawn(
                prompt=prompt,
                headless=True,
                max_turns=30,
                announce_on_complete=True,
            )

            await safe_reply(
                update,
                "🚀 **Spawned Sub-Agent**\n\n"
                f"Task ID: `{task_id}`\n"
                f"Prompt: {prompt[:100]}...\n\n"
                "The sub-agent is running in the background. I'll announce when it completes.",
            )
        except Exception as exc:
            await safe_reply(update, f"❌ Failed to spawn sub-agent: {str(exc)}")

    @rate_limited(security_manager)
    async def subagents_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all spawned sub-agents."""
        user = update.effective_user

        session = get_session(user.id)

        if not session.spawn_tool:
            await safe_reply(update, "No sub-agents spawned yet.")
            return

        status = session.spawn_tool.get_status()

        if status["total_tasks"] == 0:
            await safe_reply(update, "No sub-agents have been spawned yet.")
            return

        lines = ["**🤖 Sub-Agents**\n"]
        lines.append(
            "Total: "
            f"{status['total_tasks']} | Running: {status['running']} | Completed: {status['completed']}\n"
        )

        for task in status["tasks"]:
            lines.append(f"\n**{task['id']}** - {task['status']}")
            lines.append(f"Prompt: {task['prompt'][:60]}...")
            if task.get("completed_at"):
                lines.append(f"Completed: {task['completed_at']}")

        await safe_reply(update, "\n".join(lines))

    @rate_limited(security_manager)
    async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Schedule a recurring task."""
        user = update.effective_user

        session = get_session(user.id)

        if len(context.args) < 3:
            await safe_reply(
                update,
                "**Usage:** /schedule <name> <schedule> <prompt>\n\n"
                "Examples:\n"
                "`/schedule MorningNews every 1 hour Check news.ycombinator.com for AI news`\n"
                "`/schedule DailyReport every day at 08:00 Check website for updates`\n\n"
                "The automation will run automatically on the schedule.",
            )
            return

        if not session.cron_scheduler:
            loop = asyncio.get_running_loop()
            session.init_single_agent(context.application, loop)

        args = context.args
        name = args[0]

        schedule_end = 1
        for i in range(1, min(len(args), 6)):
            if args[i] in ["at", "minutes", "minute", "hours", "hour", "days", "day"]:
                schedule_end = i + 1

        schedule_parts = args[1:schedule_end]
        schedule_text = " ".join(schedule_parts)
        prompt = " ".join(args[schedule_end:])

        if not prompt:
            await safe_reply(update, "❌ Please provide a task prompt after the schedule.")
            return

        interval = parse_schedule(schedule_text)
        if not interval:
            await safe_reply(update, f"❌ Could not parse schedule: {schedule_text}")
            return

        job_id = session.cron_scheduler.add_job(
            name=name,
            prompt=prompt,
            interval_seconds=interval,
        )

        await safe_reply(
            update,
            "🌞 **Automation Created**\n\n"
            f"Name: {name}\n"
            f"ID: `{job_id}`\n"
            f"Schedule: {schedule_text} (every {interval}s)\n"
            f"Prompt: {prompt[:100]}...\n\n"
            "Use /automations to see all automation rules.",
        )

    @rate_limited(security_manager)
    async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all automations."""
        user = update.effective_user

        session = get_session(user.id)

        if not session.cron_scheduler:
            await safe_reply(update, "Scheduler not initialized. Send any message first.")
            return

        status = session.cron_scheduler.get_status()

        if status["total_jobs"] == 0:
            await safe_reply(
                update,
                "**📅 Automations**\n\n"
                "No automations scheduled.\n\n"
                "Use `/schedule <name> <schedule> <prompt>` to create one.",
            )
            return

        lines = ["**📅 Automations**\n"]
        lines.append(
            f"Total: {status['total_jobs']} | Enabled: {status['enabled_jobs']}\n"
        )

        for job in status["jobs"]:
            status_emoji = "✅" if job["enabled"] else "⏸️"
            lines.append(f"\n{status_emoji} **{job['name']}** (`{job['id']}`)")
            lines.append(f"Status: {'enabled' if job['enabled'] else 'paused'}")
            if job.get("next_run"):
                lines.append(f"Next run: {job['next_run']}")
            if job.get("last_run"):
                lines.append(f"Last run: {job['last_run']}")
            lines.append(f"Runs: {job['run_count']}")

        keyboard = []
        for job in status["jobs"][:6]:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            keyboard.append(
                [
                    InlineKeyboardButton(f"Run {job_id}", callback_data=f"automation:run:{job_id}"),
                    InlineKeyboardButton(
                        "Pause" if job.get("enabled") else "Resume",
                        callback_data=f"automation:{'pause' if job.get('enabled') else 'resume'}:{job_id}",
                    ),
                    InlineKeyboardButton("Delete", callback_data=f"automation:delete:{job_id}"),
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await safe_reply(update, "\n".join(lines), reply_markup=reply_markup)

    async def automations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List automations. New product-name alias for /jobs."""
        await jobs_command(update, context)

    @rate_limited(security_manager)
    async def job_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove an automation."""
        user = update.effective_user

        session = get_session(user.id)

        if not context.args:
            await safe_reply(update, "**Usage:** /job_remove <automation_id>")
            return

        if not session.cron_scheduler:
            await safe_reply(update, "❌ Scheduler not initialized.")
            return

        job_id = context.args[0]
        if len(context.args) < 2 or str(context.args[1]).strip().lower() not in {"confirm", "yes"}:
            reply_markup = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("Confirm delete", callback_data=f"automation:confirm_delete:{job_id}"),
                    InlineKeyboardButton("Cancel", callback_data="close"),
                ]]
            )
            await safe_reply(
                update,
                f"Delete automation `{job_id}`?\n\nTyped fallback: `/job_remove {job_id} confirm`.",
                reply_markup=reply_markup,
            )
            return
        success = session.cron_scheduler.remove_job(job_id)

        if success:
            await safe_reply(update, f"✅ Automation `{job_id}` removed.")
        else:
            await safe_reply(update, f"❌ Automation `{job_id}` not found.")

    async def _automation_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        user = update.effective_user
        session = get_session(user.id)

        if not context.args:
            await safe_reply(update, f"**Usage:** /automation_{action} <automation_id>")
            return

        if not session.cron_scheduler:
            await safe_reply(update, "❌ Scheduler not initialized.")
            return

        automation_id = context.args[0]
        if action == "delete" and (len(context.args) < 2 or str(context.args[1]).strip().lower() not in {"confirm", "yes"}):
            reply_markup = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("Confirm delete", callback_data=f"automation:confirm_delete:{automation_id}"),
                    InlineKeyboardButton("Cancel", callback_data="close"),
                ]]
            )
            await safe_reply(
                update,
                f"Delete automation `{automation_id}`?\n\nTyped fallback: `/automation_delete {automation_id} confirm`.",
                reply_markup=reply_markup,
            )
            return
        if action == "run":
            ok = session.cron_scheduler.run_job_now(automation_id)
        elif action == "pause":
            ok = session.cron_scheduler.disable_job(automation_id)
        elif action == "resume":
            ok = session.cron_scheduler.enable_job(automation_id)
        elif action == "delete":
            ok = session.cron_scheduler.remove_job(automation_id)
        else:
            ok = False

        if not ok:
            await safe_reply(update, f"❌ Automation `{automation_id}` not found.")
            return

        await safe_reply(update, f"✅ Automation `{automation_id}` {action} requested.")

    async def automation_run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _automation_action(update, context, "run")

    async def automation_pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _automation_action(update, context, "pause")

    async def automation_resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _automation_action(update, context, "resume")

    async def automation_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _automation_action(update, context, "delete")

    @rate_limited(security_manager)
    async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve a pending shared confirmation from Telegram."""
        user = update.effective_user
        session = get_session(user.id)
        if not context.args:
            await safe_reply(update, "**Usage:** /confirm <confirmation_id>")
            return
        confirmation_id = str(context.args[0] or "").strip()
        if not confirmation_id:
            await safe_reply(update, "**Usage:** /confirm <confirmation_id>")
            return
        sync_user_id = _session_sync_user_id(session, user.id)
        try:
            confirmation = _confirmation_store().decide_confirmation(
                user_id=sync_user_id,
                confirmation_id=confirmation_id,
                approved=True,
                decided_by_surface="telegram",
                decided_by_actor=str(user.id),
            )
            _publish_confirmation_sync(sync_user_id, confirmation)
        except KeyError:
            await safe_reply(update, f"Confirmation `{confirmation_id}` was not found.")
            return
        await safe_reply(update, f"✅ Confirmation `{confirmation_id}` approved.")

    @rate_limited(security_manager)
    async def deny_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deny a pending shared confirmation from Telegram."""
        user = update.effective_user
        session = get_session(user.id)
        if not context.args:
            await safe_reply(update, "**Usage:** /deny <confirmation_id>")
            return
        confirmation_id = str(context.args[0] or "").strip()
        if not confirmation_id:
            await safe_reply(update, "**Usage:** /deny <confirmation_id>")
            return
        sync_user_id = _session_sync_user_id(session, user.id)
        try:
            confirmation = _confirmation_store().decide_confirmation(
                user_id=sync_user_id,
                confirmation_id=confirmation_id,
                approved=False,
                decided_by_surface="telegram",
                decided_by_actor=str(user.id),
            )
            _publish_confirmation_sync(sync_user_id, confirmation)
        except KeyError:
            await safe_reply(update, f"Confirmation `{confirmation_id}` was not found.")
            return
        await safe_reply(update, f"⛔ Confirmation `{confirmation_id}` denied.")

    @rate_limited(security_manager)
    async def headless_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle headless/headed browser mode."""
        user = update.effective_user

        session = get_session(user.id)
        track_command_usage(session, "headless")

        if session.refined_agent:
            current_mode = session.refined_agent.browser.get_current_mode()
        else:
            current_mode = (
                "headless"
                if os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
                else "headed"
            )

        new_mode = "headed" if current_mode == "headless" else "headless"

        os.environ["HEADLESS"] = "true" if new_mode == "headless" else "false"

        if session.refined_agent:
            session.refined_agent.browser.headless = (new_mode == "headless")

        await safe_reply(
            update,
            "**🌐 Browser Mode**\n\n"
            f"Changed from **{current_mode}** to **{new_mode}**\n\n"
            "• **Headless**: Browser runs invisibly (faster, uses less resources)\n"
            "• **Headed**: Browser window is visible (good for debugging)\n\n"
            f"New tasks will use {new_mode} mode.",
        )

    @rate_limited(security_manager)
    async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the active managed task bulletin board."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "task")

        board = get_display_task_board(session)
        await safe_reply(update, format_task_board_for_user(board))

    @rate_limited(security_manager)
    async def reassess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Force a reassessment of the active managed task bulletin board."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "reassess")

        board = request_task_board_reassessment(session, "Manual reassessment requested by the user.")
        if not board:
            await safe_reply(update, "No active managed task.")
            return

        session.save_session()
        await safe_reply(
            update,
            "Manual reassessment requested.\n\n"
            "The active task board will be revised on the next task turn.",
        )

    return {
        "continue_command": continue_command,
        "pause_command": pause_command,
        "stop_command": stop_command,
        "task_command": task_command,
        "reassess_command": reassess_command,
        "spawn_command": spawn_command,
        "subagents_command": subagents_command,
        "schedule_command": schedule_command,
        "automations_command": automations_command,
        "automation_run_command": automation_run_command,
        "automation_pause_command": automation_pause_command,
        "automation_resume_command": automation_resume_command,
        "automation_delete_command": automation_delete_command,
        "confirm_command": confirm_command,
        "deny_command": deny_command,
        "jobs_command": jobs_command,
        "job_remove_command": job_remove_command,
        "headless_command": headless_command,
    }
