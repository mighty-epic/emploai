from __future__ import annotations

import os

import pytest


_TRUTHY = {"1", "true", "yes", "on"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if str(os.getenv("EMPLOAI_RUN_LIVE_EXTERNAL_TESTS", "")).strip().lower() in _TRUTHY:
        return
    skip_live = pytest.mark.skip(
        reason="live external test; set EMPLOAI_RUN_LIVE_EXTERNAL_TESTS=1 to run",
    )
    for item in items:
        if item.get_closest_marker("live_external") is not None:
            item.add_marker(skip_live)
