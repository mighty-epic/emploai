from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

REMOTE_HTTP_PROXY_TIMEOUT_SECONDS = 120.0

def _bridge_for_user(user_id: int) -> AppSessionBridge:

    workspace = _workspace_root()

    from mobile_app.backend.session_bridge import AppSessionBridge

    return AppSessionBridge(user_id=user_id, workspace=workspace)

def _timeline_event_is_user_visible(event: Any) -> bool:

    if not isinstance(event, dict):

        return False

    from mobile_app.backend.session_bridge import is_user_visible_timeline_event

    return is_user_visible_timeline_event(event)

def _runtime_message_is_user_visible(message: Any) -> bool:

    text = str(message or "").strip().casefold()

    if not text:

        return False

    if "planner verifier" in text or "final quality guard" in text:

        return False

    if "candidate final:" in text:

        return False

    return True

def _run_workspace_git_command(target_path: Path, git_args: list[str]) -> Dict[str, Any]:

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    try:

        result = subprocess.run(

            ["git", "-C", str(target_path), *git_args],

            capture_output=True,

            text=True,

            timeout=12,

            shell=False,

            creationflags=creationflags,

            check=False,

        )

    except FileNotFoundError:

        return {"ok": False, "error": "git is not available", "stdout": "", "stderr": ""}

    except subprocess.TimeoutExpired:

        return {"ok": False, "error": "git command timed out", "stdout": "", "stderr": ""}

    except OSError as exc:

        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}

    stdout = str(result.stdout or "").strip()

    stderr = str(result.stderr or "").strip()

    if result.returncode != 0:

        return {

            "ok": False,

            "error": stderr or stdout or f"git exited with code {result.returncode}",

            "stdout": stdout,

            "stderr": stderr,

        }

    return {"ok": True, "error": None, "stdout": stdout, "stderr": stderr}

def _workspace_git_empty_state(

    *,

    requested_path: Optional[str],

    resolved_path: Optional[Path],

    error: Optional[str] = None,

) -> Dict[str, Any]:

    return {

        "requestedPath": requested_path,

        "resolvedPath": str(resolved_path) if resolved_path is not None else None,

        "repoRoot": None,

        "isGitRepo": False,

        "currentBranch": None,

        "branches": [],

        "error": error,

    }

def _workspace_git_state(target_path: str) -> Dict[str, Any]:

    candidate = str(target_path or "").strip()

    if not candidate:

        raise HTTPException(status_code=400, detail="Missing workspace path")

    try:

        resolved_path = Path(candidate).expanduser().resolve()

    except OSError:

        resolved_path = Path(candidate).expanduser().absolute()

    if not resolved_path.exists() or not resolved_path.is_dir():

        return _workspace_git_empty_state(

            requested_path=candidate,

            resolved_path=resolved_path,

            error="Folder not available",

        )

    top_level = _run_workspace_git_command(resolved_path, ["rev-parse", "--show-toplevel"])

    if not top_level.get("ok") or not top_level.get("stdout"):

        return _workspace_git_empty_state(

            requested_path=candidate,

            resolved_path=resolved_path,

            error=None,

        )

    repo_root = str(Path(str(top_level["stdout"])).expanduser().resolve())

    current_branch_result = _run_workspace_git_command(resolved_path, ["branch", "--show-current"])

    branch_list_result = _run_workspace_git_command(

        resolved_path,

        ["for-each-ref", "--format=%(refname:short)", "refs/heads"],

    )

    current_branch = str(current_branch_result.get("stdout") or "").strip() or None if current_branch_result.get("ok") else None

    branches: list[str] = []

    if branch_list_result.get("ok"):

        seen: set[str] = set()

        for line in str(branch_list_result.get("stdout") or "").splitlines():

            branch = line.strip()

            if not branch or branch in seen:

                continue

            seen.add(branch)

            branches.append(branch)

    if current_branch and current_branch not in branches:

        branches.insert(0, current_branch)

    return {

        "requestedPath": candidate,

        "resolvedPath": str(resolved_path),

        "repoRoot": repo_root,

        "isGitRepo": True,

        "currentBranch": current_branch,

        "branches": branches,

        "error": None,

    }

def _workspace_git_checkout(target_path: str, branch_name: str) -> Dict[str, Any]:

    branch = str(branch_name or "").strip()

    if not branch:

        raise HTTPException(status_code=400, detail="Missing branch name")

    info = _workspace_git_state(target_path)

    if not bool(info.get("isGitRepo")) or not info.get("resolvedPath"):

        return {**info, "error": info.get("error") or "Not a Git repository"}

    if info.get("currentBranch") == branch:

        return info

    switched = _run_workspace_git_command(Path(str(info["resolvedPath"])), ["switch", branch])

    if not switched.get("ok"):

        return {**info, "error": str(switched.get("error") or "Failed to switch branch")}

    return _workspace_git_state(str(info["resolvedPath"]))

def _path_signature(path: Path) -> Optional[tuple[int, int]]:

    try:

        stat = path.stat()

    except OSError:

        return None

    return (int(stat.st_mtime_ns), int(stat.st_size))

def _resolve_pairing_user_id(pairing_id: str) -> int:

    pairing = _get_auth_store().get_pairing(pairing_id)

    if not pairing:

        raise HTTPException(status_code=404, detail="Unknown pairing")

    created_by = str(pairing.get("created_by") or "").strip()

    if created_by.startswith("user:"):

        try:

            return int(created_by.split(":", 1)[1])

        except ValueError:

            pass

    return _default_user_id()

def _is_remote_session_auth(payload: Dict[str, Any]) -> bool:

    return str(payload.get("auth_kind") or "").strip() == "remote_session"

def _is_remote_mobile_session_auth(payload: Dict[str, Any]) -> bool:

    return _is_remote_session_auth(payload) and str(payload.get("actor_kind") or "").strip() == "mobile"

def _is_remote_desktop_session_auth(payload: Dict[str, Any]) -> bool:

    return _is_remote_session_auth(payload) and str(payload.get("actor_kind") or "").strip() == "desktop"

def _remote_shared_state(payload: Dict[str, Any]) -> Dict[str, Any]:

    return _get_remote_control_store().get_shared_state(user_id=int(payload["user_id"]))

def _remote_current_session_id(payload: Dict[str, Any]) -> Optional[str]:

    state = _remote_shared_state(payload)

    fleet = state.get("fleet") if isinstance(state.get("fleet"), dict) else {}

    active_identity_id = str((fleet or {}).get("active_identity_id") or "").strip()

    selected_by_identity = (fleet or {}).get("selected_chat_by_identity")

    if active_identity_id and isinstance(selected_by_identity, dict):

        selected_session_id = str(selected_by_identity.get(active_identity_id) or "").strip()

        if selected_session_id:

            return selected_session_id

    current_session_id = str(state.get("current_session_id") or "").strip()

    return current_session_id or None

def _fleet_task_target_session_id(

    *,

    snapshot: Dict[str, Any],

    worker: Dict[str, Any],

    request: FleetAssignTaskRequest,

) -> Optional[str]:

    return _fleet_task_target_session_id_from_values(

        snapshot=snapshot,

        worker=worker,

        target_session_id=request.target_session_id,

        target_mode=request.target_mode,

        metadata=dict(getattr(request, "metadata", None) or {}),

    )

def _publish_fleet_delta(

    *,

    user_id: int,

    event_type: str,

    payload: Optional[Dict[str, Any]] = None,

    origin_channel: str = "fleet",

) -> None:

    """Publish a compact Fleet event plus a fresh snapshot for synced clients."""

    clean_event_type = str(event_type or "fleet_snapshot_delta").strip() or "fleet_snapshot_delta"

    payload_dict = dict(payload or {})

    try:

        snapshot = _get_remote_control_store().get_fleet_snapshot(user_id=int(user_id))

        payload_dict.setdefault("snapshot", snapshot)

    except Exception:

        logger.exception("[fleet] failed attaching snapshot to %s", clean_event_type)

    get_channel_sync_hub().publish(

        user_id=int(user_id),

        event={

            "type": clean_event_type,

            "session_id": None,

            "origin_channel": origin_channel,

            "payload": payload_dict,

        },

    )

def _publish_confirmation_delta(*, user_id: int, confirmation: Dict[str, Any], origin_channel: str = "app") -> None:

    _publish_confirmation_delta_workflow(

        sync_hub=get_channel_sync_hub(),

        user_id=int(user_id),

        confirmation=confirmation,

        origin_channel=origin_channel,

    )

def _consume_approved_confirmation(

    *,

    user_id: int,

    confirmation_id: Optional[str],

    action_kind: str,

    executed_by_surface: str,

    metadata: Optional[Dict[str, Any]] = None,

) -> Dict[str, Any]:

    return _consume_approved_confirmation_workflow(

        store=_get_remote_control_store(),

        publish_confirmation_delta=_publish_confirmation_delta,

        user_id=int(user_id),

        confirmation_id=confirmation_id,

        action_kind=action_kind,

        executed_by_surface=executed_by_surface,

        metadata=metadata,

    )

def _collect_cloud_object_keys(value: Any) -> set[str]:

    keys: set[str] = set()

    if isinstance(value, dict):

        for key, nested in value.items():

            if str(key) == "cloud_object_key":

                clean = str(nested or "").strip()

                if clean:

                    keys.add(clean)

            else:

                keys.update(_collect_cloud_object_keys(nested))

    elif isinstance(value, list):

        for item in value:

            keys.update(_collect_cloud_object_keys(item))

    return keys

def _purge_archived_cloud_objects(*, user_id: int, archived_item: Dict[str, Any]) -> Dict[str, Any]:

    keys = _collect_cloud_object_keys(archived_item.get("payload"))

    keys.update(_collect_cloud_object_keys(archived_item.get("metadata")))

    if not keys:

        return {"deleted": 0, "object_keys": []}

    store = CloudObjectStore(user_id=int(user_id))

    deleted = 0

    results: list[Dict[str, Any]] = []

    for key in sorted(keys):

        try:

            result = store.delete_object(key)

            results.append(result)

            if result.get("deleted"):

                deleted += 1

        except Exception as exc:

            logger.warning("[recovery] failed deleting cloud object %s: %s", key, exc)

            results.append({"object_key": key, "deleted": False, "reason": str(exc)})

    return {"deleted": deleted, "object_keys": sorted(keys), "results": results}

def _remote_profile_view(payload: Dict[str, Any]) -> AppUserProfile:

    state = _remote_shared_state(payload)

    return AppUserProfile(

        user_id=int(payload["user_id"]),

        current_session_id=_remote_current_session_id(payload),

        current_model=str(state.get("current_model") or "").strip() or None,

        current_variant=str(state.get("current_variant") or "").strip() or None,

        device_id=str(payload.get("mobile_id") or payload.get("desktop_id") or "").strip() or None,

        device_name=str(payload.get("device_name") or payload.get("desktop_name") or "").strip() or None,

        device_platform=str(payload.get("device_platform") or payload.get("actor_kind") or "").strip() or None,

    )

def _remote_session_summary_views(payload: Dict[str, Any]) -> list[SessionSummaryView]:

    state = _remote_shared_state(payload)

    items = []

    for raw in list(state.get("sessions") or []):

        try:

            items.append(SessionSummaryView.model_validate(raw))

        except Exception:

            continue

    return items

def _remote_session_detail_view(payload: Dict[str, Any], session_id: Optional[str]) -> SessionDetailView:

    state = _remote_shared_state(payload)

    target_session_id = str(session_id or state.get("current_session_id") or "").strip()

    if not target_session_id:

        raise HTTPException(status_code=404, detail="No current session")

    details = dict(state.get("session_details") or {})

    raw = details.get(target_session_id)

    if not raw:

        raise HTTPException(status_code=404, detail="Session detail is not available yet")

    if isinstance(raw, dict):

        raw = dict(raw)

        raw["timeline_events"] = [

            event

            for event in list(raw.get("timeline_events") or [])

            if _timeline_event_is_user_visible(event)

        ]

    try:

        return SessionDetailView.model_validate(raw)

    except Exception as exc:

        raise HTTPException(status_code=503, detail=f"Remote session detail is malformed: {exc}") from exc

async def _remote_wait_for_sync_version(user_id: int, baseline: int, *, timeout_seconds: float = 8.0) -> Dict[str, Any]:

    deadline = time.monotonic() + max(0.5, timeout_seconds)

    store = _get_remote_control_store()

    while time.monotonic() < deadline:

        state = store.get_shared_state(user_id=user_id)

        if int(state.get("sync_version", 0) or 0) > int(baseline):

            return state

        await asyncio.sleep(0.2)

    return store.get_shared_state(user_id=user_id)

def _remote_desktop_id_for_command(auth: Dict[str, Any]) -> Optional[str]:

    store = _get_remote_control_store()

    manager = get_remote_desktop_manager()

    actor_kind = str(auth.get("actor_kind") or "").strip()

    user_id = int(auth["user_id"])

    preferred_desktop_id = store.paired_desktop_id_for_payload(auth)

    if actor_kind == "desktop":

        return preferred_desktop_id

    if actor_kind != "mobile" or not preferred_desktop_id:

        return None

    if manager.is_connected_for_user(preferred_desktop_id, user_id):

        return preferred_desktop_id

    state = store.get_shared_state(user_id=user_id)

    desktop_connection = state.get("desktop_connection") if isinstance(state.get("desktop_connection"), dict) else {}

    candidate_ids = [

        str(state.get("current_desktop_id") or "").strip(),

        str(desktop_connection.get("desktop_id") or "").strip(),

    ]

    seen: set[str] = set()

    for candidate_id in candidate_ids:

        if not candidate_id or candidate_id in seen:

            continue

        seen.add(candidate_id)

        if not manager.is_connected_for_user(candidate_id, user_id):

            continue

        mobile_id = str(auth.get("mobile_id") or "").strip()

        if mobile_id and candidate_id != preferred_desktop_id:

            try:

                store.repair_mobile_pairing(

                    user_id=user_id,

                    mobile_id=mobile_id,

                    desktop_id=candidate_id,

                )

            except Exception:

                logger.exception("[remote] failed repairing stale mobile desktop pairing")

        return candidate_id

    return preferred_desktop_id

def _machine_id_for_workspace_binding(auth: Dict[str, Any]) -> str:

    for key in ("desktop_id", "device_id", "mobile_id"):

        value = str(auth.get(key) or "").strip()

        if value:

            return value

    return "local-runtime"

def _sync_session_workspace_binding(*, user_id: int, auth: Dict[str, Any], session: Any) -> None:

    workspace_id = str(getattr(session, "workspace_id", "") or "").strip()

    workspace = str(getattr(session, "workspace", "") or "").strip()

    if not workspace_id or not workspace:

        return

    try:

        path = Path(workspace).expanduser()

        status = "active" if path.exists() else "needs_reconnect"

        setattr(session, "workspace_binding_status", status)

        _get_remote_control_store().upsert_workspace_binding(

            user_id=int(user_id),

            workspace_id=workspace_id,

            machine_id=_machine_id_for_workspace_binding(auth),

            local_path=str(path),

            label=path.name or workspace_id,

            status=status,

            metadata={

                "session_id": getattr(session, "id", None),

                "source": str(auth.get("actor_kind") or "app"),

                "synced_from_session": True,

            },

        )

    except Exception:

        logger.exception("[workspace] failed syncing session workspace binding")

def _cloud_chat_backup_enabled(user_id: int) -> bool:

    try:

        profile = _get_remote_control_store().get_user_profile(user_id=int(user_id))

        preferences = profile.get("preferences") if isinstance(profile, dict) else {}

        if isinstance(preferences, dict) and "cloud_chat_backup_enabled" in preferences:

            return bool(preferences.get("cloud_chat_backup_enabled"))

    except Exception:

        logger.exception("[recovery] failed reading cloud chat backup preference")

    return True

def _mirror_session_snapshot(

    *,

    user_id: int,

    bridge: Any,

    session: Any,

    reason: str,

    status: str = "active",

) -> None:

    try:

        if not _cloud_chat_backup_enabled(int(user_id)):

            return

        payload = bridge.detailed_session_view(session)

        try:

            payload["artifacts"] = bridge.list_session_artifacts(str(getattr(session, "id", "") or payload.get("id") or ""))

        except Exception:

            payload["artifacts"] = []

        _get_remote_control_store().upsert_cloud_session_snapshot(

            user_id=int(user_id),

            session_id=str(getattr(session, "id", "") or payload.get("id") or ""),

            payload=payload,

            metadata={

                "reason": reason,

                "workspace_id": payload.get("workspace_id"),

                "fleet_identity_id": payload.get("fleet_identity_id"),

                "fleet_identity_role": payload.get("fleet_identity_role"),

                "message_count": len(list(payload.get("messages") or [])),

                "artifact_count": len(list(payload.get("artifacts") or [])),

            },

            status=status,

        )

    except Exception:

        logger.exception("[recovery] failed mirroring session snapshot")

def _mirror_session_snapshot_later(

    *,

    user_id: int,

    bridge: Any,

    session: Any,

    reason: str,

    status: str = "active",

) -> None:

    try:

        task = asyncio.create_task(

            asyncio.to_thread(

                _mirror_session_snapshot,

                user_id=user_id,

                bridge=bridge,

                session=session,

                reason=reason,

                status=status,

            )

        )

    except RuntimeError:

        _mirror_session_snapshot(

            user_id=user_id,

            bridge=bridge,

            session=session,

            reason=reason,

            status=status,

        )

        return

    _BACKGROUND_SESSION_MIRROR_TASKS.add(task)

    task.add_done_callback(lambda finished: _BACKGROUND_SESSION_MIRROR_TASKS.discard(finished))

def _workspace_id_for_task_request(*, user_id: int, auth: Dict[str, Any], request: Any) -> Optional[str]:

    metadata = dict(getattr(request, "metadata", None) or {})

    def resolve_workspace_id(target_session_id: str) -> Optional[str]:

        session = _bridge_for_user(int(user_id)).get_session(target_session_id)

        return str(getattr(session, "workspace_id", "") or "").strip() or None

    return _workspace_id_for_task_values(

        workspace_id=getattr(request, "workspace_id", None),

        target_session_id=getattr(request, "target_session_id", None),

        metadata=metadata,

        resolve_workspace_id_for_session=resolve_workspace_id,

    )

def _workspace_binding_blocker_for_task(

    *,

    user_id: int,

    worker: Dict[str, Any],

    request: Any,

) -> Optional[Dict[str, Any]]:

    metadata = dict(getattr(request, "metadata", None) or {})

    prompt = str(getattr(request, "prompt", "") or "")

    requires_workspace_write = bool(getattr(request, "requires_workspace_write", False))

    if not _task_requires_workspace_write(prompt, metadata, requires_workspace_write):

        return None

    workspace_id = _workspace_id_for_task_request(user_id=user_id, auth={}, request=request)

    if not workspace_id:

        return _workspace_binding_blocker_for_task_values(

            worker=worker,

            prompt=prompt,

            metadata=metadata,

            requires_workspace_write=requires_workspace_write,

            workspace_id=workspace_id,

            target_session_id=getattr(request, "target_session_id", None),

            workspace_bindings=(),

        )

    machine_id = str(worker.get("machine_desktop_id") or worker.get("desktop_id") or "").strip()

    snapshot = _get_remote_control_store().get_fleet_snapshot(user_id=int(user_id), desktop_id=machine_id or None)

    return _workspace_binding_blocker_for_task_values(

        worker=worker,

        prompt=prompt,

        metadata=metadata,

        requires_workspace_write=requires_workspace_write,

        workspace_id=workspace_id,

        target_session_id=getattr(request, "target_session_id", None),

        workspace_bindings=list(snapshot.get("workspace_bindings") or []),

    )

async def _remote_dispatch_command(

    auth: Dict[str, Any],

    *,

    command_name: str,

    payload: Dict[str, Any],

) -> str:

    desktop_id = _remote_desktop_id_for_command(auth)

    if not desktop_id:

        raise HTTPException(status_code=409, detail="No paired desktop is available for this account")

    if not _remote_desktop_connection_session_is_active(desktop_id=desktop_id, user_id=int(auth["user_id"])):

        raise HTTPException(status_code=409, detail="The paired desktop session expired")

    manager = get_remote_desktop_manager()

    if remote_control_sqlite_broker_enabled() and not manager.is_connected_for_user(desktop_id, int(auth["user_id"])):

        try:

            return dispatch_remote_desktop_command_via_broker(

                store=_get_remote_control_store(),

                user_id=int(auth["user_id"]),

                desktop_id=desktop_id,

                command_name=command_name,

                payload=payload,

                ttl_seconds=30,

            )

        except KeyError as exc:

            raise HTTPException(status_code=409, detail="The paired desktop is unavailable for this account") from exc

    try:

        return await manager.send_command(

            desktop_id=desktop_id,

            user_id=int(auth["user_id"]),

            command_type=command_name,

            payload=payload,

        )

    except RuntimeError as exc:

        detail = str(exc)

        if _command_error_implies_desktop_unavailable(detail):

            _mark_remote_desktop_offline_if_no_live_connection(

                user_id=int(auth["user_id"]),

                desktop_id=desktop_id,

                reason=detail,

            )

        raise HTTPException(status_code=409, detail=detail) from exc

async def _remote_request_desktop_command(

    auth: Dict[str, Any],

    *,

    command_name: str,

    payload: Dict[str, Any],

    timeout_seconds: float = 30.0,

) -> Dict[str, Any]:

    desktop_id = _remote_desktop_id_for_command(auth)

    if not desktop_id:

        raise HTTPException(status_code=409, detail="No paired desktop is available for this account")

    if not _remote_desktop_connection_session_is_active(desktop_id=desktop_id, user_id=int(auth["user_id"])):

        raise HTTPException(status_code=409, detail="The paired desktop session expired")

    manager = get_remote_desktop_manager()

    if remote_control_sqlite_broker_enabled() and not manager.is_connected_for_user(desktop_id, int(auth["user_id"])):

        try:

            return await request_remote_desktop_command_via_broker(

                store=_get_remote_control_store(),

                user_id=int(auth["user_id"]),

                desktop_id=desktop_id,

                command_name=command_name,

                payload=payload,

                timeout_seconds=timeout_seconds,

            )

        except asyncio.TimeoutError as exc:

            raise HTTPException(status_code=504, detail="The paired desktop did not answer in time") from exc

        except KeyError as exc:

            raise HTTPException(status_code=409, detail="The paired desktop is unavailable for this account") from exc

        except BrokeredRemoteCommandError as exc:

            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    try:

        reply = await manager.request_command(

            desktop_id=desktop_id,

            user_id=int(auth["user_id"]),

            command_type=command_name,

            payload=payload,

            timeout_seconds=timeout_seconds,

        )

    except asyncio.TimeoutError as exc:

        raise HTTPException(status_code=504, detail="The paired desktop did not answer in time") from exc

    except RuntimeError as exc:

        detail = str(exc)

        if _command_error_implies_desktop_unavailable(detail):

            _mark_remote_desktop_offline_if_no_live_connection(

                user_id=int(auth["user_id"]),

                desktop_id=desktop_id,

                reason=detail,

            )

        raise HTTPException(status_code=409, detail=detail) from exc

    if not bool(reply.get("ok", False)):

        detail = str(reply.get("error") or "The paired desktop could not complete the request")

        status_code = int(reply.get("status_code") or 502)

        if status_code < 400 or status_code > 599:

            status_code = 502

        raise HTTPException(status_code=status_code, detail=detail)

    return dict(reply.get("result") or {})

async def _try_dispatch_fleet_worker_task(

    *,

    user_id: int,

    worker: Dict[str, Any],

    task: Dict[str, Any],

) -> Dict[str, Any]:

    return await try_dispatch_fleet_worker_task(

        store=_get_remote_control_store(),

        remote_desktop_manager=get_remote_desktop_manager(),

        user_id=int(user_id),

        worker=worker,

        task=task,

        is_remote_session_active=_remote_desktop_connection_session_is_active,

        is_desktop_unavailable_error=_command_error_implies_desktop_unavailable,

        mark_desktop_offline=_mark_remote_desktop_offline_if_no_live_connection,

    )

async def _try_dispatch_next_fleet_worker_task(*, user_id: int, worker_id: str) -> Optional[Dict[str, Any]]:

    clean_worker_id = str(worker_id or "").strip()

    if not clean_worker_id:

        return None

    store = _get_remote_control_store()

    try:

        worker = store.get_worker(user_id=int(user_id), worker_id=clean_worker_id)

        next_task = store.get_next_queued_worker_task(user_id=int(user_id), worker_id=clean_worker_id)

        if not next_task:

            return None

        dispatched = await _try_dispatch_fleet_worker_task(

            user_id=int(user_id),

            worker=worker,

            task=next_task,

        )

        return dispatched

    except Exception:

        logger.exception("[fleet] failed dispatching next queued worker task")

        return None

async def _try_stop_fleet_worker_task(*, user_id: int, task: Dict[str, Any]) -> bool:

    return await try_stop_fleet_worker_task(

        store=_get_remote_control_store(),

        remote_desktop_manager=get_remote_desktop_manager(),

        user_id=int(user_id),

        task=task,

        is_remote_session_active=_remote_desktop_connection_session_is_active,

        is_desktop_unavailable_error=_command_error_implies_desktop_unavailable,

        mark_desktop_offline=_mark_remote_desktop_offline_if_no_live_connection,

    )

_FLEET_STOPPABLE_TASK_STATUSES = {"running", "paused", "blocked", "needs_review"}

def _fleet_active_task_for_worker(

    *,

    snapshot: Dict[str, Any],

    worker: Dict[str, Any],

    metadata: Optional[Dict[str, Any]] = None,

) -> Optional[Dict[str, Any]]:

    worker_id = str(worker.get("worker_id") or "").strip()

    if not worker_id:

        return None

    active_tasks = [

        dict(task)

        for task in list(snapshot.get("tasks") or [])

        if str(task.get("worker_id") or "").strip() == worker_id

        and str(task.get("status") or "").strip().lower() in _FLEET_STOPPABLE_TASK_STATUSES

    ]

    requested_task_id = str((metadata or {}).get("task_id") or "").strip()

    if requested_task_id:

        return next(

            (task for task in active_tasks if str(task.get("task_id") or "").strip() == requested_task_id),

            None,

        )

    active_task_id = str(worker.get("active_task_id") or "").strip()

    if active_task_id:

        matched = next(

            (task for task in active_tasks if str(task.get("task_id") or "").strip() == active_task_id),

            None,

        )

        if matched:

            return matched

    return active_tasks[0] if active_tasks else None

async def _stop_fleet_worker_active_task(

    *,

    user_id: int,

    worker_id: str,

    reason: Optional[str] = None,

    metadata: Optional[Dict[str, Any]] = None,

) -> Dict[str, Any]:

    store = _get_remote_control_store()

    worker = store.get_worker(user_id=int(user_id), worker_id=str(worker_id or "").strip())

    snapshot = store.get_fleet_snapshot(user_id=int(user_id))

    active_task = _fleet_active_task_for_worker(

        snapshot=snapshot,

        worker=worker,

        metadata=metadata,

    )

    active_task_id = str((active_task or {}).get("task_id") or "").strip()

    if not active_task_id:

        requested_task_id = str((metadata or {}).get("task_id") or "").strip()

        return {

            "worker_id": worker.get("worker_id"),

            "stopped": False,

            "reason": "task_not_active" if requested_task_id else "worker_idle",

            "task_id": requested_task_id or None,

            "worker": worker,

        }

    task = store.update_worker_task_status(

        user_id=int(user_id),

        task_id=active_task_id,

        status="stopped",

        metadata={

            **dict(metadata or {}),

            "reason": str(reason or "Stopped by manager").strip(),

            "stopped_by": "manager",

        },

    )

    live_stop_sent = await _try_stop_fleet_worker_task(user_id=int(user_id), task=task)

    return {

        "worker_id": worker.get("worker_id"),

        "stopped": True,

        "live_stop_sent": live_stop_sent,

        "task": task,

    }

def _remote_http_proxy_headers(headers: Dict[str, str], allowed: set[str]) -> Dict[str, str]:

    return filter_remote_http_proxy_headers(headers, allowed)

def _should_proxy_remote_http_request(method: str, path: str) -> bool:

    return should_proxy_remote_http_request(method, path, allowed_methods=_REMOTE_HTTP_PROXY_ALLOWED_METHODS)

def _max_base64_chars_for_bytes(byte_limit: int) -> int:

    return max_base64_chars_for_bytes(byte_limit)

def _remote_http_proxy_status_code(value: Any) -> int:

    return remote_http_proxy_status_code(value)

def _remote_http_proxy_body_bytes(value: Any) -> bytes:

    return remote_http_proxy_body_bytes(value, max_response_body_bytes=REMOTE_HTTP_PROXY_MAX_RESPONSE_BODY_BYTES)

async def _read_remote_http_proxy_request_body(request: Request) -> bytes:

    chunks: list[bytes] = []

    total = 0

    async for chunk in request.stream():

        if not chunk:

            continue

        total += len(chunk)

        if total > REMOTE_HTTP_PROXY_MAX_BODY_BYTES:

            raise HTTPException(status_code=413, detail="Remote request body is too large")

        chunks.append(chunk)

    return b"".join(chunks)

async def _remote_desktop_http_request(

    auth: Dict[str, Any],

    *,

    method: str,

    path: str,

    query_string: str = "",

    headers: Optional[Dict[str, str]] = None,

    body: bytes = b"",

    timeout_seconds: float = REMOTE_HTTP_PROXY_TIMEOUT_SECONDS,

) -> Dict[str, Any]:

    if len(body) > REMOTE_HTTP_PROXY_MAX_BODY_BYTES:

        raise HTTPException(status_code=413, detail="Remote request body is too large")

    return await _remote_request_desktop_command(

        auth,

        command_name="http_request",

        payload={

            "method": method.upper(),

            "path": path,

            "query_string": query_string,

            "headers": dict(headers or {}),

            "body_base64": base64.b64encode(body).decode("ascii") if body else "",

        },

        timeout_seconds=timeout_seconds,

    )

async def _remote_proxy_http_request(request: Request, auth: Dict[str, Any]) -> Optional[Response]:

    if not _is_remote_mobile_session_auth(auth):

        return None

    path = request.url.path

    if not _should_proxy_remote_http_request(request.method, path):

        return None

    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and path in _REMOTE_AGENT_EXPLICIT_SESSION_PATHS:

        if not str(request.query_params.get("session_id") or "").strip():

            raise HTTPException(status_code=400, detail="Open or select a chat before using agent controls.")

    body = await _read_remote_http_proxy_request_body(request)

    result = await _remote_desktop_http_request(

        auth,

        method=request.method,

        path=path,

        query_string=request.url.query,

        headers=_remote_http_proxy_headers(dict(request.headers), _REMOTE_HTTP_PROXY_REQUEST_HEADERS),

        body=body,

    )

    status_code = _remote_http_proxy_status_code(result.get("status_code"))

    headers = _remote_http_proxy_headers(dict(result.get("headers") or {}), _REMOTE_HTTP_PROXY_RESPONSE_HEADERS)

    body_bytes = _remote_http_proxy_body_bytes(result.get("body_base64"))

    return Response(content=body_bytes, status_code=status_code, headers=headers)

async def _handle_remote_screen_ws(websocket: WebSocket, auth: Dict[str, Any], send_lock: asyncio.Lock) -> None:

    async def send_model(event: RealtimeServerEvent) -> None:

        await _send_realtime_event(websocket, send_lock, event)

    try:

        fps = float(websocket.query_params.get("fps", "1.0") or "1.0")

    except ValueError:

        fps = 1.0

    fps = max(0.4, min(fps, 3.0))

    interval_seconds = 1.0 / fps

    try:

        max_width = int(websocket.query_params.get("max_width", "960") or "960")

    except ValueError:

        max_width = 960

    try:

        jpeg_quality = int(websocket.query_params.get("quality", "55") or "55")

    except ValueError:

        jpeg_quality = 55

    jpeg_quality = max(30, min(jpeg_quality, 85))

    await send_model(

        RealtimeServerEvent(

            type="screen_state",

            payload={

                "state": "connected",

                "mode": "remote",

                "fps": fps,

                "max_width": max_width,

                "quality": jpeg_quality,

            },

        )

    )

    announced_streaming = False

    try:

        while True:

            await _ensure_remote_ws_session_active(websocket, auth)

            query = f"max_width={max_width}&quality={jpeg_quality}"

            result = await _remote_desktop_http_request(

                auth,

                method="GET",

                path="/api/app/screenshot/current",

                query_string=query,

                timeout_seconds=20.0,

            )

            status_code = int(result.get("status_code") or 502)

            body_bytes = _remote_http_proxy_body_bytes(result.get("body_base64"))

            if status_code >= 400:

                detail = body_bytes.decode("utf-8", errors="replace")[:400]

                raise RuntimeError(detail or f"Desktop screenshot failed ({status_code})")

            capture = json.loads(body_bytes.decode("utf-8"))

            if not isinstance(capture, dict):

                raise RuntimeError("Desktop screenshot response was malformed")

            if not announced_streaming:

                await send_model(

                    RealtimeServerEvent(

                        type="screen_state",

                        payload={"state": "streaming", "mode": "remote", "fps": fps},

                    )

                )

                announced_streaming = True

            await send_model(RealtimeServerEvent(type="screen_frame", payload=dict(capture or {})))

            await asyncio.sleep(interval_seconds)

    except WebSocketDisconnect:

        raise

    except HTTPException as exc:

        await send_model(

            RealtimeServerEvent(

                type="screen_state",

                payload={

                    "state": "error",

                    "mode": "remote",

                    "message": str(exc.detail or "Remote desktop screen stream failed")[:400],

                },

            )

        )

    except Exception as exc:

        await send_model(

            RealtimeServerEvent(

                type="screen_state",

                payload={

                    "state": "error",

                    "mode": "remote",

                    "message": str(exc or "Remote desktop screen stream failed")[:400],

                },

            )

        )

    try:

        await websocket.close(code=1011)

    except Exception:

        pass
