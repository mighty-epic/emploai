from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from shared.atomic_io import atomic_write_json
from shared.private_paths import harden_private_path
from shared.runtime_paths import auth_store_root
from shared.secure_store import protect_json_payload, unprotect_json_payload


COMPANY_REGISTRY_SCHEMA_VERSION = 1
COMPANY_PARTITION_SCHEMA_VERSION = 1
COMPANY_REGISTRY_FILENAME = "registry.json"
COMPANY_KEY_FILENAME = "company.key.json"
COMPANY_DATA_FILENAME = "company.data.json"
COMPANY_AAD_PREFIX = "emploai-company-partition"


class CompanyStoreError(RuntimeError):
    pass


class CompanyNotFoundError(CompanyStoreError):
    pass


class CompanySelectionError(CompanyStoreError):
    pass


class CompanyRootExistsError(CompanyStoreError):
    pass


class CompanyPartitionError(CompanyStoreError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_label(value: Any, fallback: str = "My Company", limit: int = 120) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    return (cleaned or fallback)[:limit]


def _stable_membership_id(company_id: str, computer_id: str) -> str:
    digest = hashlib.sha256(f"{company_id}\n{computer_id}".encode("utf-8")).hexdigest()
    return f"mbr_{digest[:24]}"


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class CompanyStore:
    """Encrypted, accountless company registry and partition store.

    The registry contains only device-level discovery metadata. Every company's
    operating record is encrypted with a distinct random key. The key is kept in
    the operating-system credential protection mechanism via ``secure_store``.
    """

    def __init__(
        self,
        root_path: Optional[Path] = None,
        *,
        protect_payload: Callable[..., Dict[str, Any]] = protect_json_payload,
        unprotect_payload: Callable[..., Dict[str, Any]] = unprotect_json_payload,
    ):
        self.root_path = Path(root_path or auth_store_root()) / "companies"
        self.registry_path = self.root_path / COMPANY_REGISTRY_FILENAME
        self._protect_payload = protect_payload
        self._unprotect_payload = unprotect_payload
        self._lock = threading.RLock()
        self.root_path.mkdir(parents=True, exist_ok=True)
        harden_private_path(self.root_path, 0o700, is_directory=True)

    def _default_registry(self) -> Dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": COMPANY_REGISTRY_SCHEMA_VERSION,
            "companies": {},
            "selected_by_computer": {},
            "created_at": now,
            "updated_at": now,
        }

    def _load_registry_locked(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return self._default_registry()
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CompanyPartitionError("The local company registry is unreadable.") from exc
        if not isinstance(payload, dict):
            raise CompanyPartitionError("The local company registry is invalid.")
        payload.setdefault("schema_version", COMPANY_REGISTRY_SCHEMA_VERSION)
        payload.setdefault("companies", {})
        payload.setdefault("selected_by_computer", {})
        payload.setdefault("created_at", _utc_now())
        payload.setdefault("updated_at", payload["created_at"])
        return payload

    def _save_registry_locked(self, registry: Mapping[str, Any]) -> None:
        payload = dict(registry)
        payload["schema_version"] = COMPANY_REGISTRY_SCHEMA_VERSION
        payload["updated_at"] = _utc_now()
        atomic_write_json(self.registry_path, payload, sort_keys=True, private=True)

    def _partition_dir(self, company_id: str) -> Path:
        return self.root_path / str(company_id)

    def _key_path(self, company_id: str) -> Path:
        return self._partition_dir(company_id) / COMPANY_KEY_FILENAME

    def _data_path(self, company_id: str) -> Path:
        return self._partition_dir(company_id) / COMPANY_DATA_FILENAME

    def _key_purpose(self, company_id: str) -> str:
        return f"EmploAI company partition key: {company_id}"

    def _aad(self, company_id: str) -> bytes:
        return f"{COMPANY_AAD_PREFIX}:{company_id}:v{COMPANY_PARTITION_SCHEMA_VERSION}".encode("utf-8")

    def _create_partition_key_locked(self, company_id: str) -> bytes:
        partition_dir = self._partition_dir(company_id)
        partition_dir.mkdir(parents=True, exist_ok=True)
        harden_private_path(partition_dir, 0o700, is_directory=True)
        key = AESGCM.generate_key(bit_length=256)
        envelope = self._protect_payload(
            {"key": base64.b64encode(key).decode("ascii")},
            purpose=self._key_purpose(company_id),
        )
        atomic_write_json(self._key_path(company_id), envelope, sort_keys=True, private=True)
        return key

    def _partition_key_locked(self, company_id: str, *, create: bool = False) -> bytes:
        key_path = self._key_path(company_id)
        if not key_path.exists():
            if create:
                return self._create_partition_key_locked(company_id)
            raise CompanyPartitionError("The operating-system protected company key is missing.")
        try:
            envelope = json.loads(key_path.read_text(encoding="utf-8"))
            payload = self._unprotect_payload(envelope, purpose=self._key_purpose(company_id))
            key = base64.b64decode(str(payload.get("key") or ""), validate=True)
        except Exception as exc:
            raise CompanyPartitionError("The operating system could not unlock this company.") from exc
        if len(key) != 32:
            raise CompanyPartitionError("The company encryption key is invalid.")
        return key

    def _write_company_locked(self, company_id: str, company: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(company)
        payload["company_id"] = company_id
        payload["schema_version"] = COMPANY_PARTITION_SCHEMA_VERSION
        payload["updated_at"] = _utc_now()
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        key = self._partition_key_locked(company_id, create=True)
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, serialized, self._aad(company_id))
        envelope = {
            "schema_version": COMPANY_PARTITION_SCHEMA_VERSION,
            "algorithm": "AES-256-GCM",
            "company_id": company_id,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        atomic_write_json(self._data_path(company_id), envelope, sort_keys=True, private=True)
        return payload

    def _read_company_locked(self, company_id: str) -> Dict[str, Any]:
        data_path = self._data_path(company_id)
        if not data_path.exists():
            raise CompanyNotFoundError("The company partition is unavailable on this computer.")
        try:
            envelope = json.loads(data_path.read_text(encoding="utf-8"))
            nonce = base64.b64decode(str(envelope.get("nonce") or ""), validate=True)
            ciphertext = base64.b64decode(str(envelope.get("ciphertext") or ""), validate=True)
            key = self._partition_key_locked(company_id)
            serialized = AESGCM(key).decrypt(nonce, ciphertext, self._aad(company_id))
            payload = json.loads(serialized.decode("utf-8"))
        except CompanyStoreError:
            raise
        except Exception as exc:
            raise CompanyPartitionError("The encrypted company partition failed integrity verification.") from exc
        if not isinstance(payload, dict) or str(payload.get("company_id") or "") != company_id:
            raise CompanyPartitionError("The encrypted company partition does not match its registry entry.")
        return payload

    def _company_summary_from_record(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "company_id": str(record.get("company_id") or ""),
            "display_name": _clean_label(record.get("display_name")),
            "ownership": str(record.get("ownership") or "member"),
            "membership_role": str(record.get("membership_role") or "worker_node"),
            "local_computer_id": str(record.get("local_computer_id") or ""),
            "status": str(record.get("status") or "active"),
            "onboarding_status": str(record.get("onboarding_status") or "not_started"),
            "created_at": str(record.get("created_at") or _utc_now()),
            "updated_at": str(record.get("updated_at") or record.get("created_at") or _utc_now()),
        }

    def _new_company_payload(
        self,
        *,
        company_id: str,
        display_name: str,
        computer_id: str,
        computer_name: str,
        ownership: str,
        membership_role: str,
    ) -> Dict[str, Any]:
        now = _utc_now()
        membership_id = _stable_membership_id(company_id, computer_id)
        return {
            "company_id": company_id,
            "schema_version": COMPANY_PARTITION_SCHEMA_VERSION,
            "revision": 1,
            "manifest": {
                "display_name": display_name,
                "status": "active",
                "purpose": "",
                "offer": "",
                "customers": "",
                "business_model": "",
                "principles": [],
                "hard_constraints": [],
                "reserved_decisions": [],
                "external_action_default": "draft_only",
                "external_action_policies": {
                    "customer_communication": "draft_only",
                    "publishing": "draft_only",
                    "spending": "draft_only",
                    "deploying": "draft_only",
                    "external_account_changes": "draft_only",
                },
                "notification_policy": {
                    "approvals": True,
                    "risks": True,
                    "incidents": True,
                    "deadlines": True,
                    "blockers": True,
                    "quiet_hours": None,
                },
                "operating_currency": None,
                "time_zone": None,
                "jurisdiction_notes": None,
                "onboarding_status": "not_started",
                "root_computer_id": computer_id if ownership == "root" else None,
                "root_fixed": ownership == "root",
            },
            "memberships": [
                {
                    "membership_id": membership_id,
                    "company_id": company_id,
                    "computer_id": computer_id,
                    "computer_name": computer_name,
                    "membership_role": membership_role,
                    "manager_identity_id": None,
                    "default_worker_identity_id": None,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            "employees": [],
            "departments": [],
            "positions": [],
            "job_contracts": [],
            "objectives": [],
            "initiatives": [],
            "runbooks": [],
            "recurring_operations": [],
            "assignments": [],
            "handoffs": [],
            "approvals": [],
            "reports": [],
            "policies": [],
            "decisions": [],
            "knowledge": [],
            "metrics": [],
            "financial_entries": [],
            "migration": {
                "state": "legacy_compatibility",
                "source": "existing_installation",
                "verified": False,
                "warnings": [],
            },
            "created_at": now,
            "updated_at": now,
        }

    def create_root_company(
        self,
        *,
        computer_id: str,
        computer_name: str,
        display_name: str = "My Company",
    ) -> Dict[str, Any]:
        clean_computer_id = str(computer_id or "").strip()
        if not clean_computer_id:
            raise CompanyStoreError("A local computer identity is required.")
        with self._lock:
            registry = self._load_registry_locked()
            for item in dict(registry.get("companies") or {}).values():
                if (
                    str(item.get("local_computer_id") or "") == clean_computer_id
                    and str(item.get("ownership") or "") == "root"
                    and str(item.get("status") or "active") not in {"revoked", "deleting"}
                ):
                    raise CompanyRootExistsError("This computer already owns its version-one company.")
            company_id = f"cmp_{secrets.token_hex(16)}"
            now = _utc_now()
            clean_name = _clean_label(display_name)
            record = {
                "company_id": company_id,
                "display_name": clean_name,
                "ownership": "root",
                "membership_role": "root_controller",
                "local_computer_id": clean_computer_id,
                "status": "active",
                "onboarding_status": "not_started",
                "created_at": now,
                "updated_at": now,
            }
            company = self._new_company_payload(
                company_id=company_id,
                display_name=clean_name,
                computer_id=clean_computer_id,
                computer_name=_clean_label(computer_name, "This computer"),
                ownership="root",
                membership_role="root_controller",
            )
            self._write_company_locked(company_id, company)
            registry.setdefault("companies", {})[company_id] = record
            registry.setdefault("selected_by_computer", {})[clean_computer_id] = company_id
            self._save_registry_locked(registry)
            return self._read_company_locked(company_id)

    def ensure_default_company(
        self,
        *,
        computer_id: str,
        computer_name: str,
        manager_identity: Optional[Mapping[str, Any]] = None,
        default_worker_identity: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_computer_id = str(computer_id or "").strip()
        if not clean_computer_id:
            raise CompanyStoreError("A local computer identity is required.")
        with self._lock:
            registry = self._load_registry_locked()
            root_record = next(
                (
                    item
                    for item in dict(registry.get("companies") or {}).values()
                    if str(item.get("local_computer_id") or "") == clean_computer_id
                    and str(item.get("ownership") or "") == "root"
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if root_record is None:
                company = self.create_root_company(
                    computer_id=clean_computer_id,
                    computer_name=computer_name,
                    display_name="My Company",
                )
                company_id = str(company["company_id"])
                registry = self._load_registry_locked()
            else:
                company_id = str(root_record["company_id"])
                company = self._read_company_locked(company_id)
            company = self._reconcile_protected_identities_locked(
                company,
                computer_id=clean_computer_id,
                manager_identity=manager_identity,
                default_worker_identity=default_worker_identity,
            )
            selected = str(registry.get("selected_by_computer", {}).get(clean_computer_id) or "").strip()
            if not selected or selected not in dict(registry.get("companies") or {}):
                registry.setdefault("selected_by_computer", {})[clean_computer_id] = company_id
                self._save_registry_locked(registry)
            return company

    def _reconcile_protected_identities_locked(
        self,
        company: Mapping[str, Any],
        *,
        computer_id: str,
        manager_identity: Optional[Mapping[str, Any]],
        default_worker_identity: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        payload = dict(company)
        company_id = str(payload.get("company_id") or "")
        memberships = [dict(item) for item in list(payload.get("memberships") or [])]
        membership = next(
            (item for item in memberships if str(item.get("computer_id") or "") == computer_id),
            None,
        )
        if membership is None:
            now = _utc_now()
            membership = {
                "membership_id": _stable_membership_id(company_id, computer_id),
                "company_id": company_id,
                "computer_id": computer_id,
                "membership_role": "root_controller",
                "manager_identity_id": None,
                "default_worker_identity_id": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            memberships.append(membership)
        employees_by_identity = {
            str(item.get("identity_id") or ""): dict(item)
            for item in list(payload.get("employees") or [])
            if str(item.get("identity_id") or "").strip()
        }
        changed = False

        def upsert(identity: Optional[Mapping[str, Any]], *, system_role: str, company_role: str) -> None:
            nonlocal changed
            if not identity:
                return
            identity_id = str(identity.get("identity_id") or identity.get("instance_id") or "").strip()
            if not identity_id:
                return
            metadata = dict(identity.get("metadata") or {})
            current = employees_by_identity.get(identity_id, {})
            employee = {
                **current,
                "employee_id": str(current.get("employee_id") or f"emp_{secrets.token_hex(12)}"),
                "identity_id": identity_id,
                "display_name": _clean_label(identity.get("display_name"), company_role, 160),
                "system_role": system_role,
                "company_role": company_role,
                "protected": True,
                "is_default": bool(system_role == "worker" or metadata.get("is_default")),
                "home_membership_id": str(membership["membership_id"]),
                "status": str(identity.get("status") or "active"),
                "job_contract_status": str(current.get("job_contract_status") or "setup_incomplete"),
            }
            if employee != current:
                employees_by_identity[identity_id] = employee
                changed = True
            key = "manager_identity_id" if system_role == "manager" else "default_worker_identity_id"
            if membership.get(key) != identity_id:
                membership[key] = identity_id
                membership["updated_at"] = _utc_now()
                changed = True

        root_role = str(membership.get("membership_role") or "") == "root_controller"
        upsert(manager_identity, system_role="manager", company_role="CEO" if root_role else "Membership manager")
        upsert(default_worker_identity, system_role="worker", company_role="General worker")
        if not changed:
            return payload
        payload["memberships"] = memberships
        payload["employees"] = list(employees_by_identity.values())
        payload["revision"] = int(payload.get("revision") or 0) + 1
        return self._write_company_locked(company_id, payload)

    def reconcile_membership_identities(
        self,
        *,
        company_id: str,
        computer_id: str,
        manager_identity: Optional[Mapping[str, Any]] = None,
        default_worker_identity: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self._load_registry_locked()
            if str(company_id or "") not in dict(registry.get("companies") or {}):
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(str(company_id))
            if not any(
                str(item.get("computer_id") or "") == str(computer_id or "")
                for item in list(company.get("memberships") or [])
            ):
                raise CompanySelectionError("This computer is not a member of that company.")
            return self._reconcile_protected_identities_locked(
                company,
                computer_id=str(computer_id),
                manager_identity=manager_identity,
                default_worker_identity=default_worker_identity,
            )

    def _company_signing_key_locked(
        self,
        company: Dict[str, Any],
    ) -> tuple[Ed25519PrivateKey, str]:
        trust = dict(company.get("company_trust") or {})
        encoded_private = str(trust.get("signing_private_key") or "").strip()
        if encoded_private:
            try:
                private_key = Ed25519PrivateKey.from_private_bytes(
                    base64.b64decode(encoded_private, validate=True)
                )
            except Exception as exc:
                raise CompanyPartitionError(
                    "The company membership signing key is invalid."
                ) from exc
        else:
            private_key = Ed25519PrivateKey.generate()
            trust["signing_private_key"] = base64.b64encode(
                private_key.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            ).decode("ascii")
        public_key = base64.b64encode(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode("ascii")
        trust["signing_public_key"] = public_key
        company["company_trust"] = trust
        return private_key, public_key

    def _signed_membership_bundle_locked(
        self,
        *,
        company: Dict[str, Any],
        membership: Mapping[str, Any],
        parent_membership: Mapping[str, Any],
        issued_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        private_key, public_key = self._company_signing_key_locked(company)
        manifest = dict(company.get("manifest") or {})
        signed_payload = {
            "schema_version": 1,
            "company_id": str(company.get("company_id") or ""),
            "company_revision": int(company.get("revision") or 1),
            "issued_at": str(issued_at or _utc_now()),
            "root_computer_id": str(
                manifest.get("root_computer_id")
                or parent_membership.get("computer_id")
                or ""
            ),
            "parent_membership_id": str(
                parent_membership.get("membership_id") or ""
            )
            or None,
            "membership": {
                key: value
                for key, value in dict(membership).items()
                if key
                not in {
                    "manager_identity_id",
                    "default_worker_identity_id",
                }
            },
            "manifest": manifest,
            "policies": [
                dict(item)
                for item in list(company.get("policies") or [])
                if str(item.get("status") or "active") == "active"
            ],
        }
        signature = base64.b64encode(
            private_key.sign(_canonical_json_bytes(signed_payload))
        ).decode("ascii")
        return {
            "schema_version": 1,
            "algorithm": "Ed25519",
            "public_key": public_key,
            "payload": signed_payload,
            "signature": signature,
        }

    def register_child_membership(
        self,
        *,
        company_id: str,
        parent_computer_id: str,
        child_computer_id: str,
        child_computer_name: str,
    ) -> Dict[str, Any]:
        """Register a direct child and issue its signed Company cache bundle."""

        clean_company_id = str(company_id or "").strip()
        clean_parent_id = str(parent_computer_id or "").strip()
        clean_child_id = str(child_computer_id or "").strip()
        if not clean_company_id or not clean_parent_id or not clean_child_id:
            raise CompanyStoreError(
                "Company, parent computer, and child computer are required."
            )
        with self._lock:
            registry = self._load_registry_locked()
            record = dict(registry.get("companies") or {}).get(clean_company_id)
            if not record:
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(clean_company_id)
            parent_membership = next(
                (
                    item
                    for item in list(company.get("memberships") or [])
                    if str(item.get("computer_id") or "") == clean_parent_id
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if not parent_membership:
                raise CompanySelectionError(
                    "The issuing computer is not an active company member."
                )
            if str(parent_membership.get("membership_role") or "") != "root_controller":
                raise CompanySelectionError(
                    "Version-one company memberships must be issued by the root computer."
                )
            now = _utc_now()
            memberships = [
                dict(item) for item in list(company.get("memberships") or [])
            ]
            membership = next(
                (
                    item
                    for item in memberships
                    if str(item.get("computer_id") or "") == clean_child_id
                ),
                None,
            )
            if membership is None:
                membership = {
                    "membership_id": _stable_membership_id(
                        clean_company_id,
                        clean_child_id,
                    ),
                    "company_id": clean_company_id,
                    "computer_id": clean_child_id,
                    "computer_name": _clean_label(
                        child_computer_name,
                        "Child computer",
                    ),
                    "membership_role": "worker_node",
                    "parent_membership_id": str(
                        parent_membership.get("membership_id") or ""
                    )
                    or None,
                    "manager_identity_id": None,
                    "default_worker_identity_id": None,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                memberships.append(membership)
            else:
                membership["computer_name"] = _clean_label(
                    child_computer_name,
                    "Child computer",
                )
                membership["parent_membership_id"] = str(
                    parent_membership.get("membership_id") or ""
                ) or None
                membership["status"] = "active"
                membership["updated_at"] = now
            company["memberships"] = memberships
            self._company_signing_key_locked(company)
            company["revision"] = int(company.get("revision") or 0) + 1
            saved = self._write_company_locked(clean_company_id, company)
            return self._signed_membership_bundle_locked(
                company=saved,
                membership=membership,
                parent_membership=parent_membership,
                issued_at=now,
            )

    def issue_child_membership_bundle(
        self,
        *,
        company_id: str,
        child_computer_id: str,
    ) -> Dict[str, Any]:
        """Issue a current signed cache without changing Company revision."""

        clean_company_id = str(company_id or "").strip()
        clean_child_id = str(child_computer_id or "").strip()
        if not clean_company_id or not clean_child_id:
            raise CompanyStoreError("Company and child computer are required.")
        with self._lock:
            registry = self._load_registry_locked()
            if clean_company_id not in dict(registry.get("companies") or {}):
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(clean_company_id)
            membership = next(
                (
                    item
                    for item in list(company.get("memberships") or [])
                    if str(item.get("computer_id") or "") == clean_child_id
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if not membership or str(
                membership.get("membership_role") or ""
            ) != "worker_node":
                raise CompanySelectionError(
                    "That computer is not an active child Company member."
                )
            parent_membership_id = str(
                membership.get("parent_membership_id") or ""
            ).strip()
            parent_membership = next(
                (
                    item
                    for item in list(company.get("memberships") or [])
                    if str(item.get("membership_id") or "")
                    == parent_membership_id
                    and str(item.get("membership_role") or "")
                    == "root_controller"
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if not parent_membership:
                raise CompanySelectionError(
                    "The child membership has no active root controller."
                )
            had_signing_key = bool(
                str(
                    dict(company.get("company_trust") or {}).get(
                        "signing_private_key"
                    )
                    or ""
                ).strip()
            )
            bundle = self._signed_membership_bundle_locked(
                company=company,
                membership=membership,
                parent_membership=parent_membership,
            )
            if not had_signing_key:
                self._write_company_locked(clean_company_id, company)
            return bundle

    @staticmethod
    def verify_membership_bundle(
        bundle: Mapping[str, Any],
        *,
        expected_public_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify a root-signed membership bundle without persisting it."""

        payload = dict(bundle.get("payload") or {})
        if int(bundle.get("schema_version") or 0) != 1:
            raise CompanyPartitionError("Unsupported company membership bundle.")
        if str(bundle.get("algorithm") or "") != "Ed25519":
            raise CompanyPartitionError(
                "Unsupported company membership signature."
            )
        company_id = str(payload.get("company_id") or "").strip()
        public_key_text = str(bundle.get("public_key") or "").strip()
        signature_text = str(bundle.get("signature") or "").strip()
        if not company_id or not public_key_text or not signature_text:
            raise CompanyPartitionError(
                "The company membership bundle is incomplete."
            )
        if expected_public_key and not hmac.compare_digest(
            str(expected_public_key),
            public_key_text,
        ):
            raise CompanyPartitionError(
                "The company root signing identity changed unexpectedly."
            )
        try:
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(public_key_text, validate=True)
            )
            public_key.verify(
                base64.b64decode(signature_text, validate=True),
                _canonical_json_bytes(payload),
            )
        except Exception as exc:
            raise CompanyPartitionError(
                "The company membership signature is invalid."
            ) from exc
        issued_membership = dict(payload.get("membership") or {})
        membership_id = str(
            issued_membership.get("membership_id") or ""
        ).strip()
        if (
            not membership_id
            or str(issued_membership.get("company_id") or "") != company_id
            or str(issued_membership.get("membership_role") or "")
            != "worker_node"
        ):
            raise CompanyPartitionError(
                "The company membership payload is invalid."
            )
        return payload

    def import_member_company(
        self,
        *,
        bundle: Mapping[str, Any],
        local_computer_id: str,
        local_computer_name: str,
    ) -> Dict[str, Any]:
        """Verify and store a root-issued Company membership on a child."""

        payload = self.verify_membership_bundle(bundle)
        company_id = str(payload.get("company_id") or "").strip()
        public_key_text = str(bundle.get("public_key") or "").strip()
        signature_text = str(bundle.get("signature") or "").strip()
        local_id = str(local_computer_id or "").strip()
        if not local_id:
            raise CompanyPartitionError("The company membership bundle is incomplete.")
        issued_membership = dict(payload.get("membership") or {})
        membership_id = str(issued_membership.get("membership_id") or "").strip()
        with self._lock:
            registry = self._load_registry_locked()
            existing_record = dict(registry.get("companies") or {}).get(company_id)
            if existing_record and str(
                existing_record.get("local_computer_id") or ""
            ) != local_id:
                raise CompanySelectionError(
                    "That company membership belongs to another local computer."
                )
            if existing_record:
                company = self._read_company_locked(company_id)
                cached_key = str(
                    dict(company.get("upstream_cache") or {}).get(
                        "root_signing_public_key"
                    )
                    or ""
                ).strip()
                if cached_key and not hmac.compare_digest(
                    cached_key,
                    public_key_text,
                ):
                    raise CompanyPartitionError(
                        "The company root signing identity changed unexpectedly."
                    )
                cached = dict(company.get("upstream_cache") or {})
                cached_revision = int(
                    dict(cached.get("signed_payload") or {}).get(
                        "company_revision"
                    )
                    or 0
                )
                incoming_revision = int(payload.get("company_revision") or 0)
                if cached_revision > incoming_revision:
                    raise CompanyPartitionError(
                        "The company membership cache is older than the verified local copy."
                    )
                if (
                    str(cached.get("signature") or "") == signature_text
                    and cached_revision >= incoming_revision
                ):
                    return company
            else:
                company = self._new_company_payload(
                    company_id=company_id,
                    display_name=_clean_label(
                        dict(payload.get("manifest") or {}).get("display_name")
                    ),
                    computer_id=local_id,
                    computer_name=_clean_label(
                        local_computer_name,
                        "This computer",
                    ),
                    ownership="member",
                    membership_role="worker_node",
                )
            now = _utc_now()
            local_membership = {
                **issued_membership,
                "membership_id": membership_id,
                "company_id": company_id,
                "computer_id": local_id,
                "computer_name": _clean_label(
                    local_computer_name,
                    "This computer",
                ),
                "upstream_computer_id": str(
                    issued_membership.get("computer_id") or ""
                )
                or None,
                "manager_identity_id": next(
                    (
                        item.get("manager_identity_id")
                        for item in list(company.get("memberships") or [])
                        if str(item.get("membership_id") or "") == membership_id
                    ),
                    None,
                ),
                "default_worker_identity_id": next(
                    (
                        item.get("default_worker_identity_id")
                        for item in list(company.get("memberships") or [])
                        if str(item.get("membership_id") or "") == membership_id
                    ),
                    None,
                ),
                "status": "active",
                "updated_at": now,
            }
            company["memberships"] = [local_membership]
            company["manifest"] = dict(payload.get("manifest") or {})
            company["policies"] = [
                dict(item) for item in list(payload.get("policies") or [])
            ]
            company["upstream_cache"] = {
                "root_signing_public_key": public_key_text,
                "signed_payload": payload,
                "signature": signature_text,
                "algorithm": "Ed25519",
                "cached_at": now,
            }
            company["migration"] = {
                "state": "company_membership_cache",
                "source": "paired_parent",
                "verified": True,
                "warnings": [],
            }
            company["revision"] = int(payload.get("company_revision") or 1)
            saved = self._write_company_locked(company_id, company)
            record = {
                "company_id": company_id,
                "display_name": _clean_label(
                    dict(saved.get("manifest") or {}).get("display_name")
                ),
                "ownership": "member",
                "membership_role": "worker_node",
                "local_computer_id": local_id,
                "status": "active",
                "onboarding_status": str(
                    dict(saved.get("manifest") or {}).get("onboarding_status")
                    or "not_started"
                ),
                "created_at": str(
                    (existing_record or {}).get("created_at") or now
                ),
                "updated_at": now,
            }
            registry.setdefault("companies", {})[company_id] = record
            self._save_registry_locked(registry)
            return saved

    def sync_published_membership_identities(
        self,
        *,
        company_id: str,
        child_computer_id: str,
        membership_id: Optional[str],
        identities: list[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Update the root directory from a direct child's published targets."""

        clean_company_id = str(company_id or "").strip()
        clean_child_id = str(child_computer_id or "").strip()
        with self._lock:
            registry = self._load_registry_locked()
            if clean_company_id not in dict(registry.get("companies") or {}):
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(clean_company_id)
            membership = next(
                (
                    item
                    for item in list(company.get("memberships") or [])
                    if str(item.get("computer_id") or "") == clean_child_id
                ),
                None,
            )
            if not membership or (
                membership_id
                and str(membership.get("membership_id") or "")
                != str(membership_id)
            ) or str(membership.get("status") or "active") != "active":
                raise CompanySelectionError(
                    "The published identities do not match this company membership."
                )
            employees = [
                dict(item) for item in list(company.get("employees") or [])
            ]
            by_identity = {
                str(item.get("identity_id") or ""): item
                for item in employees
                if str(item.get("identity_id") or "").strip()
            }
            now = _utc_now()
            published_ids: list[str] = []
            changed = False
            for identity in identities:
                identity_id = str(identity.get("identity_id") or "").strip()
                role = str(identity.get("role") or "").strip().lower()
                if not identity_id or role not in {"manager", "worker"}:
                    continue
                published_ids.append(identity_id)
                current = by_identity.get(identity_id, {})
                employee = {
                    **current,
                    "employee_id": str(
                        current.get("employee_id")
                        or f"emp_{secrets.token_hex(12)}"
                    ),
                    "identity_id": identity_id,
                    "display_name": _clean_label(
                        identity.get("display_name"),
                        "Membership manager" if role == "manager" else "Worker",
                        160,
                    ),
                    "system_role": role,
                    "company_role": str(
                        current.get("company_role")
                        or (
                            "Membership manager"
                            if role == "manager"
                            else "General worker"
                        )
                    ),
                    "protected": bool(identity.get("protected")),
                    "is_default": bool(identity.get("is_default")),
                    "home_membership_id": str(
                        membership.get("membership_id") or ""
                    ),
                    "status": str(identity.get("status") or "active"),
                    "job_contract_status": str(
                        current.get("job_contract_status")
                        or "setup_incomplete"
                    ),
                    "published_upstream": True,
                }
                if employee != current:
                    by_identity[identity_id] = employee
                    changed = True
                key = (
                    "manager_identity_id"
                    if role == "manager"
                    else "default_worker_identity_id"
                    if bool(identity.get("is_default"))
                    else None
                )
                if key and membership.get(key) != identity_id:
                    membership[key] = identity_id
                    changed = True

            previous_published_ids = {
                str(item or "").strip()
                for item in list(
                    membership.get("published_identity_ids") or []
                )
                if str(item or "").strip()
            }
            current_published_ids = set(published_ids)
            for stale_identity_id in (
                previous_published_ids - current_published_ids
            ):
                current = by_identity.get(stale_identity_id)
                if (
                    not current
                    or str(current.get("home_membership_id") or "")
                    != str(membership.get("membership_id") or "")
                ):
                    continue
                unavailable = {
                    **current,
                    "status": "unavailable",
                    "published_upstream": False,
                }
                if unavailable != current:
                    by_identity[stale_identity_id] = unavailable
                    changed = True

            if previous_published_ids != current_published_ids:
                membership["published_identity_ids"] = published_ids
                changed = True
            if not changed:
                return dict(membership)
            membership["updated_at"] = now
            company["employees"] = list(by_identity.values())
            company["revision"] = int(company.get("revision") or 0) + 1
            self._write_company_locked(clean_company_id, company)
            return dict(membership)

    def list_companies(self, *, computer_id: str) -> list[Dict[str, Any]]:
        with self._lock:
            registry = self._load_registry_locked()
            items = [
                self._company_summary_from_record(item)
                for item in dict(registry.get("companies") or {}).values()
                if str(item.get("local_computer_id") or "") == str(computer_id or "").strip()
            ]
            return sorted(items, key=lambda item: (item["status"] != "active", item["display_name"].casefold()))

    def active_company_id(self, *, computer_id: str) -> Optional[str]:
        with self._lock:
            registry = self._load_registry_locked()
            selected = str(registry.get("selected_by_computer", {}).get(str(computer_id or "").strip()) or "").strip()
            record = dict(registry.get("companies") or {}).get(selected)
            if not record or str(record.get("status") or "active") != "active":
                return None
            return selected

    def select_company(self, *, computer_id: str, company_id: str) -> Dict[str, Any]:
        clean_computer_id = str(computer_id or "").strip()
        clean_company_id = str(company_id or "").strip()
        with self._lock:
            registry = self._load_registry_locked()
            record = dict(registry.get("companies") or {}).get(clean_company_id)
            if not record or str(record.get("local_computer_id") or "") != clean_computer_id:
                raise CompanyNotFoundError("That company is not available on this computer.")
            if str(record.get("status") or "active") != "active":
                raise CompanySelectionError("That company membership is not currently available.")
            company = self._read_company_locked(clean_company_id)
            registry.setdefault("selected_by_computer", {})[clean_computer_id] = clean_company_id
            record["last_selected_at"] = _utc_now()
            record["updated_at"] = record["last_selected_at"]
            registry["companies"][clean_company_id] = record
            self._save_registry_locked(registry)
            return company

    def get_company(self, company_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self._load_registry_locked()
            if str(company_id or "") not in dict(registry.get("companies") or {}):
                raise CompanyNotFoundError("Unknown company.")
            return self._read_company_locked(str(company_id))

    def mutate_company(
        self,
        *,
        company_id: str,
        mutation: Callable[[Dict[str, Any]], Any],
    ) -> tuple[Dict[str, Any], Any]:
        """Apply one revisioned mutation while holding the partition lock."""

        with self._lock:
            registry = self._load_registry_locked()
            if str(company_id or "") not in dict(registry.get("companies") or {}):
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(company_id)
            result = mutation(company)
            company["revision"] = int(company.get("revision") or 0) + 1
            saved = self._write_company_locked(company_id, company)
            return saved, result

    def update_company(
        self,
        *,
        company_id: str,
        display_name: Optional[str] = None,
        onboarding_status: Optional[str] = None,
        manifest_updates: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self._load_registry_locked()
            record = dict(registry.get("companies") or {}).get(company_id)
            if not record:
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(company_id)
            manifest = dict(company.get("manifest") or {})
            if display_name is not None:
                clean_name = _clean_label(display_name)
                manifest["display_name"] = clean_name
                record["display_name"] = clean_name
            if onboarding_status is not None:
                clean_status = str(onboarding_status or "").strip()[:80] or "not_started"
                manifest["onboarding_status"] = clean_status
                record["onboarding_status"] = clean_status
            for key, value in dict(manifest_updates or {}).items():
                if key in {"root_computer_id", "root_fixed"}:
                    continue
                manifest[str(key)] = value
            company["manifest"] = manifest
            company["revision"] = int(company.get("revision") or 0) + 1
            company = self._write_company_locked(company_id, company)
            record["updated_at"] = company["updated_at"]
            registry["companies"][company_id] = record
            self._save_registry_locked(registry)
            return company

    def record_verified_backup(
        self,
        *,
        company_id: str,
        backup_id: str,
        created_at: str,
    ) -> Dict[str, Any]:
        """Record only proof that an export was verified, never its key material."""

        clean_backup_id = str(backup_id or "").strip()
        if not clean_backup_id:
            raise CompanyStoreError("A verified backup ID is required.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            history = [
                dict(item)
                for item in list(company.get("backup_history") or [])
                if str(item.get("backup_id") or "") != clean_backup_id
            ]
            record = {
                "backup_id": clean_backup_id,
                "created_at": str(created_at or _utc_now()),
                "integrity": "verified",
                "portable_restore_supported_in_this_version": False,
            }
            history.append(record)
            company["backup_history"] = history[-50:]
            return record

        saved, record = self.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return {
            "company_id": company_id,
            "revision": int(saved.get("revision") or 0),
            **record,
        }

    def migration_preview(self, *, company_id: str) -> Dict[str, Any]:
        with self._lock:
            company = self.get_company(company_id)
            migration = dict(company.get("migration") or {})
            counts = {
                "memberships": len(list(company.get("memberships") or [])),
                "employees": len(list(company.get("employees") or [])),
                "positions": len(list(company.get("positions") or [])),
                "job_contracts": len(list(company.get("job_contracts") or [])),
                "objectives": len(list(company.get("objectives") or [])),
                "assignments": len(list(company.get("assignments") or [])),
                "reports": len(list(company.get("reports") or [])),
                "knowledge_records": len(list(company.get("knowledge") or [])),
            }
            warnings = list(migration.get("warnings") or [])
            incomplete = [
                str(item.get("display_name") or item.get("identity_id") or "Employee")
                for item in list(company.get("employees") or [])
                if str(item.get("job_contract_status") or "setup_incomplete")
                not in {"ready", "limited_ready"}
            ]
            if incomplete:
                warnings.append(
                    f"{len(incomplete)} employee identity record(s) still need job readiness review."
                )
            return {
                "company_id": company_id,
                "state": str(migration.get("state") or "legacy_compatibility"),
                "requires_confirmation": str(migration.get("state") or "")
                != "completed",
                "counts": counts,
                "mappings": {
                    "unscoped_local_records": "active company partition",
                    "local_manager": "protected CEO/manager identity",
                    "default_worker": "protected default employee identity",
                    "fleet_relationships": "company-scoped computer memberships",
                },
                "warnings": warnings,
                "backup_required": True,
                "recovery_note": (
                    "The verified encrypted export is the rollback artifact. "
                    "Version one cannot activate it on a different root computer."
                ),
            }

    def complete_migration(
        self,
        *,
        company_id: str,
        verified_backup_id: str,
        external_mapping_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_backup_id = str(verified_backup_id or "").strip()
        external_report = copy.deepcopy(dict(external_mapping_report or {}))

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            backup = next(
                (
                    dict(item)
                    for item in reversed(list(company.get("backup_history") or []))
                    if str(item.get("backup_id") or "") == clean_backup_id
                    and str(item.get("integrity") or "") == "verified"
                ),
                None,
            )
            if not backup:
                raise CompanySelectionError(
                    "Export and verify an encrypted company backup before completing migration."
                )
            migration = dict(company.get("migration") or {})
            completed_at = _utc_now()
            report = self.migration_preview(company_id=company_id)
            migration.update(
                {
                    "state": "completed",
                    "verified": True,
                    "verified_backup_id": clean_backup_id,
                    "completed_at": completed_at,
                    "mapping_report": {
                        "counts": dict(report.get("counts") or {}),
                        "mappings": dict(report.get("mappings") or {}),
                        "warnings": list(report.get("warnings") or []),
                        "migrated_records": external_report,
                    },
                }
            )
            company["migration"] = migration
            audit = list(company.get("company_audit_events") or [])
            audit.append(
                {
                    "event_id": f"cae_{secrets.token_hex(12)}",
                    "event_type": "legacy_company_migration_completed",
                    "company_id": company_id,
                    "backup_id": clean_backup_id,
                    "created_at": completed_at,
                }
            )
            company["company_audit_events"] = audit[-1000:]
            return migration

        saved, migration = self.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return {
            "company_id": company_id,
            "revision": int(saved.get("revision") or 0),
            "migration": migration,
        }

    def deletion_preview(
        self,
        *,
        company_id: str,
        computer_id: str,
    ) -> Dict[str, Any]:
        with self._lock:
            company = self.get_company(company_id)
            manifest = dict(company.get("manifest") or {})
            if str(manifest.get("root_computer_id") or "") != str(computer_id or ""):
                raise CompanySelectionError(
                    "Only the fixed root computer may delete this company."
                )
            terminal_assignment_states = {
                "accepted",
                "archived",
                "cancelled",
                "canceled",
                "completed",
                "failed",
                "rejected",
                "stopped",
            }
            terminal_objective_states = {
                "accepted",
                "archived",
                "cancelled",
                "canceled",
                "completed",
                "failed",
                "reviewed",
            }
            active_assignments = [
                dict(item)
                for item in list(company.get("assignments") or [])
                if str(item.get("state") or item.get("status") or "queued").casefold()
                not in terminal_assignment_states
            ]
            active_objectives = [
                dict(item)
                for item in list(company.get("objectives") or [])
                if str(item.get("status") or "draft").casefold()
                not in terminal_objective_states
            ]
            memberships = [dict(item) for item in list(company.get("memberships") or [])]
            backup_history = list(company.get("backup_history") or [])
            return {
                "company_id": company_id,
                "company_name": _clean_label(manifest.get("display_name")),
                "root_computer_id": str(manifest.get("root_computer_id") or ""),
                "active_assignment_count": len(active_assignments),
                "active_objective_count": len(active_objectives),
                "membership_count": len(memberships),
                "remote_membership_count": len(
                    [
                        item
                        for item in memberships
                        if str(item.get("computer_id") or "") != str(computer_id or "")
                    ]
                ),
                "verified_backup": (
                    dict(backup_history[-1])
                    if backup_history
                    and str(dict(backup_history[-1]).get("integrity") or "")
                    == "verified"
                    else None
                ),
                "will_revoke_memberships": [
                    {
                        "membership_id": str(item.get("membership_id") or ""),
                        "computer_name": str(
                            item.get("computer_name")
                            or item.get("computer_id")
                            or "Computer"
                        ),
                        "status": str(item.get("status") or "active"),
                    }
                    for item in memberships
                ],
                "requires_active_work_action": bool(
                    active_assignments or active_objectives
                ),
                "confirmation_text": _clean_label(manifest.get("display_name")),
                "version_one_result": (
                    "This company cannot be restored on another root computer. "
                    "A fresh local company is created for continued use."
                ),
            }

    def delete_root_company(
        self,
        *,
        company_id: str,
        computer_id: str,
        company_name_confirmation: str,
        active_work_action: str,
        final_backup_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self._load_registry_locked()
            record = dict(registry.get("companies") or {}).get(company_id)
            if not record:
                raise CompanyNotFoundError("Unknown company.")
            company = self._read_company_locked(company_id)
            preview = self.deletion_preview(
                company_id=company_id,
                computer_id=computer_id,
            )
            expected_name = str(preview["confirmation_text"])
            if str(company_name_confirmation or "").strip() != expected_name:
                raise CompanySelectionError(
                    f"Type the exact company name, {expected_name}, to delete it."
                )
            if (
                preview["requires_active_work_action"]
                and str(active_work_action or "").casefold() != "cancel"
            ):
                raise CompanySelectionError(
                    "Choose cancel active work before deleting this company."
                )
            clean_backup_id = str(final_backup_id or "").strip()
            if clean_backup_id:
                verified = any(
                    str(item.get("backup_id") or "") == clean_backup_id
                    and str(item.get("integrity") or "") == "verified"
                    for item in list(company.get("backup_history") or [])
                )
                if not verified:
                    raise CompanySelectionError(
                        "The selected final backup is not a verified export of this company."
                    )

            deleted_at = _utc_now()
            private_key, public_key = self._company_signing_key_locked(company)
            tombstone_payload = {
                "schema_version": 1,
                "company_id": company_id,
                "deleted_at": deleted_at,
                "root_computer_id": str(computer_id),
                "revoked_membership_ids": [
                    str(item.get("membership_id") or "")
                    for item in list(company.get("memberships") or [])
                    if str(item.get("membership_id") or "")
                ],
                "final_backup_id": clean_backup_id or None,
                "reason": "root_company_deleted",
            }
            tombstone = {
                "algorithm": "Ed25519",
                "public_key": public_key,
                "payload": tombstone_payload,
                "signature": base64.b64encode(
                    private_key.sign(_canonical_json_bytes(tombstone_payload))
                ).decode("ascii"),
            }

            record.update(
                {
                    "status": "revoked",
                    "updated_at": deleted_at,
                    "deleted_at": deleted_at,
                    "tombstone": tombstone,
                }
            )
            registry.setdefault("companies", {})[company_id] = record
            if (
                str(
                    registry.setdefault("selected_by_computer", {}).get(
                        str(computer_id)
                    )
                    or ""
                )
                == company_id
            ):
                registry["selected_by_computer"].pop(str(computer_id), None)
            self._save_registry_locked(registry)

            partition_dir = self._partition_dir(company_id).resolve()
            root_dir = self.root_path.resolve()
            if root_dir not in partition_dir.parents:
                raise CompanyPartitionError(
                    "The company partition path failed its deletion safety check."
                )
            if partition_dir.exists():
                shutil.rmtree(partition_dir)
            return {
                "company_id": company_id,
                "deleted_at": deleted_at,
                "tombstone": tombstone,
                "cancelled_assignment_count": int(
                    preview["active_assignment_count"]
                ),
                "cancelled_objective_count": int(
                    preview["active_objective_count"]
                ),
                "revoked_membership_count": int(preview["membership_count"]),
            }

    def context(
        self,
        *,
        computer_id: str,
        computer_name: str,
        manager_identity: Optional[Mapping[str, Any]] = None,
        default_worker_identity: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        selected_before = self.active_company_id(computer_id=computer_id)
        selected_is_root = True
        if selected_before:
            with self._lock:
                selected_record = dict(
                    self._load_registry_locked().get("companies") or {}
                ).get(selected_before, {})
                selected_is_root = str(selected_record.get("ownership") or "") == "root"
        self.ensure_default_company(
            computer_id=computer_id,
            computer_name=computer_name,
            manager_identity=manager_identity if selected_is_root else None,
            default_worker_identity=default_worker_identity if selected_is_root else None,
        )
        with self._lock:
            companies = self.list_companies(computer_id=computer_id)
            active_id = self.active_company_id(computer_id=computer_id)
            active = self._read_company_locked(active_id) if active_id else None
            return {
                "schema_version": COMPANY_REGISTRY_SCHEMA_VERSION,
                "active_company_id": active_id,
                "active_company": active,
                "companies": companies,
                "chooser_required": active is None,
                "selection_reason": None if active is not None else "The last selected company is unavailable.",
                "local_computer_id": str(computer_id),
                "local_computer_name": _clean_label(computer_name, "This computer"),
            }
