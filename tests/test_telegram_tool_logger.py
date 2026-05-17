from __future__ import annotations

import telegram_bot.tool_logger as tool_logger


class _Cp1255Stream:
    encoding = "cp1255"

    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        self.writes.append(text)
        return len(text)

    def flush(self) -> None:
        return None


def test_log_tool_call_survives_non_utf_console(monkeypatch):
    stream = _Cp1255Stream()

    monkeypatch.setattr(tool_logger.sys, "stdout", stream)
    monkeypatch.setattr(tool_logger.tool_logger, "info", lambda *args, **kwargs: None)

    tool_logger.log_tool_call(
        "describe_screen",
        {"question": "What is on the screen?"},
        provider="openai",
    )

    rendered = "".join(stream.writes)
    assert "TOOL CALL: describe_screen" in rendered
    assert "[OPENAI]" in rendered
