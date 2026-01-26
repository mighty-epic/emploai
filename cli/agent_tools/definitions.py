"""Canonical tool definitions for the CLI agent."""

from typing import List, Dict, Any

# Tool names for easy reference
TOOL_READ_FILE = "read_file"
TOOL_WRITE_FILE = "write_file"
TOOL_EDIT_FILE = "edit_file"
TOOL_LIST_DIR = "list_dir"
TOOL_FIND_FILES = "find_files"
TOOL_GREP_SEARCH = "grep_search"
TOOL_RUN_COMMAND = "run_command"
TOOL_COMMAND_STATUS = "command_status"
TOOL_SEND_INPUT = "send_input"
TOOL_WEB_SEARCH = "web_search"

# These tools will be available to the CLI agent across all models/providers
CLI_AGENT_TOOLS = [
    {
        "name": TOOL_READ_FILE,
        "description": "Read the contents of a file. Supports line ranges.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read."},
                "start_line": {"type": "integer", "description": "Line number to start reading from (1-indexed)."},
                "end_line": {"type": "integer", "description": "Line number to stop reading at (inclusive)."}
            },
            "required": ["path"]
        }
    },
    {
        "name": TOOL_WRITE_FILE,
        "description": "Create a new file or overwrite an existing one with new content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path where the file should be created/overwritten."},
                "content": {"type": "string", "description": "The full content to write to the file."}
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
        "description": "List files and directories in a given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The directory path to list (defaults to current workspace).", "default": "."}
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
        "description": "Execute a terminal command. For interactive commands, it returns a command ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to execute."}
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
    }
]
