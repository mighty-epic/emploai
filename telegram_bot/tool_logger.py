"""
Verbose tool logging for the Telegram agent.
- Terminal output: truncated for readability
- File output: full details (excluding base64 data)
"""

import os
import logging
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from shared.security_policy import redact_json, redact_text


def _resolve_logs_dir() -> Path:
    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
    if runtime_home:
        return Path(runtime_home).expanduser().resolve() / "logs"
    return Path(__file__).parent / "logs"


LOGS_DIR = _resolve_logs_dir()
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# File logger - writes full output
file_handler = logging.FileHandler(
    LOGS_DIR / f"tool_calls_{datetime.now().strftime('%Y-%m-%d')}.log",
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
))

tool_logger = logging.getLogger("tool_calls")
tool_logger.setLevel(logging.DEBUG)
tool_logger.addHandler(file_handler)
tool_logger.propagate = False  # Don't propagate to root logger


def _console_print(line: str) -> None:
    """Write a line to stdout without crashing on Windows codepages."""
    stream = sys.stdout
    if stream is None:
        return

    text = f"{line}\n"
    try:
        stream.write(text)
        stream.flush()
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return

    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    try:
        stream.write(safe_text)
        stream.flush()
        return
    except Exception:
        pass

    fallback = text.encode("ascii", errors="replace").decode("ascii")
    try:
        stream.write(fallback)
        stream.flush()
    except Exception:
        return


def _truncate_value(value: Any, max_len: int = 200) -> str:
    """Truncate a value for terminal display."""
    if value is None:
        return "None"
    
    s = redact_text(str(value))
    if len(s) > max_len:
        return s[:max_len] + f"... [{len(s)} chars]"
    return s


def _strip_base64(data: Any) -> Any:
    """Recursively strip base64 data from dicts/lists for logging."""
    data = redact_json(data)
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            # Skip base64 fields
            if k in ("image_base64", "base64", "image_data", "data") and isinstance(v, str) and len(v) > 500:
                cleaned[k] = f"[BASE64 DATA - {len(v)} chars]"
            else:
                cleaned[k] = _strip_base64(v)
        return cleaned
    elif isinstance(data, list):
        return [_strip_base64(item) for item in data]
    elif isinstance(data, str):
        # Check if it looks like base64
        if len(data) > 500 and re.match(r'^[A-Za-z0-9+/=]+$', data[:100]):
            return f"[BASE64 DATA - {len(data)} chars]"
        return data
    return data


def _truncate_args(args: Dict[str, Any], max_per_field: int = 100) -> Dict[str, Any]:
    """Truncate args dict for terminal display."""
    truncated = {}
    for k, v in args.items():
        if k in ("content", "text", "code", "body", "data"):
            truncated[k] = _truncate_value(v, max_per_field)
        elif isinstance(v, str) and len(v) > max_per_field:
            truncated[k] = v[:max_per_field] + "..."
        else:
            truncated[k] = v
    return truncated


def log_tool_call(tool_name: str, args: Dict[str, Any], provider: str = None):
    """
    Log a tool call.
    - Terminal: shows truncated version
    - File: logs full args (minus base64)
    """
    # Terminal output - truncated
    truncated_args = _truncate_args(args)
    args_str = json.dumps(truncated_args, default=str)
    if len(args_str) > 300:
        args_str = args_str[:300] + "..."
    
    provider_tag = f"[{provider.upper()}]" if provider else ""
    _console_print(f"  🔧 {provider_tag} TOOL CALL: {tool_name}")
    _console_print(f"     Args: {args_str}")
    
    # File output - full (minus base64)
    clean_args = _strip_base64(args)
    tool_logger.info(f"CALL | {tool_name} | {json.dumps(clean_args, default=str, indent=2)}")


def log_tool_result(tool_name: str, result: Any, duration_ms: float = None):
    """
    Log a tool result.
    - Terminal: shows truncated version
    - File: logs full result (minus base64)
    """
    # Determine result type and status
    if isinstance(result, dict):
        has_error = "error" in result
        status = "❌ ERROR" if has_error else "✅ SUCCESS"
    elif isinstance(result, str) and result.startswith("Error"):
        status = "❌ ERROR"
        has_error = True
    else:
        status = "✅ SUCCESS"
        has_error = False
    
    # Terminal output - truncated
    if isinstance(result, dict):
        # Show key info
        display_result = {}
        for k, v in list(result.items())[:5]:  # Max 5 keys
            if k in ("image_base64", "base64", "image_data"):
                display_result[k] = "[BASE64]"
            else:
                display_result[k] = _truncate_value(v, 100)
        result_str = json.dumps(display_result, default=str)
    else:
        result_str = _truncate_value(result, 200)
    
    duration_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
    _console_print(f"     {status}: {result_str}{duration_str}")
    
    # File output - full (minus base64)
    clean_result = _strip_base64(result)
    if isinstance(clean_result, dict):
        result_log = json.dumps(clean_result, default=str, indent=2)
    else:
        result_log = str(clean_result)
    
    tool_logger.info(f"RESULT | {tool_name} | {status}{duration_str}\n{result_log}")
    tool_logger.info("-" * 80)


def log_conversation_turn(turn_num: int, provider: str, model: str):
    """Log start of a conversation turn."""
    _console_print(f"\n{'='*60}")
    _console_print(f"  🔄 Turn {turn_num} | Provider: {provider} | Model: {model}")
    _console_print(f"{'='*60}")
    
    tool_logger.info(f"\n{'='*80}")
    tool_logger.info(f"TURN {turn_num} | Provider: {provider} | Model: {model}")
    tool_logger.info(f"{'='*80}")


def log_model_response(response_text: str, tokens: Dict[str, int] = None):
    """Log model response summary."""
    response_text = redact_text(response_text)
    # Terminal - truncated
    preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
    preview = preview.replace('\n', ' ')
    
    tokens_str = ""
    if tokens:
        tokens_str = f" | Tokens: {tokens.get('input', 0)} in, {tokens.get('output', 0)} out"
    
    _console_print(f"  💬 Response: {preview}{tokens_str}")
    
    # File - full
    tool_logger.info(f"RESPONSE{tokens_str}\n{response_text}")
