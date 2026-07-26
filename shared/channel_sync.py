from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import channel_sync_root

logger = logging.getLogger(__name__)

SyncCallback = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class SyncSubscription:
    token: str
    user_id: int
    channel: str
    callback: SyncCallback
    loop: asyncio.AbstractEventLoop
    cursor: str = ""
    poll_key: Optional[tuple[int, int]] = field(default=None, repr=False)


@dataclass
class SyncPoller:
    user_id: int
    loop: asyncio.AbstractEventLoop
    tokens: set[str] = field(default_factory=set)
    task: Optional[asyncio.Task[None]] = field(default=None, repr=False)


class ChannelSyncHub:
    """Best-effort cross-channel event fanout for one runtime process."""

    _POLL_INTERVAL_SECONDS = 0.35
    _MAX_EVENT_FILES = 600
    _KEEP_EVENT_FILES = 400

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, SyncSubscription] = {}
        self._pollers: Dict[tuple[int, int], SyncPoller] = {}

    def _event_root(self) -> Path:
        configured = str(os.getenv("EMPLOAI_CHANNEL_SYNC_DIR", "") or "").strip()
        if configured:
            root = Path(configured)
        else:
            root = channel_sync_root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _user_event_dir(self, user_id: int) -> Path:
        path = self._event_root() / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _latest_cursor(self, user_id: int) -> str:
        try:
            files = self._list_event_files(user_id)
        except OSError:
            return ""
        return files[-1].name if files else ""

    def _list_event_files(self, user_id: int) -> list[Path]:
        event_dir = self._user_event_dir(user_id)
        with os.scandir(event_dir) as entries:
            return sorted(
                event_dir / entry.name
                for entry in entries
                if entry.name.endswith(".json") and entry.is_file()
            )

    def _write_event_file(self, *, user_id: int, event: Dict[str, Any]) -> str:
        event_dir = self._user_event_dir(user_id)
        event_id = str(event.get("event_id") or uuid.uuid4().hex).strip() or uuid.uuid4().hex
        payload = dict(event)
        payload["event_id"] = event_id
        filename = f"{time.time_ns()}_{event_id}.json"
        target_path = event_dir / filename
        atomic_write_json(target_path, payload, indent=None)
        self._prune_event_files(event_dir)
        return filename

    def _prune_event_files(self, event_dir: Path) -> None:
        try:
            with os.scandir(event_dir) as entries:
                files = sorted(
                    event_dir / entry.name
                    for entry in entries
                    if entry.name.endswith(".json") and entry.is_file()
                )
        except OSError:
            return
        if len(files) <= self._MAX_EVENT_FILES:
            return
        for path in files[: max(0, len(files) - self._KEEP_EVENT_FILES)]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue

    async def _poll_group(self, key: tuple[int, int]) -> None:
        with self._lock:
            poller = self._pollers.get(key)
            subscriptions = [
                subscription
                for token in (poller.tokens if poller else ())
                if (subscription := self._subscriptions.get(token)) is not None
            ]
        if not poller or not subscriptions:
            return

        try:
            files = await asyncio.to_thread(self._list_event_files, poller.user_id)
        except OSError:
            return

        deliveries: Dict[str, list[Dict[str, Any]]] = {
            subscription.token: [] for subscription in subscriptions
        }
        for path in files:
            name = path.name
            pending = [
                subscription
                for subscription in subscriptions
                if not subscription.cursor or name > subscription.cursor
            ]
            if not pending:
                continue
            try:
                event = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
            except Exception:
                for subscription in pending:
                    subscription.cursor = name
                continue
            for subscription in pending:
                subscription.cursor = name
                deliveries[subscription.token].append(event)

        async def deliver(subscription: SyncSubscription) -> None:
            for event in deliveries[subscription.token]:
                with self._lock:
                    if subscription.token not in self._subscriptions:
                        return
                try:
                    await subscription.callback(event)
                except Exception:
                    logger.exception(
                        "Channel sync file delivery failed for user=%s channel=%s",
                        subscription.user_id,
                        subscription.channel,
                    )

        await asyncio.gather(
            *(
                deliver(subscription)
                for subscription in subscriptions
                if deliveries[subscription.token]
            )
        )

    async def _poll_group_loop(self, key: tuple[int, int]) -> None:
        try:
            while True:
                await asyncio.sleep(self._POLL_INTERVAL_SECONDS)
                await self._poll_group(key)
        except asyncio.CancelledError:
            return

    async def _ensure_poll_task(self, token: str) -> None:
        with self._lock:
            subscription = self._subscriptions.get(token)
            if not subscription:
                return
            key = (subscription.user_id, id(subscription.loop))
            subscription.poll_key = key
            poller = self._pollers.get(key)
            if poller is None:
                poller = SyncPoller(user_id=subscription.user_id, loop=subscription.loop)
                self._pollers[key] = poller
            poller.tokens.add(token)
            if poller.task is not None:
                return
            poller.task = asyncio.create_task(self._poll_group_loop(key))
            poller.task.add_done_callback(self._log_task_exception)

    def subscribe(
        self,
        *,
        user_id: int,
        channel: str,
        callback: SyncCallback,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> str:
        target_loop = loop
        if target_loop is None:
            target_loop = asyncio.get_running_loop()

        token = uuid.uuid4().hex
        subscription = SyncSubscription(
            token=token,
            user_id=user_id,
            channel=channel,
            callback=callback,
            loop=target_loop,
            cursor=self._latest_cursor(user_id),
        )
        with self._lock:
            self._subscriptions[token] = subscription
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        self._start_poll_task(subscription, current_loop=current_loop)
        return token

    def unsubscribe(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock:
            subscription = self._subscriptions.pop(token, None)
            poller = self._pollers.get(subscription.poll_key) if subscription else None
            if poller:
                poller.tokens.discard(token)
                if poller.tokens:
                    poller = None
                else:
                    self._pollers.pop(subscription.poll_key, None)
        if not subscription or not poller or not poller.task or subscription.loop.is_closed():
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is subscription.loop:
            poller.task.cancel()
            return
        try:
            subscription.loop.call_soon_threadsafe(poller.task.cancel)
        except RuntimeError:
            return

    def publish(self, *, user_id: int, event: Dict[str, Any]) -> None:
        with self._lock:
            targets = [item for item in self._subscriptions.values() if item.user_id == user_id]

        payload = dict(event)
        filename = self._write_event_file(user_id=user_id, event=payload)
        for target in targets:
            if not target.cursor or filename > target.cursor:
                target.cursor = filename

        if not targets:
            return

        current_loop: Optional[asyncio.AbstractEventLoop]
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for target in targets:
            self._dispatch(target, payload, current_loop=current_loop)

    def _start_poll_task(
        self,
        subscription: SyncSubscription,
        *,
        current_loop: Optional[asyncio.AbstractEventLoop],
    ) -> None:
        if subscription.loop.is_closed():
            self.unsubscribe(subscription.token)
            return
        if current_loop is not None and subscription.loop is current_loop:
            subscription.loop.create_task(self._ensure_poll_task(subscription.token))
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._ensure_poll_task(subscription.token),
                subscription.loop,
            )
            future.add_done_callback(self._log_future_exception)
        except RuntimeError:
            self.unsubscribe(subscription.token)

    def _dispatch(
        self,
        subscription: SyncSubscription,
        event: Dict[str, Any],
        *,
        current_loop: Optional[asyncio.AbstractEventLoop],
    ) -> None:
        async def runner() -> None:
            try:
                await subscription.callback(event)
            except Exception:
                logger.exception(
                    "Channel sync delivery failed for user=%s channel=%s",
                    subscription.user_id,
                    subscription.channel,
                )

        if subscription.loop.is_closed():
            self.unsubscribe(subscription.token)
            return

        if current_loop is not None and subscription.loop is current_loop:
            task = subscription.loop.create_task(runner())
            task.add_done_callback(self._log_task_exception)
            return

        try:
            future = asyncio.run_coroutine_threadsafe(runner(), subscription.loop)
            future.add_done_callback(self._log_future_exception)
        except RuntimeError:
            self.unsubscribe(subscription.token)

    @staticmethod
    def _log_task_exception(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Channel sync task failed")

    @staticmethod
    def _log_future_exception(future: "asyncio.Future[Any]") -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Channel sync future failed")


_hub: Optional[ChannelSyncHub] = None


def get_channel_sync_hub() -> ChannelSyncHub:
    global _hub
    if _hub is None:
        _hub = ChannelSyncHub()
    return _hub
