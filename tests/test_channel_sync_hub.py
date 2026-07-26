from __future__ import annotations

import asyncio
from pathlib import Path

from shared.channel_sync import ChannelSyncHub


def test_subscriptions_share_one_filesystem_poller_per_user_and_loop(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("EMPLOAI_CHANNEL_SYNC_DIR", str(tmp_path))

    async def scenario() -> None:
        hub = ChannelSyncHub()
        hub._POLL_INTERVAL_SECONDS = 60
        received: list[tuple[int, str]] = []

        def callback_for(index: int):
            async def callback(event: dict) -> None:
                received.append((index, str(event["kind"])))

            return callback

        tokens = [
            hub.subscribe(user_id=7, channel=f"app-{index}", callback=callback_for(index))
            for index in range(8)
        ]
        await asyncio.sleep(0)

        assert len(hub._pollers) == 1
        key, poller = next(iter(hub._pollers.items()))
        assert poller.tokens == set(tokens)

        writer = ChannelSyncHub()
        writer._write_event_file(user_id=7, event={"kind": "remote-update"})

        scans = 0
        original_list_event_files = hub._list_event_files

        def count_scans(user_id: int):
            nonlocal scans
            scans += 1
            return original_list_event_files(user_id)

        monkeypatch.setattr(hub, "_list_event_files", count_scans)
        await hub._poll_group(key)

        assert scans == 1
        assert sorted(received) == [(index, "remote-update") for index in range(8)]

        for token in tokens:
            hub.unsubscribe(token)
        await asyncio.sleep(0)
        assert hub._pollers == {}

    asyncio.run(scenario())
