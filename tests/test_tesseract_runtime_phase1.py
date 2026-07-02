from __future__ import annotations

from pathlib import Path

import local_agent_runtime.agent as single_agent_module
import telegram_bot.telegram_unified_agent as telegram_module
from shared.tesseract_runtime import (
    TESSERACT_MISSING_MESSAGE,
    configure_pytesseract_runtime,
    normalize_tesseract_error,
)


class _FakePytesseractModule:
    class pytesseract:
        tesseract_cmd = "tesseract"


def test_configure_pytesseract_runtime_uses_bundled_root(tmp_path: Path):
    bundle = tmp_path / "tesseract"
    bundle.mkdir()
    (bundle / "tesseract.exe").write_text("", encoding="utf-8")
    (bundle / "tessdata").mkdir()

    fake_module = _FakePytesseractModule()
    runtime = configure_pytesseract_runtime(fake_module, extra_roots=[bundle])

    assert runtime.executable == bundle / "tesseract.exe"
    assert fake_module.pytesseract.tesseract_cmd == str(bundle / "tesseract.exe")


def test_normalize_tesseract_error_returns_release_safe_message():
    missing_error = type("TesseractNotFoundError", (Exception,), {})
    fake_module = type("FakePytesseract", (), {"TesseractNotFoundError": missing_error})
    error = missing_error("missing tesseract")

    assert normalize_tesseract_error(error, pytesseract_module=fake_module) == TESSERACT_MISSING_MESSAGE


class _FakeScreenshot:
    size = (20, 20)
    bgra = b"\x00" * (20 * 20 * 4)


class _FakeMssContext:
    monitors = [None, object()]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def grab(self, _monitor):
        return _FakeScreenshot()


class _FakeMssModule:
    @staticmethod
    def mss():
        return _FakeMssContext()


class _FakeImageModule:
    @staticmethod
    def frombytes(*_args, **_kwargs):
        return object()


class _FakeSavableImage:
    def save(self, path):
        Path(path).write_bytes(b"fake-image")


class _FakeSavableImageModule:
    @staticmethod
    def frombytes(*_args, **_kwargs):
        return _FakeSavableImage()


def _make_missing_pytesseract():
    missing_error = type("TesseractNotFoundError", (Exception,), {})

    class _FakePytesseract:
        TesseractNotFoundError = missing_error

        class Output:
            DICT = "DICT"

        class pytesseract:
            tesseract_cmd = "missing"

        @staticmethod
        def image_to_data(*_args, **_kwargs):
            raise missing_error("missing")

        @staticmethod
        def image_to_string(*_args, **_kwargs):
            raise missing_error("missing")

    return _FakePytesseract


def test_single_agent_ocr_returns_clean_missing_tesseract_message(monkeypatch):
    fake_pytesseract = _make_missing_pytesseract()
    monkeypatch.setattr(single_agent_module, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(single_agent_module, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(single_agent_module, "mss", _FakeMssModule())
    monkeypatch.setattr(single_agent_module, "Image", _FakeImageModule)

    result = single_agent_module.SingleAgent()._ocr_screen()

    assert result == {"error": TESSERACT_MISSING_MESSAGE}


def test_single_agent_describe_screen_does_not_require_ocr(monkeypatch):
    monkeypatch.setattr(single_agent_module, "SCREEN_CAPTURE_AVAILABLE", True)
    monkeypatch.setattr(single_agent_module, "OCR_AVAILABLE", False)
    monkeypatch.setattr(single_agent_module, "mss", _FakeMssModule())
    monkeypatch.setattr(single_agent_module, "Image", _FakeSavableImageModule)

    result = single_agent_module.SingleAgent()._describe_screen()

    assert result["image_captured"] is True
    assert result["description"]


def test_telegram_ocr_returns_clean_missing_tesseract_message(monkeypatch):
    fake_pytesseract = _make_missing_pytesseract()
    monkeypatch.setattr(telegram_module, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(telegram_module, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(telegram_module, "mss", _FakeMssModule())
    monkeypatch.setattr(telegram_module, "Image", _FakeImageModule)

    result = telegram_module._execute_ocr_screen(None, {})

    assert result == f"Error performing OCR: {TESSERACT_MISSING_MESSAGE}"


def test_telegram_describe_screen_does_not_require_ocr(monkeypatch):
    monkeypatch.setattr(telegram_module, "SCREEN_CAPTURE_AVAILABLE", True)
    monkeypatch.setattr(telegram_module, "OCR_AVAILABLE", False)
    monkeypatch.setattr(telegram_module, "mss", _FakeMssModule())
    monkeypatch.setattr(telegram_module, "Image", _FakeSavableImageModule)

    result = telegram_module._execute_describe_screen(None, {})

    assert result["image_captured"] is True
    assert "looking at the screen" in result["description"].lower()
