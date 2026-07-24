from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional


CATALOG_FILENAME = "agency_agents.catalog.json"


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "company_jobs" / CATALOG_FILENAME


class JobCatalog:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or _catalog_path())
        self._lock = threading.RLock()
        self._signature: Optional[tuple[int, int]] = None
        self._payload: Dict[str, Any] = {}

    def _load_locked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": 1,
                "source": {},
                "divisions": [],
                "templates": [],
            }
        state = self.path.stat()
        signature = (int(state.st_mtime_ns), int(state.st_size))
        if signature == self._signature:
            return self._payload
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("templates"), list):
            raise RuntimeError("The local company job catalog is invalid.")
        self._payload = payload
        self._signature = signature
        return payload

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            payload = self._load_locked()
            return {
                "schema_version": int(payload.get("schema_version") or 1),
                "source": dict(payload.get("source") or {}),
                "divisions": list(payload.get("divisions") or []),
                "template_count": len(payload.get("templates") or []),
            }

    def list_templates(
        self,
        *,
        query: Optional[str] = None,
        division: Optional[str] = None,
        review_status: Optional[str] = None,
        limit: int = 245,
    ) -> list[Dict[str, Any]]:
        clean_query = " ".join(str(query or "").casefold().split())
        clean_division = str(division or "").strip().casefold()
        clean_review = str(review_status or "").strip().casefold()
        with self._lock:
            templates = list(self._load_locked().get("templates") or [])
        items = []
        for template in templates:
            if clean_division and str(template.get("division") or "").casefold() != clean_division:
                continue
            if clean_review and str(template.get("review_status") or "").casefold() != clean_review:
                continue
            if clean_query and clean_query not in str(template.get("search_text") or ""):
                tokens = clean_query.split()
                search_text = str(template.get("search_text") or "")
                if not all(token in search_text for token in tokens):
                    continue
            items.append(dict(template))
        return items[: max(1, min(int(limit), 245))]

    def get_template(self, template_id: str) -> Dict[str, Any]:
        clean_id = str(template_id or "").strip()
        with self._lock:
            for template in list(self._load_locked().get("templates") or []):
                if str(template.get("template_id") or "") == clean_id:
                    return dict(template)
        raise KeyError("Unknown job template")


_CATALOG: Optional[JobCatalog] = None


def get_job_catalog() -> JobCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = JobCatalog()
    return _CATALOG

