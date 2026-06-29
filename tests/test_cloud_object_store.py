from pathlib import Path

from shared.cloud_object_store import CloudObjectStore


def test_cloud_object_store_restores_relative_paths_and_preserves_conflicts(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path / "home"))
    store = CloudObjectStore(user_id=123)

    result = store.put_bytes(
        data=b"cloud copy",
        file_name="report.txt",
        content_type="text/plain",
        metadata={"workspace_id": "ws_1", "file_path": "nested/report.txt"},
    )
    assert result.status == "synced"
    assert result.object_key

    target_dir = tmp_path / "restore"
    existing = target_dir / "nested" / "report.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("local copy", encoding="utf-8")

    restored = store.restore_object_to_relative_path(
        object_key=result.object_key,
        target_dir=target_dir,
        relative_path="nested/report.txt",
        fallback_file_name="report.txt",
        preserve_conflicts=True,
    )

    restored_path = Path(restored["restored_path"])
    assert restored["relative_path"] == "nested/report.txt"
    assert restored["conflict_preserved"] is True
    assert existing.read_text(encoding="utf-8") == "local copy"
    assert restored_path.name == "report.cloud-copy-1.txt"
    assert restored_path.read_bytes() == b"cloud copy"
