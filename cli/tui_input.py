"""Input handling helpers for the Textual TUI."""

from __future__ import annotations

import asyncio
from threading import Thread

from textual.widgets import Input


class AgentShellInputMixin:
    def _handle_input(self, input_text: str) -> None:
        if not self.processor:
            return
        result = self.processor.handle_input(input_text, self._open_editor)

        if result.clear:
            if hasattr(self, "chat_log"):
                for child in list(self.chat_log.children):
                    child.remove()
            elif hasattr(self, "log_widget") and self.log_widget:
                self.log_widget.text = ""
        if result.output:
            self._log(result.output)
        if not result.success and not input_text.startswith("/"):
             # Show error for chat too, so user knows if it failed
            pass
        elif not result.success:
            self._log("(command failed)")
        if result.exit:
            self.action_quit()

    def _handle_async(self, input_text: str) -> None:
        async def runner_logic() -> None:
            # Running inside an active asyncio loop now!
            try:
                # We need to run the synchronous _handle_input
                # Since we are in an async function, we can just call it
                # It will block the thread, but that's fine as it's a dedicated thread
                self._handle_input(input_text)
            except Exception as e:
                self._log(f"[FATAL ERROR in runner] {str(e)}")
                import traceback
                self._log_agent(traceback.format_exc())

        def thread_entry() -> None:
            asyncio.run(runner_logic())

        thread = Thread(target=thread_entry, daemon=True)
        thread.start()
