"""Editor screen for inline file edits."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Header, Label, TextArea


class EditorScreen(Screen):
    """Modal editor for file content."""

    def __init__(self, file_path: Path, content: str, on_save: Callable[[str], None]) -> None:
        super().__init__()
        self.file_path = file_path
        self.content = content
        self.on_save = on_save

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Label(f"Editing: {self.file_path}")
            yield TextArea(self.content, id="editor")
            with Horizontal():
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            editor = self.query_one("#editor", TextArea)
            self.on_save(editor.text)
            self.app.pop_screen()
        elif event.button.id == "cancel":
            self.app.pop_screen()
