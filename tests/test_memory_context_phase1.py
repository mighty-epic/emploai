from pathlib import Path

from cli.models.session import Session
from shared.context_loader import ContextLoader
from shared.memory import MemoryManager
from single_agent.browser_tool import ARIA_SNAPSHOT_JS


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


def test_context_loader_prefers_bundled_runtime_agent_data_over_case_mismatched_repo_file(monkeypatch, tmp_path):
    monkeypatch.delenv("EMPLOAI_HOME", raising=False)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_agent_data = repo_root / "agent_data"
    repo_agent_data.mkdir()
    (repo_agent_data / "agents.md").write_text(
        "# Wrong AGENTS\n\n- This is a repo-development file and should not load.\n",
        encoding="utf-8",
    )

    bundled_agent_data = repo_root / "telegram_bot" / "agent_data"
    bundled_agent_data.mkdir(parents=True)
    (bundled_agent_data / "AGENTS.md").write_text(
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
