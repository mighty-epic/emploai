"""Logic for executing CLI agent tools."""

import os
import subprocess
import shlex
from pathlib import Path
from typing import Dict, Any, Optional, List
from .web_tools import duckduckgo_search
import shutil
from cli.config_manager import get_config_manager

class ToolExecutor:
    def __init__(self, workspace_path: Path, confirm_callback=None, single_agent=None):
        self.workspace_path = workspace_path.resolve()
        # confirm_callback: Callable[[str], bool] to ask user for permission
        self.confirm_callback = confirm_callback
        self.config_manager = get_config_manager()
        self.single_agent = single_agent
        # Track background processes (stub for now)
        self.processes = {}

    def _is_safe_path(self, path_str: str) -> bool:
        """Check if a path is within the workspace (unless setting 1.B is on)."""
        # Respect workspace_restriction setting (True = 1.A, False = 1.B)
        if not self.config_manager.get_workspace_restriction():
            return True # 1.B: System-wide access allowed
            
        try:
            p = Path(path_str).resolve()
            # If path is relative, make it absolute relative to workspace
            if not Path(path_str).is_absolute():
                p = (self.workspace_path / path_str).resolve()
            
            return str(p).startswith(str(self.workspace_path))
        except Exception:
            return False

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path safely."""
        p = Path(path_str)
        if not p.is_absolute():
            p = (self.workspace_path / p).resolve()
        else:
            p = p.resolve()
            
        if not self._is_safe_path(str(p)):
            raise PermissionError(f"Access denied: {path_str} is outside workspace.")
        return p

    def execute(self, name: str, args: Dict[str, Any]) -> Any:
        """Dispatcher for tool execution."""
        try:
            # 1. Check for CLI-specific tool
            method = getattr(self, f"tool_{name}", None)
            if method:
                return method(**args)
            
            # 2. Check for Task Agent tools
            if self.single_agent and hasattr(self.single_agent, 'tools'):
                if name in self.single_agent.tools:
                    # Execute via SingleAgent's dispatcher
                    return self.single_agent.tools[name](**args)

            return {"error": f"Unknown tool: {name}"}
        except PermissionError as e:
            return {"error": str(e)}
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

    def tool_write_file(self, path: str, content: str) -> Dict[str, Any]:
        p = self._resolve_path(path)
        # Ensure parent directory exists
        p.parent.mkdir(parents=True, exist_ok=True)
        
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "path": path, "size": len(content)}

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

    # --- TERMINAL TOOLS ---

    def tool_run_command(self, command: str) -> Dict[str, Any]:
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
        
        # Simple blocking execution for now
        # In a real app, you'd want this to be async or backgrounded
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30 # Safety timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out after 30 seconds."}

    # --- WEB TOOLS ---

    def tool_web_search(self, query: str) -> Dict[str, Any]:
        """Search the web using DuckDuckGo."""
        return duckduckgo_search(query)
