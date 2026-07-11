from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.models.session import Session
from shared.context_loader import ContextLoader
from shared.memory import MemoryManager
from local_agent_runtime.browser_tool import ARIA_SNAPSHOT_JS
from telegram_bot.telegram_runtime_tools import _execute_update_memory


@pytest.fixture(autouse=True)
def _isolate_memory_runtime_home(monkeypatch):
    monkeypatch.delenv("EMPLOAI_HOME", raising=False)


def test_memory_prompt_context_includes_long_term_and_recent_sections(tmp_path):
    manager = MemoryManager(tmp_path)
    manager.update_memory(
        "# MEMORY.md - Long-Term Memory\n\n"
        "## User Preferences\n\n"
        "- Replies should stay concise.\n\n"
        "## Context\n\n"
        "- Linux VPS display is :99.\n"
    )
    manager.append_to_daily_log("Confirmed persistent Chrome lives on the VPS display.", "agent", session_id="main")
    manager.append_to_daily_log("This belongs to a different session.", "agent", session_id="other")

    prompt_context = manager.build_prompt_context(
        session_id="main",
        long_term_chars=4000,
        recent_days=2,
        recent_chars=2000,
    )

    assert "## Long-Term Memory" in prompt_context
    assert "Replies should stay concise." in prompt_context
    assert "## Recent Context from Memory" in prompt_context
    assert "persistent Chrome lives on the VPS display" in prompt_context
    assert "different session" not in prompt_context


def test_append_to_memory_skips_duplicate_entries(tmp_path):
    manager = MemoryManager(tmp_path)

    assert manager.append_to_memory("Context", "- Real Chrome runs inside the VPS display.")
    assert not manager.append_to_memory("Context", "- Real Chrome runs inside the VPS display.")
    assert manager.read_memory().count("- Real Chrome runs inside the VPS display.") == 1


def test_memory_operations_apply_as_single_safe_write(tmp_path):
    manager = MemoryManager(tmp_path)

    result = manager.apply_operations(
        [
            {"action": "add", "section": "Context", "content": "- Kraitos is local-first."},
            {"action": "replace", "old_text": "Kraitos is local-first.", "new_text": "Kraitos stores user data locally."},
        ]
    )

    assert result["changed"] is True
    memory = manager.read_memory()
    assert "Kraitos stores user data locally." in memory
    assert "Kraitos is local-first." not in memory
    assert list((tmp_path / "memory" / "backups").glob("MEMORY.md.memory.*.bak"))


def test_memory_operations_reject_secret_like_content(tmp_path):
    manager = MemoryManager(tmp_path)
    secret_like_value = "sk-" + "thisshouldnotbestoredinmemory123456"

    with pytest.raises(ValueError):
        manager.apply_operations(
            [
                {
                    "action": "add",
                    "section": "Context",
                    "content": f"- api_key: {secret_like_value}",
                }
            ]
        )

    assert secret_like_value[:24] not in manager.read_memory()


def test_local_fact_memory_is_searchable_and_prompt_visible(tmp_path):
    manager = MemoryManager(tmp_path)
    manager.fact_store.add_fact(
        "Kraitos should preserve interactive desktop verification.",
        category="project",
        tags=["kraitos", "desktop"],
    )

    results = manager.search_memory("desktop verification", max_results=5)
    prompt_context = manager.build_prompt_context()

    assert any(result["source"] == "local-facts.sqlite" for result in results)
    assert "## Local Fact Memory" in prompt_context
    assert "interactive desktop verification" in prompt_context


def test_local_fact_memory_delete_removes_fact(tmp_path):
    manager = MemoryManager(tmp_path)
    fact = manager.fact_store.add_fact("Temporary local fact.", category="general")

    assert manager.fact_store.remove_fact(fact["id"]) is True
    assert manager.fact_store.remove_fact(fact["id"]) is False
    assert manager.fact_store.search("Temporary local fact") == []


def test_update_memory_tool_respects_write_disabled():
    session = SimpleNamespace(
        live_config={"memory.write_enabled": False},
        session_context=SimpleNamespace(can_write_memory=True),
        memory_manager=object(),
    )

    result = _execute_update_memory(session, {"section": "Context", "content": "- Save this."})

    assert result == "Memory writing is disabled in settings."


def test_memory_manager_uses_runtime_home_when_present(monkeypatch, tmp_path):
    runtime_home = tmp_path / "runtime-home"
    workspace = tmp_path / "custom-workspace"
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    manager = MemoryManager(workspace)

    assert manager.workspace == runtime_home.resolve()
    assert manager.memory_file == runtime_home.resolve() / "MEMORY.md"
    assert manager.memory_dir == runtime_home.resolve() / "memory"


def test_context_loader_includes_local_tools_file(monkeypatch, tmp_path):
    monkeypatch.delenv("EMPLOAI_HOME", raising=False)
    loader = ContextLoader(tmp_path)
    loader.initialize_workspace()
    local_tools_path = tmp_path / "agent_data" / "LOCAL_TOOLS.md"
    local_tools_path.write_text(
        "# Private Notes\n\n"
        "- Gmail account is available for the bot.\n",
        encoding="utf-8",
    )

    prompt_context = loader.build_system_prompt_context()

    assert "# LOCAL_TOOLS.md (Local-Only Notes)" in prompt_context
    assert "Gmail account is available for the bot." in prompt_context


def test_context_loader_prefers_runtime_context_over_case_mismatched_repo_file(monkeypatch, tmp_path):
    monkeypatch.delenv("EMPLOAI_HOME", raising=False)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_agent_data = repo_root / "agent_data"
    repo_agent_data.mkdir()
    (repo_agent_data / "agents.md").write_text(
        "# Wrong AGENTS\n\n- This is a repo-development file and should not load.\n",
        encoding="utf-8",
    )

    runtime_context = repo_root / "runtime_context"
    runtime_context.mkdir(parents=True)
    (runtime_context / "AGENTS.md").write_text(
        "# Correct AGENTS\n\n- This is the runtime context file.\n",
        encoding="utf-8",
    )

    prompt_context = ContextLoader(repo_root).build_system_prompt_context()

    assert "Correct AGENTS" in prompt_context
    assert "repo-development file" not in prompt_context


def test_agents_template_discourages_rereading_injected_context_files():
    template = ContextLoader._get_agents_template()

    assert "Do NOT spend file-search or file-read tool calls re-opening those files" in template
    assert "Do NOT read `MEMORY.md` just to start a task." in template
    assert "Before doing anything:\n1. Read `SOUL.md`" not in template


def test_legacy_semi_mode_is_normalized_to_auto():
    session = Session.from_dict(
        {
            "id": "abcd1234",
            "name": "Legacy Session",
            "created_at": "2026-05-08T00:00:00",
            "agent_mode": "semi",
        }
    )

    assert session.agent_mode == "auto"


def test_browser_snapshot_scripts_include_shadow_dom_support():
    repo_root = Path(__file__).resolve().parents[1]
    background_js = (repo_root / "browser_extension" / "background.js").read_text(encoding="utf-8")

    assert "shadowRoot" in ARIA_SNAPSHOT_JS
    assert "getAccessibleName" in ARIA_SNAPSHOT_JS
    assert "shadowRoot" in background_js
    assert "getAccessibleName" in background_js
    assert "allFrames: true" in background_js
    assert "snapshotRefRegistry" in background_js
    assert "executeOnResolvedRef" in background_js
    assert "function findElementByAriaRef" in background_js
    assert "findElementByAriaRef(document, ref)" in background_js
    assert "function getDeepActiveElement" in background_js
