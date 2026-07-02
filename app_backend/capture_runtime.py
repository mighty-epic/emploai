from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None


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


def _capture_with_mss():
    if Image is None or mss is None:
        raise RuntimeError("Screenshot capture unavailable (install Pillow and mss)")
    with mss.mss() as sct:
        monitor_index = 1 if len(sct.monitors) > 1 else 0
        screenshot = sct.grab(sct.monitors[monitor_index])
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")


def capture_screen_snapshot(*, max_width: int = 1280, jpeg_quality: int = 72) -> Dict[str, object]:
    temp_path: Path | None = None
    backend = "mss"

    if shutil.which("scrot"):
        temp_path = _preferred_capture_path()
        image = _capture_with_scrot(temp_path)
        backend = "scrot"
    else:
        image = _capture_with_mss()

    try:
        if max_width > 0 and image.width > max_width:
            scale = max_width / float(image.width)
            new_size = (max_width, max(1, int(image.height * scale)))
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image = image.resize(new_size, resampling)

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
        }
    finally:
        try:
            image.close()
        except Exception:
            pass
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
