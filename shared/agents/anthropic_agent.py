from typing import List, Dict, Any
from .base import BaseUnifiedAgent

class AnthropicAgent(BaseUnifiedAgent):
    """Unified Agent for Anthropic Claude."""
    
    def get_tools(self) -> List[Dict]:
        return self.tool_registry.get_tools_for_provider('anthropic')

    def _call_model(self, tools: List[Dict]) -> Any:
        # Anthropic uses a separate 'system' parameter
        messages = [m for m in self.conversation_history if m['role'] != 'system']
        
        response = self.client.messages.create(
            model=self.model_config.model_id,
            max_tokens=4096,
            system=self.system_prompt,
            tools=tools,
            messages=messages
        )
        self.conversation_history.append({
            'role': 'assistant',
            'content': response.content
        })
        return response

    def _is_task_complete(self, response: Any) -> bool:
        return response.stop_reason == 'end_turn'

    def _extract_final_message(self, response: Any) -> str:
        for block in response.content:
            if hasattr(block, 'text'): return block.text
        return str(response.content)

    def _extract_tool_calls(self, response: Any) -> List[Dict]:
        calls = []
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'tool_use':
                calls.append({'id': block.id, 'name': block.name, 'args': block.input})
        return calls

    def _add_results_to_history(self, results: List[Dict]):
        content = []
        for res in results:
            content.append({
                'type': 'tool_result',
                'tool_use_id': res['id'],
                'content': str(res['result'])
            })
        self.conversation_history.append({'role': 'user', 'content': content})
