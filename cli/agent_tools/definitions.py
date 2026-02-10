"""Canonical tool definitions for the CLI agent."""

from typing import List, Dict, Any, Optional

# Tool names for easy reference
TOOL_READ_FILE = "read_file"
TOOL_WRITE_FILE = "write_file"
TOOL_APPEND_FILE = "append_file"
TOOL_EDIT_FILE = "edit_file"
TOOL_LIST_DIR = "list_dir"
TOOL_FIND_FILES = "find_files"
TOOL_GREP_SEARCH = "grep_search"
TOOL_RUN_COMMAND = "run_command"
TOOL_COMMAND_STATUS = "command_status"
TOOL_SEND_INPUT = "send_input"
TOOL_WEB_SEARCH = "web_search"
TOOL_CHANGE_DIRECTORY = "change_directory"
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
        "description": "Execute a terminal command in a specified working directory. For interactive commands, it returns a command ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to execute."},
                "cwd": {"type": "string", "description": "Working directory to execute the command in (e.g., '..' for parent directory). Defaults to workspace root."}
            },
            "required": ["command"]
        }
    },
    {
        "name": TOOL_COMMAND_STATUS,
        "description": "Check the status and output of a previously started command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string", "description": "The ID of the command to check."}
            },
            "required": ["command_id"]
        }
    },
    {
        "name": TOOL_SEND_INPUT,
        "description": "Send keyboard input to a running interactive command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command_id": {"type": "string", "description": "The ID of the running command."},
                "input": {"type": "string", "description": "The text to send to stdin."}
            },
            "required": ["command_id", "input"]
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
        "name": TOOL_CHANGE_DIRECTORY,
        "description": "Change the base working directory (workspace) for all subsequent operations. This allows you to 'move' into a subfolder without having to provide a 'cwd' or use 'cd' in every command.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The path to switch to. Can be absolute or relative to the current workspace root."}
            },
            "required": ["path"]
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
