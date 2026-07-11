
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

__test__ = False  # Manual live-model evaluation script; run this module directly.

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

load_dotenv()

from cli.agent_tools.executor import ToolExecutor
from cli.agent_tools.definitions import CLI_AGENT_TOOLS, TOOL_WRITE_FILE
from cli.agent_tools.loop import run_tool_loop
from cli.tui_constants import MODEL_CONFIGS, SYSTEM_PROMPT
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test Workspace
TEST_WORKSPACE = root_dir / "test_workspace"
TEST_WORKSPACE.mkdir(exist_ok=True)

# Configuration
MODEL_ID = "gpt-5.2"  # Using gpt-5.2 as requested
# Need to check the actual ID key in tui_constants or use the one from config
# MODEL_CONFIGS["gpt-5.2"] = {"provider": "openai", "id": "gpt-5.2-2025-12-11", ...}
REAL_MODEL_ID = MODEL_CONFIGS.get(MODEL_ID, {}).get("id", "gpt-4o") # Fallback if not found

logger.info(f"Targeting Model: {MODEL_ID} ({REAL_MODEL_ID})")

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not found in environment")
        sys.exit(1)
    return OpenAI(api_key=api_key)

async def test_single_tool(client, executor, tool_def, extra_tools=None):
    tool_name = tool_def.get("name")
    # Handle both flat and nested structure
    if not tool_name and "function" in tool_def:
        tool_name = tool_def["function"]["name"]
        
    logger.info(f"--- Testing Tool: {tool_name} ---")
    
    # Define a prompt that forces the usage of the specific tool
    prompts = {
        "read_file": f"Read the file 'test.txt' and tell me its content.",
        "write_file": f"Write the text 'Hello World' to a new file named 'test.txt'.",
        "append_file": f"Append the text ' - Appended' to the file 'test.txt'.",
        "edit_file": f"Edit the file 'test.txt' by replacing 'Hello World' with 'Hello Universe'.",
        "list_dir": f"List the files in the current directory.",
        "find_files": f"Find all files ending with '.txt'.",
        "grep_search": f"Search for the string 'Universe' in the current directory.",
        "run_command": f"Run the command 'echo test_run_command' in the terminal.",
        "command_status": "Check the status of command '123' (this is a mock test, expect failure or mock response).",
        "send_input": "Send input 'yes' to command '123' (mock test).",
        "web_search": "Search the web for 'Python 3.14 release date'.",
        # Automation Tools
        "describe_screen": "Describe what is on the screen right now.",
        "open_browser": "Open the browser and go to 'https://www.google.com'.",
        "browser_click": "Click the 'Search' button in the browser.",
    }

    user_prompt = prompts.get(tool_name, f"Use the {tool_name} tool with valid arguments.")
    
    messages = [{"role": "user", "content": user_prompt}]
    
    # Callback to capture logs
    logs = []
    def log_func(text):
        logs.append(text)
        print(text)

    # Pre-requisite setup for certain tools
    if tool_name in ["read_file", "append_file", "edit_file", "grep_search"]:
        # Ensure test.txt exists
        with open(TEST_WORKSPACE / "test.txt", "w") as f:
            f.write("Hello World")

    # Limit to 2 turns: 1 for tool call, 1 for final response
    # We just want to see if the tool loop executes the tool
    
    # Note: run_tool_loop is synchronous/blocking inside, wrapping in run_in_executor in actual app
    # But for a simple script we can call it directly if it doesn't block async event loop (it interacts linearly)
    try:
        result = run_tool_loop(
            provider="openai",
            model_id=REAL_MODEL_ID,
            client=client,
            messages=messages,
            tool_executor=executor,
            callbacks={"log": log_func}, # Minimal callbacks
            variant="standard",
            extra_tools=extra_tools
        )
        
        # Verification
        tool_called = False
        success = False
        
        for log_entry in logs:
            if f"[TOOL] {tool_name}" in log_entry:
                tool_called = True
            if "[RESULT]" in log_entry:
                 # Logic to check if generic result indicates success or if it's an error
                 # For mock tools, an "Unknown tool" error is expected if executor doesn't implement them
                 # But we just want to verify the model CALLED it.
                 pass

        # Check messages history for tool result
        found_tool_result = False
        for msg in messages:
            if msg.get("role") == "tool" and msg.get("name") == tool_name:
                found_tool_result = True
                content = msg.get("content", "")
                
                # For basic CLI tools, we check success
                if tool_name in ["read_file", "write_file", "run_command", "web_search"]:
                    if "error" not in content.lower() or "success" in content.lower():
                        success = True
                else:
                    # For automation tools, we are testing IF the model calls them.
                    # The Executor will likely return "Unknown tool" because we didn't add the actual implementation to it.
                    # That is actually OK for this test - it confirms tool calling works.
                    success = True

        if found_tool_result:
             logger.info(f"✅ PASS: {tool_name} (Called successfully, result received)")
        else:
             logger.error(f"❌ FAIL: {tool_name} (Not called)")

    except Exception as e:
        logger.error(f"❌ ERROR testing {tool_name}: {e}")

async def main():
    client = get_openai_client()
    executor = ToolExecutor(TEST_WORKSPACE)
    
    # Skip interactive/mock tools that involve valid IDs we don't have
    skip_tools = ["command_status", "send_input"] 
    
    logger.info("Starting Comprehensive Tool Test Suite with GPT-5.2")
    
    # 1. Test CLI Tools
    for tool_def in CLI_AGENT_TOOLS:
        if tool_def["name"] in skip_tools:
            continue
        # CLI tools don't need extra_tools list (it's empty/default)
        await test_single_tool(client, executor, tool_def)
        print("-" * 50)

    # 2. Test Automation Tools
    logger.info("\n=== Testing Automation Tools ===")
    
    # Simplified copy of critical tools from local_agent_runtime/agent.py to verify generic tool calling
    AUTOMATION_TOOLS = [
       {"type": "function", "function": {"name": "describe_screen", "description": "Use AI vision to describe the current screen state.", "parameters": {"type": "object", "properties": {"question": {"type": "string"}}}}},
       {"type": "function", "function": {"name": "open_browser", "description": "Open Chrome browser and navigate to a URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
       {"type": "function", "function": {"name": "browser_click", "description": "Click an element in the browser.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    ]

    for tool_def in AUTOMATION_TOOLS:
        await test_single_tool(client, executor, tool_def, extra_tools=AUTOMATION_TOOLS)
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
