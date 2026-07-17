from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Tuple

from app_backend.windows_headless_capture import (
    ensure_windows_console_capture_session,
    windows_headless_capture_policy,
)
from app_backend.windows_capture_session import (
    DesktopCaptureUnavailableError,
    assert_capture_session_available,
    capture_backend_unavailable,
    windows_capture_session_status,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None


def _windows_platform() -> bool:
    return os.name == "nt"


def get_capture_runtime_status() -> Dict[str, object]:
    issues: list[str] = []
    backends: list[str] = []

    if shutil.which("scrot"):
        backends.append("scrot")
        if Image is None:
            issues.append("Pillow is required to process screenshots captured with scrot.")

    if Image is not None and mss is not None:
        backends.append("mss")
    elif not shutil.which("scrot"):
        if Image is None:
            issues.append("Pillow is not installed, so screenshot capture is unavailable.")
        if mss is None:
            issues.append("The `mss` Python package is not installed, so screenshot capture is unavailable.")

    return {
        "ok": not issues,
        "issues": issues,
        "backends": backends,
        "session": windows_capture_session_status(),
        "windowsHeadlessCapture": windows_headless_capture_policy(),
    }


def _preferred_capture_path(prefix: str = "app_screen") -> Path:
    target_dir = Path("local_agent_runtime/screenshots")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{prefix}_{int(time.time() * 1000)}.png"


def _capture_with_scrot(path: Path):
    result = subprocess.run(
        ["scrot", "-z", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ.copy(),
    )
    if result.returncode != 0 or not path.exists():
        raise RuntimeError(result.stderr.strip() or "scrot failed to capture the X11 display")
    if Image is None:
        raise RuntimeError("Pillow is required for screenshot processing")
    return Image.open(path).convert("RGB")


def _capture_backend_error(exc: BaseException, *, platform_name: str | None = None) -> RuntimeError:
    detail = str(exc or "").strip()
    unavailable = capture_backend_unavailable(exc, platform_name=platform_name)
    if unavailable:
        return unavailable
    return RuntimeError(detail or "Screenshot capture failed")


def _grab_with_mss():
    if Image is None or mss is None:
        raise RuntimeError("Screenshot capture unavailable (install Pillow and mss)")
    with mss.mss() as sct:
        monitor_index = 1 if len(sct.monitors) > 1 else 0
        screenshot = sct.grab(sct.monitors[monitor_index])
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")


def _record_console_handoff(capture_context: dict[str, object] | None, result: dict[str, object]) -> None:
    if capture_context is None or not bool(result.get("transitioned", False)):
        return
    capture_context["session_handoff"] = {
        "type": "rdp_to_console",
        "automatic": True,
        "sessionId": result.get("sessionId"),
    }


def _console_handoff_failure(result: dict[str, object], *, state: str) -> DesktopCaptureUnavailableError:
    return DesktopCaptureUnavailableError(
        "Windows could not move the logged-in RDP session to its console for persistent Fleet capture.",
        code=str(result.get("code") or "console_handoff_failed"),
        state=state,
        recovery=(
            "Keep the Windows user signed in and allow that user to transfer its own session to the console, then retry. "
            "EmploAI never signs in, unlocks Windows, or captures the lock screen."
        ),
    )


def _prepare_capture_session(capture_context: dict[str, object] | None = None) -> dict[str, object]:
    status = windows_capture_session_status()
    state = str(status.get("state") or "unknown").strip().lower()
    if _windows_platform() and state == "disconnected":
        handoff = ensure_windows_console_capture_session(status=status)
        if bool(handoff.get("ok", False)):
            _record_console_handoff(capture_context, handoff)
            status = windows_capture_session_status()
        elif bool(handoff.get("attempted", False)):
            raise _console_handoff_failure(handoff, state=state)
    return assert_capture_session_available(status=status)


def _capture_with_mss(capture_context: dict[str, object] | None = None):
    try:
        return _grab_with_mss()
    except Exception as exc:
        converted = _capture_backend_error(exc)
        if (
            _windows_platform()
            and isinstance(converted, DesktopCaptureUnavailableError)
            and converted.code == "framebuffer_unavailable"
        ):
            status = windows_capture_session_status()
            handoff = ensure_windows_console_capture_session(status=status)
            if bool(handoff.get("ok", False)) and bool(handoff.get("transitioned", False)):
                _record_console_handoff(capture_context, handoff)
                try:
                    return _grab_with_mss()
                except Exception as retry_exc:
                    raise _capture_backend_error(retry_exc) from retry_exc
            if bool(handoff.get("attempted", False)):
                raise _console_handoff_failure(
                    handoff,
                    state=str(status.get("state") or "interactive_display_unavailable"),
                ) from exc
        raise converted from exc


def capture_screen_image(
    *,
    max_width: int = 1280,
    capture_context: dict[str, object] | None = None,
) -> Tuple[object, str]:
    _prepare_capture_session(capture_context)
    temp_path: Path | None = None
    backend = "mss"

    if shutil.which("scrot"):
        temp_path = _preferred_capture_path()
        image = _capture_with_scrot(temp_path)
        backend = "scrot"
    else:
        image = _capture_with_mss(capture_context)

    try:
        if max_width > 0 and image.width > max_width:
            scale = max_width / float(image.width)
            new_size = (max_width, max(1, int(image.height * scale)))
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image = image.resize(new_size, resampling)
        return image, backend
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def capture_screen_snapshot(*, max_width: int = 1280, jpeg_quality: int = 72) -> Dict[str, object]:
    capture_context: dict[str, object] = {}
    image, backend = capture_screen_image(max_width=max_width, capture_context=capture_context)

    try:
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=jpeg_quality, optimize=True)
        image_bytes = output.getvalue()
        return {
            "mime_type": "image/jpeg",
            "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
            "width": image.width,
            "height": image.height,
            "backend": backend,
            "captured_at": time.time(),
            "display": windows_capture_session_status(),
            **capture_context,
        }
    finally:
        try:
            image.close()
        except Exception:
            pass
