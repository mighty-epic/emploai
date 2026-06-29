from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shared.artifact_store import ChatArtifactStore
from shared.channel_runtime_events import _publish_sync_event, _turn_sync_event, current_session_id
from shared.security_policy import redact_json, redact_text

FILE_SNAPSHOT_TOOL_NAMES = {"write_file", "edit_file", "append_file"}
TRACKED_FILE_REFRESH_TOOL_NAMES = {"read_file", "open_file"}
COMMAND_OUTPUT_TOOL_NAMES = {"run_command", "execute_command", "run_background_command", "command_status"}
BROWSER_OBSERVATION_TOOL_NAMES = {"browser_snapshot", "observe_browser", "browser_read_text"}
VISUAL_SCREEN_TOOL_NAMES = {"describe_screen", "browser_screenshot"}
_NON_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
TEXT_PREVIEW_HEAD_CHARS = 900
TEXT_PREVIEW_TAIL_CHARS = 900

def _artifact_store_for_session(session: Any, *, session_id: Optional[str] = None) -> Optional[ChatArtifactStore]:
    user_id = getattr(session, "user_id", None)
    resolved_session_id = str(session_id or current_session_id(session) or "").strip()
    if user_id is None or not resolved_session_id:
        return None
    return ChatArtifactStore(user_id=int(user_id), session_id=resolved_session_id)


def _sanitize_artifact_metadata(value: Any) -> Any:
    value = redact_json(value)
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if key in {"image_base64", "base64", "image_data", "data"} and isinstance(item, str):
                cleaned[key] = f"[omitted image data: {len(item)} chars]"
            else:
                cleaned[str(key)] = _sanitize_artifact_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_artifact_metadata(item) for item in value[:80]]
    return value


def _sanitize_runtime_event_value(value: Any, *, string_limit: int = 12000) -> Any:
    value = redact_json(value)
    safe = _sanitize_artifact_metadata(value)
    if isinstance(safe, dict):
        return {str(key): _sanitize_runtime_event_value(item, string_limit=string_limit) for key, item in safe.items()}
    if isinstance(safe, list):
        return [_sanitize_runtime_event_value(item, string_limit=string_limit) for item in safe[:80]]
    if isinstance(safe, str) and len(safe) > string_limit:
        omitted = len(safe) - string_limit
        return f"{safe[:string_limit]}\n...[truncated from runtime event: {omitted} chars]..."
    return safe


def _artifact_summary_payload(store: ChatArtifactStore, artifact_id: str) -> Optional[Dict[str, Any]]:
    record = store.get_record(artifact_id)
    if not record:
        return None
    return store.build_summary_view(record)


def _publish_artifact_created(
    session: Any,
    *,
    reservation: TurnReservation,
    store: Optional[ChatArtifactStore],
    artifact_ids: List[str],
    schedule_emit: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    if not store or not artifact_ids:
        return
    artifacts = [
        summary
        for artifact_id in artifact_ids
        for summary in [_artifact_summary_payload(store, artifact_id)]
        if summary is not None
    ]
    if not artifacts:
        return
    _publish_sync_event(
        session,
        _turn_sync_event(
            event_type="artifact_created",
            session_id=reservation.session_id,
            payload={"artifacts": artifacts},
            event_meta=reservation.event_meta,
        ),
    )
    if schedule_emit:
        schedule_emit({"type": "artifact_created", "artifacts": artifacts})


def _workspace_relative_text(session: Any, path: Path) -> str:
    workspace = str(getattr(session, "workspace", "") or "").strip()
    if not workspace:
        return path.name
    try:
        return str(path.resolve().relative_to(Path(workspace).expanduser().resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def _resolve_workspace_path(session: Any, path_value: Optional[str]) -> Optional[Path]:
    text = str(path_value or "").strip()
    if not text:
        return None
    workspace = str(getattr(session, "workspace", "") or "").strip()
    try:
        candidate = Path(text).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        if workspace:
            return (Path(workspace).expanduser().resolve() / candidate).resolve()
        return candidate.resolve()
    except Exception:
        return None


def _track_mutated_file_path(
    touched_file_paths: set[Path],
    session: Any,
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
) -> None:
    if tool_name not in FILE_SNAPSHOT_TOOL_NAMES:
        return
    candidate = None
    if isinstance(tool_result, dict):
        candidate = tool_result.get("path")
    if not candidate:
        candidate = tool_args.get("path")
    resolved = _resolve_workspace_path(session, str(candidate or ""))
    if resolved is not None:
        touched_file_paths.add(resolved)


def _track_used_file_if_already_mirrored(
    touched_file_paths: set[Path],
    session: Any,
    *,
    store: Optional[ChatArtifactStore],
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
) -> None:
    if tool_name not in TRACKED_FILE_REFRESH_TOOL_NAMES or not store:
        return
    if isinstance(tool_result, dict) and tool_result.get("error"):
        return
    candidate = tool_args.get("path")
    resolved = _resolve_workspace_path(session, str(candidate or ""))
    if resolved is None or not resolved.exists() or not resolved.is_file():
        return
    relative = _workspace_relative_text(session, resolved)
    absolute = str(resolved)
    for record in store.list_records(descending=True):
        if record.artifact_kind != "file_snapshot":
            continue
        if str(record.file_path or "") in {relative, absolute}:
            touched_file_paths.add(resolved)
            return


def _command_output_text(command: str, tool_result: Any, *, cwd: Optional[str] = None) -> str:
    command = redact_text(command)
    cwd = redact_text(cwd) if cwd else cwd
    tool_result = redact_json(tool_result)
    if isinstance(tool_result, dict):
        stdout = str(tool_result.get("stdout") or "")
        stderr = str(tool_result.get("stderr") or "")
        exit_code = tool_result.get("exit_code")
        error = str(tool_result.get("error") or "")
        lines = [f"$ {command or '[command omitted]'}"]
        if cwd:
            lines.append(f"[cwd] {cwd}")
        if exit_code is not None:
            lines.append(f"[exit_code] {exit_code}")
        if error:
            lines.append(f"[error]\n{error}")
        if stdout:
            lines.append(f"[stdout]\n{stdout}")
        if stderr:
            lines.append(f"[stderr]\n{stderr}")
        return "\n\n".join(lines)
    return f"$ {command or '[command omitted]'}\n\n{str(tool_result or '')}"


def _artifact_preview_for_command(command: str, tool_result: Any) -> str:
    command = redact_text(command)
    tool_result = redact_json(tool_result)
    if isinstance(tool_result, dict):
        stdout = str(tool_result.get("stdout") or "")
        stderr = str(tool_result.get("stderr") or "")
        tail = "\n".join(part for part in [stdout[-700:], stderr[-500:]] if part)
        return f"$ {command or '[command omitted]'}\n\n{tail}".strip()
    return f"$ {command or '[command omitted]'}\n\n{str(tool_result or '')}".strip()


def _safe_slug(value: str, *, fallback: str = "artifact") -> str:
    slug = _NON_FILENAME_RE.sub("-", str(value or "").strip()).strip("-.")
    return slug[:80] or fallback


def _preview_text(
    value: str,
    *,
    head_chars: int = TEXT_PREVIEW_HEAD_CHARS,
    tail_chars: int = TEXT_PREVIEW_TAIL_CHARS,
) -> str:
    text = redact_text(str(value or ""))
    if len(text) <= head_chars + tail_chars + 64:
        return text
    omitted = len(text) - head_chars - tail_chars
    return f"{text[:head_chars]}\n\n...[middle truncated: {omitted} chars]...\n\n{text[-tail_chars:]}"


def _serialize_search_text(*parts: Any) -> str:
    text_parts: List[str] = []
    for part in parts:
        if not part:
            continue
        part = redact_json(part)
        if isinstance(part, dict):
            text_parts.append(json.dumps(part, ensure_ascii=False, default=str))
        elif isinstance(part, (list, tuple)):
            text_parts.append(json.dumps(list(part), ensure_ascii=False, default=str))
        else:
            text_parts.append(str(part))
    return "\n".join(item for item in text_parts if item)


def _artifact_text_for_browser_observation(tool_name: str, tool_result: Any) -> str:
    tool_result = redact_json(tool_result)
    if isinstance(tool_result, dict):
        if tool_name == "browser_read_text":
            page_text = str(tool_result.get("text") or "").strip()
            title = str(tool_result.get("title") or "").strip()
            url = str(tool_result.get("url") or "").strip()
            selector = str(tool_result.get("selector") or "").strip()
            mode = str(tool_result.get("mode") or tool_result.get("backend") or "").strip()
            prefix_lines = [
                item
                for item in [
                    f"Title: {title}" if title else "",
                    f"URL: {url}" if url else "",
                    f"Selector: {selector or '<page body>'}",
                    f"Mode: {mode}" if mode else "",
                ]
                if item
            ]
            if page_text:
                prefix_lines.append("")
                prefix_lines.append(page_text)
                return "\n".join(prefix_lines).strip()
        formatted = str(tool_result.get("formatted") or "").strip()
        if formatted:
            return formatted
        return json.dumps(_sanitize_artifact_metadata(tool_result), ensure_ascii=False, indent=2, default=str)
    return str(tool_result or "")


def _artifact_text_for_ocr(tool_result: Any) -> str:
    tool_result = redact_json(tool_result)
    if isinstance(tool_result, dict):
        plain = str(tool_result.get("plain_text") or tool_result.get("unfiltered_text") or "").strip()
        if plain:
            return plain
        elements = list(tool_result.get("elements", []) or [])
        sample = []
        for item in elements[:120]:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    sample.append(text)
        return "\n".join(sample)
    return str(tool_result or "")


def _capture_tool_artifact_ids(
    session: Any,
    *,
    store: Optional[ChatArtifactStore],
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    task_id: Optional[int],
) -> List[str]:
    if not store:
        return []

    metadata = {
        "tool_args": _sanitize_artifact_metadata(tool_args),
        "tool_result": _sanitize_artifact_metadata(tool_result),
    }
    artifact_ids: List[str] = []
    workspace = str(getattr(session, "workspace", "") or "").strip() or None
    workspace_id = str(getattr(session, "workspace_id", "") or "").strip() or None
    task_id_text = str(task_id) if task_id is not None else None

    if tool_name in COMMAND_OUTPUT_TOOL_NAMES:
        command = str(tool_args.get("command") or tool_args.get("cmd") or "").strip()
        cwd = str(tool_args.get("cwd") or "").strip() or None
        text = _command_output_text(command, tool_result, cwd=cwd)
        created = store.create_text_artifact(
            artifact_kind="command_output",
            title=f"Command output: {command or tool_name}",
            text=text,
            source_kind="agent",
            payload_file_name=f"{tool_name}-{_safe_command_filename(command)}.txt",
            summary_text=text,
            preview_text=_artifact_preview_for_command(command, tool_result),
            search_text=json.dumps({"command": command, "cwd": cwd, "result": _sanitize_artifact_metadata(tool_result)}, ensure_ascii=False, default=str),
            source_tool=tool_name,
            source_command=command or None,
            workspace=workspace,
            task_id=task_id_text,
            metadata=metadata,
        )
        artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "describe_screen" and isinstance(tool_result, dict):
        description = str(tool_result.get("description") or "").strip()
        question = str(tool_result.get("vision_question") or tool_result.get("question") or tool_args.get("question") or "").strip()
        vision_summary = str(tool_result.get("vision_summary") or "").strip()
        summary_items = [
            f"Question: {question}" if question else "",
            f"Vision summary: {vision_summary}" if vision_summary else "",
        ]
        if description and description != vision_summary:
            summary_items.append(f"Tool description: {description}")
        summary_text = "\n".join(item for item in summary_items if item).strip()
        image_base64 = str(tool_result.get("image_base64") or "").strip()
        if image_base64:
            created = store.create_base64_image_artifact(
                artifact_kind="screenshot",
                title="Screen capture",
                image_base64=image_base64,
                source_kind="agent",
                payload_file_name="screen-capture.png",
                summary_text=summary_text or "Screen capture artifact",
                preview_text=summary_text or "Screen capture artifact",
                search_text=_serialize_search_text(summary_text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
        else:
            created = store.create_text_artifact(
                artifact_kind="screen_description",
                title="Screen description",
                text=summary_text or json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
        artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "ocr_screen":
        text = _artifact_text_for_ocr(tool_result)
        if text.strip():
            created = store.create_text_artifact(
                artifact_kind="ocr_text",
                title="OCR screen text",
                text=text,
                source_kind="agent",
                summary_text=text,
                preview_text=_preview_text(text, head_chars=700, tail_chars=450),
                search_text=_serialize_search_text(text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "observe_desktop":
        text = str(tool_result or "").strip()
        if text:
            created = store.create_text_artifact(
                artifact_kind="screen_description",
                title="Desktop observation",
                text=text,
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name in BROWSER_OBSERVATION_TOOL_NAMES:
        text = _artifact_text_for_browser_observation(tool_name, tool_result)
        if text.strip():
            title = "Browser observation"
            if isinstance(tool_result, dict):
                page_title = str(tool_result.get("title") or "").strip()
                if tool_name == "browser_read_text":
                    title = f"Browser text: {page_title}" if page_title else "Browser text extract"
                elif page_title:
                    title = f"Browser observation: {page_title}"
            created = store.create_text_artifact(
                artifact_kind="browser_observation",
                title=title,
                text=text,
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "browser_screenshot" and isinstance(tool_result, dict):
        image_base64 = str(tool_result.get("image_base64") or "").strip()
        title = str(tool_result.get("title") or "").strip() or "Browser screenshot"
        url = str(tool_result.get("url") or "").strip()
        question = str(tool_result.get("vision_question") or tool_result.get("question") or tool_args.get("question") or "").strip()
        vision_summary = str(tool_result.get("vision_summary") or "").strip()
        summary_text = "\n".join(
            item
            for item in [
                title,
                url,
                f"Question: {question}" if question else "",
                f"Vision summary: {vision_summary}" if vision_summary else "",
            ]
            if item
        ).strip() or "Browser screenshot"
        if image_base64:
            created = store.create_base64_image_artifact(
                artifact_kind="browser_screenshot",
                title=title if title.startswith("Browser") else f"Browser screenshot: {title}",
                image_base64=image_base64,
                source_kind="agent",
                payload_file_name="browser-screenshot.png",
                summary_text=summary_text,
                preview_text=summary_text,
                search_text=_serialize_search_text(summary_text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    return artifact_ids


def _safe_command_filename(command: str) -> str:
    return _safe_slug(command[:80] if command else "command-output", fallback="command-output")


def _snapshot_touched_file_artifact_ids(
    session: Any,
    *,
    store: Optional[ChatArtifactStore],
    touched_file_paths: set[Path],
    task_id: Optional[int],
) -> List[str]:
    if not store or not touched_file_paths:
        return []
    artifact_ids: List[str] = []
    workspace = str(getattr(session, "workspace", "") or "").strip() or None
    task_id_text = str(task_id) if task_id is not None else None
    for path in sorted(touched_file_paths, key=lambda item: str(item)):
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        file_path = _workspace_relative_text(session, resolved)
        mime_type, _ = mimetypes.guess_type(str(resolved))
        try:
            raw = resolved.read_bytes()
        except Exception:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            created = store.create_text_artifact(
                artifact_kind="file_snapshot",
                title=f"File snapshot: {file_path}",
                text=text,
                mime_type=(mime_type or "text/plain; charset=utf-8"),
                source_kind="agent",
                payload_file_name=resolved.name,
                summary_text=text,
                preview_text=_preview_text(text),
                search_text=text,
                file_path=file_path,
                workspace=workspace,
                task_id=task_id_text,
                metadata={
                    "final_per_turn": True,
                    "path": file_path,
                    "workspace_id": workspace_id,
                    "source_policy": "agent_tracked_file",
                },
            )
        else:
            created = store.create_bytes_artifact(
                artifact_kind="file_snapshot",
                title=f"File snapshot: {file_path}",
                data=raw,
                mime_type=(mime_type or "application/octet-stream"),
                source_kind="agent",
                payload_file_name=resolved.name,
                summary_text=file_path,
                preview_text=file_path,
                search_text=file_path,
                file_path=file_path,
                workspace=workspace,
                task_id=task_id_text,
                metadata={
                    "final_per_turn": True,
                    "path": file_path,
                    "workspace_id": workspace_id,
                    "source_policy": "agent_tracked_file",
                },
            )
        artifact_ids.append(created.artifact_id)
    return artifact_ids
