from __future__ import annotations

import base64
import copy
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


BACKUP_SCHEMA_VERSION = 1
BACKUP_ALGORITHM = "AES-256-GCM"
BACKUP_KDF = "scrypt"
BACKUP_KDF_N = 2**15
BACKUP_KDF_R = 8
BACKUP_KDF_P = 1
BACKUP_AAD_PREFIX = "emploai-portable-company-backup"

_SECRET_FIELD_MARKERS = {
    "password",
    "passphrase",
    "secret",
    "access_token",
    "refresh_token",
    "session_token",
    "pairing_token",
    "enrollment_token",
    "private_key",
    "api_key",
    "credential_value",
    "company_key",
}
_LOCAL_PATH_FIELDS = {
    "absolute_path",
    "workspace_path",
    "local_path",
}


class CompanyBackupError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: Any) -> bytes:
    return base64.b64decode(str(value or ""), validate=True)


def _derive_passphrase_key(passphrase: str, salt: bytes) -> bytes:
    clean = str(passphrase or "")
    if len(clean) < 12:
        raise CompanyBackupError("Use a backup passphrase with at least 12 characters.")
    return Scrypt(
        salt=salt,
        length=32,
        n=BACKUP_KDF_N,
        r=BACKUP_KDF_R,
        p=BACKUP_KDF_P,
    ).derive(clean.encode("utf-8"))


def _redact_for_portable_backup(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().casefold()
            if normalized in _SECRET_FIELD_MARKERS or normalized.endswith("_secret"):
                continue
            if normalized in _LOCAL_PATH_FIELDS:
                continue
            sanitized[str(key)] = _redact_for_portable_backup(item)
        return sanitized
    if isinstance(value, list):
        return [_redact_for_portable_backup(item) for item in value]
    return copy.deepcopy(value)


def create_portable_company_backup(
    company: Mapping[str, Any],
    *,
    passphrase: str,
) -> tuple[Dict[str, Any], str]:
    company_id = str(company.get("company_id") or "").strip()
    if not company_id:
        raise CompanyBackupError("The company record has no immutable ID.")

    created_at = _utc_now()
    backup_id = f"cbk_{secrets.token_hex(16)}"
    aad = f"{BACKUP_AAD_PREFIX}:{company_id}:{backup_id}:v{BACKUP_SCHEMA_VERSION}".encode("utf-8")
    portable_company = _redact_for_portable_backup(company)
    payload = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "backup_id": backup_id,
        "company_id": company_id,
        "created_at": created_at,
        "company": portable_company,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    data_key = AESGCM.generate_key(bit_length=256)
    payload_nonce = secrets.token_bytes(12)
    payload_ciphertext = AESGCM(data_key).encrypt(payload_nonce, serialized, aad)

    passphrase_salt = secrets.token_bytes(16)
    passphrase_key = _derive_passphrase_key(passphrase, passphrase_salt)
    passphrase_nonce = secrets.token_bytes(12)
    passphrase_wrap = AESGCM(passphrase_key).encrypt(passphrase_nonce, data_key, aad + b":passphrase")

    recovery_key_bytes = secrets.token_bytes(32)
    recovery_key = base64.urlsafe_b64encode(recovery_key_bytes).decode("ascii").rstrip("=")
    recovery_nonce = secrets.token_bytes(12)
    recovery_wrap = AESGCM(recovery_key_bytes).encrypt(recovery_nonce, data_key, aad + b":recovery")

    envelope = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "backup_id": backup_id,
        "company_id": company_id,
        "company_name": str((company.get("manifest") or {}).get("display_name") or "My Company"),
        "created_at": created_at,
        "algorithm": BACKUP_ALGORITHM,
        "aad": _b64(aad),
        "payload": {
            "nonce": _b64(payload_nonce),
            "ciphertext": _b64(payload_ciphertext),
        },
        "passphrase_wrap": {
            "kdf": BACKUP_KDF,
            "salt": _b64(passphrase_salt),
            "n": BACKUP_KDF_N,
            "r": BACKUP_KDF_R,
            "p": BACKUP_KDF_P,
            "nonce": _b64(passphrase_nonce),
            "ciphertext": _b64(passphrase_wrap),
        },
        "recovery_wrap": {
            "encoding": "base64url",
            "nonce": _b64(recovery_nonce),
            "ciphertext": _b64(recovery_wrap),
        },
        "manifest": {
            "included": [
                "charter and organization",
                "identities, positions, and job contracts",
                "objectives, work records, reports, and reviews",
                "approved company knowledge, policy, decisions, and audit history",
                "artifact metadata and company-approved artifact references",
            ],
            "excluded": [
                "raw credential values and provider secrets",
                "pairing, enrollment, session, and company encryption keys",
                "operating-system protected secret material",
                "absolute local workspace paths and bindings",
            ],
            "portable_restore_supported_in_this_version": False,
        },
        "integrity": "verified",
    }

    # Fail closed before returning a backup that cannot be opened.
    verified = decrypt_portable_company_backup(envelope, passphrase=passphrase)
    if str(verified.get("company_id") or "") != company_id:
        raise CompanyBackupError("The encrypted backup did not pass its verification check.")
    return envelope, recovery_key


def decrypt_portable_company_backup(
    envelope: Mapping[str, Any],
    *,
    passphrase: str | None = None,
    recovery_key: str | None = None,
) -> Dict[str, Any]:
    try:
        aad = _unb64(envelope.get("aad"))
        if passphrase is not None:
            wrapped = dict(envelope.get("passphrase_wrap") or {})
            passphrase_key = _derive_passphrase_key(passphrase, _unb64(wrapped.get("salt")))
            data_key = AESGCM(passphrase_key).decrypt(
                _unb64(wrapped.get("nonce")),
                _unb64(wrapped.get("ciphertext")),
                aad + b":passphrase",
            )
        elif recovery_key:
            padded = str(recovery_key) + "=" * (-len(str(recovery_key)) % 4)
            recovery_key_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
            if len(recovery_key_bytes) != 32:
                raise ValueError("invalid recovery key")
            wrapped = dict(envelope.get("recovery_wrap") or {})
            data_key = AESGCM(recovery_key_bytes).decrypt(
                _unb64(wrapped.get("nonce")),
                _unb64(wrapped.get("ciphertext")),
                aad + b":recovery",
            )
        else:
            raise CompanyBackupError("A passphrase or recovery key is required.")
        payload = dict(envelope.get("payload") or {})
        serialized = AESGCM(data_key).decrypt(
            _unb64(payload.get("nonce")),
            _unb64(payload.get("ciphertext")),
            aad,
        )
        decoded = json.loads(serialized.decode("utf-8"))
    except CompanyBackupError:
        raise
    except Exception as exc:
        raise CompanyBackupError("The backup could not be unlocked or failed integrity verification.") from exc
    if not isinstance(decoded, dict):
        raise CompanyBackupError("The decrypted backup is invalid.")
    return decoded
