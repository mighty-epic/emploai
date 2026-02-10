import json
from typing import List, Dict, Any
from .base import BaseUnifiedAgent

class GoogleAgent(BaseUnifiedAgent):
    """Unified Agent for Google Gemini."""
    
    def get_tools(self) -> List[Dict]:
        return self.tool_registry.get_tools_for_provider('google')

    def _call_model(self, tools: List[Dict]) -> Any:
        import google.generativeai as genai
        model = genai.GenerativeModel(
            model_name=self.model_config.model_id,
            tools=tools if tools else None,
            system_instruction=self.system_prompt
        )
        
        # We use start_chat for multi-turn
        # Note: Gemini parts need careful handling for multi-turn tool calling
        history = self._convert_history_for_gemini()
        
        # The last message is the current one to send
        current_msg = history.pop()
        
        chat = model.start_chat(history=history)
        response = chat.send_message(current_msg['parts'])
        
        # Add assistant response to history
        # We need to store parts including possible function calls
        parts = []
        if hasattr(response, 'text') and response.text:
            parts.append(response.text)
        
        # Extract function calls to add them to history parts
        for part in response.candidates[0].content.parts:
            if part.function_call:
                parts.append(part)

        self.conversation_history.append({
            'role': 'assistant',
            'parts': parts
        })
        return response

    def _is_task_complete(self, response: Any) -> bool:
        # Check if any candidate has function calls
        for part in response.candidates[0].content.parts:
            if part.function_call:
                return False
        return True

    def _extract_final_message(self, response: Any) -> str:
        try:
            return response.text
        except:
            return "Task completed"

    def _extract_tool_calls(self, response: Any) -> List[Dict]:
        calls = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                # Store call ID if available (Gemini doesn't always have IDs like OpenAI)
                calls.append({
                    'name': part.function_call.name,
                    'args': dict(part.function_call.args)
                })
        return calls

    def _add_results_to_history(self, results: List[Dict]):
        # In Gemini, tool results are parts of a "user" role message
        parts = []
        for res in results:
            # We must use standard part format for function responses
            parts.append({
                'function_response': {
                    'name': res['name'],
                    'response': {'result': str(res['result'])}
                }
            })
        self.conversation_history.append({'role': 'user', 'parts': parts})

    def _convert_history_for_gemini(self) -> List[Dict]:
        """Convert shared history format to Gemini parts format."""
        gemini_history = []
        for msg in self.conversation_history:
            if msg['role'] == 'system':
                continue
            role = 'user' if msg['role'] == 'user' else 'model'
            if 'parts' in msg:
                gemini_history.append({'role': role, 'parts': msg['parts']})
            elif 'content' in msg:
                # Handle standard string content
                gemini_history.append({'role': role, 'parts': [msg['content']]})
        return gemini_history
