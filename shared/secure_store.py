from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from typing import Any, Dict, Mapping


WINDOWS_DPAPI_STORAGE = "windows_dpapi"
KEYRING_STORAGE = "system_keyring"
SECURE_ENVELOPE_VERSION = 1


class SecureStorageUnavailable(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _windows_protect(raw: bytes, *, description: str) -> bytes:
    buffer = ctypes.create_string_buffer(raw, len(raw))
    input_blob = _DataBlob(
        len(raw),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        str(description),
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _windows_unprotect(raw: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(raw, len(raw))
    input_blob = _DataBlob(
        len(raw),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _keyring_account(purpose: str) -> str:
    digest = hashlib.sha256(str(purpose).encode("utf-8", errors="ignore")).hexdigest()
    return f"emploai-{digest[:32]}"


def _keyring_module():
    try:
        import keyring
        from keyring.errors import KeyringError
    except Exception as exc:  # pragma: no cover - platform packaging boundary
        raise SecureStorageUnavailable("The system credential vault is unavailable.") from exc
    return keyring, KeyringError


def protect_json_payload(payload: Mapping[str, Any], *, purpose: str) -> Dict[str, Any]:
    serialized = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if os.name == "nt":
        try:
            protected = _windows_protect(serialized, description=purpose)
        except Exception as exc:
            raise SecureStorageUnavailable("Windows credential encryption is unavailable.") from exc
        return {
            "version": SECURE_ENVELOPE_VERSION,
            "storage": WINDOWS_DPAPI_STORAGE,
            "encoding": "base64",
            "ciphertext": base64.b64encode(protected).decode("ascii"),
        }

    keyring, keyring_error = _keyring_module()
    account = _keyring_account(purpose)
    try:
        keyring.set_password("EmploAI", account, serialized.decode("utf-8"))
    except keyring_error as exc:  # pragma: no cover - depends on host vault
        raise SecureStorageUnavailable("The system credential vault rejected the secret.") from exc
    return {
        "version": SECURE_ENVELOPE_VERSION,
        "storage": KEYRING_STORAGE,
        "service": "EmploAI",
        "account": account,
    }


def unprotect_json_payload(envelope: Mapping[str, Any], *, purpose: str) -> Dict[str, Any]:
    storage = str(envelope.get("storage") or "").strip()
    if storage == WINDOWS_DPAPI_STORAGE:
        try:
            protected = base64.b64decode(str(envelope.get("ciphertext") or ""), validate=True)
            serialized = _windows_unprotect(protected)
        except Exception as exc:
            raise SecureStorageUnavailable("Windows could not decrypt the saved credentials.") from exc
    elif storage == KEYRING_STORAGE:
        keyring, keyring_error = _keyring_module()
        service = str(envelope.get("service") or "EmploAI")
        account = str(envelope.get("account") or _keyring_account(purpose))
        try:
            value = keyring.get_password(service, account)
        except keyring_error as exc:  # pragma: no cover - depends on host vault
            raise SecureStorageUnavailable("The system credential vault could not read the secret.") from exc
        if not value:
            raise SecureStorageUnavailable("The saved credential is missing from the system vault.")
        serialized = value.encode("utf-8")
    else:
        raise SecureStorageUnavailable("The credential file does not use a supported secure storage format.")

    try:
        payload = json.loads(serialized.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecureStorageUnavailable("The decrypted credential payload is invalid.") from exc
    if not isinstance(payload, dict):
        raise SecureStorageUnavailable("The decrypted credential payload is invalid.")
    return payload


def delete_secure_payload(envelope: Mapping[str, Any], *, purpose: str) -> None:
    if str(envelope.get("storage") or "") != KEYRING_STORAGE:
        return
    keyring, keyring_error = _keyring_module()
    service = str(envelope.get("service") or "EmploAI")
    account = str(envelope.get("account") or _keyring_account(purpose))
    try:
        keyring.delete_password(service, account)
    except keyring_error:
        pass
