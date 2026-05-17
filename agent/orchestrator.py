"""
Agent Orchestrator
Wraps the autonomous agent for use by the chat app.
Provides structured reports with actions and screenshots.

Future: High-level task decomposition and micro-agent coordination.
"""

import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, field, asdict

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from anthropic import Anthropic

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

import base64
import mss
import mss.tools

# pywinauto for desktop control
try:
    from pywinauto import Desktop, Application
    from pywinauto.findwindows import find_windows, ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False


# ============================================================
# MODELS CONFIG
# ============================================================

MODELS = {
    # OpenAI models
    "gpt-5": {"provider": "openai", "id": "gpt-5"},
    "gpt-5.1": {"provider": "openai", "id": "gpt-5.1"},
    "gpt-5.2": {"provider": "openai", "id": "gpt-5.2"},
    "gpt-5.4": {"provider": "openai", "id": "gpt-5.4"},
    "gpt-5.5": {"provider": "openai", "id": "gpt-5.5"},
    "gpt-5.4-mini": {"provider": "openai", "id": "gpt-5.4-mini"},
    "gpt-4.1": {"provider": "openai", "id": "gpt-4.1"},
    "gpt-4o": {"provider": "openai", "id": "gpt-4o"},
    "gpt-4o-mini": {"provider": "openai", "id": "gpt-4o-mini"},
    # Claude models with extended thinking
    "claude-sonnet-4.5": {"provider": "anthropic", "id": "claude-sonnet-4-5-20250929", "thinking": True},
    "claude-opus-4.5": {"provider": "anthropic", "id": "claude-opus-4-5-20250929", "thinking": True},
    "claude-sonnet-4.6": {"provider": "anthropic", "id": "claude-sonnet-4-6", "thinking": True},
    "claude-opus-4.6": {"provider": "anthropic", "id": "claude-opus-4-6", "thinking": True},
    "claude-opus-4.7": {"provider": "anthropic", "id": "claude-opus-4-7", "thinking": False},
    "claude-sonnet-4": {"provider": "anthropic", "id": "claude-sonnet-4-20250514", "thinking": True},
    "claude-opus-4": {"provider": "anthropic", "id": "claude-opus-4-20250514", "thinking": True},
    "claude-haiku-3.5": {"provider": "anthropic", "id": "claude-3-5-haiku-20241022", "thinking": False},
    "claude-sonnet-3.5": {"provider": "anthropic", "id": "claude-3-5-sonnet-20241022", "thinking": False},
}



# ============================================================
# TOOLS
# ============================================================

TOOLS = [
    # Browser tools
    {"type": "function", "function": {"name": "open_browser", "description": "Open browser to URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "close_browser", "description": "Close browser", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "observe", "description": "UNIFIED OBSERVATION: Takes screenshot, extracts DOM elements, and reads text (OCR) in parallel. Returns combined results. Use this after any navigation or action to understand current state.", "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "Optional: specific question for vision analysis"}}, "required": []}}},
    {"type": "function", "function": {"name": "click", "description": "Click browser element by ID, name, or text. Auto-focuses browser first.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text. IMPORTANT: Click target first to focus it!", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "target": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "press_key", "description": "Press key", "parameters": {"type": "object", "properties": {"key": {"type": "string", "enum": ["enter", "tab", "escape"]}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll page", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "wait", "description": "Wait seconds (use after navigation/clicks)", "parameters": {"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]}}},
    
    # Desktop tools
    {"type": "function", "function": {"name": "open_app", "description": "Open a desktop application by name (e.g. 'notepad', 'calc', 'explorer')", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "Application name or path"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "close_app", "description": "Close an application window by title", "parameters": {"type": "object", "properties": {"window_title": {"type": "string"}}, "required": ["window_title"]}}},
    {"type": "function", "function": {"name": "focus_window", "description": "Bring a window to foreground by title", "parameters": {"type": "object", "properties": {"window_title": {"type": "string"}}, "required": ["window_title"]}}},
    {"type": "function", "function": {"name": "minimize_window", "description": "Minimize a window by title", "parameters": {"type": "object", "properties": {"window_title": {"type": "string"}}, "required": ["window_title"]}}},
    {"type": "function", "function": {"name": "maximize_window", "description": "Maximize a window by title", "parameters": {"type": "object", "properties": {"window_title": {"type": "string"}}, "required": ["window_title"]}}},
    {"type": "function", "function": {"name": "list_windows", "description": "Get all open windows", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "observe_desktop", "description": "UNIFIED DESKTOP OBSERVATION: Gets desktop elements, OCR, and screenshot. Auto-focuses the window.", "parameters": {"type": "object", "properties": {"window_title": {"type": "string", "description": "Optional: specific window to observe"}}, "required": []}}},
    {"type": "function", "function": {"name": "click_desktop", "description": "Click a desktop UI element by name or automation_id. Auto-focuses window first.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "window_title": {"type": "string"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "type_desktop", "description": "Type text in a desktop app. Auto-focuses window first.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "target": {"type": "string", "description": "Optional element name"}, "window_title": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "menu_select", "description": "Select menu item (e.g. 'File->Save')", "parameters": {"type": "object", "properties": {"menu_path": {"type": "string", "description": "Menu path like 'File->Save As'"}, "window_title": {"type": "string"}}, "required": ["menu_path"]}}},
    
    # Completion
    {"type": "function", "function": {"name": "task_complete", "description": "Task finished", "parameters": {"type": "object", "properties": {"success": {"type": "boolean"}, "summary": {"type": "string"}}, "required": ["success", "summary"]}}},
]


# ============================================================
# ORCHESTRATOR
# ============================================================

class AgentOrchestrator:
    """
    Low-level agent for tool execution.
    Executes browser and desktop actions.
    """

    def __init__(self, model: str = "claude-sonnet-3.5", event_callback=None):
        self.model = self._normalize_model(model)
        self.model_config = MODELS.get(self.model, MODELS["claude-sonnet-3.5"])
        self.event_callback = event_callback

    @staticmethod
    def _normalize_model(model: str) -> str:
        normalized = model.strip().lower().replace("_", "-").replace(" ", "-")
        aliases = {
            "claude-3-5-sonnet": "claude-sonnet-3.5",
            "claude-3.5-sonnet": "claude-sonnet-3.5",
            "claude-3-5-sonnet-20241022": "claude-sonnet-3.5",
            "claude-3-5-haiku": "claude-haiku-3.5",
            "claude-3-5-haiku-20241022": "claude-haiku-3.5",
            "claude-sonnet-4-5": "claude-sonnet-4.5",
            "claude-opus-4-5": "claude-opus-4.5",
            "claude-sonnet-4-6": "claude-sonnet-4.6",
            "claude-opus-4-6": "claude-opus-4.6",
            "claude-opus-4-7": "claude-opus-4.7",
            "gpt-5-5": "gpt-5.5",
            "gpt-5-4-mini": "gpt-5.4-mini",
            "chatgpt5.5": "gpt-5.5",
            "chatgpt-5.5": "gpt-5.5",
            "gpt-4o-mini": "gpt-4o-mini",
        }
        return aliases.get(normalized, normalized)

        
        # Clients
        self.openai = OpenAI()
        self.anthropic = Anthropic()
        
        # State
        self.driver = None
        self.actions: List[Dict] = []
        self.screenshots: List[str] = []
        self.screenshot_dir = Path("app/static/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    def _emit(self, event_type: str, data: dict):
        """Emit event to callback if registered."""
        if self.event_callback:
            self.event_callback(event_type, data)
        print(f"[{event_type}] {data}")
    
    def execute_task(self, task: str, max_steps: int = 20) -> Dict:
        """Execute a task and return structured report."""
        self.actions = []
        self.screenshots = []
        
        system_prompt = """You are an AI agent that can control a computer.

=== UNIFIED OBSERVATION TOOLS ===
- observe(): ALWAYS use after any action. Returns DOM + OCR + Vision IN PARALLEL.
- observe_desktop(): For desktop apps. AUTO-FOCUSES window first.

=== BROWSER TOOLS ===
open_browser, close_browser, click, type_text, press_key, scroll, wait

=== DESKTOP TOOLS ===
open_app, close_app, observe_desktop, click_desktop, type_desktop, menu_select

=== BEHAVIORAL RULES ===

1. OBSERVE AFTER EVERY ACTION:
   open_browser → wait(2) → observe()
   click → observe()
   type_text → observe()

2. FOCUS BEFORE TYPING:
   click("search") → type_text("query")

3. AUTO-FOCUS: observe_desktop, click_desktop, type_desktop auto-focus the window

4. WEB APPS: Use browser for Spotify, YouTube, Gmail, etc.

=== EXAMPLE ===
1. open_browser("https://open.spotify.com")
2. wait(3)
3. observe()
4. click("Search")
5. observe()
6. type_text("Shape of You")
7. press_key("enter")
8. wait(2)
9. observe()
10. click play button
11. observe("Is the song playing?")
12. task_complete

"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]
        
        success = False
        summary = "Task incomplete"
        
        for step in range(max_steps):
            try:
                # Call LLM
                if self.model_config["provider"] == "openai":
                    response = self.openai.chat.completions.create(
                        model=self.model_config["id"],
                        messages=messages,
                        tools=TOOLS,
                        tool_choice="auto"
                    )
                    msg = response.choices[0].message
                    tool_calls = msg.tool_calls
                else:
                    # Anthropic format - convert OpenAI tools to Anthropic format
                    anthropic_tools = []
                    for t in TOOLS:
                        func = t["function"]
                        anthropic_tools.append({
                            "name": func["name"],
                            "description": func["description"],
                            "input_schema": func["parameters"]
                        })
                    
                    # Anthropic doesn't use system role in messages, use system param
                    anthropic_messages = [m for m in messages if m["role"] != "system"]
                    system_content = next((m["content"] for m in messages if m["role"] == "system"), "")
                    
                    # Check if model supports extended thinking
                    if self.model_config.get("thinking", False):
                        # Extended thinking mode
                        response = self.anthropic.messages.create(
                            model=self.model_config["id"],
                            max_tokens=16000,
                            thinking={
                                "type": "enabled",
                                "budget_tokens": 8000  # Allow up to 8k tokens for reasoning
                            },
                            system=system_content,
                            messages=anthropic_messages,
                            tools=anthropic_tools
                        )
                    else:
                        # Standard mode
                        response = self.anthropic.messages.create(
                            model=self.model_config["id"],
                            max_tokens=4096,
                            system=system_content,
                            messages=anthropic_messages,
                            tools=anthropic_tools
                        )
                    
                    # Extract tool calls from Anthropic response
                    tool_calls = []
                    thinking_content = None
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_calls.append(block)
                        elif block.type == "thinking":
                            thinking_content = block.thinking
                            print(f"[THINKING] {thinking_content[:200]}...")
                    msg = response
                
                if not tool_calls:
                    break
                
                # Execute tools
                for tc in tool_calls:
                    if self.model_config["provider"] == "openai":
                        tool_name = tc.function.name
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        tool_id = tc.id
                    else:
                        tool_name = tc.name
                        args = tc.input
                        tool_id = tc.id
                    
                    # Emit tool start event
                    self._emit("tool_start", {"tool": tool_name, "args": args})
                    
                    result = self._execute_tool(tool_name, args)
                    
                    # Emit tool result event
                    self._emit("tool_result", {
                        "tool": tool_name,
                        "success": result.get("success", False),
                        "result": str(result)[:200]
                    })
                    
                    # Log action
                    self.actions.append({
                        "step": step + 1,
                        "tool": tool_name,
                        "args": args,
                        "success": result.get("success", False)
                    })
                    
                    # FORCED OBSERVE after each action (except observe itself and wait)
                    if tool_name not in ["observe", "observe_desktop", "wait", "task_complete"]:
                        print(f"[AUTO-OBSERVE] After {tool_name}")
                        observe_result = self._observe("What changed after the action?")
                        # Add observe result to the tool result (not as separate message)
                        result["auto_observe"] = {
                            "elements": observe_result.get("elements", [])[:10],
                            "ocr_text": observe_result.get("ocr_text", "")[:500],
                            "vision": observe_result.get("vision", "")[:500]
                        }
                    
                    # VERIFICATION before task_complete
                    if tool_name == "task_complete":
                        print("[VERIFICATION] Verifying task success before completing...")
                        verify_result = self._observe("Did the task succeed? Verify the current state matches the goal.")
                        result["verification"] = verify_result.get("vision", "No vision available")
                    
                    # Add to messages - PRESERVE FULL RESPONSE for thinking
                    if self.model_config["provider"] == "openai":
                        messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                        messages.append({"role": "tool", "tool_call_id": tool_id, "content": json.dumps(result)})
                    else:
                        # For Anthropic with thinking, preserve the FULL response content
                        # This includes thinking blocks (with signature) + tool_use blocks
                        assistant_content = []
                        for block in msg.content:
                            if block.type == "thinking":
                                # Must include signature for thinking blocks
                                assistant_content.append({
                                    "type": "thinking", 
                                    "thinking": block.thinking,
                                    "signature": getattr(block, 'signature', '')
                                })
                            elif block.type == "tool_use":
                                assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                            elif block.type == "text":
                                assistant_content.append({"type": "text", "text": block.text})
                        
                        messages.append({"role": "assistant", "content": assistant_content})
                        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": json.dumps(result)}]})
                    
                    # Check completion
                    if result.get("task_done"):
                        success = result.get("success", False)
                        summary = result.get("summary", "Complete")
                        break
                
                if success or result.get("task_done"):
                    break
                    
            except Exception as e:
                summary = f"Error: {str(e)}"
                break
        
        # Cleanup
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        return {
            "success": success,
            "summary": summary,
            "actions": self.actions,
            "screenshots": self.screenshots
        }
    
    def execute_task_streaming(self, task: str, max_steps: int = 20):
        """Execute a task with streaming. Yields events for thinking and actions."""
        self.actions = []
        self.screenshots = []
        
        system_prompt = """You are an AI agent that can control a computer.

=== UNIFIED OBSERVATION TOOLS ===
- observe(): ALWAYS use after any action. Returns DOM + OCR + Vision IN PARALLEL.
- observe_desktop(): For desktop apps. AUTO-FOCUSES window first.

=== BROWSER TOOLS ===
open_browser, close_browser, click, type_text, press_key, scroll, wait

=== DESKTOP TOOLS ===
open_app, close_app, observe_desktop, click_desktop, type_desktop, menu_select

=== BEHAVIORAL RULES ===
1. OBSERVE AFTER EVERY ACTION
2. FOCUS BEFORE TYPING: click("search") → type_text("query")
3. WEB APPS: Use browser for Spotify, YouTube, Gmail, etc.
4. VERIFY before task_complete

"""
        
        messages = [{"role": "user", "content": task}]
        
        # Convert tools to Anthropic format
        anthropic_tools = []
        for t in TOOLS:
            func = t["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"]
            })
        
        success = False
        summary = "Task incomplete"
        
        for step in range(max_steps):
            try:
                yield {"type": "step_start", "step": step + 1}
                
                # Use streaming API
                if self.model_config.get("thinking", False):
                    # Streaming with thinking
                    with self.anthropic.messages.stream(
                        model=self.model_config["id"],
                        max_tokens=16000,
                        thinking={
                            "type": "enabled",
                            "budget_tokens": 8000
                        },
                        system=system_prompt,
                        messages=messages,
                        tools=anthropic_tools
                    ) as stream:
                        thinking_text = ""
                        tool_uses = []
                        current_tool = None
                        
                        for event in stream:
                            # Handle thinking delta
                            if hasattr(event, 'type'):
                                if event.type == "content_block_start":
                                    if hasattr(event, 'content_block'):
                                        if event.content_block.type == "thinking":
                                            yield {"type": "thinking_start"}
                                        elif event.content_block.type == "tool_use":
                                            current_tool = {
                                                "id": event.content_block.id,
                                                "name": event.content_block.name,
                                                "input": {}
                                            }
                                
                                elif event.type == "content_block_delta":
                                    if hasattr(event, 'delta'):
                                        if event.delta.type == "thinking_delta":
                                            thinking_text += event.delta.thinking
                                            yield {"type": "thinking_delta", "content": event.delta.thinking}
                                        elif event.delta.type == "input_json_delta":
                                            if current_tool:
                                                # Accumulate JSON
                                                pass
                                
                                elif event.type == "content_block_stop":
                                    if current_tool:
                                        tool_uses.append(current_tool)
                                        current_tool = None
                        
                        # Get final message
                        response = stream.get_final_message()
                else:
                    # Non-streaming fallback
                    response = self.anthropic.messages.create(
                        model=self.model_config["id"],
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                        tools=anthropic_tools
                    )
                
                # Extract tool calls
                tool_calls = []
                assistant_content = []
                for block in response.content:
                    if block.type == "thinking":
                        assistant_content.append({
                            "type": "thinking",
                            "thinking": block.thinking,
                            "signature": getattr(block, 'signature', '')
                        })
                        if not self.model_config.get("thinking", False):
                            yield {"type": "thinking_delta", "content": block.thinking}
                    elif block.type == "tool_use":
                        tool_calls.append(block)
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                    elif block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                
                if not tool_calls:
                    yield {"type": "no_action", "message": "No tools called"}
                    break
                
                # Execute tools
                for tc in tool_calls:
                    tool_name = tc.name
                    args = tc.input
                    tool_id = tc.id
                    
                    yield {"type": "action_start", "tool": tool_name, "args": args}
                    
                    result = self._execute_tool(tool_name, args)
                    
                    # Truncate result for streaming
                    result_str = json.dumps(result)
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "..."
                    
                    yield {
                        "type": "action_result",
                        "tool": tool_name,
                        "success": result.get("success", False),
                        "result": result_str
                    }
                    
                    # Log action
                    self.actions.append({
                        "step": step + 1,
                        "tool": tool_name,
                        "args": args,
                        "success": result.get("success", False)
                    })
                    
                    # Auto-observe
                    if tool_name not in ["observe", "observe_desktop", "wait", "task_complete"]:
                        observe_result = self._observe("What changed?")
                        result["auto_observe"] = {
                            "elements": observe_result.get("elements", [])[:5],
                            "vision": observe_result.get("vision", "")[:300]
                        }
                    
                    # Add to messages
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": json.dumps(result)}]})
                    
                    if result.get("task_done"):
                        success = result.get("success", False)
                        summary = result.get("summary", "Complete")
                        yield {"type": "complete", "success": success, "summary": summary}
                        break
                
                if success or result.get("task_done"):
                    break
                    
            except Exception as e:
                yield {"type": "error", "message": str(e)}
                summary = f"Error: {str(e)}"
                break
        
        # Cleanup
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        yield {"type": "done", "success": success, "summary": summary}
    
    def _execute_tool(self, name: str, args: Dict) -> Dict:
        """Execute a single tool."""
        try:
            # Browser tools
            if name == "open_browser":
                return self._open_browser(args["url"])
            elif name == "close_browser":
                return self._close_browser()
            elif name == "observe":
                return self._observe(args.get("question"))
            elif name == "click":
                return self._click(args["target"])
            elif name == "type_text":
                return self._type(args["text"], args.get("target"))
            elif name == "press_key":
                return self._press_key(args["key"])
            elif name == "scroll":
                return self._scroll(args["direction"])
            elif name == "wait":
                time.sleep(args["seconds"])
                return {"success": True}
            
            # Desktop tools
            elif name == "open_app":
                return self._open_app(args["app_name"])
            elif name == "close_app":
                return self._close_app(args["window_title"])
            elif name == "focus_window":
                return self._focus_window(args["window_title"])
            elif name == "minimize_window":
                return self._minimize_window(args["window_title"])
            elif name == "maximize_window":
                return self._maximize_window(args["window_title"])
            elif name == "list_windows":
                return self._list_windows()
            elif name == "observe_desktop":
                return self._observe_desktop(args.get("window_title"))
            elif name == "click_desktop":
                return self._click_desktop(args["target"], args.get("window_title"))
            elif name == "type_desktop":
                return self._type_desktop(args["text"], args.get("target"), args.get("window_title"))
            elif name == "menu_select":
                return self._menu_select(args["menu_path"], args.get("window_title"))
            
            # Completion
            elif name == "task_complete":
                return {"task_done": True, "success": args["success"], "summary": args["summary"]}
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _open_browser(self, url: str) -> Dict:
        if self.driver:
            self.driver.get(url)
        else:
            options = Options()
            options.add_argument('--log-level=3')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get(url)
        time.sleep(2)
        return {"success": True, "url": url, "title": self.driver.title}
    
    def _close_browser(self) -> Dict:
        if self.driver:
            self.driver.quit()
            self.driver = None
        return {"success": True}
    
    def _get_elements(self) -> Dict:
        if not self.driver:
            return {"error": "Browser not open"}
        
        elements = []
        for tag in ['input', 'button', 'a', 'textarea']:
            for el in self.driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not el.is_displayed():
                        continue
                    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                    text = el.text or el.get_attribute("placeholder") or ""
                    if el_id or text:
                        elements.append({"id": el_id, "tag": tag, "text": text[:40]})
                except:
                    continue
        
        return {"elements": elements[:20], "url": self.driver.current_url}
    
    def _observe(self, question: str = None) -> Dict:
        """UNIFIED OBSERVATION: DOM + OCR + Screenshot in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import pytesseract
        from PIL import Image
        
        results = {"success": True}
        
        # Take screenshot first (shared between OCR and vision)
        path = str(self.screenshot_dir / f"observe_{int(time.time())}.png")
        
        if self.driver:
            # Focus browser window
            try:
                self.driver.switch_to.window(self.driver.current_window_handle)
            except:
                pass
            self.driver.save_screenshot(path)
        else:
            with mss.mss() as sct:
                sct.shot(output=path)
        
        self.screenshots.append(f"/static/screenshots/{Path(path).name}")
        
        def get_dom():
            """Get DOM elements."""
            if not self.driver:
                return {"elements": []}
            elements = []
            for tag in ["button", "input", "a", "select", "[role='button']"]:
                for el in self.driver.find_elements(By.CSS_SELECTOR, tag)[:15]:
                    try:
                        if not el.is_displayed():
                            continue
                        el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                        text = el.text or el.get_attribute("placeholder") or ""
                        if el_id or text:
                            elements.append({"id": el_id, "tag": tag, "text": text[:40]})
                    except:
                        continue
            return {"elements": elements[:20]}
        
        def get_ocr():
            """Read text from screenshot."""
            try:
                img = Image.open(path)
                text = pytesseract.image_to_string(img)
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                return {"ocr_text": '\n'.join(lines[:30])}
            except Exception as e:
                return {"ocr_error": str(e)}
        
        def get_vision():
            """Visual analysis of screenshot."""
            try:
                with open(path, "rb") as f:
                    img_base64 = base64.b64encode(f.read()).decode()
                
                prompt = question or "Describe the current state of the screen. What elements are visible? What can be clicked?"
                
                response = self.openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                        ]
                    }],
                    max_tokens=400
                )
                return {"vision": response.choices[0].message.content}
            except Exception as e:
                return {"vision_error": str(e)}
        
        # Run all three in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(get_dom): "dom",
                executor.submit(get_ocr): "ocr",
                executor.submit(get_vision): "vision"
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    results.update(result)
                except Exception as e:
                    results[f"{futures[future]}_error"] = str(e)
        
        if self.driver:
            results["url"] = self.driver.current_url
        
        return results
    
    def _read_screen_text(self) -> Dict:
        """OCR - read all visible text from screen."""
        try:
            import pytesseract
            from PIL import Image
            
            path = str(self.screenshot_dir / f"ocr_{int(time.time())}.png")
            
            if self.driver:
                self.driver.save_screenshot(path)
            else:
                with mss.mss() as sct:
                    sct.shot(output=path)
            
            img = Image.open(path)
            text = pytesseract.image_to_string(img)
            
            # Clean up text
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            return {
                "success": True,
                "text": '\n'.join(lines[:50]),  # Limit output
                "line_count": len(lines)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _screenshot(self, question: str = None) -> Dict:
        path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
        
        if self.driver:
            self.driver.save_screenshot(path)
        else:
            with mss.mss() as sct:
                sct.shot(output=path)
        
        self.screenshots.append(f"/static/screenshots/{Path(path).name}")
        
        # Vision analysis
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        
        prompt = question or "Describe what you see."
        
        response = self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }],
            max_tokens=300
        )
        
        return {"success": True, "analysis": response.choices[0].message.content}
    
    def _find_element(self, target: str):
        if not self.driver:
            return None
        for method in [By.ID, By.NAME, By.LINK_TEXT, By.PARTIAL_LINK_TEXT]:
            try:
                return self.driver.find_element(method, target)
            except:
                pass
        try:
            return self.driver.find_element(By.XPATH, f"//*[contains(text(), '{target}')]")
        except:
            pass
        return None
    
    def _click(self, target: str) -> Dict:
        el = self._find_element(target)
        if el:
            el.click()
            time.sleep(0.5)
            return {"success": True, "clicked": target}
        return {"success": False, "error": "Element not found"}
    
    def _type(self, text: str, target: str = None) -> Dict:
        if target:
            el = self._find_element(target)
            if el:
                el.click()
                el.send_keys(text)
                return {"success": True, "typed": text}
            return {"success": False, "error": "Element not found"}
        else:
            self.driver.switch_to.active_element.send_keys(text)
            return {"success": True, "typed": text}
    
    def _press_key(self, key: str) -> Dict:
        keys = {"enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE}
        self.driver.switch_to.active_element.send_keys(keys[key])
        time.sleep(0.3)
        return {"success": True, "pressed": key}
    
    def _scroll(self, direction: str) -> Dict:
        amt = 300 if direction == "down" else -300
        self.driver.execute_script(f"window.scrollBy(0, {amt})")
        return {"success": True, "scrolled": direction}
    
    # ==================== DESKTOP TOOLS ====================
    
    def _get_window(self, title: str = None):
        """Get a window by title or the foreground window."""
        if not PYWINAUTO_AVAILABLE:
            return None
        
        try:
            if title:
                app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=2)
                return app.top_window()
            else:
                desktop = Desktop(backend="uia")
                windows = desktop.windows()
                if windows:
                    return windows[0]
        except:
            pass
        return None
    
    def _open_app(self, app_name: str) -> Dict:
        """Open an application by name."""
        try:
            # Common app mappings
            apps = {
                "notepad": "notepad.exe",
                "calc": "calc.exe",
                "calculator": "calc.exe",
                "explorer": "explorer.exe",
                "paint": "mspaint.exe",
                "cmd": "cmd.exe",
                "terminal": "wt.exe",
                "word": "winword.exe",
                "excel": "excel.exe",
            }
            
            exe = apps.get(app_name.lower(), app_name)
            subprocess.Popen(exe, shell=True)
            time.sleep(2)
            return {"success": True, "opened": app_name}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _close_app(self, window_title: str) -> Dict:
        """Close a window by title."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if window:
                window.close()
                return {"success": True, "closed": window_title}
            return {"success": False, "error": "Window not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _focus_window(self, window_title: str) -> Dict:
        """Bring window to foreground."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if window:
                window.set_focus()
                return {"success": True, "focused": window_title}
            return {"success": False, "error": "Window not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _minimize_window(self, window_title: str) -> Dict:
        """Minimize a window."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if window:
                window.minimize()
                return {"success": True, "minimized": window_title}
            return {"success": False, "error": "Window not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _maximize_window(self, window_title: str) -> Dict:
        """Maximize a window."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if window:
                window.maximize()
                return {"success": True, "maximized": window_title}
            return {"success": False, "error": "Window not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _list_windows(self) -> Dict:
        """Get all open windows."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            desktop = Desktop(backend="uia")
            windows = []
            for w in desktop.windows():
                try:
                    title = w.window_text()
                    if title:
                        windows.append(title)
                except:
                    pass
            return {"success": True, "windows": windows[:15]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _observe_desktop(self, window_title: str = None) -> Dict:
        """UNIFIED DESKTOP OBSERVATION: Auto-focus, get elements, OCR, screenshot."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import pytesseract
        from PIL import Image
        
        results = {"success": True}
        
        try:
            window = self._get_window(window_title)
            if not window:
                return {"success": False, "error": f"Window not found: {window_title}"}
            
            # AUTO-FOCUS the window first
            try:
                window.set_focus()
                time.sleep(0.5)
            except:
                pass
            
            results["window"] = window.window_text()
            
            # Take screenshot
            path = str(self.screenshot_dir / f"desktop_{int(time.time())}.png")
            with mss.mss() as sct:
                sct.shot(output=path)
            self.screenshots.append(f"/static/screenshots/{Path(path).name}")
            
            def get_elements():
                """Get UI elements from window."""
                elements = []
                for child in window.descendants()[:50]:
                    try:
                        name = child.element_info.name or ""
                        ctrl_type = child.element_info.control_type
                        auto_id = child.element_info.automation_id or ""
                        
                        if name or auto_id:
                            elements.append({
                                "name": name[:40],
                                "type": ctrl_type,
                                "id": auto_id
                            })
                    except:
                        pass
                return {"elements": elements[:20]}
            
            def get_ocr():
                """Read text from screenshot."""
                try:
                    img = Image.open(path)
                    text = pytesseract.image_to_string(img)
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    return {"ocr_text": '\n'.join(lines[:30])}
                except Exception as e:
                    return {"ocr_error": str(e)}
            
            def get_vision():
                """Visual analysis."""
                try:
                    with open(path, "rb") as f:
                        img_base64 = base64.b64encode(f.read()).decode()
                    
                    response = self.openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe this desktop application. What elements are visible? What can be clicked or interacted with?"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                            ]
                        }],
                        max_tokens=400
                    )
                    return {"vision": response.choices[0].message.content}
                except Exception as e:
                    return {"vision_error": str(e)}
            
            # Run all in parallel
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(get_elements): "elements",
                    executor.submit(get_ocr): "ocr",
                    executor.submit(get_vision): "vision"
                }
                
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=30)
                        results.update(result)
                    except Exception as e:
                        results[f"{futures[future]}_error"] = str(e)
            
            return results
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _click_desktop(self, target: str, window_title: str = None) -> Dict:
        """Click a desktop UI element."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if not window:
                return {"success": False, "error": "Window not found"}
            
            # Try to find by name or automation_id
            try:
                element = window.child_window(title=target)
                element.click_input()
                return {"success": True, "clicked": target}
            except:
                pass
            
            try:
                element = window.child_window(auto_id=target)
                element.click_input()
                return {"success": True, "clicked": target}
            except:
                pass
            
            return {"success": False, "error": f"Element '{target}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _type_desktop(self, text: str, target: str = None, window_title: str = None) -> Dict:
        """Type text in a desktop app."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if not window:
                return {"success": False, "error": "Window not found"}
            
            if target:
                try:
                    element = window.child_window(title=target)
                    element.type_keys(text, with_spaces=True)
                    return {"success": True, "typed": text}
                except:
                    try:
                        element = window.child_window(auto_id=target)
                        element.type_keys(text, with_spaces=True)
                        return {"success": True, "typed": text}
                    except:
                        return {"success": False, "error": f"Element '{target}' not found"}
            else:
                window.type_keys(text, with_spaces=True)
                return {"success": True, "typed": text}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _menu_select(self, menu_path: str, window_title: str = None) -> Dict:
        """Select a menu item (e.g. 'File->Save')."""
        if not PYWINAUTO_AVAILABLE:
            return {"success": False, "error": "pywinauto not available"}
        
        try:
            window = self._get_window(window_title)
            if not window:
                return {"success": False, "error": "Window not found"}
            
            # Parse menu path
            items = [item.strip() for item in menu_path.split("->")]
            
            window.menu_select(items)
            time.sleep(0.5)
            return {"success": True, "selected": menu_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
