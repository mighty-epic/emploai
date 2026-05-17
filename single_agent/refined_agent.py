"""
Refined Agent - Advanced automation agent with Moltbot features.
Replaces SingleAgent with:
- Safe execution (sanitized error handling)
- Context compression
- BrowserTool with ARIA snapshots
- Spawn tool integration
- Cron scheduling support
"""

import os
import json
import time
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from dataclasses import dataclass
from shared.tesseract_runtime import configure_pytesseract_runtime, normalize_tesseract_error

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Import new tools
from .browser_tool import BrowserTool, BROWSER_TOOL_DEFINITIONS, create_browser_tool
from .spawn_tool import SpawnTool, SPAWN_TOOL_DEFINITIONS, get_spawn_tool
from .cron_scheduler import CronScheduler, CRON_TOOL_DEFINITIONS, get_scheduler, parse_schedule_with_error


# Import desktop automation tools from existing agent
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

PYWINAUTO_IMPORT_ERROR = None
try:
    from pywinauto import Desktop, Application
    PYWINAUTO_AVAILABLE = True
except Exception as exc:
    Desktop = None
    Application = None
    PYWINAUTO_AVAILABLE = False
    PYWINAUTO_IMPORT_ERROR = exc

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False


try:
    import pytesseract
    from PIL import Image
    import mss
    import base64
    configure_pytesseract_runtime(pytesseract)
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# ============================================================
# SYSTEM PROMPT
# ============================================================

REFINED_AGENT_PROMPT = """You are RefinedAgent, an advanced AI automation assistant with browser and desktop control capabilities.

You have access to powerful tools organized into categories:

## BROWSER TOOLS (with ARIA Snapshots)
The browser uses ARIA snapshots for reliable interaction. Instead of guessing selectors:
1. Call browser_snapshot to get a clean list of interactive elements with [ref=N] IDs
2. Use browser_click_ref with the reference number for reliable clicking

- browser_navigate(url): Open URL (auto-starts browser)
- browser_snapshot(): Get ARIA snapshot - returns clean tree like "- button "Login" [ref=1]"
- browser_click_ref(ref): Click by reference number from snapshot (RELIABLE — primary method)
# - browser_click(target): DISABLED — use browser_click_ref instead. Fall back to physical click(x,y) via ocr_screen if needed.
- browser_type(text, clear_first): Type into focused element
- browser_press_key(key): Press enter, tab, escape, arrow keys, etc
- browser_scroll(direction, amount): Scroll page up/down
- browser_back/forward: Navigate history
- browser_switch_tab(index): Switch to tab by index
- browser_close_tab(): Close current tab
- browser_stop(): Close browser

## DESKTOP TOOLS
- describe_screen(question): AI vision description of current screen
- ocr_screen(): OCR text extraction with element coordinates
- observe_desktop(): List all open windows
- open_app(app_name): Open application via Win+R
- focus_window(title): Bring window to front
- minimize/maximize/close_window(title): Window management

## INPUT TOOLS
- click(x, y): Click at coordinates (use ocr_screen to find positions)
- right_click(x, y): Right-click at coordinates
- double_click(x, y): Double-click at coordinates
- type_text(text): Type using keyboard
- press_key(key): Press single key
- hotkey(keys): Key combination like "ctrl+c"
- scroll(direction, amount): Scroll at mouse position
- drag_and_drop(start_x, start_y, end_x, end_y): Drag operation

## CLIPBOARD TOOLS
- get_clipboard(): Get clipboard content
- set_clipboard(text): Copy text to clipboard

## SPAWN TOOLS (Parallel Execution)
- spawn_sub_agent(prompt, headless=True, max_turns=20): Spawn background sub-agent
  * Use this for research tasks while continuing main conversation
  * Example: "Spawn a sub-agent to read FastAPI docs and summarize"
- list_sub_agents(): Check status of spawned agents
- get_sub_agent_result(task_id): Get full result
- stop_sub_agent(task_id): Cancel running sub-agent

## SCHEDULING TOOLS
- schedule_job(name, prompt, schedule): Schedule recurring task
  * Examples: "every 5 minutes", "every 1 hour", "every day at 08:00"
  * Jobs persist across restarts and run automatically
- list_scheduled_jobs(): View all scheduled jobs
- get_scheduled_job(job_id): Inspect one job in detail
- update_scheduled_job(job_id, ...): Modify name, prompt, schedule, or enabled state
- run_scheduled_job_now(job_id): Queue a job to run on the next scheduler check
- remove_scheduled_job(job_id): Delete a job
- enable_job(job_id) / disable_job(job_id): Toggle jobs

## UTILITY TOOLS
- wait(seconds): Pause execution

## BEST PRACTICES

1. **Browser Interaction**: Always use browser_snapshot first, then browser_click_ref with the reference number. browser_click is disabled. If browser_click_ref fails, fall back to physical click(x, y) via ocr_screen.

2. **Desktop Interaction**: Use describe_screen to understand layout, then ocr_screen to get exact coordinates for clicking.

3. **Error Recovery**: If a tool fails, try an alternative approach. Don't retry the same failing action.

4. **Parallel Research**: Use spawn_sub_agent for independent research tasks while you continue the main workflow.

5. **Scheduling**: Use schedule_job for recurring monitoring tasks.

6. **Context Awareness**: The user may be using the computer simultaneously. Check screen state before actions.

7. **Safe Execution**: All tools have error handling. Report failures clearly and suggest alternatives.

8. **Vision-Free Browsing**: Rely on ARIA snapshots for complex pages - they're more reliable than visual analysis for interaction.

Remember: You're running in {mode} mode (headless=True means invisible browser, False means visible)."""


# ============================================================
# CONTEXT COMPRESSOR
# ============================================================

class ContextCompressor:
    """Compresses conversation history to maintain context window."""
    
    def __init__(self, max_tokens: int = 100000, compression_threshold: float = 0.7):
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
    
    def should_compress(self, messages: List[Dict]) -> bool:
        """Check if compression is needed."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        # Rough estimate: 4 chars per token
        estimated_tokens = total_chars / 4
        return estimated_tokens > (self.max_tokens * self.compression_threshold)
    
    def compress(self, messages: List[Dict]) -> List[Dict]:
        """Compress messages by summarizing older turns."""
        if not self.should_compress(messages):
            return messages
        
        # Keep system prompt and recent messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        
        # Keep last 10 messages in full
        keep_count = 10
        if len(non_system) <= keep_count:
            return messages
        
        to_summarize = non_system[:-keep_count]
        to_keep = non_system[-keep_count:]
        
        # Create summary of older messages
        summary_lines = []
        for msg in to_summarize:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))[:200]
            summary_lines.append(f"{role}: {content}")
        
        summary = "[Previous conversation summary]\n" + "\n".join(summary_lines)
        
        compressed = system_msgs + [{"role": "system", "content": summary}] + to_keep
        return compressed
    
    def get_token_estimate(self, messages: List[Dict]) -> Dict[str, int]:
        """Estimate token usage."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_tokens = int(total_chars / 4)
        
        return {
            "estimated_tokens": estimated_tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": (estimated_tokens / self.max_tokens) * 100,
            "message_count": len(messages)
        }


# ============================================================
# REFINED AGENT
# ============================================================

class RefinedAgent:
    """
    Advanced automation agent with safe execution and context management.
    Replaces SingleAgent with Moltbot-inspired features.
    """
    
    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        headless: bool = True,
        screenshot_dir: str = "single_agent/screenshots",
        logger: Optional[Callable[[str], None]] = None,
        spawn_tool: Optional[SpawnTool] = None,
        cron_scheduler: Optional[CronScheduler] = None,
        announcement_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize RefinedAgent.
        
        Args:
            model: LLM model ID
            headless: Whether to run browser in headless mode
            screenshot_dir: Directory for screenshots
            logger: Optional logging callback
            spawn_tool: Optional SpawnTool instance
            cron_scheduler: Optional CronScheduler instance
            announcement_callback: Callback for announcements
        """
        self.model = model
        self.headless = headless
        self.logger = logger
        self.announcement_callback = announcement_callback
        
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize browser tool
        self.browser = create_browser_tool(headless=headless)
        
        # Initialize context compressor
        self.context_compressor = ContextCompressor()
        
        # Initialize spawn tool
        self.spawn_tool = spawn_tool or get_spawn_tool(
            agent_factory=self._create_sub_agent,
            announcement_callback=announcement_callback
        )
        
        # Initialize cron scheduler
        self.cron_scheduler = cron_scheduler or get_scheduler(
            spawn_callback=self._spawn_cron_agent,
            announcement_callback=announcement_callback
        )
        
        # Conversation state
        self.messages: List[Dict] = []
        self.current_task: Optional[str] = None
        self._turns_used = 0
        
        # Control flags
        self.is_paused = False
        self.should_stop = False
        
        self.client = self._create_client_for_model(model)
        
        # Tool mappings
        self._setup_tools()
    
    def _create_client_for_model(self, model: str):
        """Create the appropriate LLM client for the selected model."""
        model_lower = (model or "").lower()

        if model_lower.startswith("claude"):
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                try:
                    from anthropic import Anthropic
                    return Anthropic(api_key=api_key)
                except Exception:
                    return None
            return None

        if model_lower.startswith("gemini"):
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key and OPENAI_AVAILABLE:
                try:
                    return OpenAI(
                        api_key=api_key,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                    )
                except Exception:
                    return None
            return None

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and OPENAI_AVAILABLE:
            try:
                return OpenAI(api_key=api_key)
            except Exception:
                return None
        return None

    def _setup_tools(self) -> None:
        """Setup tool function mappings."""
        self.tools = {
            # Browser tools
            "browser_navigate": self._browser_navigate,
            "browser_snapshot": self._browser_snapshot,
            "browser_click_ref": self._browser_click_ref,
            # "browser_click": self._browser_click,  # DISABLED: use browser_click_ref
            "browser_type": self._browser_type,
            "browser_press_key": self._browser_press_key,
            "browser_scroll": self._browser_scroll,
            "browser_back": self._browser_back,
            "browser_forward": self._browser_forward,
            "browser_switch_tab": self._browser_switch_tab,
            "browser_close_tab": self._browser_close_tab,
            "browser_stop": self._browser_stop,
            
            # Desktop tools
            "describe_screen": self._describe_screen,
            "ocr_screen": self._ocr_screen,
            "observe_desktop": self._observe_desktop,
            "open_app": self._open_app,
            "focus_window": self._focus_window,
            "minimize_window": self._minimize_window,
            "maximize_window": self._maximize_window,
            "close_window": self._close_window,
            
            # Input tools
            "click": self._click,
            "right_click": self._right_click,
            "double_click": self._double_click,
            "type_text": self._type_text,
            "press_key": self._press_key,
            "hotkey": self._hotkey,
            "scroll": self._scroll,
            "drag_and_drop": self._drag_and_drop,
            
            # Clipboard tools
            "get_clipboard": self._get_clipboard,
            "set_clipboard": self._set_clipboard,
            
            # Spawn tools
            "spawn_sub_agent": self._spawn_sub_agent,
            "list_sub_agents": self._list_sub_agents,
            "get_sub_agent_result": self._get_sub_agent_result,
            "stop_sub_agent": self._stop_sub_agent,
            
            # Cron tools
            "schedule_job": self._schedule_job,
            "list_scheduled_jobs": self._list_scheduled_jobs,
            "get_scheduled_job": self._get_scheduled_job,
            "update_scheduled_job": self._update_scheduled_job,
            "run_scheduled_job_now": self._run_scheduled_job_now,
            "remove_scheduled_job": self._remove_scheduled_job,
            "enable_job": self._enable_job,
            "disable_job": self._disable_job,
            
            # Utility
            "wait": self._wait,
        }
    
    def _create_sub_agent(self, headless: bool = True) -> 'RefinedAgent':
        """Factory for creating sub-agents."""
        return RefinedAgent(
            model=self.model,
            headless=headless,
            screenshot_dir=str(self.screenshot_dir),
            logger=self.logger
        )
    
    async def _spawn_cron_agent(self, job_id: str, prompt: str) -> None:
        """Callback for cron scheduler to spawn agents."""
        agent = self._create_sub_agent(headless=True)
        # Run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: agent.run(prompt, max_turns=50))
    
    def _log(self, message: str) -> None:
        """Log message via callback or print."""
        if self.logger:
            self.logger(message)
        else:
            print(message)
    
    def _safe_execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute tool with safe error handling."""
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_msg = f"Error executing {func.__name__}: {str(e)}"
            self._log(f"  [ERROR] {error_msg}")
            return {"error": error_msg, "tool": func.__name__}
    
    # ============================================================
    # BROWSER TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _browser_navigate(self, url: str) -> Dict:
        return self._safe_execute(self.browser.navigate, url)
    
    def _browser_snapshot(self) -> Dict:
        return self._safe_execute(self.browser.snapshot)
    
    def _browser_click_ref(self, ref: int) -> Dict:
        return self._safe_execute(self.browser.click_by_ref, ref)
    
    def _browser_click(self, target: str) -> Dict:
        return self._safe_execute(self.browser.click, target)
    
    def _browser_type(self, text: str, clear_first: bool = False) -> Dict:
        return self._safe_execute(self.browser.type, text, clear_first)
    
    def _browser_press_key(self, key: str) -> Dict:
        return self._safe_execute(self.browser.press_key, key)
    
    def _browser_scroll(self, direction: str = "down", amount: int = 300) -> Dict:
        return self._safe_execute(self.browser.scroll, direction, amount)
    
    def _browser_back(self) -> Dict:
        return self._safe_execute(self.browser.back)
    
    def _browser_forward(self) -> Dict:
        return self._safe_execute(self.browser.forward)
    
    def _browser_switch_tab(self, index: int) -> Dict:
        return self._safe_execute(self.browser.switch_tab, index)
    
    def _browser_close_tab(self) -> Dict:
        return self._safe_execute(self.browser.close_tab)
    
    def _browser_stop(self) -> Dict:
        return self._safe_execute(self.browser.stop)
    
    # ============================================================
    # DESKTOP/OBSERVATION TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _describe_screen(self, question: Optional[str] = None) -> Dict:
        """
        Capture the screen for visual analysis.
        The primary model will use the captured image to answer your question.
        """
        if not TESSERACT_AVAILABLE:
            return {"error": "Vision tools not available (missing mss/PIL/pytesseract)"}
            
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
                img.save(path)
                
                with open(path, "rb") as f:
                    base64_image = base64.b64encode(f.read()).decode('utf-8')
                
                return {
                    "image_captured": True,
                    "image_base64": base64_image,
                    "description": "Screenshot captured successfully. Looking at the screen now.",
                    "question": question or "What is on the screen?"
                }
        except Exception as e:
            return {"error": str(e)}
    
    def _ocr_screen(self) -> Dict:
        """OCR screen for text and coordinates."""
        if not TESSERACT_AVAILABLE:
            return {"error": "OCR tools unavailable (missing Pillow/pytesseract)"}
        
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                
                elements = []
                for i in range(len(data['text'])):
                    text = data['text'][i].strip()
                    confidence = int(data['conf'][i])
                    
                    if text and confidence > 30:
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]
                        center_x = x + w // 2
                        center_y = y + h // 2
                        
                        elements.append({
                            "text": text,
                            "x": center_x,
                            "y": center_y,
                            "confidence": confidence
                        })
                
                unfiltered_text = pytesseract.image_to_string(img)
                
                return {
                    "elements": elements[:2000],
                    "unfiltered_text": unfiltered_text[:30000],
                    "total_elements": len(elements)
                }
        except Exception as e:
            return {"error": normalize_tesseract_error(e, pytesseract_module=pytesseract)}
    
    def _observe_desktop(self) -> Dict:
        """List open windows."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Desktop observation not available"}
        
        try:
            desktop = Desktop(backend="uia")
            windows = []
            for win in desktop.windows():
                try:
                    title = win.window_text()
                    if title:
                        windows.append({"title": title, "is_active": win.is_active()})
                except:
                    continue
            return {"windows": windows[:20]}
        except Exception as e:
            return {"error": str(e)}
    
    def _open_app(self, app_name: str) -> Dict:
        """Open application via Win+R."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            pyautogui.hotkey('win', 'r')
            time.sleep(0.3)
            pyautogui.write(app_name)
            pyautogui.press('enter')
            time.sleep(1)
            return {"success": True, "opened": app_name}
        except Exception as e:
            return {"error": str(e)}
    
    def _focus_window(self, title: str) -> Dict:
        """Focus window by title."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Window management not available"}
        
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if matches:
                matches[0].set_focus()
                return {"success": True, "focused": matches[0].window_text()}
            return {"error": f"Window not found: {title}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _minimize_window(self, title: str) -> Dict:
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Window management not available"}
        
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if matches:
                matches[0].minimize()
                return {"success": True}
            return {"error": f"Window not found: {title}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _maximize_window(self, title: str) -> Dict:
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Window management not available"}
        
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if matches:
                matches[0].maximize()
                return {"success": True}
            return {"error": f"Window not found: {title}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _close_window(self, title: str) -> Dict:
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Window management not available"}
        
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if matches:
                matches[0].close()
                return {"success": True}
            return {"error": f"Window not found: {title}"}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # INPUT TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            x = int(float(str(x).split(",")[0].strip()))
            y = int(float(str(y).split(",")[0].strip()))
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.click()
            return {"success": True, "clicked": f"({x}, {y})"}
        except Exception as e:
            return {"error": str(e)}
    
    def _right_click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            x = int(float(str(x).split(",")[0].strip()))
            y = int(float(str(y).split(",")[0].strip()))
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.rightClick()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def _double_click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            x = int(float(str(x).split(",")[0].strip()))
            y = int(float(str(y).split(",")[0].strip()))
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.doubleClick()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def _type_text(self, text: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            pyautogui.write(text, interval=0.02)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}
    
    def _press_key(self, key: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            pyautogui.press(key)
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"error": str(e)}
    
    def _hotkey(self, keys: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            key_list = [k.strip() for k in keys.split('+')]
            pyautogui.hotkey(*key_list)
            return {"success": True, "hotkey": keys}
        except Exception as e:
            return {"error": str(e)}
    
    def _scroll(self, direction: str = "down", amount: int = 3) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            clicks = -amount if direction == "up" else amount
            pyautogui.scroll(clicks)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def _drag_and_drop(self, start_x: int, start_y: int, end_x: int, end_y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "Input automation not available"}
        
        try:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=0.5)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # CLIPBOARD TOOLS
    # ============================================================
    
    def _get_clipboard(self) -> Dict:
        try:
            return {"content": pyperclip.paste()}
        except Exception as e:
            return {"error": str(e)}
    
    def _set_clipboard(self, text: str) -> Dict:
        try:
            pyperclip.copy(text)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # SPAWN TOOLS
    # ============================================================
    
    def _spawn_sub_agent(self, prompt: str, headless: bool = True, max_turns: int = 20) -> Dict:
        """Spawn a sub-agent in the background."""
        import asyncio
        
        try:
            # Run spawn asynchronously
            loop = asyncio.get_event_loop()
            task_id = loop.run_until_complete(
                self.spawn_tool.spawn(prompt, headless=headless, max_turns=max_turns)
            )
            return {
                "success": True,
                "task_id": task_id,
                "message": f"Started background task {task_id}. I'll announce when it completes."
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _list_sub_agents(self) -> Dict:
        """List all sub-agents."""
        try:
            tasks = self.spawn_tool.list_tasks()
            return {
                "tasks": [t.to_dict() for t in tasks]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_sub_agent_result(self, task_id: str) -> Dict:
        """Get sub-agent result."""
        try:
            task = self.spawn_tool.get_task(task_id)
            if not task:
                return {"error": f"Task {task_id} not found"}
            return {
                "task": task.to_dict(),
                "full_result": task.result
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _stop_sub_agent(self, task_id: str) -> Dict:
        """Stop a sub-agent."""
        try:
            success = self.spawn_tool.stop_task(task_id)
            return {"success": success, "stopped": task_id}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # CRON TOOLS
    # ============================================================
    
    def _schedule_job(self, name: str, prompt: str, schedule: str) -> Dict:
        """Schedule a recurring job."""
        try:
            interval, error = parse_schedule_with_error(schedule)
            if error:
                return {"error": error}
            
            job_id = self.cron_scheduler.add_job(
                name,
                prompt,
                interval,
                schedule_text=schedule,
            )
            job = self.cron_scheduler.get_job(job_id)
            return {
                "success": True,
                "job_id": job_id,
                "job": job.to_dict() if job else None,
                "message": f"Scheduled job '{name}' (ID: {job_id}) to run {schedule}"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _list_scheduled_jobs(self) -> Dict:
        """List scheduled jobs."""
        try:
            return self.cron_scheduler.get_status()
        except Exception as e:
            return {"error": str(e)}

    def _get_scheduled_job(self, job_id: str) -> Dict:
        """Get one scheduled job."""
        try:
            job = self.cron_scheduler.get_job(job_id)
            if not job:
                return {"error": f"Job {job_id} not found"}
            return {"success": True, "job": job.to_dict()}
        except Exception as e:
            return {"error": str(e)}

    def _update_scheduled_job(
        self,
        job_id: str,
        name: Optional[str] = None,
        prompt: Optional[str] = None,
        schedule: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Dict:
        """Update an existing scheduled job."""
        try:
            interval = None
            if schedule is not None:
                interval, error = parse_schedule_with_error(schedule)
                if error:
                    return {"error": error}

            success = self.cron_scheduler.update_job(
                job_id,
                name=name,
                prompt=prompt,
                schedule_text=schedule,
                interval_seconds=interval,
                enabled=enabled,
            )
            if not success:
                return {"error": f"Job {job_id} not found"}

            job = self.cron_scheduler.get_job(job_id)
            return {"success": True, "job": job.to_dict() if job else None}
        except Exception as e:
            return {"error": str(e)}

    def _run_scheduled_job_now(self, job_id: str) -> Dict:
        """Queue a scheduled job to run on the next check."""
        try:
            success = self.cron_scheduler.run_job_now(job_id)
            if not success:
                return {"error": f"Job {job_id} not found"}
            return {"success": True, "job_id": job_id}
        except Exception as e:
            return {"error": str(e)}
    
    def _remove_scheduled_job(self, job_id: str) -> Dict:
        """Remove a scheduled job."""
        try:
            success = self.cron_scheduler.remove_job(job_id)
            return {"success": success}
        except Exception as e:
            return {"error": str(e)}
    
    def _enable_job(self, job_id: str) -> Dict:
        """Enable a job."""
        try:
            success = self.cron_scheduler.enable_job(job_id)
            return {"success": success}
        except Exception as e:
            return {"error": str(e)}
    
    def _disable_job(self, job_id: str) -> Dict:
        """Disable a job."""
        try:
            success = self.cron_scheduler.disable_job(job_id)
            return {"success": success}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # UTILITY TOOLS
    # ============================================================
    
    def _wait(self, seconds: float = 1) -> Dict:
        time.sleep(seconds)
        return {"waited": seconds}
    
    # ============================================================
    # MAIN EXECUTION LOOP
    # ============================================================
    
    def run(self, task: str, max_turns: int = 20) -> str:
        """
        Execute a task with the agent.
        
        Args:
            task: Task description/prompt
            max_turns: Maximum turns before stopping
        
        Returns:
            Task result as string
        """
        self._log(f"\n[TASK] {task}")
        
        # Reset state
        self.is_paused = False
        self.should_stop = False
        self.current_task = task
        self._turns_used = 0
        
        # Build system prompt with mode info
        mode_str = "headless" if self.headless else "headed"
        system_prompt = REFINED_AGENT_PROMPT.format(mode=mode_str)
        
        # Initialize conversation
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}"}
        ]
        
        return self._run_loop(max_turns)
    
    def continue_task(self, max_turns: int = 20) -> str:
        """Continue a paused task."""
        if not self.current_task:
            return "No task to continue."
        
        self._log(f"\n[RESUMING] {self.current_task}")
        self.is_paused = False
        self.should_stop = False
        
        self.messages.append({
            "role": "user",
            "content": "Continue the task from where you left off."
        })
        
        return self._run_loop(max_turns)
    
    def _run_loop(self, max_turns: int) -> str:
        """Main execution loop."""
        for turn in range(max_turns):
            # Check control flags
            if self.should_stop:
                self._log(f"⏹️ [STOPPED] at turn {self._turns_used + turn + 1}")
                self.current_task = None
                return f"⏹️ Task stopped at turn {self._turns_used + turn}."
            
            if self.is_paused:
                self._log(f"⏸️ [PAUSED] at turn {self._turns_used + turn + 1}")
                return f"⏸️ Task paused after {self._turns_used + turn} turns. Use /continue to resume."
            
            # Compress context if needed
            if self.context_compressor.should_compress(self.messages):
                self._log("  [COMPRESSING CONTEXT]")
                self.messages = self.context_compressor.compress(self.messages)
            
            self._log(f"\n--- Turn {self._turns_used + turn + 1} ---")
            
            try:
                if self.client is None:
                    raise RuntimeError(f"No LLM client configured for model: {self.model}")

                # Get LLM response
                if self.model.lower().startswith("claude"):
                    system_messages = [m for m in self.messages if m.get("role") == "system"]
                    non_system_messages = [m for m in self.messages if m.get("role") != "system"]
                    system_text = "\n\n".join(str(m.get("content", "")) for m in system_messages) or None
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=2000,
                        system=system_text,
                        tools=self.get_tool_definitions(),
                        messages=non_system_messages,
                    )

                    assistant_text = ""
                    tool_calls = []
                    for block in response.content:
                        if getattr(block, "type", None) == "text":
                            assistant_text += getattr(block, "text", "")
                        elif getattr(block, "type", None) == "tool_use":
                            tool_calls.append(type("ToolCall", (), {
                                "id": block.id,
                                "function": type("Fn", (), {
                                    "name": block.name,
                                    "arguments": json.dumps(block.input)
                                })()
                            })())

                    message = type("Msg", (), {"content": assistant_text or None, "tool_calls": tool_calls})()
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=self.get_tool_definitions(),
                        max_tokens=2000
                    )
                    
                    message = response.choices[0].message
                
                # Check if complete (no tool calls)
                if not message.tool_calls:
                    self._log(f"[COMPLETE] {message.content}")
                    self.current_task = None
                    return message.content or "Task completed."
                
                # Execute tools
                self.messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in (message.tool_calls or [])
                    ] if message.tool_calls else None,
                })
                tool_results = []
                
                for tool_call in message.tool_calls:
                    # Check flags before each tool
                    if self.should_stop:
                        self._log(f"⏹️ [STOPPED] before executing tool")
                        self.current_task = None
                        return f"⏹️ Task stopped during turn {self._turns_used + turn + 1}."
                    
                    if self.is_paused:
                        self._log(f"⏸️ [PAUSED] before executing tool")
                        self.messages.extend(tool_results)
                        return f"⏸️ Task paused. Use /continue to resume."
                    
                    # Execute tool safely
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    
                    self._log(f"  [TOOL] {func_name}({args})")
                    
                    if func_name in self.tools:
                        result = self.tools[func_name](**args)
                    else:
                        result = {"error": f"Unknown tool: {func_name}"}
                    
                    # Truncate long results
                    result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                    if len(result_str) > 2000:
                        result_str = result_str[:2000] + "... (truncated)"
                    
                    self._log(f"  [RESULT] {result_str}")
                    
                    if self.model.lower().startswith("claude"):
                        tool_results.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result_str,
                            }]
                        })
                    else:
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_str
                        })
                
                self.messages.extend(tool_results)
            
            except Exception as e:
                self._log(f"[ERROR] {e}")
                error_msg = f"Error: {str(e)}. Please try a different approach."
                self.messages.append({"role": "user", "content": error_msg})
        
        # Max turns reached
        self._turns_used += max_turns
        last_msg = self.messages[-1]
        content = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")
        return f"{content or 'Task stopped'} (Max turns reached)"
    
    def get_tool_definitions(self) -> List[Dict]:
        """Get all tool definitions in provider-compatible format."""
        tools = (
            BROWSER_TOOL_DEFINITIONS +
            SPAWN_TOOL_DEFINITIONS +
            CRON_TOOL_DEFINITIONS +
            self._get_desktop_tool_definitions()
        )

        if self.model.lower().startswith("claude"):
            converted = []
            for tool in tools:
                if "function" in tool:
                    func = tool["function"]
                    converted.append({
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                    })
                else:
                    converted.append(tool)
            return converted

        return tools
    
    def _get_desktop_tool_definitions(self) -> List[Dict]:
        """Get desktop/input tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "describe_screen",
                    "description": "Use AI vision to describe the current screen state",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "Optional question about the screen"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "ocr_screen",
                    "description": "Read all text on screen using OCR with coordinates",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "observe_desktop",
                    "description": "List all open windows",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open a Windows application by name",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {"type": "string"}
                        },
                        "required": ["app_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "focus_window",
                    "description": "Bring window to front by title",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"}
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click at screen coordinates (use ocr_screen first)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"}
                        },
                        "required": ["x", "y"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Type text using keyboard",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "press_key",
                    "description": "Press a single key (enter, tab, escape, etc)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"}
                        },
                        "required": ["key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "hotkey",
                    "description": "Press key combination like ctrl+c",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keys": {"type": "string"}
                        },
                        "required": ["keys"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_clipboard",
                    "description": "Get clipboard content",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_clipboard",
                    "description": "Copy text to clipboard",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "wait",
                    "description": "Wait for specified seconds",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "seconds": {"type": "number", "default": 1}
                        }
                    }
                }
            }
        ]
    
    def pause(self) -> None:
        """Request pause after current turn."""
        self.is_paused = True
        self._log("[PAUSE REQUESTED]")
    
    def stop(self) -> None:
        """Request immediate stop."""
        self.should_stop = True
        self._log("[STOP REQUESTED]")
    
    def get_context_stats(self) -> Dict[str, Any]:
        """Get context compression stats."""
        return self.context_compressor.get_token_estimate(self.messages)


# Convenience function
def create_refined_agent(
    model: str = "gemini-2.0-flash-exp",
    headless: bool = True,
    **kwargs
) -> RefinedAgent:
    """Factory function to create a RefinedAgent."""
    return RefinedAgent(model=model, headless=headless, **kwargs)
