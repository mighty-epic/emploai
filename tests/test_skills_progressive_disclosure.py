from skills import SkillRegistry
from shared.local_skill_authoring import create_local_skill, slugify_skill_name, workflow_from_recent_messages
from shared.local_skill_sync import sync_bundled_skills


def test_skill_body_loads_only_when_detail_is_requested(tmp_path):
    skill_dir = tmp_path / "local-desktop"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: local-desktop\n"
        "description: Use desktop verification for local app workflows.\n"
        "---\n"
        "# Local Desktop Skill\n\n"
        "Always verify visible desktop state after interactive actions.\n",
        encoding="utf-8",
    )
    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "checklist.md").write_text("- observe\n- act\n- verify\n", encoding="utf-8")

    registry = SkillRegistry(tmp_path)
    skill = registry.loader.get_skill("local-desktop")

    assert skill is not None
    assert skill.body_loaded is False
    assert "Always verify visible desktop state" not in registry.get_skills_index()

    detail = registry.get_skill_detail("local-desktop")

    assert detail is not None
    assert detail["body_loaded"] is True
    assert "Always verify visible desktop state" in detail["body"]
    assert detail["resources"] == [{"name": "checklist.md", "type": "reference", "loaded": False}]
    assert skill.body_loaded is True


def _write_skill(root, name, body):
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name} description.\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_bundled_skill_sync_preserves_user_edits_and_deletions(tmp_path):
    bundled = tmp_path / "bundled"
    local = tmp_path / "local"
    _write_skill(bundled, "desktop-flow", "Bundled v1")

    first = sync_bundled_skills(bundled, local)

    assert first["copied"] == ["desktop-flow"]
    assert "Bundled v1" in (local / "desktop-flow" / "SKILL.md").read_text(encoding="utf-8")

    (local / "desktop-flow" / "SKILL.md").write_text(
        "---\nname: desktop-flow\ndescription: custom.\n---\nUser edited\n",
        encoding="utf-8",
    )
    (bundled / "desktop-flow" / "SKILL.md").write_text(
        "---\nname: desktop-flow\ndescription: bundled.\n---\nBundled v2\n",
        encoding="utf-8",
    )

    second = sync_bundled_skills(bundled, local)

    assert second["skipped"] == ["desktop-flow"]
    assert "User edited" in (local / "desktop-flow" / "SKILL.md").read_text(encoding="utf-8")

    import shutil

    shutil.rmtree(local / "desktop-flow")
    third = sync_bundled_skills(bundled, local)

    assert third["deleted_respected"] == ["desktop-flow"]
    assert not (local / "desktop-flow").exists()


def test_local_skill_authoring_creates_interactive_skill_and_registry_reload(tmp_path):
    registry = SkillRegistry(tmp_path)

    result = create_local_skill(
        tmp_path,
        name="Verify Desktop Flow!",
        description="Verify a desktop workflow.",
        workflow="- Observe the desktop.\n- Act.\n- Verify the result.",
    )
    registry.reload()
    detail = registry.get_skill_detail(result["name"])

    assert result["name"] == "verify-desktop-flow"
    assert detail is not None
    assert "Keep the desktop/runtime state visible and verified" in detail["body"]
    assert registry.gating.is_available("verify-desktop-flow")


def test_local_skill_authoring_rejects_empty_or_duplicate_skill(tmp_path):
    assert slugify_skill_name("  My Skill  ") == "my-skill"
    create_local_skill(tmp_path, name="my-skill", workflow="Do the thing.")

    import pytest

    with pytest.raises(FileExistsError):
        create_local_skill(tmp_path, name="my-skill", workflow="Do the thing again.")

    with pytest.raises(ValueError):
        create_local_skill(tmp_path, name="   ", workflow="No name.")


def test_workflow_from_recent_messages_preserves_local_chat_source():
    workflow = workflow_from_recent_messages(
        [
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "Open the app and verify the settings panel."},
            {"role": "assistant", "content": "I opened settings and confirmed the local memory controls."},
        ]
    )

    assert "drafted from recent local chat history" in workflow
    assert "Open the app and verify the settings panel." in workflow
    assert "local memory controls" in workflow
    assert "Keep each desktop, browser, terminal, or file action verified" in workflow
