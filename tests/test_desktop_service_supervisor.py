from __future__ import annotations

import threading

from desktop_runtime.service_supervisor import BackgroundServiceSupervisor


def test_background_service_supervisor_runs_and_stops():
    called = threading.Event()
    supervisor = BackgroundServiceSupervisor(called.set, interval_seconds=0.1)

    supervisor.start()
    assert called.wait(timeout=1.0)
    supervisor.stop(timeout_seconds=1.0)
    assert not supervisor._thread.is_alive()


def test_background_service_supervisor_recovers_after_check_failure():
    recovered = threading.Event()
    attempts = []

    def check_services():
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise RuntimeError("temporary check failure")
        recovered.set()

    supervisor = BackgroundServiceSupervisor(check_services, interval_seconds=0.1)
    supervisor.start()
    try:
        assert recovered.wait(timeout=1.0)
    finally:
        supervisor.stop(timeout_seconds=1.0)

    assert len(attempts) >= 2
