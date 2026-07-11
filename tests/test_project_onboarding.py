from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from shared.project_onboarding import (
    ProjectOnboardingStore,
    merge_tool_packs,
    project_onboarding_prompt_for_session,
    render_project_onboarding_prompt,
)
from shared.tool_packs import PACK_BROWSER_ISOLATED, PACK_WORKSPACE_READ, PACK_WORKSPACE_WRITE
from telegram_bot.telegram_unified_agent import build_unified_system_prompt


def _session_for(workspace: Path | str, *, user_id: int = 1):
    return SimpleNamespace(
        user_id=user_id,
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        system_info="Active Windows: EmploAI App",
        context_loader=None,
        live_config={},
        session_context=None,
        memory_manager=None,
        workspace=workspace,
        current_model="gpt-5.4-mini",
        current_variant="standard",
        _active_tool_packs_for_current_run=[],
    )


def test_project_onboarding_store_is_local_and_redacts_secret_like_text(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path / "emploai-home"))
    workspace = tmp_path / "trade_system"
    workspace.mkdir()
    secret = "sk-proj-" + ("a" * 48)

    store = ProjectOnboardingStore(user_id=42)
    profile = store.upsert(
        workspace=str(workspace),
        profile={
            "enabled": True,
            "role_identity": "Trade system operations agent",
            "job_mission": "Maintain workflows and run tests",
            "required_tools": ["read files", "Gmail"],
            "workflows": ["Review failures", "Run regression tests"],
            "raw_notes": f"temporary api_key={secret}",
        },
    )

    stored_text = json.dumps(store._read_payload(), sort_keys=True)
    prompt = render_project_onboarding_prompt(profile)

    assert store.path == tmp_path / "emploai-home" / "data" / "user_42" / "project-onboarding.json"
    assert secret not in stored_text
    assert secret not in prompt
    assert "[REDACTED_SECRET]" in stored_text
    assert "Trade system operations agent" in prompt
    assert any("Configure Gmail/login credentials" in item for item in profile["missing_requirements"])


def test_project_onboarding_prompt_only_applies_to_matching_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path / "emploai-home"))
    workspace = tmp_path / "hermes"
    other_workspace = tmp_path / "other"
    workspace.mkdir()
    other_workspace.mkdir()

    ProjectOnboardingStore(user_id=7).upsert(
        workspace=str(workspace),
        profile={
            "enabled": True,
            "role_identity": "Hermes maintainer",
            "job_mission": "Keep the agent memory and skills reliable",
        },
    )

    assert "Hermes maintainer" in project_onboarding_prompt_for_session(_session_for(workspace, user_id=7))
    assert project_onboarding_prompt_for_session(_session_for(other_workspace, user_id=7)) == ""


def test_unified_prompt_includes_project_onboarding_after_core_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_HOME", str(tmp_path / "emploai-home"))
    workspace = tmp_path / "kraitos"
    workspace.mkdir()

    ProjectOnboardingStore(user_id=5).upsert(
        workspace=str(workspace),
        profile={
            "enabled": True,
            "role_identity": "Kraitos project operator",
            "job_mission": "Understand the project job and workflows before acting",
            "communication_style": "Be concise and direct",
        },
    )

    prompt = build_unified_system_prompt(_session_for(workspace, user_id=5))

    assert "## PROJECT ONBOARDING PROFILE (managed local section)" in prompt
    assert "Kraitos project operator" in prompt
    assert prompt.index("## CORE CONTRACT") < prompt.index("## PROJECT ONBOARDING PROFILE")


def test_merge_tool_packs_preserves_existing_and_adds_inferred():
    merged = merge_tool_packs([PACK_WORKSPACE_READ], [PACK_BROWSER_ISOLATED, PACK_WORKSPACE_WRITE])

    assert merged.index(PACK_WORKSPACE_READ) < merged.index(PACK_BROWSER_ISOLATED)
    assert PACK_WORKSPACE_WRITE in merged
