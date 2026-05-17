from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


logger = logging.getLogger(__name__)

SyncCallback = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class SyncSubscription:
    token: str
    user_id: int
    channel: str
    callback: SyncCallback
    loop: asyncio.AbstractEventLoop


class ChannelSyncHub:
    """Best-effort cross-channel event fanout for one runtime process."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, SyncSubscription] = {}

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
        )
        with self._lock:
            self._subscriptions[token] = subscription
        return token

    def unsubscribe(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock:
            self._subscriptions.pop(token, None)

    def publish(self, *, user_id: int, event: Dict[str, Any]) -> None:
        with self._lock:
            targets = [item for item in self._subscriptions.values() if item.user_id == user_id]

        if not targets:
            return

        current_loop: Optional[asyncio.AbstractEventLoop]
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for target in targets:
            self._dispatch(target, event, current_loop=current_loop)

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
