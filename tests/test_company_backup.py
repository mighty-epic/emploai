from __future__ import annotations

import json

import pytest

from app_backend.company_backup import (
    CompanyBackupError,
    create_portable_company_backup,
    decrypt_portable_company_backup,
)


def _company():
    return {
        "company_id": "cmp_backup_test",
        "manifest": {"display_name": "Private Company", "purpose": "Test backup"},
        "employees": [{"identity_id": "worker-a", "display_name": "Worker"}],
        "credentials": [
            {
                "credential_id": "cred-1",
                "credential_value": "must-never-leave",
                "access_token": "secret-token",
            }
        ],
        "workspace_bindings": [
            {
                "workspace_id": "workspace-1",
                "absolute_path": "C:/private/repository",
                "display_name": "Repository",
            }
        ],
    }


def test_portable_backup_is_encrypted_verified_and_excludes_secrets():
    envelope, recovery_key = create_portable_company_backup(
        _company(),
        passphrase="correct horse battery staple",
    )

    serialized = json.dumps(envelope)
    assert "Private Company" in serialized
    assert "must-never-leave" not in serialized
    assert "secret-token" not in serialized
    assert "C:/private/repository" not in serialized
    assert envelope["integrity"] == "verified"
    assert envelope["manifest"]["portable_restore_supported_in_this_version"] is False

    unlocked = decrypt_portable_company_backup(
        envelope,
        passphrase="correct horse battery staple",
    )
    assert unlocked["company_id"] == "cmp_backup_test"
    assert "credential_value" not in unlocked["company"]["credentials"][0]
    assert "access_token" not in unlocked["company"]["credentials"][0]
    assert "absolute_path" not in unlocked["company"]["workspace_bindings"][0]

    recovered = decrypt_portable_company_backup(envelope, recovery_key=recovery_key)
    assert recovered["company_id"] == "cmp_backup_test"


def test_portable_backup_rejects_weak_or_wrong_passphrase():
    with pytest.raises(CompanyBackupError):
        create_portable_company_backup(_company(), passphrase="too short")

    envelope, _recovery_key = create_portable_company_backup(
        _company(),
        passphrase="correct horse battery staple",
    )
    with pytest.raises(CompanyBackupError):
        decrypt_portable_company_backup(
            envelope,
            passphrase="wrong horse battery staple",
        )
