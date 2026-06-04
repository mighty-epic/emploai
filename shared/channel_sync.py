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
    poll_task: Optional[asyncio.Task[None]] = field(default=None, repr=False)


class ChannelSyncHub:
    """Best-effort cross-channel event fanout for one runtime process."""

    _POLL_INTERVAL_SECONDS = 0.35
    _MAX_EVENT_FILES = 600
    _KEEP_EVENT_FILES = 400

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, SyncSubscription] = {}

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
            files = sorted(
                path.name
                for path in self._user_event_dir(user_id).glob("*.json")
                if path.is_file()
            )
        except OSError:
            return ""
        return files[-1] if files else ""

    def _write_event_file(self, *, user_id: int, event: Dict[str, Any]) -> str:
        event_dir = self._user_event_dir(user_id)
        event_id = str(event.get("event_id") or uuid.uuid4().hex).strip() or uuid.uuid4().hex
        payload = dict(event)
        payload["event_id"] = event_id
        filename = f"{time.time_ns()}_{event_id}.json"
        target_path = event_dir / filename
        temp_path = event_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(target_path)
        self._prune_event_files(event_dir)
        return filename

    def _prune_event_files(self, event_dir: Path) -> None:
        try:
            files = sorted(path for path in event_dir.glob("*.json") if path.is_file())
        except OSError:
            return
        if len(files) <= self._MAX_EVENT_FILES:
            return
        for path in files[: max(0, len(files) - self._KEEP_EVENT_FILES)]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue

    async def _poll_subscription(self, token: str) -> None:
        with self._lock:
            subscription = self._subscriptions.get(token)
        if not subscription:
            return

        try:
            files = sorted(
                path for path in self._user_event_dir(subscription.user_id).glob("*.json") if path.is_file()
            )
        except OSError:
            return

        for path in files:
            name = path.name
            if subscription.cursor and name <= subscription.cursor:
                continue
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                subscription.cursor = name
                continue
            subscription.cursor = name
            try:
                await subscription.callback(event)
            except Exception:
                logger.exception(
                    "Channel sync file delivery failed for user=%s channel=%s",
                    subscription.user_id,
                    subscription.channel,
                )

    async def _poll_subscription_loop(self, token: str) -> None:
        try:
            while True:
                await asyncio.sleep(self._POLL_INTERVAL_SECONDS)
                await self._poll_subscription(token)
        except asyncio.CancelledError:
            return

    async def _ensure_poll_task(self, token: str) -> None:
        with self._lock:
            subscription = self._subscriptions.get(token)
            if not subscription or subscription.poll_task is not None:
                return
            subscription.poll_task = asyncio.create_task(self._poll_subscription_loop(token))
            subscription.poll_task.add_done_callback(self._log_task_exception)

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
        if not subscription or not subscription.poll_task or subscription.loop.is_closed():
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is subscription.loop:
            subscription.poll_task.cancel()
            return
        try:
            subscription.loop.call_soon_threadsafe(subscription.poll_task.cancel)
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
