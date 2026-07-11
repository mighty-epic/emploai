"""Core slash commands for the TUI."""

from __future__ import annotations

from cli.tui_constants import (
    AGENT_MODE_LABELS,
    AGENT_MODES,
    AVAILABLE_MODELS,
    MODEL_CONFIGS,
    MODEL_CONTEXT_SIZES,
)
from shared.model_availability import filter_models_by_provider_access

VARIANT_ALIASES = {
    "light": "low",
}


def _normalize_variant_name(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return VARIANT_ALIASES.get(normalized, normalized)


def help(context, args, result_cls):
    lines = [
        "CHAT MODE:",
        "  Just type to chat with the AI model",
        "",
        "SLASH COMMANDS:",
        "  /help                         Show this help",
        "  /exit | /quit                 Exit the shell",
        "  /clear                        Clear the log",
        "  /history                      Show command history",
        "",
        "MODEL & AGENT COMMANDS:",
        "  /model                        Open model selector",
        "  /variant [name]               Show/set model variant (standard, thinking)",
        "  /mode [name]                  Show/set agent mode (manual, auto)",
        "  /context                      Show context usage",
        "  /reset                        Reset chat history",
        "",
        "AGENT MODES:",
        "  manual  - CLI and Task agents are independent",
        "  auto    - Unified agent with merged capabilities",
        "",
        "FILE COMMANDS:",
        "  /pwd                          Show workspace root",
        "  /cd <path>                    Change working directory",
        "  /ls [path]                    List directory",
        "  /cat <path>                   Show file contents",
        "  /touch <path>                 Create empty file",
        "  /write <path> <text>          Write/overwrite file",
        "  /append <path> <text>         Append to file",
        "  /mv <src> <dest>              Move/rename file",
        "  /cp <src> <dest>              Copy file",
        "  /edit <path>                  Open editor",
        "  /mkdir <path>                 Create directory",
        "  /rm [-r] <path>               Remove file or directory",
        "  /stat <path>                  Show file metadata",
        "  /search <pattern> <path>      Search file contents",
        "",
        "AUTOMATION:",
        "  /run <command>                Run shell command",
        "  /task [options] <task>        Run dual-agent automation task",
        "    Options: --url URL, --max-cycles N",
        "  /continue [max_cycles]        Resume a paused dual-agent task",
        "",
        "PAUSE MODE:",
        "  Press Esc once to pause a running task",
        "  Press Esc again (while pausing or paused) to cancel the task completely",
        "  While paused, chat directly with the Memory Agent",
        "  Use /continue to resume the task",
        "",
        "SESSION MANAGEMENT:",
        "  /session                      List all sessions",
        "  /session new [name]           Create new session",
        "  /session <id>                 Switch to session",
        "  /session delete <id>          Delete a session",
        "  /session export               Export current session to markdown",
        "  /rename <name>                Rename current session",
        "  /settings                     Open global settings",
        "PROVIDER CONFIG:",
        "  /providers                    Show configured providers",
        "  ctrl+p → Configure providers  Open provider config screen",
        "",
        "KEYBOARD SHORTCUTS:",
        "  ctrl+p   Open command palette",
        "  ctrl+m   Switch model",
        "  ctrl+n   New session",
        "  ctrl+l   Switch session",
        "  ctrl+t   Cycle variant",
        "  tab      Cycle agent mode",
    ]
    return result_cls(True, "\n".join(lines))


def exit(context, args, result_cls):
    return result_cls(True, "Exiting...", exit=True)


def clear(context, args, result_cls):
    return result_cls(True, "", clear=True)


def history(context, args, result_cls):
    if not context.history:
        return result_cls(True, "(no history)")
    lines = [f"{idx + 1}: {command}" for idx, command in enumerate(context.history)]
    return result_cls(True, "\n".join(lines))


def model(context, args, result_cls):
    enabled_providers = set(context.config_manager.get_enabled_providers())
    available_models = filter_models_by_provider_access(AVAILABLE_MODELS, MODEL_CONFIGS, enabled_providers)

    if args:
        new_model = args[0]
        if new_model not in MODEL_CONFIGS:
            return result_cls(False, f"Unknown model: {new_model}.")
        if new_model not in available_models:
            provider = MODEL_CONFIGS.get(new_model, {}).get("provider", "unknown")
            return result_cls(False, f"{provider} API key is not configured for model: {new_model}.")
        context.current_model = new_model
        context.max_tokens = MODEL_CONTEXT_SIZES.get(new_model, 128000)
        # Sync variant when model changes
        available = context._get_available_variants(new_model)
        if context.current_variant not in available:
            context.current_variant = context._get_default_variant(new_model)
        context.update_status()
        return result_cls(True, "")

    context.open_model_picker()
    return result_cls(True, "")


def variant(context, args, result_cls):
    """Show or set the current model variant."""
    available = context._get_available_variants(context.current_model)

    if not args:
        # Show current variant and available options
        lines = [
            f"Current variant: {context.current_variant}",
            f"Available for {context.current_model}: {', '.join(available)}",
        ]
        return result_cls(True, "\n".join(lines))

    new_variant = _normalize_variant_name(args[0])
    if new_variant not in available:
        return result_cls(
            False,
            "Variant '{variant}' not available for {model}. Available: {available}".format(
                variant=new_variant,
                model=context.current_model,
                available=", ".join(available),
            ),
        )

    context.current_variant = new_variant
    context.update_status()
    return result_cls(True, f"Switched to variant: {context.current_variant}")


def mode(context, args, result_cls):
    """Show or set the agent mode."""
    if not args:
        # Show current mode and available options
        mode_label = AGENT_MODE_LABELS.get(context.agent_mode, context.agent_mode)
        lines = [
            f"Current agent mode: {mode_label}",
            "",
            "Available modes:",
            "  manual - CLI and Task agents are completely independent",
            "  auto   - Unified agent with merged CLI + Task capabilities",
            "",
            "Use Tab to cycle through modes or /mode <name> to set directly.",
        ]
        return result_cls(True, "\n".join(lines))

    new_mode = args[0].lower()
    if new_mode == "semi":
        context.agent_mode = "auto"
        context.update_status()
        return result_cls(True, "Agent mode set to: [AUTO] (`semi` is retired and now maps to auto)")
    if new_mode not in AGENT_MODES:
        return result_cls(False, f"Unknown mode: {new_mode}. Available: {', '.join(AGENT_MODES)}")

    context.agent_mode = new_mode
    context.update_status()
    mode_label = AGENT_MODE_LABELS.get(context.agent_mode, context.agent_mode)
    return result_cls(True, f"Agent mode set to: {mode_label}")


def context_info(context, args, result_cls):
    pct = context.get_context_percentage()
    lines = [
        f"Model: {context.current_model}",
        f"Context used: {context.total_tokens_used:,} / {context.max_tokens:,} tokens",
        f"Usage: {pct:.1f}%",
        f"Messages in history: {len(context.chat_history)}",
    ]
    return result_cls(True, "\n".join(lines))


def reset(context, args, result_cls):
    context.chat_history = []
    context.total_tokens_used = 0
    context.update_status()
    return result_cls(True, "Chat history reset.")


def settings(context, args, result_cls):
    """Open the global settings screen."""
    if hasattr(context, "open_settings") and callable(context.open_settings):
        context.open_settings()
        return result_cls(True, "")
    return result_cls(False, "Settings screen not available.")
