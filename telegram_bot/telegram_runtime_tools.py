"""Desktop, memory, sub-agent, and scheduler tool handlers for Telegram auto mode."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Any, Dict

from shared.channel_sync import get_channel_sync_hub
from single_agent.cron_scheduler import parse_schedule_with_error

PYAUTOGUI_IMPORT_ERROR = None
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception as exc:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    PYAUTOGUI_IMPORT_ERROR = exc

PYWINAUTO_IMPORT_ERROR = None
try:
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except Exception as exc:
    Desktop = None
    PYWINAUTO_AVAILABLE = False
    PYWINAUTO_IMPORT_ERROR = exc

try:
    import mss
    from PIL import Image
    SCREEN_CAPTURE_AVAILABLE = True
except Exception:
    mss = None
    Image = None
    SCREEN_CAPTURE_AVAILABLE = False

try:
    import pytesseract
    from shared.tesseract_runtime import configure_pytesseract_runtime, normalize_tesseract_error
    configure_pytesseract_runtime(pytesseract)
    OCR_AVAILABLE = SCREEN_CAPTURE_AVAILABLE
except Exception:
    pytesseract = None
    OCR_AVAILABLE = False

TESSERACT_AVAILABLE = OCR_AVAILABLE

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

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
            location = f"{r['source']}:{r['line']}" if r.get("line") is not None else r["source"]
            output.append(f"**{location}**\n{r['content']}")
        return '\n\n---\n\n'.join(output)
    except Exception as e:
        return f"Error searching memory: {str(e)}"


def _execute_update_memory(session, args: Dict) -> str:
    try:
        updated = session.memory_manager.append_to_memory(args['section'], args['content'])
        if updated:
            return f"Updated {args['section']} in MEMORY.md"
        return f"No change made to {args['section']} in MEMORY.md"
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

        session.set_workspace(path)
        session.save_session()
        current_session_id = session.session_manager.get_current_session_id() if session.session_manager else None
        if current_session_id:
            origin_channel = "telegram" if getattr(session, "_app", None) else "app"
            sync_user_id = getattr(session, "sync_user_id", None)
            get_channel_sync_hub().publish(
                user_id=int(sync_user_id) if sync_user_id is not None else int(session.user_id),
                event={
                    "type": "session_config",
                    "session_id": current_session_id,
                    "origin_channel": origin_channel,
                    "payload": {"setting": "workspace"},
                },
            )

        return f"Current working directory changed to: {path}"
    except Exception as e:
        return f"Error changing directory: {str(e)}"


def _execute_describe_screen(session, args: Dict) -> Dict:
    if not SCREEN_CAPTURE_AVAILABLE:
        return {"error": "Screenshot tools unavailable (missing mss/Pillow)"}

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
    if not OCR_AVAILABLE:
        return "OCR tools unavailable (missing pytesseract/Tesseract runtime)"

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
        return f"Error performing OCR: {normalize_tesseract_error(e, pytesseract_module=pytesseract)}"


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
        # Robust parsing in case model sends strings or comma-separated values
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))

        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    except Exception as e:
        return f"Error clicking: {str(e)}"


def _execute_right_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))
        pyautogui.rightClick(x, y)
        return f"Right-clicked at ({x}, {y})"
    except Exception as e:
        return f"Error right-clicking: {str(e)}"


def _execute_double_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))
        pyautogui.doubleClick(x, y)
        return f"Double-clicked at ({x}, {y})"
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
        return (
            f"Launch request sent for: {args['name']}. "
            "This does not confirm success; verify the resulting window or error state visually before assuming the app opened."
        )
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


def _execute_schedule_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        interval, error = parse_schedule_with_error(args["schedule"])
        if error:
            return {"error": error}

        job_id = session.cron_scheduler.add_job(
            name=args["name"],
            prompt=args["prompt"],
            interval_seconds=interval,
            schedule_text=args["schedule"],
            timezone_offset_hours=2,
        )
        job = session.cron_scheduler.get_job(job_id)
        return {
            "success": True,
            "job_id": job_id,
            "job": job.to_dict() if job else None,
            "message": f"Job '{args['name']}' scheduled: {args['schedule']} (ID: {job_id})",
        }
    except Exception as e:
        return {"error": f"Error scheduling job: {str(e)}"}


def _execute_list_scheduled_jobs(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        return session.cron_scheduler.get_status()
    except Exception as e:
        return {"error": f"Error listing jobs: {str(e)}"}


def _execute_get_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        job = session.cron_scheduler.get_job(args["job_id"])
        if not job:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job": job.to_dict()}
    except Exception as e:
        return {"error": f"Error getting job: {str(e)}"}


def _execute_update_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        interval = None
        schedule = args.get("schedule")
        if schedule is not None:
            interval, error = parse_schedule_with_error(schedule)
            if error:
                return {"error": error}

        success = session.cron_scheduler.update_job(
            args["job_id"],
            name=args.get("name"),
            prompt=args.get("prompt"),
            schedule_text=schedule,
            interval_seconds=interval,
            enabled=args.get("enabled"),
            timezone_offset_hours=2,
        )
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error updating job: {str(e)}"}


def _execute_run_scheduled_job_now(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.run_job_now(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job_id": args["job_id"]}
    except Exception as e:
        return {"error": f"Error triggering job: {str(e)}"}


def _execute_remove_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        deleted = session.cron_scheduler.remove_job(args["job_id"])
        if not deleted:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job_id": args["job_id"]}
    except Exception as e:
        return {"error": f"Error removing job: {str(e)}"}


def _execute_enable_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.enable_job(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error enabling job: {str(e)}"}


def _execute_disable_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.disable_job(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error disabling job: {str(e)}"}
