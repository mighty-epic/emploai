from pathlib import Path

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


def test_context_loader_includes_local_tools_file(tmp_path):
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
