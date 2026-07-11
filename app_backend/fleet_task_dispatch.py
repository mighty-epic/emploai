from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from app_backend.remote_command_broker import dispatch_remote_desktop_command_via_broker
from app_backend.remote_control_runtime import remote_control_sqlite_broker_enabled


logger = logging.getLogger(__name__)

SessionActiveChecker = Callable[..., bool]
DesktopUnavailableChecker = Callable[[str], bool]
DesktopOfflineMarker = Callable[..., None]
LocalTaskDispatcher = Callable[..., Awaitable[Dict[str, Any]]]
LocalTaskStopper = Callable[..., Awaitable[bool]]


def fleet_run_task_payload(*, worker: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "worker_id": worker.get("worker_id"),
        "worker_name": worker.get("display_name"),
        "fleet_identity_id": worker.get("instance_id"),
        "prompt": task.get("prompt"),
        "source": task.get("source") or "manager",
        "target_session_id": (task.get("metadata") or {}).get("target_session_id"),
        "metadata": task.get("metadata") or {},
    }


async def try_dispatch_fleet_worker_task(
    *,
    store: Any,
    remote_desktop_manager: Any,
    user_id: int,
    worker: Dict[str, Any],
    task: Dict[str, Any],
    is_remote_session_active: SessionActiveChecker,
    is_desktop_unavailable_error: Optional[DesktopUnavailableChecker] = None,
    mark_desktop_offline: Optional[DesktopOfflineMarker] = None,
    dispatch_local_task: Optional[LocalTaskDispatcher] = None,
) -> Dict[str, Any]:
    if str(task.get("status") or "") != "queued":
        return task
    if str(worker.get("active_task_id") or "").strip():
        return task
    try:
        next_task = store.get_next_queued_worker_task(
            user_id=int(user_id),
            worker_id=str(worker.get("worker_id") or ""),
        )
    except Exception:
        logger.exception("[fleet] failed checking worker queue before dispatch")
        return task
    if not next_task or str(next_task.get("task_id") or "") != str(task.get("task_id") or ""):
        return task

    if str(worker.get("kind") or "").strip().lower() == "local":
        if dispatch_local_task is None:
            return task
        return await dispatch_local_task(
            store=store,
            user_id=int(user_id),
            worker=worker,
            task=task,
        )

    desktop_id = str(worker.get("machine_desktop_id") or "").strip()
    desktop_connected_here = bool(desktop_id and remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id)))
    if not desktop_id or (not desktop_connected_here and not remote_control_sqlite_broker_enabled()):
        return task
    if not is_remote_session_active(desktop_id=desktop_id, user_id=int(user_id)):
        return task

    command_payload = fleet_run_task_payload(worker=worker, task=task)
    try:
        if desktop_connected_here:
            await remote_desktop_manager.send_command(
                desktop_id=desktop_id,
                user_id=int(user_id),
                command_type="fleet_run_task",
                payload=command_payload,
            )
        else:
            dispatch_remote_desktop_command_via_broker(
                store=store,
                user_id=int(user_id),
                desktop_id=desktop_id,
                command_name="fleet_run_task",
                payload=command_payload,
                ttl_seconds=30,
            )
    except (KeyError, RuntimeError) as exc:
        detail = str(exc)
        if (
            is_desktop_unavailable_error
            and is_desktop_unavailable_error(detail)
            and mark_desktop_offline
        ):
            mark_desktop_offline(
                user_id=int(user_id),
                desktop_id=desktop_id,
                reason=detail,
            )
        raise

    return store.update_worker_task_status(
        user_id=int(user_id),
        task_id=str(task.get("task_id") or ""),
        status="running",
        metadata={"dispatched_to_desktop_id": desktop_id},
    )


async def try_stop_fleet_worker_task(
    *,
    store: Any,
    remote_desktop_manager: Any,
    user_id: int,
    task: Dict[str, Any],
    is_remote_session_active: SessionActiveChecker,
    is_desktop_unavailable_error: Optional[DesktopUnavailableChecker] = None,
    mark_desktop_offline: Optional[DesktopOfflineMarker] = None,
    stop_local_task: Optional[LocalTaskStopper] = None,
) -> bool:
    task_id = str(task.get("task_id") or "").strip()
    worker_id = str(task.get("worker_id") or "").strip()
    if not task_id or not worker_id:
        return False
    try:
        worker = store.get_worker(user_id=int(user_id), worker_id=worker_id)
    except Exception:
        logger.exception("[fleet] failed resolving worker for stop request")
        return False

    if str(worker.get("kind") or "").strip().lower() == "local":
        if stop_local_task is None:
            return False
        return await stop_local_task(user_id=int(user_id), task=task)

    desktop_id = str(worker.get("machine_desktop_id") or "").strip()
    desktop_connected_here = bool(desktop_id and remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id)))
    if not desktop_id or (not desktop_connected_here and not remote_control_sqlite_broker_enabled()):
        return False
    if not is_remote_session_active(desktop_id=desktop_id, user_id=int(user_id)):
        return False

    command_payload = {
        "task_id": task_id,
        "worker_id": worker_id,
    }
    try:
        if desktop_connected_here:
            await remote_desktop_manager.send_command(
                desktop_id=desktop_id,
                user_id=int(user_id),
                command_type="fleet_stop_task",
                payload=command_payload,
            )
        else:
            dispatch_remote_desktop_command_via_broker(
                store=store,
                user_id=int(user_id),
                desktop_id=desktop_id,
                command_name="fleet_stop_task",
                payload=command_payload,
                ttl_seconds=30,
            )
        return True
    except (KeyError, RuntimeError) as exc:
        detail = str(exc)
        if (
            is_desktop_unavailable_error
            and is_desktop_unavailable_error(detail)
            and mark_desktop_offline
        ):
            mark_desktop_offline(
                user_id=int(user_id),
                desktop_id=desktop_id,
                reason=detail,
            )
        logger.exception("[fleet] failed sending worker stop command")
        return False
    except Exception:
        logger.exception("[fleet] failed sending worker stop command")
        return False
