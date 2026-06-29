"""Canonical tool definitions for the CLI agent."""

from typing import List, Dict, Any, Optional

# Tool names for easy reference
TOOL_READ_FILE = "read_file"
TOOL_OPEN_FILE = "open_file"
TOOL_WRITE_FILE = "write_file"
TOOL_APPEND_FILE = "append_file"
TOOL_EDIT_FILE = "edit_file"
TOOL_LIST_DIR = "list_dir"
TOOL_FIND_FILES = "find_files"
TOOL_GREP_SEARCH = "grep_search"
TOOL_RUN_COMMAND = "run_command"
TOOL_RUN_BACKGROUND_COMMAND = "run_background_command"
TOOL_COMMAND_STATUS = "command_status"
TOOL_SEND_INPUT = "send_input"
TOOL_KILL_COMMAND = "kill_command"
TOOL_WEB_SEARCH = "web_search"
TOOL_FETCH_URL = "fetch_url"
TOOL_PULL_SKILL = "pull_skill"

# =============================================================================
# CLI AGENT TOOLS
# =============================================================================
# These tools are available to the CLI agent across all models/providers

CLI_AGENT_TOOLS = [
    {
        "name": TOOL_READ_FILE,
        "description": "Read the contents of a file. Supports line ranges. If accessing paths outside workspace, user confirmation will be requested.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read. Can use relative paths like '../file.txt' to access parent directories."},
                "start_line": {"type": "integer", "description": "Line number to start reading from (1-indexed)."},
                "end_line": {"type": "integer", "description": "Line number to stop reading at (inclusive)."}
            },
            "required": ["path"]
        }
    },
    {
        "name": TOOL_OPEN_FILE,
        "description": "Open an existing local file visibly through the operating system or a specified app. Use this for 'open/show this saved file' tasks after resolving the exact path. This submits a direct file-open request; verify the resulting window/content visually before claiming success.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Exact file path to open. Relative paths resolve against the current workspace; absolute paths are accepted."},
                "app": {"type": "string", "description": "Optional app/executable to open the file with, such as notepad. Omit to use the OS file association."}
            },
            "required": ["path"]
        }
    },
    {
        "name": TOOL_WRITE_FILE,
        "description": "Create or overwrite a file with content. **CRITICAL: You MUST provide BOTH path AND content parameters.** This tool will FAIL if content is missing. Example: write_file(path='file.txt', content='Hello world'). If you only have a path with no content, do NOT call this tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to create/overwrite. Must not be empty."},
                "content": {"type": "string", "description": "File content. REQUIRED. MUST NOT BE EMPTY. This is the actual text to write. If you don't have content, do not call write_file. Keep under 100 lines per call; use append_file for additional chunks."}
            },
            "required": ["path", "content"],
            "additionalProperties": False
        }
    },
    {
        "name": TOOL_APPEND_FILE,
        "description": "Append content to the end of an existing file. ⚠️ BOTH 'path' and 'content' parameters are REQUIRED. Use after write_file for multi-chunk files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to append to. File must already exist."},
                "content": {"type": "string", "description": "The content to append to the file. REQUIRED. Keep under 100 lines per chunk."}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": TOOL_EDIT_FILE,
        "description": "Edit an existing file by replacing a specific block of text.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to edit."},
                "old_content": {"type": "string", "description": "The exact block of text to search for and replace."},
                "new_content": {"type": "string", "description": "The new text to replace the old block with."}
            },
            "required": ["path", "old_content", "new_content"]
        }
    },
    {
        "name": TOOL_LIST_DIR,
        "description": "List files and directories in a given path. Can navigate to parent directories (e.g., '..' or '../..') with user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The directory path to list. Use '..' for parent directory. Defaults to current workspace.", "default": "."}
            }
        }
    },
    {
        "name": TOOL_FIND_FILES,
        "description": "Search for files by name or pattern in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "The pattern or name to look for (e.g., '*.py' or 'app')."}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": TOOL_GREP_SEARCH,
        "description": "Search for a specific string or regex pattern across files.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The string or regex pattern to search for."},
                "path": {"type": "string", "description": "Directory or file to search in (defaults to .)", "default": "."},
                "is_regex": {"type": "boolean", "description": "Whether the query is a regex pattern.", "default": False}
            },
            "required": ["query"]
        }
    },
    {
        "name": TOOL_RUN_COMMAND,
        "description": "Execute a SHORT terminal command synchronously. Commands are hidden by default and return captured output. Use visible_terminal=true only when the user explicitly wants to see or interact with a terminal window. Use this for quick commands that complete in under 30 seconds. Choose shell='powershell' for PowerShell commands such as Get-Location, Resolve-Path, Get-ChildItem, or Start-Process; choose shell='cmd' for cmd commands such as dir, where, or start. For long-running commands (servers, builds, tests, watches), use run_background_command instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to execute."},
                "cwd": {"type": "string", "description": "Working directory to execute the command in. Defaults to workspace root."},
                "shell": {
                    "type": "string",
                    "enum": ["auto", "cmd", "powershell", "pwsh", "bash"],
                    "description": "Shell to use. Defaults to auto (current platform default). On Windows, use powershell for PowerShell syntax and cmd for cmd.exe syntax."
                },
                "visible_terminal": {
                    "type": "boolean",
                    "description": "Default false. Keep false for hidden captured command execution. Set true only when the user explicitly wants a visible terminal window.",
                    "default": False
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": TOOL_RUN_BACKGROUND_COMMAND,
        "description": "Start a command in the BACKGROUND. Background commands are hidden by default and return captured output through command_status. Use visible_terminal=true only when the user explicitly wants to see or interact with a terminal window. Use this for long-running commands (dev servers, builds, npm install, test suites, file watchers, app launches, or any command that may take more than 30 seconds). Choose shell='powershell' for PowerShell commands and shell='cmd' for cmd.exe commands. The runtime will proactively resume the task when a task-owned command exits unless persistent=true or resume_policy='manual'. After starting, use command_status to check output/progress, send_input to interact with hidden commands, or kill_command to stop it.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to run in the background."},
                "cwd": {"type": "string", "description": "Working directory. Defaults to workspace root."},
                "shell": {
                    "type": "string",
                    "enum": ["auto", "cmd", "powershell", "pwsh", "bash"],
                    "description": "Shell to use. Defaults to auto (current platform default). On Windows, use powershell for PowerShell syntax and cmd for cmd.exe syntax."
                },
                "visible_terminal": {
                    "type": "boolean",
                    "description": "Default false. Keep false for hidden captured background execution. Set true only when the user explicitly wants a visible terminal window; command_status can track process state but terminal output/input belongs to that visible window.",
                    "default": False
                },
                "resume_policy": {
                    "type": "string",
                    "enum": ["on_exit", "on_ready", "on_meaningful_output", "manual", "none", "off"],
                    "description": "Default on_exit. Use on_ready for servers/dev apps that should wake the agent as soon as useful output says they are ready. Use on_meaningful_output for watchers/tests that should wake on useful output. Use manual/none/off only when this process should not wake the agent.",
                    "default": "on_exit"
                },
                "persistent": {
                    "type": "boolean",
                    "description": "Default false. Set true only for dev servers/watchers that should remain alive after the immediate task.",
                    "default": False
                },
                "ready_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional regex or text patterns that mean a long-lived process is ready, such as a localhost URL or 'server running'. Used with resume_policy='on_ready'.",
                    "default": []
                },
                "meaningful_output_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional regex or text patterns that mean a watcher/build/test produced a useful milestone. Used with resume_policy='on_meaningful_output'.",
                    "default": []
                },
                "failure_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional regex or text patterns that mean a long-lived process hit an error and the agent should resume to diagnose.",
                    "default": []
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": TOOL_COMMAND_STATUS,
        "description": "Check the status and recent output of a background command started with run_background_command. Returns whether the command is still running, its exit code (if finished), and the latest stdout/stderr output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string", "description": "The command_id returned by run_background_command."}
            },
            "required": ["command_id"]
        }
    },
    {
        "name": TOOL_SEND_INPUT,
        "description": "Send text input (stdin) to a running background command. Use this for interactive commands that prompt for input (e.g., confirmation prompts, REPLs).",
        "parameters": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string", "description": "The command_id of the running background command."},
                "input": {"type": "string", "description": "The text to send to stdin. A newline is appended automatically."}
            },
            "required": ["command_id", "input"]
        }
    },
    {
        "name": TOOL_KILL_COMMAND,
        "description": "Kill/terminate a running background command. Use this to stop long-running processes, servers, or commands that are stuck.",
        "parameters": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string", "description": "The command_id of the command to kill."}
            },
            "required": ["command_id"]
        }
    },
    {
        "name": TOOL_WEB_SEARCH,
        "description": "Search the web for information using DuckDuckGo.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"]
        }
    },
    {
        "name": TOOL_FETCH_URL,
        "description": "Fetch the text content of a specific HTTP or HTTPS URL. Use after web_search when you need to inspect a known source directly.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full http:// or https:// URL to fetch."}
            },
            "required": ["url"]
        }
    },
    {
        "name": TOOL_PULL_SKILL,
        "description": "Load a specific skill's full instructions and tools into your context. Use this when the 'Available Skills' index suggests a skill is relevant to the task.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "The exact name of the skill to pull (e.g., 'mobile-developer')."}
            },
            "required": ["skill_name"]
        }
    }
]
