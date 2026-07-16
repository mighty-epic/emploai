from __future__ import annotations

import logging
import threading
from collections.abc import Callable


logger = logging.getLogger(__name__)


class BackgroundServiceSupervisor:
    def __init__(
        self,
        check_services: Callable[[], None],
        *,
        interval_seconds: float = 5.0,
        initial_delay_seconds: float = 0.0,
    ) -> None:
        self._check_services = check_services
        self._interval_seconds = max(0.1, float(interval_seconds))
        self._initial_delay_seconds = max(0.0, float(initial_delay_seconds))
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="emploai-service-supervisor",
            daemon=True,
        )

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=max(0.0, float(timeout_seconds)))

    def _run(self) -> None:
        if self._stop_event.wait(self._initial_delay_seconds):
            return
        while not self._stop_event.is_set():
            try:
                self._check_services()
            except Exception:
                logger.exception("Background service supervision check failed")
            if self._stop_event.wait(self._interval_seconds):
                return
