"""Logging helpers for the Textual TUI."""

from __future__ import annotations

import threading
from typing import Callable

from textual.widgets import Collapsible

from cli.tui_widgets import TaskBlock, TextMessageBlock


def run_safe(app, func: Callable[[], None]) -> None:
    """Run a function safely on the UI thread."""
    try:
        # Check if we are on the UI thread using multiple indicators
        is_ui_thread = False
        if hasattr(app, "_thread_id"):
            is_ui_thread = threading.get_ident() == app._thread_id

        if is_ui_thread:
            func()
        else:
            app.call_from_thread(func)
    except Exception:
        # Fallback for early startup
        try:
            func()
        except Exception:
            pass


def log(app, message: str, role: str = "info", **kwargs) -> None:
    def do_log() -> None:
        # If this is a task-related log and we have an active task block, update it
        if hasattr(app, "_active_task_block") and app._active_task_block:
            # Basic heuristics to extract status from the log line
            status = message.strip()
            if "[Cycle" in status:
                app._active_task_block.update_status(status)
            elif "TASK COMPLETE" in status or "TASK PAUSED" in status:
                # We'll finalize in _log_task_finished
                pass
            else:
                app._active_task_block.update_status(status)
            return

        # Otherwise, create a new text block
        block = TextMessageBlock(message, role=role, **kwargs)
        app.chat_log.mount(block)
        app.chat_log.call_after_refresh(app.chat_log.scroll_end)

    run_safe(app, do_log)


def log_inline(app, message: str) -> None:
    def do_log_inline() -> None:
        # Check if last block is a TextMessageBlock and not a task block
        children = app.chat_log.children
        if children and isinstance(children[-1], TextMessageBlock):
            children[-1].append_text(message)
        else:
            block = TextMessageBlock(message)
            app.chat_log.mount(block)
            app.chat_log.call_after_refresh(app.chat_log.scroll_end)

    run_safe(app, do_log_inline)


def log_agent(app, message: str) -> None:
    def do_log_agent() -> None:
        if not hasattr(app, "agent_log") or not app.agent_log:
            return

        # Show the global details if it's currently hidden, UNLESS it's just a pause request
        if "Pause requested" in message:
             pass
        else:
            try:
                collapsible = app.query_one("#agent_details_collapsible", Collapsible)
                collapsible.remove_class("hidden")
            except Exception:
                pass

        app.agent_log.append_log(message)

        # Also feed to the active task block if one exists
        if hasattr(app, "_active_task_block") and app._active_task_block:
            app._active_task_block.append_detail(message)

    run_safe(app, do_log_agent)


def start_task_log(app, task_name: str) -> None:
    def do_start() -> None:
        block = TaskBlock(task_name)
        app.chat_log.mount(block)
        app._active_task_block = block
        app.chat_log.call_after_refresh(app.chat_log.scroll_end)

        # Clear global agent log for fresh monitoring
        if hasattr(app, "agent_log") and app.agent_log:
            app.agent_log.text = ""

    run_safe(app, do_start)


def finish_task_log(app, success: bool, summary: str) -> None:
    def do_finish() -> None:
        if hasattr(app, "_active_task_block") and app._active_task_block:
            app._active_task_block.finish(success, summary)
            app._active_task_block = None

        # Hide the global details monitor
        try:
            collapsible = app.query_one("#agent_details_collapsible", Collapsible)
            collapsible.add_class("hidden")
        except Exception:
            pass

    run_safe(app, do_finish)
