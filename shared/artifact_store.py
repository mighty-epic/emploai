from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.runtime_paths import user_state_root


TEXT_PREVIEW_HEAD_CHARS = 900
TEXT_PREVIEW_TAIL_CHARS = 900
INDEX_SEGMENT_CHARS = 1800
MAX_INLINE_TEXT_CHARS = 120_000
MAX_INLINE_IMAGE_BYTES = 1_500_000
MAX_ARTIFACT_INDEX_ITEMS = 10
MAX_RETRIEVED_SEGMENTS = 4
_NON_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_slug(value: str, *, fallback: str = "artifact") -> str:
    slug = _NON_FILENAME_RE.sub("-", str(value or "").strip()).strip("-.")
    return slug[:80] or fallback


def _compact_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _preview_text(value: str, *, head_chars: int = TEXT_PREVIEW_HEAD_CHARS, tail_chars: int = TEXT_PREVIEW_TAIL_CHARS) -> str:
    text = str(value or "")
    if len(text) <= head_chars + tail_chars + 64:
        return text
    omitted = len(text) - head_chars - tail_chars
    return f"{text[:head_chars]}\n\n...[middle truncated: {omitted} chars]...\n\n{text[-tail_chars:]}"


def _chunk_text(value: str, *, chunk_chars: int = INDEX_SEGMENT_CHARS) -> List[str]:
    text = str(value or "")
    if not text:
        return []
    return [text[index:index + chunk_chars] for index in range(0, len(text), chunk_chars)]


def _build_segments(title: str, text: str) -> List[Dict[str, Any]]:
    preview = _preview_text(text)
    if len(text) <= INDEX_SEGMENT_CHARS:
        return [
            {
                "id": "seg-1",
                "title": title,
                "part": 1,
                "total_parts": 1,
                "text": preview,
            }
        ]

    chunks = _chunk_text(text)
    total = len(chunks)
    segments: List[Dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if index == 1 or index == total:
            segment_text = _preview_text(chunk, head_chars=700, tail_chars=500)
        else:
            segment_text = chunk[:1000]
        segments.append(
            {
                "id": f"seg-{index}",
                "title": f"{title} (part {index}/{total})",
                "part": index,
                "total_parts": total,
                "text": segment_text,
            }
        )
    return segments


def _serialize_search_text(*parts: Any) -> str:
    text_parts: List[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, dict):
            text_parts.append(json.dumps(part, ensure_ascii=False, default=str))
        elif isinstance(part, (list, tuple)):
            text_parts.append(json.dumps(list(part), ensure_ascii=False, default=str))
        else:
            text_parts.append(str(part))
    return "\n".join(item for item in text_parts if item)


def _score_match(query: str, haystacks: List[str]) -> float:
    normalized_query = _compact_whitespace(query).lower()
    if not normalized_query:
        return 0.0
    tokens = [token for token in re.split(r"\W+", normalized_query) if token]
    if not tokens:
        return 0.0

    score = 0.0
    for haystack in haystacks:
        text = _compact_whitespace(haystack).lower()
        if not text:
            continue
        if normalized_query in text:
            score += 8.0
        for token in tokens:
            if token in text:
                score += 1.0
    return score


@dataclass
class ArtifactRecord:
    artifact_id: str
    session_id: str
    source_kind: str
    artifact_kind: str
    title: str
    created_at: str
    mime_type: str
    size_bytes: int
    payload_path: str
    payload_encoding: str = "binary"
    payload_file_name: Optional[str] = None
    payload_ext: Optional[str] = None
    preview_text: str = ""
    summary_text: str = ""
    search_text: str = ""
    index_segments: List[Dict[str, Any]] = field(default_factory=list)
    source_tool: Optional[str] = None
    source_command: Optional[str] = None
    file_path: Optional[str] = None
    workspace: Optional[str] = None
    task_id: Optional[str] = None
    sub_goal_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "source_kind": self.source_kind,
            "artifact_kind": self.artifact_kind,
            "title": self.title,
            "created_at": self.created_at,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "payload_path": self.payload_path,
            "payload_encoding": self.payload_encoding,
            "payload_file_name": self.payload_file_name,
            "payload_ext": self.payload_ext,
            "preview_text": self.preview_text,
            "summary_text": self.summary_text,
            "search_text": self.search_text,
            "index_segments": list(self.index_segments),
            "source_tool": self.source_tool,
            "source_command": self.source_command,
            "file_path": self.file_path,
            "workspace": self.workspace,
            "task_id": self.task_id,
            "sub_goal_id": self.sub_goal_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRecord":
        return cls(
            artifact_id=str(data.get("artifact_id") or ""),
            session_id=str(data.get("session_id") or ""),
            source_kind=str(data.get("source_kind") or "agent"),
            artifact_kind=str(data.get("artifact_kind") or "text"),
            title=str(data.get("title") or "Artifact"),
            created_at=str(data.get("created_at") or _now_iso()),
            mime_type=str(data.get("mime_type") or "application/octet-stream"),
            size_bytes=int(data.get("size_bytes") or 0),
            payload_path=str(data.get("payload_path") or ""),
            payload_encoding=str(data.get("payload_encoding") or "binary"),
            payload_file_name=data.get("payload_file_name"),
            payload_ext=data.get("payload_ext"),
            preview_text=str(data.get("preview_text") or ""),
            summary_text=str(data.get("summary_text") or ""),
            search_text=str(data.get("search_text") or ""),
            index_segments=list(data.get("index_segments", []) or []),
            source_tool=data.get("source_tool"),
            source_command=data.get("source_command"),
            file_path=data.get("file_path"),
            workspace=data.get("workspace"),
            task_id=data.get("task_id"),
            sub_goal_id=data.get("sub_goal_id"),
            metadata=dict(data.get("metadata", {}) or {}),
        )


class ChatArtifactStore:
    def __init__(self, *, user_id: int, session_id: str) -> None:
        self.user_id = int(user_id)
        self.session_id = str(session_id or "").strip()
        self.base_path = (user_state_root(self.user_id) / "artifacts" / "chats" / self.session_id).resolve()
        self.payloads_dir = self.base_path / "payloads"
        self.index_path = self.base_path / "index.json"
        self.payloads_dir.mkdir(parents=True, exist_ok=True)

    def _read(self) -> Dict[str, Any]:
        if not self.index_path.exists():
            return {"items": []}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}
        if not isinstance(payload, dict):
            return {"items": []}
        payload.setdefault("items", [])
        return payload

    def _write(self, payload: Dict[str, Any]) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.payloads_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_records(self, *, descending: bool = True) -> List[ArtifactRecord]:
        items = [ArtifactRecord.from_dict(item) for item in list(self._read().get("items", []))]
        items.sort(key=lambda item: item.created_at, reverse=descending)
        return items

    def get_record(self, artifact_id: str) -> Optional[ArtifactRecord]:
        normalized = str(artifact_id or "").strip()
        if not normalized:
            return None
        for record in self.list_records(descending=False):
            if record.artifact_id == normalized:
                return record
        return None

    def payload_absolute_path(self, artifact_id: str) -> Optional[Path]:
        record = self.get_record(artifact_id)
        if not record:
            return None
        return (self.base_path / record.payload_path).resolve()

    def meta(self) -> Dict[str, Any]:
        items = self.list_records(descending=True)
        return {
            "artifact_count": len(items),
            "latest_artifact_at": items[0].created_at if items else None,
        }

    def _persist_record(self, record: ArtifactRecord) -> ArtifactRecord:
        payload = self._read()
        items = [item for item in list(payload.get("items", [])) if str(item.get("artifact_id") or "") != record.artifact_id]
        items.append(record.to_dict())
        items.sort(key=lambda item: str(item.get("created_at") or ""))
        payload["items"] = items[-2000:]
        self._write(payload)
        return record

    def create_bytes_artifact(
        self,
        *,
        artifact_kind: str,
        title: str,
        data: bytes,
        mime_type: str,
        source_kind: str = "agent",
        payload_file_name: Optional[str] = None,
        summary_text: str = "",
        preview_text: str = "",
        search_text: str = "",
        source_tool: Optional[str] = None,
        source_command: Optional[str] = None,
        file_path: Optional[str] = None,
        workspace: Optional[str] = None,
        task_id: Optional[str] = None,
        sub_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        artifact_id = uuid.uuid4().hex
        guessed_ext = mimetypes.guess_extension(mime_type or "") or ""
        payload_name = payload_file_name or f"{_safe_slug(title)}{guessed_ext or '.bin'}"
        relative_payload = Path("payloads") / f"{artifact_id}-{_safe_slug(payload_name, fallback='payload')}"
        absolute_payload = self.base_path / relative_payload
        absolute_payload.parent.mkdir(parents=True, exist_ok=True)
        absolute_payload.write_bytes(data)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            session_id=self.session_id,
            source_kind=source_kind,
            artifact_kind=artifact_kind,
            title=title,
            created_at=_now_iso(),
            mime_type=mime_type or "application/octet-stream",
            size_bytes=len(data),
            payload_path=str(relative_payload).replace("\\", "/"),
            payload_encoding="binary",
            payload_file_name=payload_name,
            payload_ext=Path(payload_name).suffix or guessed_ext or None,
            preview_text=preview_text,
            summary_text=summary_text,
            search_text=search_text,
            index_segments=_build_segments(title, summary_text or preview_text or search_text or title),
            source_tool=source_tool,
            source_command=source_command,
            file_path=file_path,
            workspace=workspace,
            task_id=task_id,
            sub_goal_id=sub_goal_id,
            metadata=dict(metadata or {}),
        )
        return self._persist_record(record)

    def create_text_artifact(
        self,
        *,
        artifact_kind: str,
        title: str,
        text: str,
        mime_type: str = "text/plain; charset=utf-8",
        source_kind: str = "agent",
        payload_file_name: Optional[str] = None,
        summary_text: Optional[str] = None,
        preview_text: Optional[str] = None,
        search_text: Optional[str] = None,
        source_tool: Optional[str] = None,
        source_command: Optional[str] = None,
        file_path: Optional[str] = None,
        workspace: Optional[str] = None,
        task_id: Optional[str] = None,
        sub_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        normalized_text = str(text or "")
        payload_name = payload_file_name or f"{_safe_slug(title)}.txt"
        return self.create_bytes_artifact(
            artifact_kind=artifact_kind,
            title=title,
            data=normalized_text.encode("utf-8"),
            mime_type=mime_type,
            source_kind=source_kind,
            payload_file_name=payload_name,
            summary_text=summary_text or normalized_text,
            preview_text=preview_text or _preview_text(normalized_text),
            search_text=search_text or normalized_text,
            source_tool=source_tool,
            source_command=source_command,
            file_path=file_path,
            workspace=workspace,
            task_id=task_id,
            sub_goal_id=sub_goal_id,
            metadata=metadata,
        )

    def create_json_artifact(
        self,
        *,
        artifact_kind: str,
        title: str,
        payload: Dict[str, Any],
        source_kind: str = "agent",
        payload_file_name: Optional[str] = None,
        summary_text: str = "",
        preview_text: str = "",
        search_text: str = "",
        source_tool: Optional[str] = None,
        source_command: Optional[str] = None,
        file_path: Optional[str] = None,
        workspace: Optional[str] = None,
        task_id: Optional[str] = None,
        sub_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return self.create_text_artifact(
            artifact_kind=artifact_kind,
            title=title,
            text=text,
            mime_type="application/json",
            source_kind=source_kind,
            payload_file_name=payload_file_name or f"{_safe_slug(title)}.json",
            summary_text=summary_text or text,
            preview_text=preview_text or _preview_text(text),
            search_text=search_text or text,
            source_tool=source_tool,
            source_command=source_command,
            file_path=file_path,
            workspace=workspace,
            task_id=task_id,
            sub_goal_id=sub_goal_id,
            metadata=metadata,
        )

    def create_base64_image_artifact(
        self,
        *,
        artifact_kind: str,
        title: str,
        image_base64: str,
        mime_type: str = "image/png",
        source_kind: str = "agent",
        payload_file_name: Optional[str] = None,
        summary_text: str = "",
        preview_text: str = "",
        search_text: str = "",
        source_tool: Optional[str] = None,
        source_command: Optional[str] = None,
        file_path: Optional[str] = None,
        workspace: Optional[str] = None,
        task_id: Optional[str] = None,
        sub_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        data = base64.b64decode(str(image_base64 or "").encode("utf-8"))
        return self.create_bytes_artifact(
            artifact_kind=artifact_kind,
            title=title,
            data=data,
            mime_type=mime_type,
            source_kind=source_kind,
            payload_file_name=payload_file_name or f"{_safe_slug(title)}.png",
            summary_text=summary_text,
            preview_text=preview_text,
            search_text=search_text,
            source_tool=source_tool,
            source_command=source_command,
            file_path=file_path,
            workspace=workspace,
            task_id=task_id,
            sub_goal_id=sub_goal_id,
            metadata=metadata,
        )

    def build_prompt_messages(
        self,
        *,
        user_message: str,
        task_focus: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        items = self.list_records(descending=True)
        if not items:
            return []

        index_lines = [
            "CHAT ARTIFACT INDEX (current chat only):",
            "- These artifacts are already available from this chat's runtime-owned artifact store.",
            "- Use the titles, previews, and retrieved excerpts below instead of recreating or re-reading equivalent evidence when it already exists.",
        ]
        for record in items[:MAX_ARTIFACT_INDEX_ITEMS]:
            preview = _compact_whitespace(record.preview_text or record.summary_text or "")
            if len(preview) > 180:
                preview = preview[:177] + "..."
            index_lines.append(
                f"- [{record.artifact_id}] {record.created_at} | {record.artifact_kind} | {record.title}"
                + (f" | {preview}" if preview else "")
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": "\n".join(index_lines)}]
        query = _serialize_search_text(user_message, task_focus)
        if not _compact_whitespace(query):
            return messages

        matches: List[tuple[float, ArtifactRecord, Dict[str, Any]]] = []
        for record in items:
            base_score = _score_match(query, [record.title, record.preview_text, record.summary_text, record.search_text])
            if base_score <= 0.0:
                continue
            best_segment = None
            best_segment_score = 0.0
            for segment in record.index_segments:
                score = _score_match(query, [segment.get("title", ""), segment.get("text", "")])
                if score > best_segment_score:
                    best_segment = segment
                    best_segment_score = score
            matches.append((base_score + best_segment_score, record, best_segment or {"title": record.title, "text": record.preview_text or record.summary_text}))

        matches.sort(key=lambda item: item[0], reverse=True)
        if not matches:
            return messages

        excerpt_lines = [
            "RELEVANT CHAT ARTIFACT EXCERPTS:",
            "- These excerpts come only from artifacts already saved in this chat.",
        ]
        for _, record, segment in matches[:MAX_RETRIEVED_SEGMENTS]:
            excerpt_lines.append(f"## [{record.artifact_id}] {segment.get('title') or record.title}")
            excerpt_lines.append(str(segment.get("text") or record.preview_text or record.summary_text or "").strip())

        messages.append({"role": "system", "content": "\n\n".join(excerpt_lines)})
        return messages

    def build_summary_view(self, record: ArtifactRecord) -> Dict[str, Any]:
        return {
            "artifact_id": record.artifact_id,
            "title": record.title,
            "artifact_kind": record.artifact_kind,
            "source_kind": record.source_kind,
            "created_at": record.created_at,
            "mime_type": record.mime_type,
            "size_bytes": record.size_bytes,
            "preview_text": record.preview_text,
            "summary_text": record.summary_text[:3000] if record.summary_text else "",
            "source_tool": record.source_tool,
            "source_command": record.source_command,
            "file_path": record.file_path,
            "workspace": record.workspace,
            "metadata": dict(record.metadata),
        }

    def build_detail_view(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        record = self.get_record(artifact_id)
        if not record:
            return None
        payload_path = self.payload_absolute_path(artifact_id)
        inline_text: Optional[str] = None
        image_base64: Optional[str] = None
        if payload_path and payload_path.exists():
            if record.mime_type.startswith("text/") or record.mime_type == "application/json":
                try:
                    inline_text = payload_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    inline_text = None
                if inline_text and len(inline_text) > MAX_INLINE_TEXT_CHARS:
                    inline_text = inline_text[:MAX_INLINE_TEXT_CHARS] + "\n...[truncated]"
            elif record.mime_type.startswith("image/"):
                try:
                    raw = payload_path.read_bytes()
                except Exception:
                    raw = b""
                if raw and len(raw) <= MAX_INLINE_IMAGE_BYTES:
                    image_base64 = base64.b64encode(raw).decode("utf-8")

        detail = self.build_summary_view(record)
        detail.update(
            {
                "payload_file_name": record.payload_file_name,
                "inline_text": inline_text,
                "image_base64": image_base64,
                "index_segments": list(record.index_segments),
            }
        )
        return detail
