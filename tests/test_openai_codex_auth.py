import json
import os

from shared import openai_codex_auth


class _DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self):
        return b'{"output_text":"ready","output":[]}'


def test_codex_responses_endpoint_forces_store_false(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        openai_codex_auth,
        "refresh_codex_auth_if_needed",
        lambda: {
            "base_url": "https://codex.example.test",
            "account_id": "acct_test",
            "tokens": {"access_token": "token_test"},
        },
    )

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _DummyResponse()

    monkeypatch.setattr(openai_codex_auth.urllib.request, "urlopen", fake_urlopen)

    response = openai_codex_auth.create_codex_client().responses.create(
        model="gpt-5.4",
        input=[{"role": "user", "content": "hello"}],
        store=True,
    )

    assert captured["url"] == "https://codex.example.test/responses"
    assert captured["body"]["store"] is False
    assert response.output_text == "ready"


def test_codex_auth_store_is_os_encrypted_and_recovers_backup(monkeypatch, tmp_path):
    auth_path = tmp_path / "openai-codex-auth.json"
    monkeypatch.setenv("EMPLOAI_CODEX_AUTH_PATH", str(auth_path))
    payload = {
        "provider": "openai-codex",
        "tokens": {
            "access_token": "secret-access-token",
            "refresh_token": "secret-refresh-token",
        },
    }

    openai_codex_auth._write_store(payload)

    serialized = auth_path.read_text(encoding="utf-8")
    assert "secret-access-token" not in serialized
    assert openai_codex_auth._read_store()["tokens"]["refresh_token"] == "secret-refresh-token"

    auth_path.write_text('{"ciphertext":', encoding="utf-8")
    assert openai_codex_auth._read_store()["tokens"]["access_token"] == "secret-access-token"
    assert "secret-access-token" not in auth_path.read_text(encoding="utf-8")


def test_codex_auth_legacy_plaintext_migrates_without_leaking_token(monkeypatch, tmp_path):
    auth_path = tmp_path / "openai-codex-auth.json"
    monkeypatch.setenv("EMPLOAI_CODEX_AUTH_PATH", str(auth_path))
    auth_path.write_text(
        json.dumps({"tokens": {"access_token": "legacy-secret-token"}}),
        encoding="utf-8",
    )

    assert openai_codex_auth._read_store()["tokens"]["access_token"] == "legacy-secret-token"
    assert "legacy-secret-token" not in auth_path.read_text(encoding="utf-8")
