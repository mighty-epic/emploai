"""
Unified agent helpers for the Telegram agent.
"""

import asyncio
import logging
import time
import base64
from pathlib import Path
from typing import Any, Dict, Callable

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

try:
    import mss
    from PIL import Image
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

from telegram.constants import ParseMode
from shared import (
    create_unified_agent,
    get_heartbeat_manager,
)
from single_agent.browser_tool import create_browser_tool


logger = logging.getLogger(__name__)


def create_unified_agent_for_task(session, app, loop) -> None:
    """Create a unified agent that works with ANY model."""
    session._app = app
    session._loop = loop

    def logger_func(text: str):
        print(f"[AGENT] {text}")
        if session._app and session._loop:
            asyncio.run_coroutine_threadsafe(
                session._send_log(text), session._loop
            )

    client, provider = session.get_client_for_model()

    if not client:
        logger.error(f"No API key for provider: {provider}")
        raise ValueError(
            f"No API key configured for {provider}. Set {provider.upper()}_API_KEY environment variable."
        )

    from cli.tui_constants import UNIFIED_AGENT_PROMPT
    
    # Build system prompt with skills index
    skills_index = ""
    if hasattr(session, "skill_registry") and session.skill_registry:
        skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
    
    system_prompt = UNIFIED_AGENT_PROMPT + skills_index

    session.unified_agent = create_unified_agent(
        model_name=session.current_model,
        client=client,
        tool_executor=_build_unified_tool_executor(session),
        workspace=session.workspace,
        logger_func=logger_func,
        system_prompt=system_prompt
    )

    if session.live_config.get('heartbeat.enabled', False):
        def heartbeat_agent_callback(prompt: str) -> str:
            return session.unified_agent.run(prompt, max_turns=10)

        def heartbeat_announcement(text: str):
            if session._app:
                asyncio.run_coroutine_threadsafe(
                    session._app.bot.send_message(
                        chat_id=session.user_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    loop
                )

        session.heartbeat_manager = get_heartbeat_manager(
            workspace=session.workspace,
            interval_seconds=session.live_config.get('heartbeat.interval_seconds', 1800),
            announcement_callback=heartbeat_announcement,
            agent_callback=heartbeat_agent_callback
        )
        session.heartbeat_manager.start()


def _build_unified_tool_executor(session) -> Callable[[str, Dict], Any]:
    tool_map = {
        'read_file': lambda args: _execute_read_file(session, args),
        'write_file': lambda args: _execute_write_file(session, args),
        'edit_file': lambda args: _execute_edit_file(session, args),
        'list_files': lambda args: _execute_list_files(session, args),
        'execute_command': lambda args: _execute_command(session, args),
        'web_search': lambda args: _execute_web_search(session, args),
        'fetch_url': lambda args: _execute_fetch_url(session, args),
        'browser_navigate': lambda args: _execute_browser_navigate(session, args),
        'browser_click': lambda args: _execute_browser_click(session, args),
        'browser_type': lambda args: _execute_browser_type(session, args),
        'browser_screenshot': lambda args: _execute_browser_screenshot(session, args),
        'browser_snapshot': lambda args: _execute_browser_snapshot(session, args),
        'browser_click_ref': lambda args: _execute_browser_click_ref(session, args),
        'browser_back': lambda args: _execute_browser_back(session, args),
        'browser_forward': lambda args: _execute_browser_forward(session, args),
        'browser_switch_tab': lambda args: _execute_browser_switch_tab(session, args),
        'browser_close_tab': lambda args: _execute_browser_close_tab(session, args),
        'browser_stop': lambda args: _execute_browser_stop(session, args),
        'search_memory': lambda args: _execute_search_memory(session, args),
        'update_memory': lambda args: _execute_update_memory(session, args),
        'change_directory': lambda args: _execute_change_directory(session, args),
        'describe_screen': lambda args: _execute_describe_screen(session, args),
        'ocr_screen': lambda args: _execute_ocr_screen(session, args),
        'observe_desktop': lambda args: _execute_observe_desktop(session, args),
        'click': lambda args: _execute_click(session, args),
        'right_click': lambda args: _execute_right_click(session, args),
        'double_click': lambda args: _execute_double_click(session, args),
        'type_text': lambda args: _execute_type_text(session, args),
        'press_key': lambda args: _execute_press_key(session, args),
        'hotkey': lambda args: _execute_hotkey(session, args),
        'scroll': lambda args: _execute_scroll(session, args),
        'open_app': lambda args: _execute_open_app(session, args),
        'focus_window': lambda args: _execute_focus_window(session, args),
        'get_clipboard': lambda args: _execute_get_clipboard(session, args),
        'set_clipboard': lambda args: _execute_set_clipboard(session, args),
        'spawn_sub_agent': lambda args: _execute_spawn_sub_agent(session, args),
        'list_sub_agents': lambda args: _execute_list_sub_agents(session, args),
        'schedule_job': lambda args: _execute_schedule_job(session, args),
        'list_scheduled_jobs': lambda args: _execute_list_scheduled_jobs(session, args),
        'remove_scheduled_job': lambda args: _execute_remove_scheduled_job(session, args),
    }

    def unified_tool_executor(tool_name: str, tool_args: Dict) -> Any:
        executor = tool_map.get(tool_name)
        if executor:
            return executor(tool_args)
        return f"Unknown tool: {tool_name}"

    return unified_tool_executor


def _execute_read_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
            
        if not path.exists():
            return f"File not found: {path}"
        content = path.read_text(encoding='utf-8')
        if 'start_line' in args or 'end_line' in args:
            lines = content.split('\n')
            start = args.get('start_line', 1) - 1
            end = args.get('end_line', len(lines))
            content = '\n'.join(lines[start:end])
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def _execute_write_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args['content'], encoding='utf-8')
        return f"Wrote {len(args['content'])} chars to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def _execute_edit_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
            
        if not path.exists():
            return f"File not found: {path}"
        content = path.read_text(encoding='utf-8')
        old_text = args['old_text']
        new_text = args['new_text']
        if old_text not in content:
            return f"Text not found in file: {old_text[:50]}..."
        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding='utf-8')
        return f"Edited {path}"
    except Exception as e:
        return f"Error editing file: {str(e)}"


def _execute_list_files(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        if not path.exists():
            return f"Directory not found: {path}"
        if not path.is_dir():
            return f"Not a directory: {path}"
        recursive = args.get('recursive', False)
        pattern = '**/*' if recursive else '*'
        files = list(path.glob(pattern))
        if len(files) > 100:
            files = files[:100]
            result = '\n'.join(str(f) for f in files)
            result += f"\n... and {len(files) - 100} more files"
            return result
        return '\n'.join(str(f) for f in files)
    except Exception as e:
        return f"Error listing files: {str(e)}"


def _execute_command(session, args: Dict) -> str:
    try:
        import subprocess
        result = subprocess.run(
            args['command'],
            shell=True,
            cwd=args.get('cwd') or str(session.workspace),
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout or result.stderr or "(no output)"
        return output[:5000]
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def _execute_web_search(session, args: Dict) -> str:
    return f"Web search for '{args['query']}' - Not implemented yet"


def _execute_fetch_url(session, args: Dict) -> str:
    try:
        import requests
        response = requests.get(args['url'], timeout=10)
        response.raise_for_status()
        return response.text[:5000]
    except Exception as e:
        return f"Error fetching URL: {str(e)}"


def _get_browser_tool(session):
    """Get the browser tool for this session, creating if needed."""
    if hasattr(session, 'browser_tool') and session.browser_tool:
        return session.browser_tool
    
    # Try to reuse from refined_agent
    if session.refined_agent and hasattr(session.refined_agent, 'browser') and session.refined_agent.browser:
        session.browser_tool = session.refined_agent.browser
        return session.browser_tool
        
    # Create new
    session.browser_tool = create_browser_tool(headless=True)
    return session.browser_tool


def _execute_browser_navigate(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.navigate(args['url'])
    if "error" in result:
        return f"Browser error: {result['error']}"
    return f"Navigated to {result['url']} - {result['title']}"


def _execute_browser_click(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.click(args['target'])
    if "error" in result:
        return f"Click error: {result['error']}"
    return "Clicked successfully"


def _execute_browser_type(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.type(args['text'], clear_first=args.get('clear_first', False))
    if "error" in result:
        return f"Type error: {result['error']}"
    return f"Typed: {args['text']}"


def _execute_browser_screenshot(session, args: Dict) -> Dict:
    browser = _get_browser_tool(session)
    if not browser.driver:
        return {"error": "Browser not started"}
    try:
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        path = temp_dir / f"browser_{int(time.time())}.png"
        browser.driver.save_screenshot(str(path))
        
        with open(path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
            
        return {
            "image_captured": True,
            "image_base64": base64_image,
            "description": f"Browser screenshot captured successfully.",
            "metadata": {"path": str(path)}
        }
    except Exception as e:
        return {"error": f"Screenshot error: {str(e)}"}


def _execute_browser_snapshot(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.snapshot()
    if "error" in result:
        return f"Snapshot error: {result['error']}"
    return f"Browser ARIA Snapshot:\n{result['formatted']}"


def _execute_browser_click_ref(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.click_by_ref(args['ref'])
    if "error" in result:
        return f"Click ref error: {result['error']}"
    return f"Clicked element ref={args['ref']}"


def _execute_browser_back(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.back()
    if "error" in result: return result['error']
    return f"Went back to {result.get('url')}"


def _execute_browser_forward(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.forward()
    if "error" in result: return result['error']
    return f"Went forward to {result.get('url')}"


def _execute_browser_switch_tab(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.switch_tab(args['index'])
    if "error" in result: return result['error']
    return f"Switched to tab {args['index']}"


def _execute_browser_close_tab(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.close_tab()
    if "error" in result: return result['error']
    return "Closed current tab"


def _execute_browser_stop(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.stop()
    if "error" in result: return result['error']
    return "Browser stopped"


def _execute_search_memory(session, args: Dict) -> str:
    try:
        results = session.memory_manager.search_memory(
            args['query'],
            max_results=args.get('max_results', 5)
        )
        if not results:
            return f"No memory results found for: {args['query']}"
        output = []
        for r in results:
            output.append(f"**{r['source']}:{r['line']}**\n{r['content']}")
        return '\n\n---\n\n'.join(output)
    except Exception as e:
        return f"Error searching memory: {str(e)}"


def _execute_update_memory(session, args: Dict) -> str:
    try:
        session.memory_manager.append_to_memory(args['section'], args['content'])
        return f"Updated {args['section']} in MEMORY.md"
    except Exception as e:
        return f"Error updating memory: {str(e)}"


def _execute_change_directory(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        
        if not path.exists():
            return f"Directory not found: {path}"
        if not path.is_dir():
            return f"Not a directory: {path}"
            
        session.workspace = path
        if session.tool_executor:
            session.tool_executor.workspace_path = path

        return f"Current working directory changed to: {path}"
    except Exception as e:
        return f"Error changing directory: {str(e)}"


def _execute_describe_screen(session, args: Dict) -> Dict:
    if not TESSERACT_AVAILABLE:
        return {"error": "Vision/Screenshot tools not available (missing mss/PIL/pytesseract)"}
    
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Save temp screenshot
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            path = temp_dir / f"screen_{int(time.time())}.png"
            img.save(path)
            
            with open(path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode('utf-8')
            
            return {
                "image_captured": True,
                "image_base64": base64_image,
                "description": "Screenshot captured successfully. I am now looking at the screen.",
                "metadata": {"path": str(path)}
            }
    except Exception as e:
        return {"error": f"Error describing screen: {str(e)}"}


def _execute_ocr_screen(session, args: Dict) -> str:
    if not TESSERACT_AVAILABLE:
        return "OCR tools not available"
    
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            elements = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if text and int(data['conf'][i]) > 40:
                    elements.append({
                        "text": text,
                        "x": data['left'][i] + data['width'][i] // 2,
                        "y": data['top'][i] + data['height'][i] // 2
                    })
            
            text_summary = "\n".join([f"'{e['text']}' at ({e['x']}, {e['y']})" for e in elements[:100]])
            return f"OCR Elements found:\n{text_summary}"
    except Exception as e:
        return f"Error performing OCR: {str(e)}"


def _execute_observe_desktop(session, args: Dict) -> str:
    if not PYWINAUTO_AVAILABLE:
        return "Desktop automation not available"
    
    try:
        desktop = Desktop(backend="uia")
        windows = []
        for win in desktop.windows():
            title = win.window_text()
            if title:
                windows.append(title)
        return "Open Windows:\n" + "\n".join(windows[:20])
    except Exception as e:
        return f"Error listing windows: {str(e)}"


def _execute_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.click(args['x'], args['y'])
        return f"Clicked at ({args['x']}, {args['y']})"
    except Exception as e:
        return f"Error clicking: {str(e)}"


def _execute_right_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.rightClick(args['x'], args['y'])
        return f"Right-clicked at ({args['x']}, {args['y']})"
    except Exception as e:
        return f"Error right-clicking: {str(e)}"


def _execute_double_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.doubleClick(args['x'], args['y'])
        return f"Double-clicked at ({args['x']}, {args['y']})"
    except Exception as e:
        return f"Error double-clicking: {str(e)}"


def _execute_type_text(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.write(args['text'], interval=0.01)
        return f"Typed: {args['text']}"
    except Exception as e:
        return f"Error typing: {str(e)}"


def _execute_press_key(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.press(args['key'])
        return f"Pressed key: {args['key']}"
    except Exception as e:
        return f"Error pressing key: {str(e)}"


def _execute_hotkey(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        keys = args['keys'].split('+')
        pyautogui.hotkey(*keys)
        return f"Pressed hotkey: {args['keys']}"
    except Exception as e:
        return f"Error pressing hotkey: {str(e)}"


def _execute_scroll(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        amount = args.get('amount', 3)
        clicks = -amount if args['direction'] == 'up' else amount
        pyautogui.scroll(clicks)
        return f"Scrolled {args['direction']} {amount} units"
    except Exception as e:
        return f"Error scrolling: {str(e)}"


def _execute_open_app(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.hotkey('win', 'r')
        time.sleep(0.5)
        pyautogui.write(args['name'])
        pyautogui.press('enter')
        return f"Attempted to open: {args['name']}"
    except Exception as e:
        return f"Error opening app: {str(e)}"


def _execute_focus_window(session, args: Dict) -> str:
    if not PYWINAUTO_AVAILABLE: return "pywinauto not available"
    try:
        desktop = Desktop(backend="uia")
        matches = [w for w in desktop.windows() if args['title'].lower() in w.window_text().lower()]
        if matches:
            matches[0].set_focus()
            return f"Focused window: {matches[0].window_text()}"
        return f"Window not found: {args['title']}"
    except Exception as e:
        return f"Error focusing window: {str(e)}"


def _execute_get_clipboard(session, args: Dict) -> str:
    if not PYPERCLIP_AVAILABLE: return "pyperclip not available"
    try:
        return f"Clipboard content: {pyperclip.paste()}"
    except Exception as e:
        return f"Error reading clipboard: {str(e)}"


def _execute_set_clipboard(session, args: Dict) -> str:
    if not PYPERCLIP_AVAILABLE: return "pyperclip not available"
    try:
        session.memory_manager.copy_to_clipboard(args['text'])
        return "Clipboard updated"
    except Exception as e:
        return f"Error setting clipboard: {str(e)}"


def _execute_spawn_sub_agent(session, args: Dict) -> str:
    if not session.spawn_tool:
        return "Spawn tool not initialized"
    try:
        prompt = args['prompt']
        headless = args.get('headless', True)
        # Use our session's loop to run the async spawn
        future = asyncio.run_coroutine_threadsafe(
            session.spawn_tool.spawn(prompt, headless=headless, max_turns=50, announce_on_complete=True),
            session._loop
        )
        task_id = future.result(timeout=10)
        return f"Spawned sub-agent task {task_id}. I'll announce when it completes."
    except Exception as e:
        return f"Error spawning sub-agent: {str(e)}"


def _execute_list_sub_agents(session, args: Dict) -> str:
    if not session.spawn_tool:
        return "Spawn tool not initialized"
    try:
        tasks = session.spawn_tool.list_tasks()
        if not tasks:
            return "No background tasks running"
        lines = []
        for t in tasks:
            lines.append(f"Task {t.id}: {t.status} - {t.prompt[:50]}...")
        return "Running Tasks:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


def _execute_schedule_job(session, args: Dict) -> str:
    if not session.cron_scheduler:
        return "Cron scheduler not initialized"
    try:
        session.cron_scheduler.add_job(
            name=args['name'],
            prompt=args['prompt'],
            schedule_str=args['schedule']
        )
        return f"Job '{args['name']}' scheduled: {args['schedule']}"
    except Exception as e:
        return f"Error scheduling job: {str(e)}"


def _execute_list_scheduled_jobs(session, args: Dict) -> str:
    if not session.cron_scheduler:
        return "Cron scheduler not initialized"
    try:
        jobs = session.cron_scheduler.list_jobs()
        if not jobs:
            return "No scheduled jobs"
        lines = []
        for j in jobs:
            status = "Enabled" if j.get('enabled', True) else "Disabled"
            lines.append(f"[{status}] {j['id']}: {j['schedule']} - {j['prompt'][:30]}...")
        return "Scheduled Jobs:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error listing jobs: {str(e)}"


def _execute_remove_scheduled_job(session, args: Dict) -> str:
    if not session.cron_scheduler:
        return "Cron scheduler not initialized"
    try:
        deleted = session.cron_scheduler.remove_job(args['job_id'])
        if deleted:
            return f"Job {args['job_id']} removed"
        return f"Job {args['job_id']} not found"
    except Exception as e:
        return f"Error removing job: {str(e)}"
