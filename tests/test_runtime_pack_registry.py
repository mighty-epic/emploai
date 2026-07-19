from __future__ import annotations

from app_backend import runtime_pack_registry, voice_pack_manager


def test_runtime_pack_registry_lists_voice_and_optional_context_without_installing(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_pack_registry, "shared_state_root", lambda: tmp_path)
    monkeypatch.setattr(
        voice_pack_manager,
        "get_voice_pack_status",
        lambda pack_id: {
            "id": pack_id,
            "installed": False,
            "available": False,
            "managed": True,
            "removable": False,
        },
    )

    summary = runtime_pack_registry.runtime_pack_summary()
    by_id = {pack["id"]: pack for pack in summary["packs"]}

    assert set(voice_pack_manager.VOICE_PACK_IDS).issubset(by_id)
    assert by_id[runtime_pack_registry.CONTEXT_INDEX_ENGLISH_PACK_ID]["approx_size_mb"] == 90
    assert by_id[runtime_pack_registry.CONTEXT_INDEX_ENGLISH_PACK_ID]["installed"] is False
    assert "Lexical search works" in by_id[runtime_pack_registry.CONTEXT_INDEX_ENGLISH_PACK_ID]["description"]
    assert summary["count"] == len(voice_pack_manager.VOICE_PACK_IDS) + 1
