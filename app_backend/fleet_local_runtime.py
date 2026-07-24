from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from app_backend.fleet_worker_report import extract_worker_report
from shared.channel_sync import get_channel_sync_hub


logger = logging.getLogger(__name__)

BridgeFactory = Callable[[int], Any]
FleetDeltaPublisher = Callable[..., None]
RunTurn = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass
class LocalFleetTaskHandle:
    user_id: int
    worker_id: str
    task_id: str
    session_id: str
    runner: Optional[asyncio.Task[None]] = None
    runtime: Any = None
    stop_requested: bool = False


class LocalFleetRuntime:
    """Runs logical local Fleet workers inside the desktop backend process."""

    def __init__(self, *, run_turn: Optional[RunTurn] = None) -> None:
        self._run_turn = run_turn
        self._handles_by_task: Dict[str, LocalFleetTaskHandle] = {}
        self._task_by_worker: Dict[tuple[int, str], str] = {}
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        *,
        store: Any,
        user_id: int,
        worker: Dict[str, Any],
        task: Dict[str, Any],
        bridge_factory: BridgeFactory,
        publish_fleet_delta: Optional[FleetDeltaPublisher] = None,
    ) -> Dict[str, Any]:
        if str(worker.get("kind") or "").strip().lower() != "local":
            return task
        if str(task.get("status") or "").strip().lower() != "queued":
            return task

        worker_id = str(worker.get("worker_id") or "").strip()
        task_id = str(task.get("task_id") or "").strip()
        if not worker_id or not task_id:
            raise ValueError("Local Fleet dispatch requires worker_id and task_id")

        async with self._lock:
            existing_task_id = self._task_by_worker.get((int(user_id), worker_id))
            if existing_task_id:
                return task

            bridge = bridge_factory(int(user_id))
            session_id, task = self._ensure_worker_session(
                store=store,
                user_id=int(user_id),
                worker=worker,
                task=task,
                bridge=bridge,
            )
            handle = LocalFleetTaskHandle(
                user_id=int(user_id),
                worker_id=worker_id,
                task_id=task_id,
                session_id=session_id,
            )
            self._handles_by_task[task_id] = handle
            self._task_by_worker[(int(user_id), worker_id)] = task_id

            lease = await bridge.orchestrator.prepare_turn(session_id, origin_channel="app")
            if lease.acquired:
                running = store.update_worker_task_status(
                    user_id=int(user_id),
                    task_id=task_id,
                    status="running",
                    metadata={
                        "dispatch_transport": "local_runtime",
                        "target_session_id": session_id,
                    },
                )
                handle.runtime = lease.worker
                handle.runner = asyncio.create_task(
                    self._execute_with_lease(
                        store=store,
                        bridge=bridge,
                        worker=worker,
                        task=running,
                        handle=handle,
                        lease=lease,
                        publish_fleet_delta=publish_fleet_delta,
                    )
                )
                self._publish_task_status(
                    user_id=int(user_id),
                    task=running,
                    publish_fleet_delta=publish_fleet_delta,
                    detail="Local worker accepted task",
                )
                return running

            queued = store.update_worker_task_status(
                user_id=int(user_id),
                task_id=task_id,
                status="queued",
                metadata={
                    "dispatch_transport": "local_runtime",
                    "target_session_id": session_id,
                    "dispatch_wait_reason": lease.error or "Waiting for an available runtime resource",
                },
            )
            handle.runner = asyncio.create_task(
                self._wait_for_lease_and_execute(
                    store=store,
                    bridge=bridge,
                    worker=worker,
                    task=queued,
                    handle=handle,
                    publish_fleet_delta=publish_fleet_delta,
                )
            )
            return queued

    async def stop(self, *, user_id: int, task: Dict[str, Any]) -> bool:
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            return False
        async with self._lock:
            handle = self._handles_by_task.get(task_id)
            if not handle or int(handle.user_id) != int(user_id):
                return False
            handle.stop_requested = True
            runtime = handle.runtime
            if runtime is not None:
                runtime.should_interrupt = True
                runtime.interrupt_message = None
            return True

    async def shutdown(self) -> None:
        async with self._lock:
            handles = list(self._handles_by_task.values())
            for handle in handles:
                handle.stop_requested = True
                if handle.runtime is not None:
                    handle.runtime.should_interrupt = True
                    handle.runtime.interrupt_message = None
            runners = [handle.runner for handle in handles if handle.runner is not None]
        if not runners:
            return
        try:
            await asyncio.wait(runners, timeout=2.0)
        finally:
            for runner in runners:
                if not runner.done():
                    runner.cancel()

    def active_task_ids(self) -> list[str]:
        return sorted(self._handles_by_task)

    def _ensure_worker_session(
        self,
        *,
        store: Any,
        user_id: int,
        worker: Dict[str, Any],
        task: Dict[str, Any],
        bridge: Any,
    ) -> tuple[str, Dict[str, Any]]:
        metadata = dict(task.get("metadata") or {})
        company_id = str(
            metadata.get("company_id")
            or dict(worker.get("metadata") or {}).get("company_id")
            or ""
        ).strip() or None
        target_session_id = str(metadata.get("target_session_id") or "").strip()
        session = None
        if target_session_id:
            try:
                candidate = bridge.get_session(target_session_id)
                candidate_worker_id = str(getattr(candidate, "fleet_worker_id", "") or "").strip()
                candidate_role = str(getattr(candidate, "fleet_identity_role", "") or "").strip().lower()
                candidate_company_id = str(getattr(candidate, "company_id", "") or "").strip()
                if (
                    candidate_worker_id == str(worker.get("worker_id") or "").strip()
                    and candidate_role == "worker"
                    and (not company_id or candidate_company_id == company_id)
                ):
                    session = candidate
            except Exception:
                session = None

        if session is None:
            workspace = self._workspace_from_metadata(metadata)
            session = bridge.create_session(
                f"{str(worker.get('display_name') or 'Worker')}: {str(task.get('task_id') or '')[-6:]}",
                workspace=workspace,
                enabled_tool_packs=list(metadata.get("enabled_tool_packs") or []),
                security_permission_mode=metadata.get("security_permission_mode"),
                headless_eligible=True,
                workspace_id=metadata.get("workspace_id"),
                workspace_binding_status=metadata.get("workspace_binding_status"),
                fleet_identity_id=str(worker.get("instance_id") or "").strip() or None,
                fleet_identity_role="worker",
                fleet_worker_id=str(worker.get("worker_id") or "").strip() or None,
                fleet_task_mode="delegated",
                fleet_task_id=str(task.get("task_id") or "").strip() or None,
                fleet_identity_metadata=dict(worker.get("metadata") or {}),
                company_id=company_id,
                activate=False,
            )
            target_session_id = str(session.id)
            try:
                store.set_active_chat_for_fleet_identity(
                    user_id=int(user_id),
                    identity_id=str(worker.get("instance_id") or ""),
                    chat_id=target_session_id,
                    source="local_runtime",
                    company_id=company_id,
                    include_unscoped_company_records=company_id is None,
                )
            except Exception:
                logger.exception("[fleet] failed selecting local worker chat")

        updated_task = store.update_worker_task_status(
            user_id=int(user_id),
            task_id=str(task.get("task_id") or ""),
            status="queued",
            metadata={"target_session_id": target_session_id, "dispatch_transport": "local_runtime"},
        )
        return target_session_id, updated_task

    @staticmethod
    def _workspace_from_metadata(metadata: Dict[str, Any]) -> Optional[Path]:
        raw = str(metadata.get("workspace") or metadata.get("workspace_path") or "").strip()
        if not raw:
            return None
        try:
            path = Path(raw).expanduser().resolve()
        except Exception:
            return None
        return path if path.exists() and path.is_dir() else None

    async def _wait_for_lease_and_execute(
        self,
        *,
        store: Any,
        bridge: Any,
        worker: Dict[str, Any],
        task: Dict[str, Any],
        handle: LocalFleetTaskHandle,
        publish_fleet_delta: Optional[FleetDeltaPublisher],
    ) -> None:
        while True:
            current = store.get_worker_task(user_id=handle.user_id, task_id=handle.task_id)
            if handle.stop_requested or str(current.get("status") or "") != "queued":
                await self._finish_without_run_if_needed(
                    store=store,
                    handle=handle,
                    current=current,
                    publish_fleet_delta=publish_fleet_delta,
                )
                return
            lease = await bridge.orchestrator.prepare_turn(handle.session_id, origin_channel="app")
            if lease.acquired:
                running = store.update_worker_task_status(
                    user_id=handle.user_id,
                    task_id=handle.task_id,
                    status="running",
                    metadata={"dispatch_wait_reason": None, "dispatch_transport": "local_runtime"},
                )
                handle.runtime = lease.worker
                self._publish_task_status(
                    user_id=handle.user_id,
                    task=running,
                    publish_fleet_delta=publish_fleet_delta,
                    detail="Local worker accepted queued task",
                )
                await self._execute_with_lease(
                    store=store,
                    bridge=bridge,
                    worker=worker,
                    task=running,
                    handle=handle,
                    lease=lease,
                    publish_fleet_delta=publish_fleet_delta,
                )
                return
            await asyncio.sleep(0.25)

    async def _execute_with_lease(
        self,
        *,
        store: Any,
        bridge: Any,
        worker: Dict[str, Any],
        task: Dict[str, Any],
        handle: LocalFleetTaskHandle,
        lease: Any,
        publish_fleet_delta: Optional[FleetDeltaPublisher],
    ) -> None:
        runtime = lease.worker
        handle.runtime = runtime
        try:
            if handle.stop_requested:
                await self._complete_report(
                    store=store,
                    handle=handle,
                    status="stopped",
                    summary="Task stopped by manager before the worker turn started.",
                    evidence=[],
                    artifacts=[],
                    blockers=["Stopped by manager"],
                    confidence="medium",
                    next_suggested_action="Review the task instructions and retry if needed.",
                    raw={"session_id": handle.session_id, "stopped_before_start": True},
                    publish_fleet_delta=publish_fleet_delta,
                )
                return

            run_turn = self._run_turn or self._default_run_turn
            result = await run_turn(
                runtime,
                user_message=str(task.get("prompt") or ""),
                source_format="app_text",
                surface_mode="fleet",
                interrupt_policy="none",
                source_client_id=f"fleet:{handle.task_id}",
            )
            provider_failure = result.get("failure") if isinstance(result.get("failure"), dict) else None
            if provider_failure:
                failure_code = str(provider_failure.get("code") or "provider_failed")
                provider_name = str(provider_failure.get("provider_id") or "provider")
                model_name = str(provider_failure.get("model_id") or "model")
                await self._complete_report(
                    store=store,
                    handle=handle,
                    status="failed",
                    summary=str(
                        provider_failure.get("user_message")
                        or "The configured AI provider could not complete this worker task."
                    ),
                    evidence=[],
                    artifacts=[],
                    blockers=[
                        {
                            "code": failure_code,
                            "provider_id": provider_name,
                            "model_id": model_name,
                        }
                    ],
                    confidence="low",
                    next_suggested_action="Switch to an available provider and explicitly retry the failed task.",
                    raw={
                        "session_id": result.get("session_id") or handle.session_id,
                        "provider_failure": provider_failure,
                    },
                    publish_fleet_delta=publish_fleet_delta,
                )
                return
            assistant_text = str(result.get("assistant_text") or result.get("raw_response") or "").strip()
            parsed = extract_worker_report(assistant_text)
            if not parsed:
                parsed = {
                    "status": "needs_review",
                    "summary": assistant_text or "The worker returned no structured report.",
                    "evidence": [],
                    "artifacts": [],
                    "blockers": [
                        {
                            "kind": "report_validation",
                            "message": "The worker response did not contain the required structured report fields.",
                        }
                    ],
                    "confidence": "low",
                    "next_suggested_action": "Review the worker transcript and retry with corrected report instructions.",
                    "raw": {"malformed_worker_report": True},
                }
            stopped = handle.stop_requested or str(
                store.get_worker_task(user_id=handle.user_id, task_id=handle.task_id).get("status") or ""
            ) in {"stopped", "canceled"}
            artifacts = list(parsed.get("artifacts") or [])
            artifacts.extend(self._assistant_artifacts(runtime, handle.session_id, artifacts))
            evidence = list(parsed.get("evidence") or [])
            if not evidence and not stopped:
                evidence.append(
                    {
                        "kind": "session",
                        "session_id": handle.session_id,
                        "detail": "Worker final response and runtime timeline were persisted.",
                    }
                )
            await self._complete_report(
                store=store,
                handle=handle,
                status="stopped" if stopped else str(parsed.get("status") or "completed"),
                summary="Task stopped by manager." if stopped else str(parsed.get("summary") or assistant_text or "Task completed."),
                evidence=evidence,
                artifacts=artifacts,
                blockers=["Stopped by manager"] if stopped else list(parsed.get("blockers") or []),
                confidence="medium" if stopped else parsed.get("confidence"),
                next_suggested_action=(
                    "Review the partial worker transcript if needed."
                    if stopped
                    else parsed.get("next_suggested_action")
                ),
                raw={
                    "session_id": result.get("session_id") or handle.session_id,
                    "stopped": stopped,
                    **dict(parsed.get("raw") or {}),
                },
                publish_fleet_delta=publish_fleet_delta,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("[fleet] local worker task failed")
            await self._complete_report(
                store=store,
                handle=handle,
                status="stopped" if handle.stop_requested else "failed",
                summary=(
                    "Task stopped by manager."
                    if handle.stop_requested
                    else f"Worker task failed: {type(exc).__name__}: {exc}"
                ),
                evidence=[],
                artifacts=[],
                blockers=["Stopped by manager"] if handle.stop_requested else [str(exc)],
                confidence="medium" if handle.stop_requested else "low",
                next_suggested_action="Inspect worker runtime logs and retry.",
                raw={"session_id": handle.session_id, "error": str(exc)},
                publish_fleet_delta=publish_fleet_delta,
            )
        finally:
            await bridge.orchestrator.complete_turn(lease)
            await self._release_handle(handle)
            try:
                next_worker = store.get_worker(user_id=handle.user_id, worker_id=handle.worker_id)
                next_task = store.get_next_queued_worker_task(user_id=handle.user_id, worker_id=handle.worker_id)
                if next_task:
                    await self.dispatch(
                        store=store,
                        user_id=handle.user_id,
                        worker=next_worker,
                        task=next_task,
                        bridge_factory=lambda _user_id: bridge,
                        publish_fleet_delta=publish_fleet_delta,
                    )
            except Exception:
                logger.exception("[fleet] failed auto-continuing an eligible local worker queue")

    async def _finish_without_run_if_needed(
        self,
        *,
        store: Any,
        handle: LocalFleetTaskHandle,
        current: Dict[str, Any],
        publish_fleet_delta: Optional[FleetDeltaPublisher],
    ) -> None:
        status = str(current.get("status") or "").strip().lower()
        if status in {"stopped", "canceled"} and not current.get("report_id"):
            await self._complete_report(
                store=store,
                handle=handle,
                status=status,
                summary="Task stopped before the local worker runtime became available.",
                evidence=[],
                artifacts=[],
                blockers=["Stopped by manager"],
                confidence="medium",
                next_suggested_action="Retry the task when runtime resources are available.",
                raw={"session_id": handle.session_id, "stopped_before_start": True},
                publish_fleet_delta=publish_fleet_delta,
            )
        await self._release_handle(handle)

    async def _complete_report(
        self,
        *,
        store: Any,
        handle: LocalFleetTaskHandle,
        status: str,
        summary: str,
        evidence: list[Any],
        artifacts: list[Any],
        blockers: list[Any],
        confidence: Optional[str],
        next_suggested_action: Optional[str],
        raw: Dict[str, Any],
        publish_fleet_delta: Optional[FleetDeltaPublisher],
    ) -> Optional[Dict[str, Any]]:
        current = store.get_worker_task(user_id=handle.user_id, task_id=handle.task_id)
        if current.get("report_id"):
            return None
        try:
            task_metadata = dict(current.get("metadata") or {})
            origin = {
                key: task_metadata.get(key)
                for key in ("origin_manager_session_id", "origin_manager_message_id", "origin_run_id")
                if task_metadata.get(key)
            }
            report = store.complete_worker_task_report(
                user_id=handle.user_id,
                task_id=handle.task_id,
                status=status,
                summary=summary,
                evidence=evidence,
                artifacts=artifacts,
                blockers=blockers,
                confidence=confidence,
                next_suggested_action=next_suggested_action,
                raw={"transport": "local_runtime", "origin": origin, **dict(raw or {})},
            )
        except ValueError as exc:
            if "already has a completed report" in str(exc):
                return None
            raise

        get_channel_sync_hub().publish(
            user_id=handle.user_id,
            event={
                "type": "status",
                "session_id": handle.session_id,
                "origin_channel": "app",
                "payload": {
                    "message": f"Fleet task report completed: {report.get('status')}",
                    "fleet_report": report,
                },
            },
        )
        if publish_fleet_delta:
            publish_fleet_delta(
                user_id=handle.user_id,
                event_type="fleet_task_report",
                payload={"report": report},
                origin_channel="worker",
            )
        try:
            from shared.proactive_runtime import append_fleet_report_event

            append_fleet_report_event(user_id=handle.user_id, report=report)
        except Exception:
            logger.exception("[fleet] failed appending local worker report event")
        return report

    async def _release_handle(self, handle: LocalFleetTaskHandle) -> None:
        async with self._lock:
            self._handles_by_task.pop(handle.task_id, None)
            key = (handle.user_id, handle.worker_id)
            if self._task_by_worker.get(key) == handle.task_id:
                self._task_by_worker.pop(key, None)

    @staticmethod
    async def _default_run_turn(runtime: Any, **kwargs: Any) -> Dict[str, Any]:
        from app_backend.runtime import run_app_chat_turn

        return await run_app_chat_turn(runtime, **kwargs)

    @staticmethod
    def _assistant_artifacts(runtime: Any, session_id: str, existing: list[Any]) -> list[Dict[str, Any]]:
        existing_ids = {
            str(item.get("artifact_id") or "")
            for item in existing
            if isinstance(item, dict)
        }
        history = list(getattr(runtime, "chat_history", []) or [])
        for message in reversed(history):
            if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
                continue
            metadata = dict(message.get("metadata") or {})
            return [
                {"artifact_id": artifact_id, "session_id": session_id}
                for artifact_id in list(metadata.get("artifact_ids") or [])
                if str(artifact_id or "").strip() and str(artifact_id) not in existing_ids
            ]
        return []

    @staticmethod
    def _publish_task_status(
        *,
        user_id: int,
        task: Dict[str, Any],
        publish_fleet_delta: Optional[FleetDeltaPublisher],
        detail: str,
    ) -> None:
        if publish_fleet_delta:
            publish_fleet_delta(
                user_id=int(user_id),
                event_type="fleet_task_status",
                payload={"task": task, "detail": detail},
                origin_channel="worker",
            )


_LOCAL_FLEET_RUNTIME = LocalFleetRuntime()


def get_local_fleet_runtime() -> LocalFleetRuntime:
    return _LOCAL_FLEET_RUNTIME
