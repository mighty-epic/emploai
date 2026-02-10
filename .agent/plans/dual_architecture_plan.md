# Dual-Model Orchestrator & Context Compression Plan

## Overview
This plan outlines the implementation of a sophisticated Auto Mode architecture that:
1. Uses the user's selected model for CLI/coding tools
2. Automatically switches to Gemini 3 Flash for automation/vision tools
3. Compresses context at 50% capacity to maintain speed and prevent overflow

---
the changes are specifically for the auto mode and not the other modes , the other modes ie manual and semi should stay the same
## Phase 1: Tool Namespace Tagging

### Goal
Categorize all tools into namespaces so the Orchestrator knows which model should handle them.

### Changes Required

#### File: `cli/agent_tools/definitions.py`
- Add a `namespace` field to each tool definition
- Create two constants: `NAMESPACE_CLI` and `NAMESPACE_AUTOMATION`

```python
NAMESPACE_CLI = "cli"
NAMESPACE_AUTOMATION = "automation"

# Example tool with namespace:
{
    "name": TOOL_READ_FILE,
    "namespace": NAMESPACE_CLI,  # <-- NEW
    "description": "Read the contents of a file...",
    ...
}
```

#### File: `single_agent/agent.py`
- Add `namespace` to each tool in `AGENT_TOOLS`
- All automation tools get `"namespace": "automation"`

### Deliverables
- [ ] Update `CLI_AGENT_TOOLS` with `namespace: cli`
- [ ] Update `AGENT_TOOLS` with `namespace: automation`
- [ ] Create helper function `get_tool_namespace(tool_name) -> str`

---

## Phase 2: Orchestrator State Machine

### Goal
Create an Orchestrator class that manages which model is "active" and handles handoffs.

### New File: `cli/agent_tools/orchestrator.py`

```python
class DualModelOrchestrator:
    """Manages model switching based on tool namespaces."""
    
    def __init__(self, primary_client, primary_model_id, gemini_client):
        self.primary_client = primary_client
        self.primary_model_id = primary_model_id
        self.gemini_client = gemini_client
        self.gemini_model_id = "gemini-3-flash-preview"
        
        self.current_namespace = "cli"  # Start with CLI
        self.shared_messages = []       # Single history for both
    
    def get_active_client(self):
        """Return the client for the current namespace."""
        if self.current_namespace == "automation":
            return self.gemini_client, self.gemini_model_id
        return self.primary_client, self.primary_model_id
    
    def detect_handoff(self, tool_calls: List[Dict]) -> bool:
        """Check if any called tool requires a namespace switch."""
        for call in tool_calls:
            tool_namespace = get_tool_namespace(call["name"])
            if tool_namespace != self.current_namespace:
                return True
        return False
    
    def perform_handoff(self, new_namespace: str):
        """Switch the active model."""
        self.current_namespace = new_namespace
        # History is shared, no duplication needed
```

### Integration Points
- `telegram_agent.py`: Replace direct `run_tool_loop` call with `orchestrator.run()`
- `cli/agent_tools/loop.py`: Modify to accept an Orchestrator and use its `get_active_client()`

### Handoff Logic (Pseudocode)
```
1. User sends message
2. Orchestrator.run(message):
   a. Get active client (starts as Primary)
   b. Call model.chat() with merged tools
   c. If model calls tools:
      - Execute each tool
      - Check namespace of each tool
      - If namespace differs from current: perform_handoff()
   d. Loop until no tool calls or max turns
3. Return final response
```

### Deliverables
- [ ] Create `orchestrator.py` with `DualModelOrchestrator` class
- [ ] Add `get_tool_namespace()` helper
- [ ] Modify `run_tool_loop()` to accept orchestrator parameter
- [ ] Update `handle_message()` in Telegram to use orchestrator in Auto mode

---

## Phase 3: Context Compression Engine

### Goal
Implement automatic context folding when any model hits 50% capacity.

### New File: `cli/agent_tools/context_manager.py`

```python
class ContextManager:
    """Monitors and compresses context to stay under 50%."""
    
    COMPRESSION_THRESHOLD = 0.50  # 50%
    TARGET_AFTER_COMPRESSION = 0.15  # Compress down to ~15%
    
    def __init__(self, model_context_sizes: Dict[str, int], compression_client):
        self.model_sizes = model_context_sizes
        self.compression_client = compression_client  # Fast model for summarization
    
    def estimate_tokens(self, messages: List[Dict]) -> int:
        """Rough token count (4 chars = 1 token)."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4
    
    def needs_compression(self, messages: List[Dict], model_id: str) -> bool:
        """Check if context usage exceeds threshold."""
        max_tokens = self.model_sizes.get(model_id, 128000)
        used_tokens = self.estimate_tokens(messages)
        return (used_tokens / max_tokens) >= self.COMPRESSION_THRESHOLD
    
    def compress(self, messages: List[Dict]) -> List[Dict]:
        """Compress the middle of the conversation."""
        # Pin: System prompt (index 0)
        # Pin: First user message (index 1)
        # Pin: Last 5 messages
        
        pinned_start = messages[:2]
        pinned_end = messages[-5:]
        middle = messages[2:-5]
        
        if len(middle) < 3:
            return messages  # Not enough to compress
        
        # Generate summary of middle section
        summary_prompt = [
            {"role": "system", "content": "Summarize this conversation history concisely. Focus on: decisions made, tools used, results obtained, and current progress."},
            {"role": "user", "content": self._format_for_summary(middle)}
        ]
        
        summary_response = self.compression_client.chat.completions.create(
            model="gemini-3-flash-preview",  # Fast and cheap
            messages=summary_prompt,
            max_tokens=500
        )
        
        summary_text = summary_response.choices[0].message.content
        
        # Rebuild messages with summary
        compressed = pinned_start + [
            {"role": "system", "content": f"[COMPRESSED HISTORY]\n{summary_text}"}
        ] + pinned_end
        
        return compressed
    
    def _format_for_summary(self, messages: List[Dict]) -> str:
        """Format messages for the summarizer."""
        lines = []
        for m in messages:
            role = m.get("role", "user").upper()
            content = m.get("content", "")[:500]  # Truncate long messages
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
```

### Integration Points
- Call `context_manager.needs_compression()` at the START of each turn in `run_tool_loop`
- If True, call `context_manager.compress()` before sending to model
- Log compression events for debugging

### Deliverables
- [ ] Create `context_manager.py` with `ContextManager` class
- [ ] Add token estimation logic
- [ ] Implement compression with pinned messages
- [ ] Integrate into `run_tool_loop()` and `orchestrator.py`
- [ ] Add compression logging/notifications

---

## Phase 4: Unified Integration

### Goal
Wire everything together in the Telegram bot for Auto Mode.

### Changes to `telegram_agent.py`

```python
# In handle_message(), when agent_mode == "auto":

from cli.agent_tools.orchestrator import DualModelOrchestrator
from cli.agent_tools.context_manager import ContextManager

# Create orchestrator
orchestrator = DualModelOrchestrator(
    primary_client=client,
    primary_model_id=model_id,
    gemini_client=session.gemini_client
)

# Create context manager
context_manager = ContextManager(
    model_context_sizes=MODEL_CONTEXT_SIZES,
    compression_client=session.gemini_client
)

# Run with orchestration
result = await loop.run_in_executor(
    None,
    lambda: orchestrator.run(
        messages=messages,
        tool_executor=session.tool_executor,
        context_manager=context_manager,
        callbacks=callbacks
    )
)
```

### Deliverables
- [ ] Update `handle_message()` for Auto mode orchestration
- [ ] Ensure Gemini client is always initialized in TelegramSession
- [ ] Add user-facing notifications for model switches (optional)
- [ ] Add `/context` command to show current usage percentage

---

## Phase 5: Testing & Edge Cases

### Test Scenarios
1. **Pure CLI Task**: User asks to refactor a file. Should stay on Primary model.
2. **Pure Automation Task**: User asks to open Spotify. Should switch to Gemini immediately.
3. **Mixed Task**: User asks to "scrape a website and save results to data.json"
   - Start on Primary (planning)
   - Switch to Gemini (open_browser, observe, scrape)
   - Switch back to Primary (write_file)
4. **Context Overflow**: Send 100+ messages. Should compress at 50%.
5. **Compression Quality**: Verify summary captures key decisions.

### Edge Cases to Handle
- [ ] What if Gemini API is unavailable? Fallback to Primary for automation.
- [ ] What if compression fails? Keep last N messages only.
- [ ] Parallel tool calls with mixed namespaces? Execute all, then switch based on majority.

---

## Implementation Order

| Step | Task | Estimated Effort |
|------|------|------------------|
| 1 | Add namespace tags to tool definitions | 30 min |
| 2 | Create `get_tool_namespace()` helper | 15 min |
| 3 | Create `ContextManager` class | 1 hour |
| 4 | Create `DualModelOrchestrator` class | 1.5 hours |
| 5 | Modify `run_tool_loop()` to support orchestration | 1 hour |
| 6 | Update `telegram_agent.py` for Auto mode | 45 min |
| 7 | Add compression logging & /context command | 30 min |
| 8 | Testing all scenarios | 1 hour |

**Total Estimated Time: ~6-7 hours**

---

## Success Criteria
- [x] Auto mode seamlessly switches between models based on tool type
- [x] No model ever exceeds 50% context usage
- [x] Compression preserves essential context (user can reference earlier decisions)
- [ ] No noticeable latency increase from orchestration overhead (needs testing)
- [x] All existing functionality (Manual, Semi, Task) remains unaffected

---

## Implementation Status (Completed 2026-02-01)

### Files Created:
1. **`cli/agent_tools/context_manager.py`** - Monitors and compresses context at 50% capacity
2. **`cli/agent_tools/orchestrator.py`** - Manages model switching between CLI and automation tools

### Files Modified:
1. **`cli/agent_tools/definitions.py`** - Added namespace tags to all CLI tools + helper functions
2. **`telegram_agent.py`** - Integrated orchestrator for Auto mode + enhanced /context command

### How It Works (Auto Mode):
1. User sends message → Orchestrator receives it
2. Orchestrator uses primary model (user's choice) for planning/CLI tools
3. When automation tool is called → Switches to Gemini 3 Flash
4. When CLI tool is called → Switches back to primary model
5. Context manager monitors usage → Compresses at 50% threshold
6. Final response includes stats on switches and compressions
