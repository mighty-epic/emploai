"""
Memory Agent - Planner with Full Context
Holds task, step list, and action history.
Issues requests to Executor and manages pruning.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
from typing import Dict, Any, Optional, List, Tuple

from openai import OpenAI
import anthropic

from .schemas import (
    MemoryContext, StepInfo, ActionHistoryEntry,
    ExecutorRequest, ExecutorResponse, RequestType,
    ObserveRequest, ActionRequest, StepRequest, ObservationMethod, ActionType
)


# ============================================================
# MEMORY AGENT TOOLS
# ============================================================

MEMORY_AGENT_TOOLS = [
    # Request high-level step
    {
        "type": "function",
        "function": {
            "name": "request_step",
            "description": "Send EXACTLY ONE atomic physical action or observation to the Executor. DO NOT bundle multiple actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "The SINGLE atomic action to perform (e.g., 'Type the email', NOT 'Type the email and press enter')"
                    }
                },
                "required": ["description"]
            }
        }
    },
    # Task complete
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal that the entire task is complete",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "summary": {"type": "string"}
                },
                "required": ["success", "summary"]
            }
        }
    }
]


# ============================================================
# MEMORY AGENT SYSTEM PROMPT
# ============================================================

MEMORY_AGENT_SYSTEM_PROMPT = """You are a Memory Agent. Goal: Task completion via strict delegation.
1. **ULTRA-ATOMICITY**: Every 'request_step' MUST be a SINGLE physical movement. 
   - GOOD: "Type the email address"
   - BAD: "Type the email and press enter" (This is TWO steps).
   - **NEVER** bundle multiple actions. If you need to type and then enter, you MUST use two separate turns.
2. **VISION VERIFICATION**: After every physical action, you MUST use 'summarize_screen' or another observation to verify the result before moving to the next physical action.
3. **DIRECT NAVIGATION**: Use 'navigate_to' for all web tasks (Spotify, Sheets, etc.).
4. **EXECUTOR TOOLS**: summarize_screen (Vision), observe_desktop, observe_browser, click_element, type_text, press_key, scroll, navigate_to.
5. **STRATEGIC PIVOT**: If an action doesn't change the screen state as expected, DO NOT repeat it. Try a different element or approach.
Context: {context}"""


class MemoryAgent:
    """
    Memory Agent (Planner) with full context.
    Coordinates with Executor by sending high-level steps.
    """
    
    def __init__(
        self,
        model: str = "gemini-3-pro-preview",
        max_tokens: Optional[int] = None,
    ):
        self.model = model
        
        # Gemini: 1,000,000 | Grok: 2,000,000
        if max_tokens is not None:
            self.max_tokens = max_tokens
        elif "gemini" in self.model.lower():
            self.max_tokens = 1000000
        elif "grok" in self.model.lower():
            self.max_tokens = 2000000
        else:
            self.max_tokens = 128000
            
        self.context: Optional[MemoryContext] = None
        self.client = self._setup_client()
        self.executor_callback = None
    
    def _setup_client(self):
        m_lower = self.model.lower()
        if "gemini" in m_lower:
            return OpenAI(api_key=os.getenv("GEMINI_API_KEY"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        elif "grok" in m_lower:
            return OpenAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1")
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def set_executor_callback(self, callback):
        self.executor_callback = callback
    
    def initialize_task(self, task: str):
        self.context = MemoryContext(task=task)
    
    def think_and_act(self) -> Tuple[str, Optional[ExecutorRequest], bool]:
        if not self.context:
            return "No task initialized", None, True
        
        self._maybe_prune()
        system_prompt = MEMORY_AGENT_SYSTEM_PROMPT.format(context=self.context.to_context_string())
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "What is the next step?"}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=MEMORY_AGENT_TOOLS,
                tool_choice="auto",
                max_tokens=2000
            )
            return self._process_response(response)
        except Exception as e:
            return f"Error in thinking: {str(e)}", None, True
    
    def _process_response(self, response) -> Tuple[str, Optional[ExecutorRequest], bool]:
        message = response.choices[0].message
        thought = message.content or ""
        
        if not message.tool_calls:
            return thought, None, False
        
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            
            if func_name == "request_step":
                description = func_args.get("description", "")
                request = ExecutorRequest(
                    request_type=RequestType.STEP,
                    step=StepRequest(description=description)
                )
                return thought, request, False
            
            elif func_name == "task_complete":
                success = func_args.get("success", True)
                summary = func_args.get("summary", "")
                return f"Task complete. Success: {success}. {summary}", None, True
        
        return thought, None, False
    
    def receive_executor_response(self, request: ExecutorRequest, response: ExecutorResponse, thought: str):
        entry = ActionHistoryEntry(thought=thought, request=request, result=response)
        self.context.action_history.append(entry)
        
        # If the request was a step, we don't have atomic success/fail Tracking here anymore
        # The Memory Agent will see the summary in context and decide
    
    def _maybe_prune(self):
        estimated_tokens = len(self.context.action_history) * 500 + 1000
        threshold = self.max_tokens * 0.8 if self.max_tokens >= 500000 else self.max_tokens * 0.5
        if estimated_tokens > threshold:
            self.context.prune_if_needed(self.max_tokens, estimated_tokens)
    
    def get_context_summary(self) -> str:
        return self.context.to_context_string() if self.context else "No context"
    
    def chat_with_user(self, user_message: str) -> str:
        if not self.context: return "No task active."
        messages = [
            {"role": "system", "content": f"You are a paused agent. Context: {self.context.to_context_string()}"},
            {"role": "user", "content": user_message}
        ]
        try:
            response = self.client.chat.completions.create(model=self.model, messages=messages, max_tokens=1000)
            return response.choices[0].message.content or "Okay."
        except Exception as e: return f"Error: {e}"
    
    def inject_user_instruction(self, instruction: str):
        if self.context:
            note_entry = ActionHistoryEntry(
                thought=f"[USER INSTRUCTION]: {instruction}",
                request=ExecutorRequest(request_type=RequestType.STEP, step=StepRequest(description="User instruction")),
                result=ExecutorResponse(request_type=RequestType.STEP, action=ActionResult(success=True, action_taken="Acknowledged"))
            )
            self.context.action_history.append(note_entry)
