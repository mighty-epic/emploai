
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

load_dotenv()

from emploai.cli.agent_tools.executor import ToolExecutor
from emploai.cli.agent_tools.definitions import CLI_AGENT_TOOLS
from emploai.cli.agent_tools.loop import run_tool_loop
from emploai.cli.tui_constants import MODEL_CONFIGS
from openai import OpenAI

# -----------------------------------------------------------------------------
# LOGGING SETUP
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# TEST CONFIGURATION
# -----------------------------------------------------------------------------
TEST_WORKSPACE = root_dir / "test_workspace"
TEST_WORKSPACE.mkdir(exist_ok=True)

MODEL_ID = "gpt-5.2"
REAL_MODEL_ID = MODEL_CONFIGS.get(MODEL_ID, {}).get("id", "gpt-4o")

logger.info(f"Using Model: {MODEL_ID} ({REAL_MODEL_ID})")

# -----------------------------------------------------------------------------
# TOOL DEFINITIONS (Simulated Automation Tools + CLI Tools)
# -----------------------------------------------------------------------------
# Mock version of automation tools found in local_agent_runtime/agent.py
# The model will see these descriptions and must choose correctly.
AUTOMATION_TOOLS = [
   {"type": "function", "function": {"name": "describe_screen", "description": "Use AI vision to describe the current screen state. Best for understanding UI layout.", "parameters": {"type": "object", "properties": {"question": {"type": "string"}}}}},
   {"type": "function", "function": {"name": "open_browser", "description": "Open Chrome browser and navigate to a URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
   {"type": "function", "function": {"name": "browser_click", "description": "Click an element in the browser by text content or CSS selector.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
   {"type": "function", "function": {"name": "open_app", "description": "Open a Windows application by name.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}}},
]

# We only pass AUTOMATION_TOOLS as extra_tools because run_tool_loop 
# automatically includes the base CLI tools (formatted correctly).
# Passing CLI_AGENT_TOOLS here causes format errors (flat dict vs openai schema) and duplication.
EXTRA_TOOLS = AUTOMATION_TOOLS

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY missing")
        sys.exit(1)
    return OpenAI(api_key=api_key)

async def run_scenario(client, executor, description, user_prompt, expected_tool):
    """
    Run a specific scenario where the model has ALL tools available, 
    but should pick only ONE specific tool.
    """
    logger.info(f"\n>> SCENARIO: {description}")
    logger.info(f"   Prompt: '{user_prompt}'")
    logger.info(f"   Expected Tool: {expected_tool}")

    messages = [{"role": "user", "content": user_prompt}]
    
    # Callback to capture logs
    logs = []
    def log_func(text):
        logs.append(text)
        print(text)

    # Allow up to 3 turns, but we expect it to happen quickly
    result = run_tool_loop(
        provider="openai",
        model_id=REAL_MODEL_ID,
        client=client,
        messages=messages,
        tool_executor=executor,
        callbacks={"log": log_func},
        variant="standard",
        extra_tools=EXTRA_TOOLS  # <--- CRITICAL: Giving it EVERYTHING (CLI + Automation)
    )

    # Verify results
    called_tools = []
    for msg in messages:
        if msg.get("role") == "tool":
            called_tools.append(msg.get("name"))
    
    unique_tools = list(set(called_tools))
    
    if expected_tool in unique_tools:
        logger.info(f"✅ SUCCESS: Model called '{expected_tool}'.")
        if len(unique_tools) == 1:
            logger.info("   (Perfect! No other tools called.)")
        else:
            logger.warning(f"   (Warning: Also called {unique_tools})")
    else:
        logger.error(f"❌ FAILURE: Model did NOT call '{expected_tool}'.")
        logger.error(f"   Called: {unique_tools}")
    
    # Check if final response exists
    if hasattr(result, 'content') and result.content:
        logger.info(f"   Response: {result.content[:100]}...")

# -----------------------------------------------------------------------------
# MAIN TEST LOGIC
# -----------------------------------------------------------------------------
async def main():
    client = get_openai_client()
    executor = ToolExecutor(TEST_WORKSPACE)
    
    # Ensure test file exists for file ops
    with open(TEST_WORKSPACE / "decision_test.txt", "w") as f:
        f.write("Secret Data: 42")

    scenarios = [
        {
            "desc": "File Read (Simple CLI)",
            "prompt": "Read the content of 'decision_test.txt' in the current directory.",
            "expected": "read_file"
        },
        {
            "desc": "Web Navigation (Automation)",
            "prompt": "Open the browser and navigate to https://news.ycombinator.com",
            "expected": "open_browser"
        },
        {
            "desc": "System Enumeration (CLI)",
            "prompt": "List all files in the current folder.",
            "expected": "list_dir"
        },
        {
            "desc": "Desktop Action (Automation)",
            "prompt": "Open the Notepad application on my computer.",
            "expected": "open_app"
        }
    ]
    
    for s in scenarios:
        await run_scenario(client, executor, s["desc"], s["prompt"], s["expected"])
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(main())
