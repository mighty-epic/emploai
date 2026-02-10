import json
from typing import List, Dict, Any
from .base import BaseUnifiedAgent

class OpenAIsAgent(BaseUnifiedAgent):
    """Unified Agent for OpenAI and compatible providers."""
    
    def get_tools(self) -> List[Dict]:
        return self.tool_registry.get_tools_for_provider('openai')

    def _call_model(self, tools: List[Dict]) -> Any:
        response = self.client.chat.completions.create(
            model=self.model_config.model_id,
            messages=self.conversation_history,
            tools=tools if tools else None,
            tool_choice='auto' if tools else None
        )
        msg = response.choices[0].message
        self.conversation_history.append({
            'role': 'assistant',
            'content': msg.content,
            'tool_calls': msg.tool_calls if hasattr(msg, 'tool_calls') else None
        })
        return response

    def _is_task_complete(self, response: Any) -> bool:
        msg = response.choices[0].message
        return not hasattr(msg, 'tool_calls') or msg.tool_calls is None

    def _extract_final_message(self, response: Any) -> str:
        return response.choices[0].message.content or "Task completed"

    def _extract_tool_calls(self, response: Any) -> List[Dict]:
        msg = response.choices[0].message
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            return [
                {'id': tc.id, 'name': tc.function.name, 'args': json.loads(tc.function.arguments)}
                for tc in msg.tool_calls
            ]
        return []

    def _add_results_to_history(self, results: List[Dict]):
        for res in results:
            self.conversation_history.append({
                'role': 'tool',
                'tool_call_id': res['id'],
                'name': res['name'],
                'content': str(res['result'])
            })
