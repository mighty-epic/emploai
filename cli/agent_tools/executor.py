"""Logic for executing CLI agent tools."""

import os
import subprocess
import shlex
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional, List
from .web_tools import duckduckgo_search
import shutil
from cli.config_manager import get_config_manager

INJECTED_CONTEXT_FILENAMES = {
    "agents.md",
    "soul.md",
    "user.md",
    "tools.md",
    "memory.md",
}


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
        # Track background processes: {command_id: {process, output_lines, thread, command, ...}}
        self._background_commands: Dict[str, Dict[str, Any]] = {}

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
                return method(**args)

            # 1.5. Check for session-specific handlers (Telegram bridge/browser tools)
            custom_handler = self.custom_tool_handlers.get(name)
            if custom_handler:
                return custom_handler(args)
            
            # 2. Check for Task Agent tools
            if self.single_agent and hasattr(self.single_agent, 'tools'):
                if name in self.single_agent.tools:
                    # Execute via SingleAgent's dispatcher
                    return self.single_agent.tools[name](**args)
                if hasattr(self.single_agent, "_execute_tool"):
                    return self.single_agent._execute_tool(name, args)

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
            stderr=asyncio.subprocess.PIPE
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

    def tool_run_command(self, command: str, cwd: str = None) -> Dict[str, Any]:
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
        
        # Interruption-aware execution using Popen
        try:
            import time
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            start_time = time.time()
            timeout = 30 # Synchronous commands must finish in 30s. Use background tools for longer tasks.
            
            while process.poll() is None:
                # Check for interruption flag
                if self.check_interruption and self.check_interruption():
                    self._terminate_process_tree(process)
                    return {
                        "error": "Command terminated by user interruption.",
                        "interrupted": True,
                        "stdout": "Command was terminated before completion."
                    }
                
                # Check for timeout
                if time.time() - start_time > timeout:
                    self._terminate_process_tree(process)
                    return {"error": f"Command timed out after {timeout} seconds."}
                
                time.sleep(0.1) # Poll every 100ms
            
            stdout, stderr = process.communicate()
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": process.returncode
            }
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}

    # -----------------------------------------------------------------------
    # Background Command System
    # -----------------------------------------------------------------------

    def _bg_reader_thread(self, command_id: str):
        """Daemon thread that continuously reads stdout from a background process."""
        entry = self._background_commands.get(command_id)
        if not entry:
            return
        proc = entry["process"]
        out_lines = entry["output_lines"]
        try:
            for raw_line in iter(proc.stdout.readline, ""):
                out_lines.append(raw_line.rstrip("\n"))
        except (ValueError, OSError):
            pass  # pipe closed

    def tool_run_background_command(self, command: str, cwd: str = None) -> Dict[str, Any]:
        """Start a command in the background. Returns immediately with a command_id."""
        if cwd:
            work_dir = self._resolve_path(cwd)
        else:
            work_dir = self.workspace_path

        command_id = uuid.uuid4().hex[:8]

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr into stdout
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
            )
        except Exception as e:
            return {"error": f"Failed to start background command: {str(e)}"}

        entry = {
            "process": process,
            "command": command,
            "cwd": str(work_dir),
            "output_lines": deque(maxlen=200),  # keep last 200 lines
            "thread": None,
        }
        self._background_commands[command_id] = entry

        # Start reader thread (daemon so it won't block shutdown)
        reader = threading.Thread(
            target=self._bg_reader_thread,
            args=(command_id,),
            daemon=True,
        )
        entry["thread"] = reader
        reader.start()

        return {
            "command_id": command_id,
            "pid": process.pid,
            "status": "running",
            "message": f"Background command started. Use command_status('{command_id}') to check output.",
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
            "status": "running" if is_running else "exited",
            "output": "\n".join(tail),
            "total_lines": len(recent),
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
            self._terminate_process_tree(proc)
        except Exception as e:
            return {"error": f"Failed to kill command: {str(e)}"}

        return {
            "status": "killed",
            "exit_code": proc.returncode,
            "message": f"Command '{command_id}' has been terminated.",
        }

    # --- WEB TOOLS ---

    def tool_web_search(self, query: str) -> Dict[str, Any]:
        """Search the web using DuckDuckGo."""
        return duckduckgo_search(query)
