from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from app_backend.company_store import CompanySelectionError, CompanyStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _text(value: Any, field: str, limit: int) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized[:limit]


class CompanyIntelligenceService:
    """Explicitly published Company knowledge, metrics, and financial facts."""

    def __init__(self, *, store: CompanyStore):
        self.store = store

    @staticmethod
    def _root_membership(
        company: Mapping[str, Any],
        computer_id: str,
    ) -> Mapping[str, Any]:
        membership = next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "")
                == str(computer_id or "")
                and str(item.get("status") or "active") == "active"
            ),
            None,
        )
        if not membership:
            raise CompanySelectionError(
                "This computer is not a member of that company."
            )
        if str(membership.get("membership_role") or "") != "root_controller":
            raise CompanySelectionError(
                "Company intelligence must be published on the root computer."
            )
        return membership

    @staticmethod
    def _audit(
        company: Dict[str, Any],
        *,
        event_type: str,
        target_kind: str,
        target_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        company.setdefault("company_audit_events", []).append(
            {
                "event_id": _record_id("caud"),
                "event_type": event_type,
                "target_kind": target_kind,
                "target_id": target_id,
                "metadata": dict(metadata or {}),
                "created_at": _utc_now(),
            }
        )

    def publish_knowledge(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        content: str,
        provenance: Mapping[str, Any],
        sensitivity: str,
        review_due_at: Optional[str],
    ) -> Dict[str, Any]:
        source = str(
            provenance.get("source")
            or provenance.get("source_ref")
            or ""
        ).strip()
        if not source:
            raise ValueError(
                "Knowledge provenance must identify its source."
            )
        knowledge_id = _record_id("know")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            item = {
                "knowledge_id": knowledge_id,
                "title": _text(title, "knowledge title", 240),
                "content": _text(content, "knowledge content", 40000),
                "provenance": dict(provenance),
                "sensitivity": str(
                    sensitivity or "company"
                ).strip()[:80],
                "review_due_at": (
                    str(review_due_at or "").strip() or None
                ),
                "published_by_identity_id": str(
                    membership.get("manager_identity_id") or ""
                )
                or None,
                "status": "active",
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("knowledge", []).append(item)
            self._audit(
                company,
                event_type="knowledge_published",
                target_kind="knowledge",
                target_id=knowledge_id,
                metadata={"source": source},
            )
            return item

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def review_knowledge(
        self,
        *,
        company_id: str,
        computer_id: str,
        knowledge_id: str,
        next_review_due_at: Optional[str],
        review_note: str,
    ) -> Dict[str, Any]:
        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            item = next(
                (
                    knowledge
                    for knowledge in list(company.get("knowledge") or [])
                    if str(knowledge.get("knowledge_id") or "")
                    == str(knowledge_id or "")
                ),
                None,
            )
            if not item:
                raise KeyError("Unknown knowledge item")
            now = _utc_now()
            item["review_due_at"] = (
                str(next_review_due_at or "").strip() or None
            )
            item["last_review_note"] = _text(
                review_note,
                "knowledge review note",
                4000,
            )
            item["last_reviewed_at"] = now
            item["last_reviewed_by_identity_id"] = str(
                membership.get("manager_identity_id") or ""
            ) or None
            item["updated_at"] = now
            self._audit(
                company,
                event_type="knowledge_reviewed",
                target_kind="knowledge",
                target_id=str(knowledge_id),
            )
            return dict(item)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_metric(
        self,
        *,
        company_id: str,
        computer_id: str,
        name: str,
        definition: str,
        formula: str,
        unit: str,
        source: str,
        cadence: str,
        owner_identity_id: Optional[str],
        guardrails: list[str],
    ) -> Dict[str, Any]:
        metric_id = _record_id("met")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            owner_id = str(
                owner_identity_id
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            if owner_id and not any(
                str(item.get("identity_id") or "") == owner_id
                for item in list(company.get("employees") or [])
            ):
                raise ValueError(
                    "The metric owner does not belong to this company."
                )
            metric = {
                "metric_id": metric_id,
                "name": _text(name, "metric name", 240),
                "definition": _text(
                    definition,
                    "metric definition",
                    4000,
                ),
                "formula": _text(formula, "metric formula", 2000),
                "unit": _text(unit, "metric unit", 80),
                "source": _text(source, "metric source", 2000),
                "cadence": str(cadence or "monthly").strip()[:120],
                "owner_identity_id": owner_id or None,
                "guardrails": [
                    str(item).strip()[:1000]
                    for item in guardrails
                    if str(item).strip()
                ],
                "observations": [],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("metrics", []).append(metric)
            self._audit(
                company,
                event_type="metric_defined",
                target_kind="metric",
                target_id=metric_id,
            )
            return metric

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def record_metric_observation(
        self,
        *,
        company_id: str,
        computer_id: str,
        metric_id: str,
        value: Any,
        period_start: Optional[str],
        period_end: Optional[str],
        confidence: str,
        evidence: list[Mapping[str, Any]],
        note: Optional[str],
    ) -> Dict[str, Any]:
        observation_id = _record_id("obs")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            metric = next(
                (
                    item
                    for item in list(company.get("metrics") or [])
                    if str(item.get("metric_id") or "")
                    == str(metric_id or "")
                ),
                None,
            )
            if not metric:
                raise KeyError("Unknown metric")
            observation = {
                "observation_id": observation_id,
                "value": value,
                "period_start": str(period_start or "").strip() or None,
                "period_end": str(period_end or "").strip() or None,
                "confidence": str(
                    confidence or "unknown"
                ).strip()[:80],
                "evidence": [dict(item) for item in evidence],
                "note": str(note or "").strip() or None,
                "recorded_at": now,
            }
            metric.setdefault("observations", []).append(observation)
            metric["updated_at"] = now
            self._audit(
                company,
                event_type="metric_observation_recorded",
                target_kind="metric",
                target_id=str(metric_id),
                metadata={"observation_id": observation_id},
            )
            return observation

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def record_financial_entry(
        self,
        *,
        company_id: str,
        computer_id: str,
        entry_type: str,
        amount: float,
        currency: str,
        description: str,
        recognized_at: str,
        source: str,
        evidence: list[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        clean_type = str(entry_type or "").strip().lower()
        if clean_type not in {"revenue", "cost"}:
            raise ValueError("Financial entry type must be revenue or cost.")
        if float(amount) < 0:
            raise ValueError("Financial amount cannot be negative.")
        entry_id = _record_id("fin")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            entry = {
                "financial_entry_id": entry_id,
                "entry_type": clean_type,
                "amount": float(amount),
                "currency": _text(
                    currency,
                    "financial currency",
                    12,
                ).upper(),
                "description": _text(
                    description,
                    "financial description",
                    2000,
                ),
                "recognized_at": _text(
                    recognized_at,
                    "recognition date",
                    80,
                ),
                "source": _text(
                    source,
                    "financial source",
                    2000,
                ),
                "evidence": [dict(item) for item in evidence],
                "status": "recorded",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("financial_entries", []).append(entry)
            self._audit(
                company,
                event_type="financial_entry_recorded",
                target_kind="financial_entry",
                target_id=entry_id,
                metadata={
                    "entry_type": clean_type,
                    "currency": entry["currency"],
                },
            )
            return entry

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result
