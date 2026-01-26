"""Task and session-related slash commands for the TUI."""

from __future__ import annotations

import subprocess


def run_command(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /run <command>")
    command_str = " ".join(args)
    result = subprocess.run(
        command_str,
        shell=True,
        cwd=context.cwd,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    error = result.stderr.strip()
    parts = []
    if output:
        parts = [output]
    if error:
        parts = [*parts, f"[stderr]\n{error}"]
    if result.returncode != 0:
        parts = [*parts, f"[exit code] {result.returncode}"]
    return result_cls(result.returncode == 0, "\n".join(parts) or "(no output)")


def task(context, args, result_cls):
    if not args:
        return result_cls(False, "Usage: /task [--url URL] [--max-cycles N] <task>")
    try:
        url = None
        max_cycles = 50
        idx = 0
        while idx < len(args):
            if args[idx] == "--url" and idx + 1 < len(args):
                url = args[idx + 1]
                idx += 2
            elif args[idx] == "--max-cycles" and idx + 1 < len(args):
                max_cycles = int(args[idx + 1])
                idx += 2
            else:
                break
        task_text = " ".join(args[idx:])
        if not task_text:
            return result_cls(False, "Usage: /task [--url URL] [--max-cycles N] <task>")
    except ValueError as exc:
        return result_cls(False, f"Invalid option: {exc}")

    context.start_task_log(task_text)

    # --- SINGLE AGENT INTEGRATION ---
    try:
        # We use the new SingleAgent
        # It logs automatically to detail_log via the callback we registered
        summary = context.single_agent.run(task_text, max_turns=max_cycles)
        success = True  # SingleAgent doesn't return success explicitly, assume success if no exception
        # We don't fail on "Max turns" anymore, as per user experience
        if "Error" in summary and "Max turns" not in summary:
            success = False
    except Exception as e:
        summary = f"Agent failed: {e}"
        success = False

    context.finish_task_log(success, summary)
    return result_cls(success, summary)


def pause_task(context, args, result_cls):
    """Request the running agent to pause."""
    if not context.single_agent.current_task:
        return result_cls(False, "No task is currently running.")

    context.single_agent.pause()
    return result_cls(
        True,
        f"Pause requested for: {context.single_agent.current_task}. Agent will stop after current turn.",
    )


def continue_task(context, args, result_cls):
    """Continue a paused agent task."""
    # Check SingleAgent first (new)
    if not context.single_agent.current_task:
        return result_cls(False, "No paused task to continue. Start a task with /task first.")

    max_cycles = 50
    if args:
        try:
            max_cycles = int(args[0])
        except ValueError:
            return result_cls(False, "Usage: /continue [max_cycles]")

    context.start_task_log(f"Resuming: {context.single_agent.current_task}")

    try:
        summary = context.single_agent.continue_task(max_turns=max_cycles)
        success = True
        if "Error" in summary and "Max turns" not in summary:
            success = False
    except Exception as e:
        summary = f"Resume failed: {e}"
        success = False

    context.finish_task_log(success, summary)
    return result_cls(success, summary)


def session(context, args, result_cls):
    """Session management command."""
    if not args:
        # Open the visual session switcher (like /model opens model picker)
        context.open_session_switcher()
        return result_cls(True, "")

    subcommand = args[0].lower()

    if subcommand == "new":
        name = " ".join(args[1:]) if len(args) > 1 else None
        new_session = context.new_session(name)
        return result_cls(True, f"Created new session: {new_session.name} ({new_session.id})", clear=True)

    if subcommand == "delete":
        if len(args) < 2:
            return result_cls(False, "Usage: /session delete <session_id>")
        session_id = args[1]
        if context.session and session_id == context.session.id:
            return result_cls(False, "Cannot delete current session. Switch to another first.")
        context.session_manager.delete_session(session_id)
        return result_cls(True, f"Deleted session: {session_id}")

    if subcommand == "export":
        if not context.session:
            return result_cls(False, "No current session to export.")
        export = context.session_manager.export_session(context.session.id, format="markdown")
        # Save to file
        export_path = context.base_path / f"session_{context.session.id}.md"
        export_path.write_text(export, encoding="utf-8")
        return result_cls(True, f"Session exported to: {export_path}")

    # Assume it's a session ID to switch to
    if context.switch_session(subcommand):
        return result_cls(True, f"Switched to session: {context.session.name}")
    return result_cls(False, f"Session not found: {subcommand}")


def rename(context, args, result_cls):
    """Rename the current session."""
    if not args:
        return result_cls(False, "Usage: /rename <new_name>")

    if not context.session:
        return result_cls(False, "No current session to rename.")

    new_name = " ".join(args)
    old_name = context.session.name
    context.session.name = new_name
    context._auto_save_session()
    return result_cls(True, f"Renamed session: '{old_name}' → '{new_name}'")


def providers(context, args, result_cls):
    """Show and manage provider configuration."""
    lines = ["Provider Configuration:"]

    for provider_id in ["openai", "anthropic", "google", "xai"]:
        has_key = context.config_manager.get_api_key(provider_id) is not None
        status = "[green]✓ Configured[/green]" if has_key else "[dim]Not configured[/dim]"
        lines.append(f"  {provider_id}: {status}")

    lines.append("\nTo configure providers, use ctrl+p → Configure providers")
    lines.append("Or set environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.")
    return result_cls(True, "\n".join(lines))
