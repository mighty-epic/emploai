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
    ObserveRequest, ActionRequest, ObservationMethod, ActionType
)


# ============================================================
# MEMORY AGENT TOOLS
# ============================================================

MEMORY_AGENT_TOOLS = [
    # Decomposition
    {
        "type": "function",
        "function": {
            "name": "decompose_task",
            "description": "Break down the main task into atomic steps",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "description": {"type": "string"}
                            }
                        }
                    }
                },
                "required": ["steps"]
            }
        }
    },
    # Request observation
    {
        "type": "function",
        "function": {
            "name": "request_observation",
            "description": "Ask Executor to observe current screen state",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["browser", "desktop", "general"],
                        "description": "Observation method based on task context"
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "Optional: specific area to focus on (e.g., 'search results', 'top menu')"
                    },
                    "question": {
                        "type": "string",
                        "description": "Optional: specific question to answer (e.g., 'Is the play button visible?')"
                    }
                },
                "required": ["method"]
            }
        }
    },
    # Request action
    {
        "type": "function",
        "function": {
            "name": "request_action",
            "description": "Ask Executor to perform an atomic action",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": ["click", "type", "press_key", "scroll", "navigate", "focus_window"]
                    },
                    "target": {
                        "type": "string",
                        "description": "Element to interact with (text, description, or identifier)"
                    },
                    "value": {
                        "type": "string",
                        "description": "Value for typing, key to press, URL to navigate, etc."
                    }
                },
                "required": ["action_type"]
            }
        }
    },
    # Update step status
    {
        "type": "function",
        "function": {
            "name": "update_step_status",
            "description": "Mark a step as complete or failed",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_number": {"type": "integer"},
                    "status": {"type": "string", "enum": ["complete", "failed"]},
                    "reason": {"type": "string"}
                },
                "required": ["step_number", "status"]
            }
        }
    },
    # Replan
    {
        "type": "function",
        "function": {
            "name": "replan_steps",
            "description": "Update the step list based on current situation",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "description": {"type": "string"}
                            }
                        }
                    },
                    "reason": {"type": "string"}
                },
                "required": ["new_steps", "reason"]
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

MEMORY_AGENT_SYSTEM_PROMPT = """You are a MEMORY AGENT (Planner). You maintain full context of the task and coordinate with a stateless Executor.

YOUR RESPONSIBILITIES:
1. Decompose tasks into atomic steps
2. Request observations from Executor to understand current state
3. Request actions from Executor to make progress
4. Track progress and update step statuses
5. Replan if needed when steps fail or situation changes
6. Complete the task when all steps are done

THE EXECUTOR:
- Has NO memory between requests
- Can observe screen state (browser, desktop, or general)
- Can execute atomic actions (click, type, press_key, scroll, navigate, focus_window)
- Reports results honestly, including failures

YOUR WORKFLOW:
1. First, decompose the task into steps using decompose_task
2. Request an observation only when you need state (initially, after navigation, after an action with unclear outcome, or when stuck)
3. Based on the latest state, request the appropriate action
4. Re-observe only when needed to confirm or unblock progress; avoid multiple observation-only cycles in a row
5. Update step status based on results
6. If a step fails after retries, consider replanning
7. When all steps complete, call task_complete


OBSERVATION GUIDANCE:
- Use "browser" method for web-based tasks
- Use "desktop" method for desktop application tasks
- Use "general" for mixed or unknown contexts
- Be specific about what you're looking for (focus_area, question)
- Don't be too broad (asking for everything) or too narrow (missing context)

ACTION GUIDANCE:
- Give clear, specific targets that the Executor can find
- Include enough detail for the Executor to identify the element
- For clicks: describe the element by visible text, label, or position
- For typing: specify what field to type into if not already focused

PRUNING:
- Your action history will be pruned when context gets too long
- Task and step list are never pruned
- Only old actions/observations are pruned

CURRENT CONTEXT:
{context}

Based on the current context, decide what to do next."""


class MemoryAgent:
    """
    Memory Agent (Planner) with full context.
    Coordinates with Executor to complete tasks.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 128000,  # Model's max context
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.context: Optional[MemoryContext] = None
        
        # Setup LLM client
        self.client = self._setup_client()
        
        # Callback for sending requests to executor
        self.executor_callback = None
    
    def _setup_client(self):
        """Setup OpenAI client."""
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def set_executor_callback(self, callback):
        """Set callback function to send requests to Executor."""
        self.executor_callback = callback
    
    def initialize_task(self, task: str):
        """Initialize a new task."""
        self.context = MemoryContext(task=task)
    
    def think_and_act(self) -> Tuple[str, Optional[ExecutorRequest], bool]:
        """
        One thinking cycle: decide what to do next.
        Returns: (thought, request_to_executor_or_None, is_complete)
        """
        if not self.context:
            return "No task initialized", None, True
        
        # Check if pruning needed
        self._maybe_prune()
        
        # Build system prompt with context
        system_prompt = MEMORY_AGENT_SYSTEM_PROMPT.format(
            context=self.context.to_context_string()
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "What should we do next?"}
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
        """Process LLM response and extract next action."""
        message = response.choices[0].message
        thought = message.content or ""
        
        if not message.tool_calls:
            return thought, None, False
        
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            
            if func_name == "decompose_task":
                return self._handle_decompose(func_args, thought)
            
            elif func_name == "request_observation":
                return self._handle_request_observation(func_args, thought)
            
            elif func_name == "request_action":
                return self._handle_request_action(func_args, thought)
            
            elif func_name == "update_step_status":
                return self._handle_update_status(func_args, thought)
            
            elif func_name == "replan_steps":
                return self._handle_replan(func_args, thought)
            
            elif func_name == "task_complete":
                return self._handle_task_complete(func_args, thought)
        
        return thought, None, False
    
    def _handle_decompose(self, args: Dict, thought: str) -> Tuple[str, None, bool]:
        """Handle task decomposition."""
        steps = args.get("steps", [])
        self.context.step_list = [
            StepInfo(
                step_number=s.get("step_number", i+1),
                description=s.get("description", ""),
                status="pending" if i > 0 else "in_progress"
            )
            for i, s in enumerate(steps)
        ]
        return f"{thought}\nDecomposed into {len(steps)} steps.", None, False
    
    def _handle_request_observation(self, args: Dict, thought: str) -> Tuple[str, ExecutorRequest, bool]:
        """Handle observation request."""
        method_str = args.get("method", "general")
        method = {
            "browser": ObservationMethod.BROWSER,
            "desktop": ObservationMethod.DESKTOP,
            "general": ObservationMethod.GENERAL
        }.get(method_str, ObservationMethod.GENERAL)
        
        request = ExecutorRequest(
            request_type=RequestType.OBSERVE,
            observe=ObserveRequest(
                method=method,
                focus_area=args.get("focus_area"),
                question=args.get("question")
            )
        )
        
        return thought, request, False
    
    def _handle_request_action(self, args: Dict, thought: str) -> Tuple[str, ExecutorRequest, bool]:
        """Handle action request."""
        action_type_str = args.get("action_type", "click")
        action_type = {
            "click": ActionType.CLICK,
            "type": ActionType.TYPE,
            "press_key": ActionType.PRESS_KEY,
            "scroll": ActionType.SCROLL,
            "navigate": ActionType.NAVIGATE,
            "focus_window": ActionType.FOCUS_WINDOW
        }.get(action_type_str, ActionType.CLICK)
        
        request = ExecutorRequest(
            request_type=RequestType.ACTION,
            action=ActionRequest(
                action_type=action_type,
                target=args.get("target"),
                value=args.get("value")
            )
        )
        
        return thought, request, False
    
    def _handle_update_status(self, args: Dict, thought: str) -> Tuple[str, None, bool]:
        """Handle step status update."""
        step_num = args.get("step_number", 1)
        status = args.get("status", "complete")
        
        for step in self.context.step_list:
            if step.step_number == step_num:
                step.status = status
                if status == "complete":
                    self.context.advance_step()
                break
        
        return f"{thought}\nStep {step_num} marked as {status}.", None, False
    
    def _handle_replan(self, args: Dict, thought: str) -> Tuple[str, None, bool]:
        """Handle replanning."""
        new_steps = args.get("new_steps", [])
        reason = args.get("reason", "")
        
        # Keep completed steps, replace pending ones
        completed = [s for s in self.context.step_list if s.status == "complete"]
        next_num = len(completed) + 1
        
        new_step_list = completed + [
            StepInfo(
                step_number=next_num + i,
                description=s.get("description", ""),
                status="pending" if i > 0 else "in_progress"
            )
            for i, s in enumerate(new_steps)
        ]
        
        self.context.step_list = new_step_list
        self.context.current_step_index = len(completed)
        
        return f"{thought}\nReplanned: {reason}", None, False
    
    def _handle_task_complete(self, args: Dict, thought: str) -> Tuple[str, None, bool]:
        """Handle task completion."""
        success = args.get("success", True)
        summary = args.get("summary", "")
        return f"Task complete. Success: {success}. {summary}", None, True
    
    def receive_executor_response(self, request: ExecutorRequest, response: ExecutorResponse, thought: str):
        """
        Receive response from Executor and update context.
        """
        entry = ActionHistoryEntry(
            thought=thought,
            request=request,
            result=response
        )
        self.context.action_history.append(entry)
        
        # Update step attempts if action failed
        if response.action and not response.action.success:
            current_step = self.context.get_current_step()
            if current_step:
                current_step.attempts += 1
    
    def _maybe_prune(self):
        """Prune action history if context exceeds 25% of max tokens."""
        # Rough estimate: each action history entry is ~200 tokens
        estimated_tokens = len(self.context.action_history) * 200 + 500  # base context
        threshold = self.max_tokens * 0.25
        
        if estimated_tokens > threshold:
            self.context.prune_if_needed(self.max_tokens, estimated_tokens)
    
    def get_context_summary(self) -> str:
        """Get current context summary for logging."""
        return self.context.to_context_string() if self.context else "No context"
    
    def chat_with_user(self, user_message: str) -> str:
        """
        Chat with the user during a pause in task execution.
        The agent has full context and can answer questions, provide progress,
        or accept modifications to the task plan.
        
        Args:
            user_message: The user's message/question
            
        Returns:
            The agent's response
        """
        if not self.context:
            return "No task is currently active. Start a task first with /task."
        
        # Build a conversational prompt with full context
        context_str = self.context.to_context_string()
        
        system_prompt = f"""You are a Memory Agent (Planner) that is currently paused mid-task.
The user has interrupted you to ask a question or give instructions.

YOUR CURRENT CONTEXT:
{context_str}

WHAT YOU CAN DO:
1. Answer questions about the current task progress
2. Explain what step you're on and what you've done so far
3. Accept modifications to the plan (the user might ask you to skip steps, add steps, or change approach)
4. Provide a status report
5. Acknowledge instructions that will be applied when the task resumes

Be helpful and conversational. If the user gives you instructions to modify the task, acknowledge them and explain how you'll proceed when resumed.

IMPORTANT: You are NOT executing actions right now - you're just chatting. The user will type /continue to resume the task."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000
            )
            return response.choices[0].message.content or "I understand. Let me know when you're ready to continue with /continue."
        except Exception as e:
            return f"Error communicating: {str(e)}"
    
    def inject_user_instruction(self, instruction: str):
        """
        Inject a user instruction into the action history so the agent
        remembers it when resuming.
        """
        if self.context:
            # Add a special marker in the context that the agent will see
            # We'll add it as a note in the action history
            from .schemas import ActionHistoryEntry, ExecutorRequest, ExecutorResponse, RequestType
            
            # Create a pseudo-entry to record the user's instruction
            note_entry = ActionHistoryEntry(
                thought=f"[USER INSTRUCTION DURING PAUSE]: {instruction}",
                request=ExecutorRequest(request_type=RequestType.OBSERVE),  # Dummy
                result=ExecutorResponse(
                    request_type=RequestType.OBSERVE,
                    observation=None,
                    action=None,
                    impossible=False
                )
            )
            self.context.action_history.append(note_entry)
