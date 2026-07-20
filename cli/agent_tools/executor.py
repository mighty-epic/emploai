"""Logic for executing CLI agent tools."""

import os
import re
import subprocess
import shlex
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional, List
from .web_tools import duckduckgo_search
import shutil
from cli.config_manager import get_config_manager
from shared.security_policy import (
    SecurityContext,
    confirmation_prompt_for,
    default_security_context,
    evaluate_tool_call,
    filter_tool_result,
    normalize_permission_mode,
)
from shared.subprocess_utils import hidden_subprocess_kwargs

INJECTED_CONTEXT_FILENAMES = {
    "agents.md",
    "soul.md",
    "user.md",
    "tools.md",
    "memory.md",
}

DEFAULT_READY_OUTPUT_PATTERNS = [
    r"\bready\b",
    r"\blistening on\b",
    r"\bserver (is )?running\b",
    r"\blocal:\s+https?://",
    r"https?://(localhost|127\.0\.0\.1)",
    r"\bcompiled successfully\b",
    r"\bbuilt in \d",
]

DEFAULT_MEANINGFUL_OUTPUT_PATTERNS = [
    r"\btests? (passed|failed)\b",
    r"\b\d+\s+passed\b",
    r"\b\d+\s+failed\b",
    r"\bbuild (completed|complete|failed)\b",
    r"\b(error|exception|traceback)\b",
]

DEFAULT_FAILURE_OUTPUT_PATTERNS = [
    r"\b(error|failed|failure|exception|traceback)\b",
    r"\bunhandled\b",
    r"\baddress already in use\b",
]

LONG_RUNNING_COMMAND_SECONDS = 5.0
LIVE_OUTPUT_EVENT_INTERVAL_SECONDS = 1.0
BACKGROUND_NO_PROGRESS_SECONDS = [60.0, 300.0]
BACKGROUND_NO_PROGRESS_REPEAT_SECONDS = 600.0


class ToolExecutor:
    def __init__(
        self,
        workspace_path: Path,
        confirm_callback=None,
        single_agent=None,
        check_interruption=None,
        get_interrupt_message=None,
        clear_interrupt=None,
        activate_deferred_interrupts=None,
        has_deferred_interrupts=None,
        skill_registry=None,
        active_skills=None,
    ):
        self.workspace_path = workspace_path.resolve()
        # confirm_callback: Callable[[str], bool] to ask user for permission
        self.confirm_callback = confirm_callback
        # check_interruption: Callable[[], bool] to check if execution should be interrupted
        self.check_interruption = check_interruption
        # get_interrupt_message: Callable[[], Optional[str]] to get the message that caused interruption
        self.get_interrupt_message = get_interrupt_message
        # clear_interrupt: Callable[[], None] to reset the interrupt flag after handling
        self.clear_interrupt = clear_interrupt
        # activate_deferred_interrupts: Callable[[], bool] to arm queued "after tool" interrupts
        self.activate_deferred_interrupts = activate_deferred_interrupts
        # has_deferred_interrupts: Callable[[], bool] to check whether deferred steering is waiting
        self.has_deferred_interrupts = has_deferred_interrupts
        self.config_manager = get_config_manager()
        self.single_agent = single_agent
        self.skill_registry = skill_registry
        self.active_skills = active_skills if active_skills is not None else []
        # Optional session-specific handlers (used by Telegram auto mode).
        self.custom_tool_handlers: Dict[str, Any] = {}
        # Optional callback that returns the current allowed tool-name set for the turn.
        self.allowed_tool_names_provider = None
        # Optional callback that returns a shared.security_policy.SecurityContext
        # or a permission-mode string for this chat/session.
        self.security_context_provider = None
        # Track background processes: {command_id: {process, output_lines, thread, command, ...}}
        self._background_commands: Dict[str, Dict[str, Any]] = {}
        # Optional proactive runtime hooks. The context provider is sampled when a
        # command starts; the event callback is called from a daemon watcher thread
        # when the process exits.
        self.background_command_context_provider = None
        self.background_command_event_callback = None
        self.visual_monitor_context_provider = None
        self.visual_monitor_event_callback = None

    def _background_command_context(self) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        context_provider = getattr(self, "background_command_context_provider", None)
        if callable(context_provider):
            try:
                provided = context_provider()
                if isinstance(provided, dict):
                    context = dict(provided)
            except Exception:
                context = {}
        return context

    def _visual_monitor_context(self) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        context_provider = getattr(self, "visual_monitor_context_provider", None)
        if callable(context_provider):
            try:
                provided = context_provider()
                if isinstance(provided, dict):
                    context = dict(provided)
            except Exception:
                context = {}
        return context

    @staticmethod
    def _normalize_pattern_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in re.split(r"[\n,]", value) if part.strip()]
            return parts[:20]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:20]
        return []

    @staticmethod
    def _line_matches_any(line: str, patterns: List[str]) -> bool:
        text = str(line or "")
        if not text.strip():
            return False
        for pattern in patterns:
            try:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    return True
            except re.error:
                if pattern.casefold() in text.casefold():
                    return True
        return False

    def _security_context(self) -> SecurityContext:
        if callable(self.security_context_provider):
            try:
                provided = self.security_context_provider()
                if isinstance(provided, SecurityContext):
                    return provided
                if isinstance(provided, dict):
                    return SecurityContext(
                        permission_mode=normalize_permission_mode(provided.get("permission_mode")),
                        workspace_path=str(provided.get("workspace_path") or self.workspace_path),
                        workspace_binding_status=provided.get("workspace_binding_status"),
                        workspace_write_enabled=provided.get("workspace_write_enabled"),
                        actor_kind=provided.get("actor_kind"),
                        surface=provided.get("surface"),
                        session_id=provided.get("session_id"),
                        identity_id=provided.get("identity_id"),
                        run_mode=provided.get("run_mode"),
                    )
                if provided:
                    return SecurityContext(
                        permission_mode=normalize_permission_mode(provided),
                        workspace_path=str(self.workspace_path),
                    )
            except Exception:
                pass
        return default_security_context(workspace_path=str(self.workspace_path))

    def _authorize_tool_call(self, name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        decision = evaluate_tool_call(name, args or {}, context=self._security_context())
        if decision.allowed:
            return None
        if decision.needs_confirmation:
            if self.confirm_callback:
                prompt = confirmation_prompt_for(decision, tool_name=name, args=args or {})
                try:
                    if self.confirm_callback(prompt):
                        return None
                except Exception:
                    pass
            return {
                "error": decision.reason or "Security confirmation was required and not approved.",
                "error_type": "security_confirmation_required",
                "tool_name": name,
                "security_decision": decision.action,
                "risk": decision.risk,
                "retry": False,
            }
        return decision.to_tool_result(tool_name=name)

    def _filter_tool_result(self, name: str, args: Dict[str, Any], result: Any) -> Any:
        return filter_tool_result(name, args or {}, result)

    def _terminate_process_tree(self, process: subprocess.Popen, *, timeout: float = 3.0) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=max(1.0, timeout),
                    check=False,
                    **hidden_subprocess_kwargs(),
                )
                return
            except Exception:
                pass
        try:
            process.terminate()
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _context_file_access_error(self, name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target_name = ""
        if name == "read_file":
            target_name = Path(str(args.get("path") or "")).name.lower()
        elif name == "find_files":
            target_name = str(args.get("pattern") or "").strip().lower()

        if target_name and target_name in INJECTED_CONTEXT_FILENAMES:
            return {
                "error": (
                    f"{target_name} is already injected into the runtime prompt context. "
                    "Do not spend tool calls searching for or reading it again during normal execution."
                ),
                "error_type": "redundant_context_lookup",
                "tool_name": name,
                "target": target_name,
            }
        return None

    def _is_safe_path(self, path_str: str) -> bool:
        """
        Check if a path is within the workspace.
        
        NOTE: Directory lock removed. Agent can move freely across codebase.
        """
        # Allow all paths - no workspace restriction
        return True

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path. No workspace restriction - agent can navigate freely."""
        # Expand environment variables (e.g. %USERPROFILE% or $HOME)
        expanded = os.path.expandvars(path_str)
        p = Path(expanded)
        if not p.is_absolute():
            p = (self.workspace_path / p).resolve()
        else:
            p = p.resolve()
        return p

    def _normalize_command_shell(self, shell: Optional[str]) -> str:
        requested = str(shell or "auto").strip().lower()
        aliases = {
            "": "auto",
            "default": "auto",
            "platform": "auto",
            "cmd.exe": "cmd",
            "powershell.exe": "powershell",
            "ps": "powershell",
            "ps1": "powershell",
            "pwsh.exe": "pwsh",
            "sh": "bash",
        }
        normalized = aliases.get(requested, requested)
        allowed = {"auto", "cmd", "powershell", "pwsh", "bash"}
        if normalized not in allowed:
            raise ValueError(
                f"Unsupported shell '{shell}'. Use one of: auto, cmd, powershell, pwsh, bash."
            )
        return normalized

    def _build_command_invocation(self, command: str, shell: Optional[str]) -> tuple[Any, bool, str]:
        requested = self._normalize_command_shell(shell)

        if requested == "auto":
            return command, True, "cmd" if os.name == "nt" else "sh"

        if requested == "cmd":
            if os.name != "nt":
                raise ValueError("shell='cmd' is only available on Windows.")
            return ["cmd.exe", "/d", "/s", "/c", command], False, "cmd"

        if requested == "powershell":
            executable = shutil.which("powershell") or ("powershell.exe" if os.name == "nt" else None)
            if not executable:
                raise ValueError("shell='powershell' was requested, but powershell is not available.")
            return [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], False, "powershell"

        if requested == "pwsh":
            executable = shutil.which("pwsh")
            if not executable:
                raise ValueError("shell='pwsh' was requested, but pwsh is not available.")
            return [executable, "-NoProfile", "-Command", command], False, "pwsh"

        executable = shutil.which("bash")
        if not executable:
            raise ValueError("shell='bash' was requested, but bash is not available.")
        return [executable, "-lc", command], False, "bash"

    def _command_creationflags(self, *, visible_terminal: bool) -> int:
        if os.name != "nt":
            return 0
        if visible_terminal:
            return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def _unsafe_process_scope_error(self, command: str) -> Optional[Dict[str, Any]]:
        normalized = str(command or "").strip()
        if not normalized:
            return None
        lower = normalized.lower()

        broad_reason = None
        if re.search(r"\btaskkill(?:\.exe)?\b", lower):
            has_image_name = bool(re.search(r"(?:^|\s)/(?:im|fi)\s+", lower))
            has_pid = bool(re.search(r"(?:^|\s)/(?:pid)\s+\d+", lower))
            if has_image_name and not has_pid:
                broad_reason = "taskkill by image/filter can terminate unrelated user applications."
        elif re.search(r"\bstop-process\b", lower):
            has_exact_id = bool(re.search(r"(?:^|\s)-(?:id|pid)\s+\d+", lower))
            has_name = bool(re.search(r"(?:^|\s)-(?:name|processname)\s+\S+", lower))
            piped_from_get_process = bool(re.search(r"\bget-process\b.*\|\s*stop-process\b", lower))
            if (has_name or piped_from_get_process) and not has_exact_id:
                broad_reason = "Stop-Process by name can terminate unrelated user applications."
        elif re.search(r"\b(?:pkill|killall)\b", lower):
            broad_reason = "pkill/killall can terminate unrelated user applications by name."

        if not broad_reason:
            return None

        return {
            "error": (
                f"Unsafe broad process-control command blocked: {broad_reason} "
                "Use kill_command(command_id) for background commands started by this agent, "
                "or inspect processes and target an exact PID/window that is known to belong to this task."
            ),
            "error_type": "unsafe_process_scope",
            "retry": True,
            "NEXT": (
                "Choose a scoped cleanup route: kill_command for a known command_id, "
                "taskkill /PID <pid> for an exact task-owned PID, or close_window with an exact window title."
            ),
        }

    def _validate_required_params(self, tool_name: str, args: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate that required parameters are present for specific tools.
        Returns: (is_valid, error_message)
        """
        required_params = {
            "write_file": ["path", "content"],
            "append_file": ["path", "content"],
            "edit_file": ["path", "old_content", "new_content"],
        }
        
        if tool_name not in required_params:
            return True, ""  # No special validation
        
        required = required_params[tool_name]
        missing = []
        empty = []
        
        for param in required:
            if param not in args:
                missing.append(param)
            elif not args[param] or (isinstance(args[param], str) and not args[param].strip()):
                empty.append(param)
        
        if missing or empty:
            msg = f"write_file REQUIRES both 'path' and 'content' parameters.\n"
            if missing:
                msg += f"Missing: {', '.join(missing)}\n"
            if empty:
                msg += f"Empty/None: {', '.join(empty)}\n"
            msg += f"You provided: {list(args.keys())}"
            return False, msg
        
        return True, ""

    def execute(self, name: str, args: Dict[str, Any]) -> Any:
        """Dispatcher for tool execution."""
        try:
            allowed_tool_names = None
            if callable(self.allowed_tool_names_provider):
                allowed_tool_names = self.allowed_tool_names_provider()
            if allowed_tool_names is not None and name not in allowed_tool_names:
                return {
                    "error": f"Tool '{name}' is not enabled for this chat's current tool-pack configuration.",
                    "error_type": "policy",
                    "tool_name": name,
                }

            context_lookup_error = self._context_file_access_error(name, args)
            if context_lookup_error is not None:
                return context_lookup_error

            security_error = self._authorize_tool_call(name, args)
            if security_error is not None:
                return security_error

            # Check for interruption before executing (optional callback)
            if self.check_interruption and self.check_interruption():
                return {"interrupted": True, "message": "Execution interrupted by user"}
            
            # Validate required parameters first
            is_valid, error_msg = self._validate_required_params(name, args)
            if not is_valid:
                return {
                    "error": error_msg,
                    "error_type": "missing_required_parameter",
                    "tool_name": name,
                    "provided_params": list(args.keys()),
                    "retry": True
                }
            
            # 1. Check for CLI-specific tool
            method = getattr(self, f"tool_{name}", None)
            if method:
                return self._filter_tool_result(name, args, method(**args))

            # 1.5. Check for session-specific handlers (Telegram bridge/browser tools)
            custom_handler = self.custom_tool_handlers.get(name)
            if custom_handler:
                return self._filter_tool_result(name, args, custom_handler(args))
            
            # 2. Check for Task Agent tools
            if self.single_agent and hasattr(self.single_agent, 'tools'):
                if name in self.single_agent.tools:
                    # Execute via SingleAgent's dispatcher
                    return self._filter_tool_result(name, args, self.single_agent.tools[name](**args))
                if hasattr(self.single_agent, "_execute_tool"):
                    return self._filter_tool_result(name, args, self.single_agent._execute_tool(name, args))

            return {"error": f"Unknown tool: {name}", "error_type": "unknown_tool", "tool_name": name}
        except PermissionError as e:
            return {"error": str(e)}
        except ValueError as e:
            # Parameter validation errors from the tool function
            return {
                "error": str(e),
                "error_type": "validation_error",
                "tool_name": name,
                "retry": True
            }
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}

    # --- FILE TOOLS ---

    def tool_read_file(self, path: str, start_line: int = None, end_line: int = None) -> Dict[str, Any]:
        p = self._resolve_path(path)
        if not p.is_file():
            return {"error": f"Not a file: {path}"}
            
        with open(p, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if start_line or end_line:
            start = (start_line - 1) if start_line else 0
            end = end_line if end_line else len(lines)
            content = "".join(lines[start:end])
        else:
            content = "".join(lines)
            
        return {"content": content, "lines": len(lines)}

    def tool_open_file(self, path: str, app: str = "") -> Dict[str, Any]:
        """Open an existing file directly through an app or OS file association."""
        p = self._resolve_path(path)
        if not p.is_file():
            return {"error": f"Not a file: {path}", "error_type": "not_found", "path": str(p)}

        app_name = str(app or "").strip()
        try:
            if app_name:
                subprocess.Popen(
                    [app_name, str(p)],
                    cwd=str(self.workspace_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                method = app_name
            elif os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
                method = "os.startfile"
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                method = "open"
            else:
                subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                method = "xdg-open"
            return {
                "success": True,
                "path": str(p),
                "launch_requested": True,
                "method": method,
                "verified": False,
                "NEXT": "Verify the exact file window/content is visible before claiming success.",
            }
        except FileNotFoundError:
            return {
                "error": f"App or opener not found: {app_name or 'system file association'}",
                "error_type": "opener_not_found",
                "path": str(p),
                "retry": True,
            }
        except Exception as exc:
            return {"error": f"Failed to open file: {exc}", "error_type": "open_failed", "path": str(p), "retry": True}

    def tool_write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Create or overwrite a file with the specified content.
        
        Args:
            path: File path to create/overwrite (required)
            content: File content to write (required - must not be empty)
        
        Raises:
            ValueError: If path or content is missing/empty
        
        Returns:
            Dict with success status and file size
        """
        # Validate required parameters (strict matching)
        if not path or not isinstance(path, str) or not path.strip():
            raise ValueError("write_file: 'path' parameter is REQUIRED and must not be empty")
        
        if not content or not isinstance(content, str):
            raise ValueError(
                f"write_file: 'content' parameter is REQUIRED and must be a non-empty string.\n"
                f"You provided path='{path}' but content is missing.\n"
                f"Call write_file with both path AND the actual file content you want to write."
            )
        
        p = self._resolve_path(path)
        # Ensure parent directory exists
        p.parent.mkdir(parents=True, exist_ok=True)
        
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "path": str(p.relative_to(self.workspace_path)), "size": len(content)}

    def tool_append_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Append content to the end of an existing file.
        
        Args:
            path: Path to the file to append to (required)
            content: Content to append (required - must not be empty)
        
        Raises:
            ValueError: If path or content is missing/empty
            FileNotFoundError: If file doesn't exist
        """
        # Validate required parameters
        if not path or not isinstance(path, str) or not path.strip():
            raise ValueError("append_file: 'path' parameter is REQUIRED and must not be empty")
        
        if not content or not isinstance(content, str):
            raise ValueError(
                f"append_file: 'content' parameter is REQUIRED and must be a non-empty string.\n"
                f"You provided path='{path}' but content is missing.\n"
                f"Call append_file with both path AND the content you want to append."
            )
        
        p = self._resolve_path(path)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}. Use write_file first to create the file.")
        
        with open(p, 'a', encoding='utf-8') as f:
            f.write(content)
        
        # Get new file size
        total_size = p.stat().st_size
        return {"success": True, "path": str(p.relative_to(self.workspace_path)), "appended": len(content), "total_size": total_size}

    def tool_edit_file(self, path: str, old_content: str, new_content: str) -> Dict[str, Any]:
        p = self._resolve_path(path)
        if not p.is_file():
            return {"error": f"File not found: {path}"}
            
        with open(p, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if old_content not in content:
            return {"error": "The original block of text was not found in the file."}
            
        updated_content = content.replace(old_content, new_content, 1)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(updated_content)
            
        return {"success": True, "message": "File updated successfully."}

    def tool_str_replace_based_edit_tool(self, command: str, path: str = "", **kwargs) -> Dict[str, Any]:
        """
        Handler for Claude's native text_editor_20250728 tool.
        Maps text_editor commands to existing file operation methods.
        
        Commands:
            view        - Read file contents or list directory (maps to read_file / list_dir)
            create      - Create a new file with content (maps to write_file)
            str_replace - Replace text in a file (maps to edit_file)
            insert      - Insert text at a specific line number
        """
        if command == "view":
            if not path:
                return {"error": "path is required for view command"}
            p = self._resolve_path(path)
            if p.is_dir():
                return self.tool_list_dir(path)
            view_range = kwargs.get("view_range")
            if view_range and isinstance(view_range, list) and len(view_range) == 2:
                start_line = view_range[0]
                end_line = view_range[1] if view_range[1] != -1 else None
                return self.tool_read_file(path, start_line=start_line, end_line=end_line)
            return self.tool_read_file(path)

        elif command == "create":
            file_text = kwargs.get("file_text", "")
            if not path:
                return {"error": "path is required for create command"}
            if not file_text:
                return {"error": "file_text is required for create command"}
            return self.tool_write_file(path, file_text)

        elif command == "str_replace":
            old_str = kwargs.get("old_str", "")
            new_str = kwargs.get("new_str", "")
            if not path:
                return {"error": "path is required for str_replace command"}
            if not old_str:
                return {"error": "old_str is required for str_replace command"}
            return self.tool_edit_file(path, old_str, new_str)

        elif command == "insert":
            insert_line = kwargs.get("insert_line", 0)
            insert_text = kwargs.get("insert_text", "")
            if not path:
                return {"error": "path is required for insert command"}
            if not insert_text:
                return {"error": "insert_text is required for insert command"}
            p = self._resolve_path(path)
            if not p.is_file():
                return {"error": f"File not found: {path}"}
            with open(p, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            insert_idx = max(0, min(insert_line, len(lines)))
            if not insert_text.endswith('\n'):
                insert_text += '\n'
            lines.insert(insert_idx, insert_text)
            with open(p, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return {"success": True, "message": f"Text inserted at line {insert_line} in {path}"}

        else:
            return {"error": f"Unknown text_editor command: {command}"}

    def tool_change_directory(self, path: str) -> Dict[str, Any]:
        """Update the base workspace path for the executor."""
        new_path = self._resolve_path(path)
        if not new_path.exists():
            return {"error": f"Directory not found: {path}"}
        if not new_path.is_dir():
            return {"error": f"Path is not a directory: {path}"}
        
        old_path = self.workspace_path
        self.workspace_path = new_path.resolve()
        
        return {
            "success": True, 
            "old_workspace": str(old_path),
            "new_workspace": str(self.workspace_path),
            "message": f"Base workspace updated to {self.workspace_path}"
        }

    def tool_list_dir(self, path: str = ".") -> Dict[str, Any]:
        resolve_p = self._resolve_path(path)
        if not resolve_p.is_dir():
            return {"error": f"Not a directory: {path}"}
            
        items = []
        for item in resolve_p.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None
            })
        return {"items": items}

    def tool_find_files(self, pattern: str) -> Dict[str, Any]:
        # Use simple os.walk or glob
        results = []
        for p in self.workspace_path.rglob(pattern):
            if p.is_file():
                results.append(str(p.relative_to(self.workspace_path)))
            if len(results) > 100: # Limit result count
                break
        return {"files": results}

    def tool_grep_search(self, query: str, path: str = ".", is_regex: bool = False) -> Dict[str, Any]:
        # Simple implementation using subprocess and grep (or ripgrep if available)
        # For cross-platform fallback, we'll use a simple python search for now
        root = self._resolve_path(path)
        matches = []
        
        for p in root.rglob('*'):
            if p.is_file() and not '.git' in str(p):
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f, 1):
                            if query in line:
                                matches.append({
                                    "file": str(p.relative_to(self.workspace_path)),
                                    "line": i,
                                    "content": line.strip()
                                })
                            if len(matches) > 50: break
                except Exception: continue
            if len(matches) > 50: break
                
        return {"matches": matches}

    def tool_pull_skill(self, skill_name: str) -> Dict[str, Any]:
        """Load a specific skill's full instructions and tools into context."""
        if not self.skill_registry:
            return {"error": "Skill registry not initialized in this session."}
            
        skill = self.skill_registry.loader.get_skill(skill_name)
        if not skill:
            # Try searching by description keywords if exact name fails
            matches = self.skill_registry.loader.search_skills(skill_name)
            if matches:
                 return {"error": f"Skill '{skill_name}' not found. Did you mean: {', '.join([s.name for s in matches])}?"}
            return {"error": f"Skill '{skill_name}' not found in registry."}
            
        if not self.skill_registry.gating.is_available(skill_name):
            reason = self.skill_registry.gating.get_unavailable_reason(skill_name)
            return {"error": f"Skill '{skill_name}' is gated and unavailable: {reason}"}
            
        context = self.skill_registry.loader.get_skill_context(skill_name)
        
        # PERSISTENCE: Mark skill as active in this session
        if skill_name not in self.active_skills:
            self.active_skills.append(skill_name)
            
        return {
            "success": True, 
            "skill_name": skill_name, 
            "instructions": context,
            "message": f"Skill '{skill_name}' loaded. Follow the provided instructions and standards for this task."
        }

    # --- TERMINAL TOOLS ---

    async def _async_run_command(self, command: str, work_dir: Path, timeout: int = 30) -> Dict[str, Any]:
        """Internal async runner for commands (not yet used by sync execute)."""
        import asyncio
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **hidden_subprocess_kwargs(),
        )
        
        try:
            # Simple wait with timeout - interruption handling would go here in an async loop
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return {
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": process.returncode
            }
        except asyncio.TimeoutError:
            process.kill()
            return {"error": f"Command timed out after {timeout} seconds."}

    def tool_run_command(self, command: str, cwd: str = None, shell: str = "auto", visible_terminal: bool = False) -> Dict[str, Any]:
        # Resolve working directory (default to workspace)
        if cwd:
            work_dir = self._resolve_path(cwd)
        else:
            work_dir = self.workspace_path
        
        # Check if confirmation is required
        needs_confirmation = self.config_manager.get_command_confirmation()
        
        # Check allow list (exact match or prefix)
        allow_list = self.config_manager.get_command_allow_list()
        if needs_confirmation and allow_list:
            command_base = command.split()[0] if command.split() else ""
            if command_base in allow_list or command in allow_list:
                needs_confirmation = False

        if needs_confirmation and self.confirm_callback:
            approved = self.confirm_callback(command)
            if not approved:
                return {"error": "User rejected command execution."}

        unsafe_error = self._unsafe_process_scope_error(command)
        if unsafe_error is not None:
            return unsafe_error
        
        # Interruption-aware execution using Popen
        try:
            import time
            popen_args, use_shell, resolved_shell = self._build_command_invocation(command, shell)
            creationflags = self._command_creationflags(visible_terminal=bool(visible_terminal))
            if visible_terminal and os.name == "nt":
                process = subprocess.Popen(
                    popen_args,
                    shell=use_shell,
                    cwd=work_dir,
                    text=True,
                    creationflags=creationflags,
                )
            else:
                process = subprocess.Popen(
                    popen_args,
                    shell=use_shell,
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=creationflags,
                )
            
            start_time = time.time()
            timeout = 30 # Synchronous commands must finish in 30s. Use background tools for longer tasks.
            command_id = f"sync_{uuid.uuid4().hex[:8]}"
            entry = {
                "process": process,
                "command": command,
                "shell": resolved_shell,
                "cwd": str(work_dir),
                "output_lines": deque(maxlen=200),
                "stdout_lines": deque(maxlen=200),
                "stderr_lines": deque(maxlen=200),
                "thread": None,
                "stderr_thread": None,
                "completion_thread": None,
                "visible_terminal": bool(visible_terminal and os.name == "nt"),
                "started_at": start_time,
                "resume_policy": "manual",
                "persistent": False,
                "ready_patterns": [],
                "meaningful_output_patterns": [],
                "failure_patterns": [],
                "context": self._background_command_context(),
                "ui_only": True,
                "synchronous": True,
            }
            self._background_commands[command_id] = entry
            if not (visible_terminal and os.name == "nt"):
                stdout_reader = threading.Thread(
                    target=self._read_command_stream,
                    args=(command_id, process.stdout),
                    kwargs={"stream_name": "stdout"},
                    daemon=True,
                )
                stderr_reader = threading.Thread(
                    target=self._read_command_stream,
                    args=(command_id, process.stderr),
                    kwargs={"stream_name": "stderr"},
                    daemon=True,
                )
                entry["thread"] = stdout_reader
                entry["stderr_thread"] = stderr_reader
                stdout_reader.start()
                stderr_reader.start()
            long_running = threading.Thread(
                target=self._bg_long_running_thread,
                args=(command_id,),
                daemon=True,
            )
            entry["long_running_thread"] = long_running
            long_running.start()
            
            while process.poll() is None:
                # Check for interruption flag
                if self.check_interruption and self.check_interruption():
                    entry["killed_by_user"] = True
                    self._terminate_process_tree(process)
                    if entry.get("long_running_announced"):
                        self._emit_background_command_event(
                            self._background_event_payload(command_id, entry, status="process_failed", exit_code=process.returncode)
                        )
                    else:
                        self._background_commands.pop(command_id, None)
                    return {
                        "error": "Command terminated by user interruption.",
                        "interrupted": True,
                        "stdout": "Command was terminated before completion.",
                        "command_id": command_id,
                    }
                
                # Check for timeout
                if time.time() - start_time > timeout:
                    entry["killed_by_user"] = True
                    self._terminate_process_tree(process)
                    if entry.get("long_running_announced"):
                        self._emit_background_command_event(
                            self._background_event_payload(command_id, entry, status="process_failed", exit_code=process.returncode)
                        )
                    else:
                        self._background_commands.pop(command_id, None)
                    return {"error": f"Command timed out after {timeout} seconds.", "command_id": command_id}
                
                time.sleep(0.1) # Poll every 100ms
            
            if visible_terminal and os.name == "nt":
                stdout, stderr = "", ""
            else:
                for reader in (entry.get("thread"), entry.get("stderr_thread")):
                    if reader:
                        try:
                            reader.join(timeout=0.5)
                        except Exception:
                            pass
                stdout = "\n".join(list(entry.get("stdout_lines") or []))
                stderr = "\n".join(list(entry.get("stderr_lines") or []))
            if entry.get("long_running_announced"):
                status = "process_failed" if process.returncode not in (None, 0) else "process_completed"
                self._emit_background_command_event(
                    self._background_event_payload(command_id, entry, status=status, exit_code=process.returncode)
                )
            else:
                self._background_commands.pop(command_id, None)
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": process.returncode,
                "shell": resolved_shell,
                "visible_terminal": bool(visible_terminal and os.name == "nt"),
                "output_capture": "visible_terminal" if visible_terminal and os.name == "nt" else "captured",
                "command_id": command_id,
            }
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}

    # -----------------------------------------------------------------------
    # Background Command System
    # -----------------------------------------------------------------------

    def _append_command_output_line(self, entry: Dict[str, Any], line: str, *, stream_name: str = "stdout") -> None:
        clean_line = str(line or "")
        stream_key = "stderr_lines" if stream_name == "stderr" else "stdout_lines"
        if stream_key not in entry:
            entry[stream_key] = deque(maxlen=200)
        entry[stream_key].append(clean_line)
        display_line = f"[stderr] {clean_line}" if stream_name == "stderr" else clean_line
        entry["output_lines"].append(display_line)

    def _read_command_stream(self, command_id: str, stream: Any, *, stream_name: str = "stdout") -> None:
        entry = self._background_commands.get(command_id)
        if not entry or stream is None:
            return
        try:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip("\n")
                self._append_command_output_line(entry, line, stream_name=stream_name)
                self._maybe_emit_background_output_event(command_id, line)
        except (ValueError, OSError):
            pass  # pipe closed

    def _bg_reader_thread(self, command_id: str):
        """Daemon thread that continuously reads stdout from a background process."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return
        proc = entry["process"]
        self._read_command_stream(command_id, proc.stdout, stream_name="stdout")

    def _background_event_payload(self, command_id: str, entry: Dict[str, Any], *, status: str, output: str = "", exit_code: Any = None) -> Dict[str, Any]:
        proc = entry.get("process")
        recent = list(entry.get("output_lines") or [])
        return {
            "command_id": command_id,
            "pid": getattr(proc, "pid", None),
            "command": entry.get("command"),
            "shell": entry.get("shell", "auto"),
            "cwd": entry.get("cwd"),
            "started_at": entry.get("started_at"),
            "completed_at": time.time() if status in {"process_completed", "process_failed"} else None,
            "exit_code": exit_code,
            "output": output if output else ("" if entry.get("visible_terminal") else "\n".join(recent[-80:])),
            "total_lines": len(recent),
            "visible_terminal": bool(entry.get("visible_terminal")),
            "output_capture": "visible_terminal" if entry.get("visible_terminal") else "captured",
            "resume_policy": entry.get("resume_policy") or "on_exit",
            "persistent": bool(entry.get("persistent")),
            "auto_resume": not bool(entry.get("killed_by_user")) and not bool(entry.get("ui_only")),
            "status": status,
            "ui_only": bool(entry.get("ui_only")),
            "synchronous": bool(entry.get("synchronous")),
            "ready_patterns": list(entry.get("ready_patterns") or []),
            "meaningful_output_patterns": list(entry.get("meaningful_output_patterns") or []),
            "failure_patterns": list(entry.get("failure_patterns") or []),
            **dict(entry.get("context") or {}),
        }

    def _emit_background_command_event(self, event: Dict[str, Any]) -> None:
        callback = getattr(self, "background_command_event_callback", None)
        if callable(callback):
            try:
                callback(event)
            except Exception:
                pass

    def _maybe_emit_background_output_event(self, command_id: str, line: str) -> None:
        entry = self._background_commands.get(command_id)
        if not entry or entry.get("visible_terminal"):
            return
        resume_policy = str(entry.get("resume_policy") or "on_exit").strip().lower()
        if resume_policy in {"manual", "none", "off"}:
            self._maybe_emit_live_output_event(command_id, entry)
            return
        line_text = str(line or "")
        now = time.time()
        failure_patterns = list(entry.get("failure_patterns") or []) + DEFAULT_FAILURE_OUTPUT_PATTERNS
        ready_patterns = list(entry.get("ready_patterns") or []) + DEFAULT_READY_OUTPUT_PATTERNS
        meaningful_patterns = list(entry.get("meaningful_output_patterns") or []) + DEFAULT_MEANINGFUL_OUTPUT_PATTERNS

        if (
            not entry.get("failure_emitted")
            and resume_policy in {"on_meaningful_output", "on_ready"}
            and self._line_matches_any(line_text, failure_patterns)
        ):
            entry["failure_emitted"] = True
            entry["last_output_event_at"] = now
            self._emit_background_command_event(
                self._background_event_payload(command_id, entry, status="process_meaningful_output", output=line_text)
            )
            return

        if (
            not entry.get("ready_emitted")
            and resume_policy == "on_ready"
            and self._line_matches_any(line_text, ready_patterns)
        ):
            entry["ready_emitted"] = True
            entry["last_output_event_at"] = now
            self._emit_background_command_event(
                self._background_event_payload(command_id, entry, status="process_ready", output=line_text)
            )
            return

        if (
            not entry.get("meaningful_emitted")
            and resume_policy == "on_meaningful_output"
            and self._line_matches_any(line_text, meaningful_patterns)
        ):
            entry["meaningful_emitted"] = True
            entry["last_output_event_at"] = now
            self._emit_background_command_event(
                self._background_event_payload(command_id, entry, status="process_meaningful_output", output=line_text)
            )
            return

        self._maybe_emit_live_output_event(command_id, entry)

    def _mark_long_running_if_needed(self, command_id: str, entry: Dict[str, Any], *, force: bool = False) -> bool:
        proc = entry.get("process")
        if not proc or proc.poll() is not None:
            return False
        now = time.time()
        if entry.get("long_running_announced"):
            return False
        if not force and now - float(entry.get("started_at") or now) < LONG_RUNNING_COMMAND_SECONDS:
            return False
        entry["long_running_announced"] = True
        entry["last_live_output_event_at"] = now
        self._emit_background_command_event(
            self._background_event_payload(command_id, entry, status="process_running")
        )
        return True

    def _maybe_emit_live_output_event(self, command_id: str, entry: Dict[str, Any]) -> None:
        if entry.get("visible_terminal"):
            return
        if not entry.get("long_running_announced"):
            self._mark_long_running_if_needed(command_id, entry)
            if not entry.get("long_running_announced"):
                return
        now = time.time()
        previous = float(entry.get("last_live_output_event_at") or 0)
        if now - previous < LIVE_OUTPUT_EVENT_INTERVAL_SECONDS:
            return
        entry["last_live_output_event_at"] = now
        self._emit_background_command_event(
            self._background_event_payload(command_id, entry, status="process_output")
        )

    def _bg_long_running_thread(self, command_id: str) -> None:
        time.sleep(LONG_RUNNING_COMMAND_SECONDS)
        entry = self._background_commands.get(command_id)
        if not entry:
            return
        self._mark_long_running_if_needed(command_id, entry, force=True)

    def _bg_no_progress_thread(self, command_id: str) -> None:
        deadline_index = 0
        next_deadline = BACKGROUND_NO_PROGRESS_SECONDS[0]
        while True:
            entry = self._background_commands.get(command_id)
            if not entry:
                return
            if bool(entry.get("persistent")) or bool(entry.get("ui_only")):
                return
            resume_policy = str(entry.get("resume_policy") or "on_exit").strip().lower()
            if resume_policy in {"manual", "none", "off"}:
                return
            proc = entry.get("process")
            if not proc or proc.poll() is not None or bool(entry.get("killed_by_user")):
                return

            started_at = float(entry.get("started_at") or time.time())
            target_at = started_at + float(next_deadline)
            while True:
                entry = self._background_commands.get(command_id)
                if not entry:
                    return
                proc = entry.get("process")
                if not proc or proc.poll() is not None or bool(entry.get("killed_by_user")):
                    return
                remaining = target_at - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(2.0, max(0.2, remaining)))

            entry = self._background_commands.get(command_id)
            if not entry:
                return
            proc = entry.get("process")
            if not proc or proc.poll() is not None or bool(entry.get("killed_by_user")):
                return
            event = self._background_event_payload(command_id, entry, status="process_no_progress")
            event["no_progress_seconds"] = max(0.0, time.time() - started_at)
            event["deadline_seconds"] = next_deadline
            event["auto_resume"] = not bool(entry.get("killed_by_user")) and not bool(entry.get("persistent"))
            self._emit_background_command_event(event)

            deadline_index += 1
            if deadline_index < len(BACKGROUND_NO_PROGRESS_SECONDS):
                next_deadline = BACKGROUND_NO_PROGRESS_SECONDS[deadline_index]
            else:
                next_deadline += BACKGROUND_NO_PROGRESS_REPEAT_SECONDS

    def _bg_completion_thread(self, command_id: str):
        """Daemon thread that emits a proactive event when a background process exits."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return
        proc = entry.get("process")
        if proc is None:
            return
        try:
            exit_code = proc.wait()
        except Exception:
            return

        reader = entry.get("thread")
        if reader and reader is not threading.current_thread():
            try:
                reader.join(timeout=0.25)
            except Exception:
                pass

        status = "process_failed" if exit_code not in (None, 0) else "process_completed"
        event = self._background_event_payload(command_id, entry, status=status, exit_code=exit_code)
        event["auto_resume"] = not bool(entry.get("killed_by_user")) and not bool(entry.get("persistent"))
        self._emit_background_command_event(event)

    def tool_run_background_command(
        self,
        command: str,
        cwd: str = None,
        shell: str = "auto",
        visible_terminal: bool = False,
        resume_policy: str = "on_exit",
        persistent: bool = False,
        ready_patterns: Optional[List[str]] = None,
        meaningful_output_patterns: Optional[List[str]] = None,
        failure_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Start a command in the background. Returns immediately with a command_id."""
        if cwd:
            work_dir = self._resolve_path(cwd)
        else:
            work_dir = self.workspace_path

        command_id = uuid.uuid4().hex[:8]

        unsafe_error = self._unsafe_process_scope_error(command)
        if unsafe_error is not None:
            return unsafe_error

        try:
            popen_args, use_shell, resolved_shell = self._build_command_invocation(command, shell)
            creationflags = self._command_creationflags(visible_terminal=bool(visible_terminal))
            if visible_terminal and os.name == "nt":
                process = subprocess.Popen(
                    popen_args,
                    shell=use_shell,
                    cwd=work_dir,
                    text=True,
                    creationflags=creationflags,
                )
            else:
                process = subprocess.Popen(
                    popen_args,
                    shell=use_shell,
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # merge stderr into stdout
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # line-buffered
                    creationflags=creationflags,
                )
        except Exception as e:
            return {"error": f"Failed to start background command: {str(e)}"}

        context = {}
        context_provider = getattr(self, "background_command_context_provider", None)
        if callable(context_provider):
            try:
                provided = context_provider()
                if isinstance(provided, dict):
                    context = dict(provided)
            except Exception:
                context = {}

        normalized_resume_policy = str(resume_policy or "on_exit").strip().lower()
        if normalized_resume_policy not in {"on_exit", "on_ready", "on_meaningful_output", "manual", "none", "off"}:
            normalized_resume_policy = "on_exit"

        entry = {
            "process": process,
            "command": command,
            "shell": resolved_shell,
            "cwd": str(work_dir),
            "output_lines": deque(maxlen=200),  # keep last 200 lines
            "thread": None,
            "completion_thread": None,
            "visible_terminal": bool(visible_terminal and os.name == "nt"),
            "started_at": time.time(),
            "resume_policy": normalized_resume_policy,
            "persistent": bool(persistent),
            "ready_patterns": self._normalize_pattern_list(ready_patterns),
            "meaningful_output_patterns": self._normalize_pattern_list(meaningful_output_patterns),
            "failure_patterns": self._normalize_pattern_list(failure_patterns),
            "context": context,
        }
        self._background_commands[command_id] = entry
        self._emit_background_command_event(
            self._background_event_payload(command_id, entry, status="waiting_on_process", output="")
        )
        long_running = threading.Thread(
            target=self._bg_long_running_thread,
            args=(command_id,),
            daemon=True,
        )
        entry["long_running_thread"] = long_running
        long_running.start()
        no_progress = threading.Thread(
            target=self._bg_no_progress_thread,
            args=(command_id,),
            daemon=True,
        )
        entry["no_progress_thread"] = no_progress
        no_progress.start()

        if not (visible_terminal and os.name == "nt"):
            # Start reader thread (daemon so it won't block shutdown)
            reader = threading.Thread(
                target=self._bg_reader_thread,
                args=(command_id,),
                daemon=True,
            )
            entry["thread"] = reader
            reader.start()

        completion = threading.Thread(
            target=self._bg_completion_thread,
            args=(command_id,),
            daemon=True,
        )
        entry["completion_thread"] = completion
        completion.start()

        return {
            "command_id": command_id,
            "pid": process.pid,
            "status": "running",
            "shell": resolved_shell,
            "visible_terminal": bool(visible_terminal and os.name == "nt"),
            "output_capture": "visible_terminal" if visible_terminal and os.name == "nt" else "captured",
            "resume_policy": normalized_resume_policy,
            "persistent": bool(persistent),
            "ready_patterns": list(entry.get("ready_patterns") or []),
            "meaningful_output_patterns": list(entry.get("meaningful_output_patterns") or []),
            "failure_patterns": list(entry.get("failure_patterns") or []),
            "message": (
                f"Background command started in a visible terminal. Use command_status('{command_id}') to check process state."
                if visible_terminal and os.name == "nt"
                else f"Background command started. Use command_status('{command_id}') to check output."
            ),
        }

    def tool_command_status(self, command_id: str) -> Dict[str, Any]:
        """Check the status and recent output of a background command."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return {"error": f"No background command found with id '{command_id}'."}

        proc = entry["process"]
        exit_code = proc.poll()
        is_running = exit_code is None
        recent = list(entry["output_lines"])  # snapshot

        # Return last 50 lines to keep response size reasonable
        tail = recent[-50:] if len(recent) > 50 else recent

        result = {
            "command_id": command_id,
            "command": entry["command"],
            "shell": entry.get("shell", "auto"),
            "status": "running" if is_running else "exited",
            "output": "\n".join(tail),
            "total_lines": len(recent),
            "visible_terminal": bool(entry.get("visible_terminal")),
            "output_capture": "visible_terminal" if entry.get("visible_terminal") else "captured",
            "resume_policy": entry.get("resume_policy") or "on_exit",
            "persistent": bool(entry.get("persistent")),
            "started_at": entry.get("started_at"),
            "ready_emitted": bool(entry.get("ready_emitted")),
            "meaningful_emitted": bool(entry.get("meaningful_emitted")),
            "failure_emitted": bool(entry.get("failure_emitted")),
        }
        if not is_running:
            result["exit_code"] = exit_code
        return result

    def tool_send_input(self, command_id: str, input: str) -> Dict[str, Any]:
        """Send text input to a running background command's stdin."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return {"error": f"No background command found with id '{command_id}'."}

        proc = entry["process"]
        if proc.poll() is not None:
            return {"error": f"Command '{command_id}' has already exited (code {proc.returncode}). Cannot send input."}
        if entry.get("visible_terminal"):
            return {
                "error": "This background command is running in a visible terminal. Type directly in that terminal window instead of using send_input.",
                "error_type": "visible_terminal_input",
                "command_id": command_id,
            }

        try:
            proc.stdin.write(input + "\n")
            proc.stdin.flush()
            return {"status": "sent", "input": input}
        except (BrokenPipeError, OSError) as e:
            return {"error": f"Failed to send input: {str(e)}"}

    def tool_kill_command(self, command_id: str) -> Dict[str, Any]:
        """Kill a running background command."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return {"error": f"No background command found with id '{command_id}'."}

        proc = entry["process"]
        if proc.poll() is not None:
            return {
                "status": "already_exited",
                "exit_code": proc.returncode,
                "message": f"Command '{command_id}' was already finished.",
            }

        try:
            entry["killed_by_user"] = True
            self._terminate_process_tree(proc)
        except Exception as e:
            return {"error": f"Failed to kill command: {str(e)}"}

        return {
            "status": "killed",
            "exit_code": proc.returncode,
            "message": f"Command '{command_id}' has been terminated.",
        }

    def tool_start_visual_monitor(self, threshold_preset: str, reason: str) -> Dict[str, Any]:
        """Start a full-screen visual monitor for long uncertain UI waits."""
        from shared.visual_monitor_runtime import get_visual_monitor_manager

        callback = getattr(self, "visual_monitor_event_callback", None)
        return get_visual_monitor_manager().start_monitor(
            threshold_preset=threshold_preset,
            reason=reason,
            context=self._visual_monitor_context(),
            event_callback=callback if callable(callback) else None,
        )

    def tool_stop_visual_monitor(self, monitor_id: str = "") -> Dict[str, Any]:
        """Stop one monitor or this session/task's active visual monitors."""
        from shared.visual_monitor_runtime import get_visual_monitor_manager

        context = self._visual_monitor_context()
        clean_monitor_id = str(monitor_id or "").strip() or None
        return get_visual_monitor_manager().stop_monitor(
            monitor_id=clean_monitor_id,
            session_id=None if clean_monitor_id else str(context.get("session_id") or "") or None,
            task_id=None if clean_monitor_id else str(context.get("task_id") or "") or None,
            identity_id=None if clean_monitor_id else str(context.get("fleet_identity_id") or "") or None,
            reason="Stopped by agent",
        )

    def kill_all_background_commands(self) -> Dict[str, Any]:
        """Terminate every background command started by this executor."""
        killed: List[Dict[str, Any]] = []
        already_exited: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for command_id, entry in list(self._background_commands.items()):
            proc = entry.get("process")
            if proc is None:
                continue
            if proc.poll() is not None:
                already_exited.append(
                    {
                        "command_id": command_id,
                        "pid": getattr(proc, "pid", None),
                        "exit_code": proc.returncode,
                    }
                )
                continue
            try:
                entry["killed_by_user"] = True
                self._terminate_process_tree(proc)
                killed.append(
                    {
                        "command_id": command_id,
                        "pid": getattr(proc, "pid", None),
                        "exit_code": proc.returncode,
                        "visible_terminal": bool(entry.get("visible_terminal")),
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "command_id": command_id,
                        "pid": getattr(proc, "pid", None),
                        "error": str(exc),
                    }
                )

        return {
            "killed": killed,
            "already_exited": already_exited,
            "errors": errors,
            "killed_count": len(killed),
            "already_exited_count": len(already_exited),
            "error_count": len(errors),
        }

    # --- WEB TOOLS ---

    def tool_web_search(self, query: str) -> Dict[str, Any]:
        """Search the web using DuckDuckGo."""
        return duckduckgo_search(query)

    def tool_fetch_url(self, url: str) -> Dict[str, Any]:
        """Fetch a specific web page and return a bounded text preview."""
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        target = str(url or "").strip()
        if not target.lower().startswith(("http://", "https://")):
            return {
                "error": "fetch_url only supports http:// and https:// URLs.",
                "error_type": "validation_error",
                "url": target,
            }

        try:
            request = Request(target, headers={"User-Agent": "EmploAI-Agent/1.0"})
            with urlopen(request, timeout=15) as response:
                raw = response.read(1_000_000)
                charset = response.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                return {
                    "url": target,
                    "status": getattr(response, "status", None),
                    "content_type": response.headers.get("content-type", ""),
                    "content": text[:10000],
                    "truncated": len(text) > 10000,
                }
        except HTTPError as e:
            return {
                "error": f"HTTP error fetching URL: {e.code} {e.reason}",
                "error_type": "http_error",
                "url": target,
                "status": e.code,
            }
        except URLError as e:
            return {
                "error": f"URL error fetching URL: {e.reason}",
                "error_type": "connection_error",
                "url": target,
            }
        except Exception as e:
            return {"error": f"Error fetching URL: {str(e)}", "error_type": "fetch_error", "url": target}
