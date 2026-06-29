import json
from typing import List, Dict, Any
from .base import BaseUnifiedAgent
from cli.agent_tools.gemini_client import is_openai_compatible_client


def _openai_tool_call_dict(call: Any) -> Dict[str, Any]:
    if isinstance(call, dict):
        return call
    model_dump = getattr(call, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    function = getattr(call, "function", None)
    return {
        "id": getattr(call, "id", None),
        "type": getattr(call, "type", "function"),
        "function": {
            "name": getattr(function, "name", ""),
            "arguments": getattr(function, "arguments", "") or "",
        },
    }


def _openai_messages_from_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    for msg in history:
        role = msg.get("role", "user")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        item = {"role": role, "content": msg.get("content") or ""}
        if role == "assistant" and msg.get("tool_calls"):
            item["tool_calls"] = [_openai_tool_call_dict(call) for call in msg.get("tool_calls") or []]
            if not item["content"]:
                item["content"] = None
        if role == "tool":
            item["tool_call_id"] = msg.get("tool_call_id")
            item["name"] = msg.get("name")
        messages.append(item)
    return messages

class GoogleAgent(BaseUnifiedAgent):
    """Unified Agent for Google Gemini."""
    
    def get_tools(self) -> List[Dict]:
        if is_openai_compatible_client(self.client):
            return self.tool_registry.get_tools_for_provider('openai')
        return self.tool_registry.get_tools_for_provider('google')

    def _call_model(self, tools: List[Dict]) -> Any:
        if is_openai_compatible_client(self.client):
            response = self.client.chat.completions.create(
                model=self.model_config.model_id,
                messages=_openai_messages_from_history(self.conversation_history),
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
            )
            message = response.choices[0].message if response.choices else None
            self.conversation_history.append({
                "role": "assistant",
                "content": getattr(message, "content", None),
                "tool_calls": getattr(message, "tool_calls", None),
            })
            return response

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
        if is_openai_compatible_client(self.client):
            message = response.choices[0].message if response.choices else None
            return not bool(getattr(message, "tool_calls", None))

        # Check if any candidate has function calls
        for part in response.candidates[0].content.parts:
            if part.function_call:
                return False
        return True

    def _extract_final_message(self, response: Any) -> str:
        if is_openai_compatible_client(self.client):
            message = response.choices[0].message if response.choices else None
            return str(getattr(message, "content", "") or "Task completed")

        try:
            return response.text
        except:
            return "Task completed"

    def _extract_tool_calls(self, response: Any) -> List[Dict]:
        if is_openai_compatible_client(self.client):
            message = response.choices[0].message if response.choices else None
            calls = []
            for call in list(getattr(message, "tool_calls", None) or []):
                function = getattr(call, "function", None)
                try:
                    args = json.loads(getattr(function, "arguments", "") or "{}")
                except Exception:
                    args = {}
                calls.append({
                    "id": getattr(call, "id", None),
                    "name": getattr(function, "name", ""),
                    "args": args,
                })
            return calls

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
        if is_openai_compatible_client(self.client):
            for res in results:
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": res.get("id"),
                    "name": res["name"],
                    "content": json.dumps(res["result"], ensure_ascii=False, default=str),
                })
            return

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
