import json
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class BaseUnifiedAgent:
    """
    Abstract Base Class for provider-specific Unified Agents.
    Handles shared logic for tool execution, interruption, and turn management.
    """
    def __init__(
        self,
        model_config: Any,
        client: Any,
        tool_executor: Callable[[str, Dict], Any],
        workspace: Path,
        logger_func: Optional[Callable[[str], None]] = None,
        system_prompt: Optional[str] = None
    ):
        self.model_config = model_config
        self.client = client
        self.tool_executor = tool_executor
        self.workspace = workspace
        self.logger = logger_func or print
        self.system_prompt = system_prompt
        
        # We'll expect the registry to be passed or accessible
        from shared.unified_agent import UnifiedToolRegistry
        self.tool_registry = UnifiedToolRegistry()
        
        self.conversation_history = []
        self.current_task = None
        self._should_stop = False
        self._should_pause = False

    def run(self, prompt: str, max_turns: int = 100) -> str:
        """The main execution loop, shared by all providers."""
        self.current_task = prompt
        self._should_stop = False
        self._should_pause = False
        
        if not self.conversation_history:
            if self.system_prompt:
                self.conversation_history.append({'role': 'system', 'content': self.system_prompt})
            self.conversation_history.append({'role': 'user', 'content': prompt})
        
        tools = self.get_tools()
        
        for turn in range(max_turns):
            if self._should_stop:
                self.logger("[STOPPED] Agent stopped by user")
                break
            if self._should_pause:
                return "Task paused. Use /continue to resume."
            
            self.logger(f"[Turn {turn + 1}/{max_turns}]")
            
            try:
                # 1. Call the provider-specific model implementation
                response = self._call_model(tools)
                
                # 2. Check for completion or tool calls
                if self._is_task_complete(response):
                    return self._extract_final_message(response)
                
                # 3. Execute tools
                if not self._execute_tool_calls(response):
                    return self._extract_final_message(response)
                    
            except Exception as e:
                self.logger(f"[ERROR] {str(e)}")
                return f"Error: {str(e)}"
        
        return f"Max turns ({max_turns}) reached."

    def stop(self): self._should_stop = True
    def pause(self): self._should_pause = True
    
    def _execute_tool_calls(self, response: Any) -> bool:
        """Executes tool calls using the shared tool_executor."""
        tool_calls = self._extract_tool_calls(response)
        if not tool_calls: return False
        
        results = []
        for tc in tool_calls:
            if self._should_stop or self._should_pause:
                results.append({'id': tc.get('id'), 'name': tc['name'], 'result': "Cancelled"})
                continue
                
            self.logger(f"[TOOL] {tc['name']}({tc['args']})")
            try:
                res = self.tool_executor(tc['name'], tc['args'])
                results.append({'id': tc.get('id'), 'name': tc['name'], 'result': res})
                self.logger(f"[RESULT] {str(res)[:100]}")
            except Exception as e:
                results.append({'id': tc.get('id'), 'name': tc['name'], 'result': f"Error: {e}"})
                
        self._add_results_to_history(results)
        return True

    # Methods to be implemented by child classes
    def get_tools(self) -> List[Dict]: raise NotImplementedError()
    def _call_model(self, tools: List[Dict]) -> Any: raise NotImplementedError()
    def _is_task_complete(self, response: Any) -> bool: raise NotImplementedError()
    def _extract_final_message(self, response: Any) -> str: raise NotImplementedError()
    def _extract_tool_calls(self, response: Any) -> List[Dict]: raise NotImplementedError()
    def _add_results_to_history(self, results: List[Dict]): raise NotImplementedError()
