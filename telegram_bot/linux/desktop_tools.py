"""
Linux replacements for Windows-only desktop automation tools.

This module intentionally overrides the generic desktop path on Linux/X11:
- window management -> `wmctrl` / `xdotool`
- screenshots / OCR -> `scrot` + `pytesseract`
- physical input -> `xdotool`
- app launch -> direct command execution / `xdg-open`

The VPS deployment runs on Xvfb/Openbox, so X11-native tools are more reliable
than the generic `mss` + `pyautogui` path for live headed automation.
"""

from __future__ import annotations

import base64
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, Tuple
from shared.tesseract_runtime import configure_pytesseract_runtime, normalize_tesseract_error

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - exercised via feature checks
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

try:
    import pytesseract
    configure_pytesseract_runtime(pytesseract)
except ImportError:  # pragma: no cover - exercised via feature checks
    pytesseract = None

try:
    import mss
except ImportError:  # pragma: no cover - exercised via feature checks
    mss = None


OCR_AVAILABLE = Image is not None and pytesseract is not None
MSS_AVAILABLE = Image is not None and mss is not None


def _has_command(cmd: str) -> bool:
    """Check if a system command is available on PATH."""
    return shutil.which(cmd) is not None


def _float_conf(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return -1.0


def _parse_coordinate(value: object) -> int:
    text = str(value).split(",")[0].strip()
    return int(float(text))


def _temp_capture_path(prefix: str = "screen") -> Path:
    preferred_dir = Path("local_agent_runtime/screenshots")
    preferred_dir.mkdir(parents=True, exist_ok=True)
    return preferred_dir / f"{prefix}_{int(time.time() * 1000)}.png"


def _capture_screenshot_path(prefix: str = "screen") -> Path:
    path = _temp_capture_path(prefix)

    if _has_command("scrot"):
        result = subprocess.run(
            ["scrot", "-z", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ.copy(),
        )
        if result.returncode == 0 and path.exists():
            return path
        raise RuntimeError(result.stderr.strip() or "scrot failed to capture the X11 display")

    if MSS_AVAILABLE:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            image.save(path)
            return path

    raise RuntimeError("Screenshot capture unavailable (install scrot or mss)")


def _load_image(path: Path):
    if Image is None:
        raise RuntimeError("Pillow is not available")
    with Image.open(path) as image:
        return image.convert("RGB")


def _ocr_variants(image) -> Iterable[tuple[str, object]]:
    yield "raw", image

    grayscale = ImageOps.grayscale(image)
    high_contrast = ImageEnhance.Contrast(grayscale).enhance(1.8)
    sharpened = high_contrast.filter(ImageFilter.SHARPEN)
    yield "contrast", sharpened

    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    upscaled = sharpened.resize(
        (max(1, int(image.width * 1.35)), max(1, int(image.height * 1.35))),
        resampling,
    )
    yield "upscaled", upscaled


def _extract_line_elements(data: Dict[str, list], min_confidence: float = 35.0) -> list[Dict[str, object]]:
    lines: dict[tuple[int, int, int], Dict[str, object]] = {}
    total_boxes = len(data.get("text", []))

    for i in range(total_boxes):
        text = str(data["text"][i]).strip()
        confidence = _float_conf(data["conf"][i])
        if not text or confidence < min_confidence:
            continue

        key = (
            int(data.get("block_num", [0] * total_boxes)[i]),
            int(data.get("par_num", [0] * total_boxes)[i]),
            int(data.get("line_num", [i])[i]),
        )
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        entry = lines.setdefault(
            key,
            {
                "tokens": [],
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
                "confidences": [],
            },
        )
        entry["tokens"].append(text)
        entry["left"] = min(int(entry["left"]), left)
        entry["top"] = min(int(entry["top"]), top)
        entry["right"] = max(int(entry["right"]), left + width)
        entry["bottom"] = max(int(entry["bottom"]), top + height)
        entry["confidences"].append(confidence)

    elements = []
    for line in lines.values():
        text = " ".join(line["tokens"]).strip()
        if not text:
            continue
        left = int(line["left"])
        top = int(line["top"])
        right = int(line["right"])
        bottom = int(line["bottom"])
        width = max(1, right - left)
        height = max(1, bottom - top)
        confidences = line["confidences"] or [0.0]
        elements.append(
            {
                "text": text,
                "x": left + width // 2,
                "y": top + height // 2,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "confidence": round(sum(confidences) / len(confidences), 2),
            }
        )

    elements.sort(key=lambda item: (int(item["top"]), int(item["left"])))
    return elements


def _extract_best_ocr(image) -> Dict[str, object]:
    if not OCR_AVAILABLE:
        raise RuntimeError("OCR tools are not available (missing Pillow/pytesseract)")

    best: Dict[str, object] | None = None
    best_score: tuple[int, float, int] = (-1, -1.0, -1)
    best_plain_text = ""
    config = "--oem 3 --psm 11"

    for variant_name, variant_image in _ocr_variants(image):
        data = pytesseract.image_to_data(
            variant_image,
            output_type=pytesseract.Output.DICT,
            config=config,
        )
        elements = _extract_line_elements(data)
        confidences = [float(item["confidence"]) for item in elements if item.get("confidence") is not None]
        average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        plain_text = pytesseract.image_to_string(variant_image, config=config).strip()
        score = (len(elements), average_confidence, len(plain_text))
        if score > best_score:
            best_score = score
            best_plain_text = plain_text
            best = {
                "elements": elements[:500],
                "variant": variant_name,
                "average_confidence": round(average_confidence, 2),
            }

    if best is None:
        best = {"elements": [], "variant": "none", "average_confidence": 0.0}

    best["unfiltered_text"] = best_plain_text[:30000]
    best["plain_text"] = best_plain_text[:30000]
    best["total_elements"] = len(best["elements"])
    return best


def _display_geometry() -> Tuple[int, int] | None:
    if not _has_command("xdotool"):
        return None
    try:
        output = subprocess.check_output(
            ["xdotool", "getdisplaygeometry"],
            text=True,
            timeout=5,
        ).strip()
        width_text, height_text = output.split()
        return int(width_text), int(height_text)
    except Exception:
        return None


def _clamp_coordinates(x: int, y: int) -> tuple[int, int, bool]:
    geometry = _display_geometry()
    if not geometry:
        return x, y, False

    width, height = geometry
    clamped_x = max(0, min(width - 1, x))
    clamped_y = max(0, min(height - 1, y))
    return clamped_x, clamped_y, (clamped_x != x or clamped_y != y)


_KEY_ALIASES = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "pgup": "Page_Up",
    "pgdn": "Page_Down",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "space": "space",
    "tab": "Tab",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def _normalize_key_name(key: str) -> str:
    return _KEY_ALIASES.get(key.strip().lower(), key.strip())


def _execute_pointer_action(args: Dict, *, button: int, action_name: str, repeat: int = 1) -> Dict[str, object]:
    if not _has_command("xdotool"):
        return {"error": "Input automation unavailable (install xdotool)"}

    try:
        raw_x = _parse_coordinate(args["x"])
        raw_y = _parse_coordinate(args["y"])
        x, y, was_clamped = _clamp_coordinates(raw_x, raw_y)

        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], check=True, timeout=5)
        click_args = ["xdotool", "click"]
        if repeat > 1:
            click_args.extend(["--repeat", str(repeat), "--delay", "120"])
        click_args.append(str(button))
        subprocess.run(click_args, check=True, timeout=5)
        return {
            "success": True,
            action_name: f"({x}, {y})",
            "raw_target": f"({raw_x}, {raw_y})",
            "x": x,
            "y": y,
            "clamped_to_display": was_clamped,
            "backend": "xdotool",
            "NEXT": "Call ocr_screen or describe_screen now to verify the UI changed before the next physical action.",
        }
    except Exception as e:
        return {"error": f"Error performing {action_name}: {str(e)}"}


_APP_ALIASES = {
    "browser": ["xdg-open"],
    "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "google chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "chromium": ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"],
    "terminal": ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "lxterminal", "xterm"],
}

_CHROME_DEFAULT_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
]


def _resolve_launch_command(name: str) -> list[str] | None:
    """Resolve a user/model-provided app name to an executable command."""
    try:
        parts = shlex.split(name)
    except ValueError:
        parts = [name]

    if not parts:
        return None

    base = parts[0]
    if _has_command(base):
        return parts

    alias_keys = [name.strip().lower()]
    if base.lower() not in alias_keys:
        alias_keys.append(base.lower())

    for key in alias_keys:
        for candidate in _APP_ALIASES.get(key, []):
            if _has_command(candidate):
                return [candidate, *parts[1:]]

    return None


def _is_chrome_command(command: list[str]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    return executable in {
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    }


def _with_chrome_defaults(command: list[str]) -> list[str]:
    if not _is_chrome_command(command):
        return command

    existing_flags = set(command[1:])
    extras = [flag for flag in _CHROME_DEFAULT_FLAGS if flag not in existing_flags]
    return [*command, *extras]


def _chrome_launch_runtime_error(command: list[str]) -> str | None:
    """Return a helpful deployment/runtime error for invalid Chrome launches."""
    if not _is_chrome_command(command):
        return None

    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid) and geteuid() == 0:
        return (
            "Headed Chrome cannot be launched as root on Linux. Run the X11 "
            "display session and telegram agent under the same non-root user "
            "(for example, 'emploai')."
        )

    return None


# ==========================================================================
# OBSERVE DESKTOP — replaces pywinauto Desktop().windows()
# ==========================================================================

def _execute_observe_desktop(session, args: Dict) -> str:
    """List open windows using wmctrl or xdotool."""
    try:
        active_title = ""
        if _has_command("xdotool"):
            try:
                active_title = subprocess.check_output(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    text=True,
                    timeout=2,
                ).strip()
            except Exception:
                active_title = ""

        if _has_command("wmctrl"):
            try:
                output = subprocess.check_output(
                    ["wmctrl", "-l"], text=True, timeout=5
                )
                lines = output.strip().splitlines()
                titles = []
                for line in lines:
                    # wmctrl -l format: <window_id> <desktop> <host> <title>
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        title = parts[3]
                        prefix = "* " if active_title and title == active_title else "- "
                        titles.append(prefix + title)
                if titles:
                    return "Open Windows:\n" + "\n".join(titles[:20])
            except Exception:
                pass

        if _has_command("xdotool"):
            output = subprocess.check_output(
                ["xdotool", "search", "--name", ""],
                text=True, timeout=5
            )
            window_ids = output.strip().splitlines()[:20]
            titles = []
            for wid in window_ids:
                try:
                    name = subprocess.check_output(
                        ["xdotool", "getwindowname", wid],
                        text=True, timeout=2
                    ).strip()
                    if name and len(name) > 2:
                        prefix = "* " if active_title and name == active_title else "- "
                        titles.append(prefix + name)
                except Exception:
                    pass
            if titles:
                return "Open Windows:\n" + "\n".join(titles[:20])
            return "No windows found."

        return "Desktop observation unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error listing windows: {str(e)}"


# ==========================================================================
# FOCUS WINDOW — replaces pywinauto set_focus()
# ==========================================================================

def _execute_focus_window(session, args: Dict) -> str:
    """Focus a window by title using wmctrl or xdotool."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Focused window matching: {title}"
            return f"Window not found: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowactivate", window_ids[0]],
                    timeout=5
                )
                return f"Focused window: {title}"
            return f"Window not found: {title}"

        return "Window focus unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error focusing window: {str(e)}"


# ==========================================================================
# MINIMIZE WINDOW — replaces pywinauto minimize()
# ==========================================================================

def _execute_minimize_window(session, args: Dict) -> str:
    """Minimize a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowminimize", window_ids[0]],
                    timeout=5
                )
                return f"Minimized window: {title}"
            return f"Window not found: {title}"

        return "Window minimize unavailable (install xdotool)"
    except Exception as e:
        return f"Error minimizing window: {str(e)}"


# ==========================================================================
# MAXIMIZE WINDOW — replaces pywinauto maximize()
# ==========================================================================

def _execute_maximize_window(session, args: Dict) -> str:
    """Maximize a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            # wmctrl can maximize by removing then adding maximized state
            subprocess.run(
                ["wmctrl", "-r", title, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True, text=True, timeout=5
            )
            return f"Maximized window: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                # Use wmctrl-style maximize via key simulation
                subprocess.run(
                    ["xdotool", "windowactivate", window_ids[0]],
                    timeout=5
                )
                subprocess.run(
                    ["xdotool", "key", "super+Up"],
                    timeout=5
                )
                return f"Maximized window: {title}"
            return f"Window not found: {title}"

        return "Window maximize unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error maximizing window: {str(e)}"


# ==========================================================================
# CLOSE WINDOW — replaces pywinauto close()
# ==========================================================================

def _execute_close_window(session, args: Dict) -> str:
    """Close a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            result = subprocess.run(
                ["wmctrl", "-c", title],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Closed window: {title}"
            return f"Window not found: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowclose", window_ids[0]],
                    timeout=5
                )
                return f"Closed window: {title}"
            return f"Window not found: {title}"

        return "Window close unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error closing window: {str(e)}"


# ==========================================================================
# OPEN APP — replaces Win+R hotkey approach
# ==========================================================================

def _execute_open_app(session, args: Dict) -> str:
    """Open an application using direct command or xdg-open."""
    # Support both 'name' (from telegram_unified_agent) and 'app_name' (from SingleAgent)
    name = args.get("name") or args.get("app_name", "")
    if not name:
        return "Error: 'name' argument is required"

    try:
        launch_cmd = _resolve_launch_command(name)
        if launch_cmd:
            launch_cmd = _with_chrome_defaults(launch_cmd)
            runtime_error = _chrome_launch_runtime_error(launch_cmd)
            if runtime_error:
                return runtime_error
            subprocess.Popen(
                launch_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
            return f"Launched: {' '.join(launch_cmd)}"

        # Try xdg-open (for URLs, file types, etc.)
        if _has_command("xdg-open"):
            subprocess.Popen(
                ["xdg-open", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
            return f"Attempted to open: {name}"

        return f"Cannot open '{name}' — command not found and xdg-open unavailable"
    except Exception as e:
        return f"Error opening app: {str(e)}"


# ==========================================================================
# SCREEN CAPTURE / OCR — replaces generic mss path for Linux VPS/X11
# ==========================================================================

def _execute_describe_screen(session, args: Dict) -> Dict[str, object]:
    if Image is None:
        return {"error": "Vision tools unavailable (missing Pillow)"}

    try:
        path = _capture_screenshot_path("screen")
        with path.open("rb") as handle:
            image_base64 = base64.b64encode(handle.read()).decode("utf-8")

        image = _load_image(path)
        return {
            "image_captured": True,
            "image_base64": image_base64,
            "description": "Screenshot captured successfully. The vision model can now inspect the live desktop.",
            "question": args.get("question", ""),
            "metadata": {
                "path": str(path),
                "width": image.width,
                "height": image.height,
                "backend": "scrot" if _has_command("scrot") else "mss",
            },
        }
    except Exception as e:
        return {"error": f"Error describing screen: {str(e)}"}


def _execute_ocr_screen(session, args: Dict) -> Dict[str, object]:
    if not OCR_AVAILABLE:
        return {"error": "OCR tools unavailable (missing Pillow/pytesseract)"}

    try:
        path = _capture_screenshot_path("ocr")
        image = _load_image(path)
        result = _extract_best_ocr(image)
        result["metadata"] = {
            "path": str(path),
            "width": image.width,
            "height": image.height,
            "backend": "scrot" if _has_command("scrot") else "mss",
        }
        return result
    except Exception as e:
        return {"error": f"Error performing OCR: {normalize_tesseract_error(e, pytesseract_module=pytesseract)}"}


# ==========================================================================
# INPUT TOOLS — replaces pyautogui path on Linux VPS/X11
# ==========================================================================

def _execute_click(session, args: Dict) -> Dict[str, object]:
    return _execute_pointer_action(args, button=1, action_name="clicked")


def _execute_right_click(session, args: Dict) -> Dict[str, object]:
    return _execute_pointer_action(args, button=3, action_name="right_clicked")


def _execute_double_click(session, args: Dict) -> Dict[str, object]:
    return _execute_pointer_action(args, button=1, action_name="double_clicked", repeat=2)


def _execute_type_text(session, args: Dict) -> Dict[str, object]:
    if not _has_command("xdotool"):
        return {"error": "Input automation unavailable (install xdotool)"}

    text = str(args.get("text", ""))
    if not text:
        return {"error": "Error: 'text' argument is required"}

    try:
        subprocess.run(
            ["xdotool", "type", "--delay", "12", "--clearmodifiers", "--", text],
            check=True,
            timeout=max(5, min(30, len(text) // 20 + 5)),
        )
        return {
            "success": True,
            "typed": text,
            "backend": "xdotool",
            "NEXT": "Call ocr_screen or describe_screen now to verify the typed text appeared correctly.",
        }
    except Exception as e:
        return {"error": f"Error typing: {str(e)}"}


def _execute_press_key(session, args: Dict) -> Dict[str, object]:
    if not _has_command("xdotool"):
        return {"error": "Input automation unavailable (install xdotool)"}

    key = args.get("key", "")
    if not key:
        return {"error": "Error: 'key' argument is required"}

    try:
        normalized = _normalize_key_name(str(key))
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", normalized],
            check=True,
            timeout=5,
        )
        return {
            "success": True,
            "pressed": normalized,
            "backend": "xdotool",
            "NEXT": "Call ocr_screen or describe_screen now to verify the key press had the intended effect.",
        }
    except Exception as e:
        return {"error": f"Error pressing key: {str(e)}"}


def _execute_hotkey(session, args: Dict) -> Dict[str, object]:
    if not _has_command("xdotool"):
        return {"error": "Input automation unavailable (install xdotool)"}

    keys = args.get("keys", "")
    if not keys:
        return {"error": "Error: 'keys' argument is required"}

    try:
        normalized = "+".join(_normalize_key_name(part) for part in str(keys).split("+") if part.strip())
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", normalized],
            check=True,
            timeout=5,
        )
        return {
            "success": True,
            "hotkey": normalized,
            "backend": "xdotool",
            "NEXT": "Call ocr_screen or describe_screen now to verify the shortcut worked before continuing.",
        }
    except Exception as e:
        return {"error": f"Error pressing hotkey: {str(e)}"}


def _execute_scroll(session, args: Dict) -> Dict[str, object]:
    if not _has_command("xdotool"):
        return {"error": "Input automation unavailable (install xdotool)"}

    direction = str(args.get("direction", "down")).lower()
    amount = max(1, int(args.get("amount", 3)))
    button = "4" if direction == "up" else "5"

    try:
        subprocess.run(
            ["xdotool", "click", "--repeat", str(amount), "--delay", "80", button],
            check=True,
            timeout=5,
        )
        return {
            "success": True,
            "scrolled": direction,
            "amount": amount,
            "backend": "xdotool",
        }
    except Exception as e:
        return {"error": f"Error scrolling: {str(e)}"}


# ==========================================================================
# EXPORT: All Linux desktop overrides
# ==========================================================================

def get_linux_desktop_overrides():
    """Return a dict of tool_name -> handler_function for Linux.

    Each function has the signature: func(session, args: Dict) -> str
    These override the Windows-only implementations.
    """
    return {
        "describe_screen": _execute_describe_screen,
        "ocr_screen": _execute_ocr_screen,
        "observe_desktop": _execute_observe_desktop,
        "click": _execute_click,
        "right_click": _execute_right_click,
        "double_click": _execute_double_click,
        "type_text": _execute_type_text,
        "press_key": _execute_press_key,
        "hotkey": _execute_hotkey,
        "scroll": _execute_scroll,
        "focus_window": _execute_focus_window,
        "minimize_window": _execute_minimize_window,
        "maximize_window": _execute_maximize_window,
        "close_window": _execute_close_window,
        "open_app": _execute_open_app,
    }
