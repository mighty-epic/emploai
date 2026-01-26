"""Unified tool-calling loop for multiple LLM providers."""

import json
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Callable
from cli.tui_constants import ChatMessage, SYSTEM_PROMPT, RESPONSE_MAX_TOKENS
from .adapters import get_tools_for_provider
from .definitions import TOOL_RUN_COMMAND

@dataclass
class LoopResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

def run_tool_loop(
    provider: str,
    model_id: str,
    client: Any,
    messages: List[Dict[str, Any]],
    tool_executor: Any,
    callbacks: Dict[str, Callable],
    variant: str = "standard",
    extra_tools: List[Dict[str, Any]] = None,
    custom_system_prompt: str = None
) -> LoopResult:
    """
    Executes a multi-turn conversation loop where the model can call tools.
    Supports OpenAI-compatible and Anthropic protocols.
    """
    log = callbacks.get("log")
    log_inline = callbacks.get("log_inline")
    append_stream = callbacks.get("append_stream")
    begin_stream = callbacks.get("begin_stream")
    finish_stream = callbacks.get("finish_stream")
    update_status = callbacks.get("update_status")

    # Local copy of messages for the loop
    # Note: messages should NOT include the system prompt for Anthropic (it goes in a param)
    
    max_turns = 10
    total_tokens = 0
    final_response = ""

    for turn in range(max_turns):
        # 1. Get tools in correct format
        tools = get_tools_for_provider(provider)
        
        # 2. Call the Model
        if provider == "google":
            # Gemini Native Tool Use
            model = client.GenerativeModel(
                model_name=model_id,
                system_instruction=custom_system_prompt or SYSTEM_PROMPT,
                tools=[{
                    "function_declarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": t["parameters"]
                        } for t in get_tools_for_provider("openai")
                    ]
                }]
            )
            
            # Start a chat with history
            # Convert messages to Gemini history format (simple version)
            # Gemini history: [{"role": "user"/"model", "parts": [...]}]
            gemini_history = []
            for msg in messages[:-1]: # All but last
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({"role": role, "parts": [str(msg["content"])]})
            
            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(messages[-1]["content"])
            
            while response:
                # Handle Response Parts
                assistant_content = ""
                tool_requests = []
                
                for part in response.candidates[0].content.parts:
                    if part.text:
                        assistant_content += part.text
                        begin_stream()
                        append_stream(part.text)
                        finish_stream()
                    if part.function_call:
                        tool_requests.append(part.function_call)
                
                if not tool_requests:
                    final_response = assistant_content
                    break
                    
                # Execute Tools and send back results
                tool_results = []
                for fc in tool_requests:
                    func_name = fc.name
                    func_args = {k: v for k, v in fc.args.items()}
                    
                    log(f"  [TOOL] {func_name}({func_args})")
                    result = tool_executor.execute(func_name, func_args)
                    
                    result_str = json.dumps(result)
                    if len(result_str) > 4000: result_str = result_str[:4000] + "..."
                    log(f"  [RESULT] {result_str[:200]}...")
                    
                    # Gemini expects ToolResponse parts
                    tool_results.append({
                        "function_response": {
                            "name": func_name,
                            "response": result
                        }
                    })
                
                # Send tool results back to Gemini
                response = chat.send_message(tool_results)
            
            break # Gemini handles its own turns inside the while loop

    max_turns = 10
    total_usage = {"input": 0, "output": 0}
    final_response = ""

    for turn in range(max_turns):
        tools = get_tools_for_provider(provider)
        if extra_tools:
            tools.extend(extra_tools)
            
        sys_prompt = custom_system_prompt or SYSTEM_PROMPT
        
        # --- ANTHROPIC STREAMING ---
        if provider == "anthropic":
            kwargs = {
                "model": model_id,
                "max_tokens": RESPONSE_MAX_TOKENS,
                "system": sys_prompt,
                "messages": [m for m in messages if m["role"] != "system"],
                "tools": tools,
            }
            if variant == "thinking":
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": min(RESPONSE_MAX_TOKENS - 1000, 16000)}
                if kwargs["max_tokens"] < 20000: kwargs["max_tokens"] = 20000

            assistant_text = ""
            tool_calls = []
            
            with client.messages.stream(**kwargs) as stream:
                begin_stream()
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            assistant_text += event.delta.text
                            append_stream(event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            # Stream thoughts in dimmed style
                            append_stream(f"[dim]{event.delta.thinking}[/dim]")
                    elif event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            # We stop generic streaming to UI once tools start
                            # (unless we want to show tool indicators)
                            pass
                finish_stream()
                
                final_msg = stream.get_final_message()
                # Update usage
                if final_msg.usage:
                    total_usage["input"] += final_msg.usage.input_tokens
                    total_usage["output"] += final_msg.usage.output_tokens
                
                # Extract any text blocks and tool calls for history
                assistant_blocks = []
                for block in final_msg.content:
                    if block.type == "text":
                        assistant_blocks.append({"type": "text", "text": block.text})
                    elif block.type == "thinking":
                        assistant_blocks.append({"type": "thinking", "thinking": block.thinking})
                    elif block.type == "tool_use":
                        assistant_blocks.append(block.model_dump())
                        tool_calls.append(block)

                messages.append({"role": "assistant", "content": assistant_blocks})

            if not tool_calls:
                final_response = assistant_text
                break

            # Execute Tools
            for tc in tool_calls:
                log(f"  [TOOL] {tc.name}({tc.input})")
                result = tool_executor.execute(tc.name, tc.input)
                result_str = json.dumps(result)
                if len(result_str) > 8000: result_str = result_str[:8000] + "... (truncated)"
                
                messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tc.id, "content": result_str}]
                })

        # --- OPENAI COMPATIBLE STREAMING ---
        else:
            kwargs = {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "stream": True,
                "stream_options": {"include_usage": True}
            }
            if variant in ["low", "medium", "high", "xhigh"]:
                kwargs["reasoning_effort"] = variant if variant != "xhigh" else "high"

            assistant_text = ""
            # Because streaming tool calls are chunks, we must accumulate them
            # Format: {index: {"name": str, "args": str, "id": str}}
            tool_call_chunks = {}
            
            begin_stream()
            response_stream = client.chat.completions.create(**kwargs)
            for chunk in response_stream:
                if not chunk.choices:
                    if hasattr(chunk, "usage") and chunk.usage:
                        total_usage["input"] += chunk.usage.prompt_tokens
                        total_usage["output"] += chunk.usage.completion_tokens
                    continue
                    
                delta = chunk.choices[0].delta
                
                # Handling Text Content
                if hasattr(delta, "content") and delta.content:
                    assistant_text += delta.content
                    append_stream(delta.content)
                
                # Handling Reasoning Content (DeepSeek/GPT-O1)
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    append_stream(f"[dim]{reasoning}[/dim]")

                # Handling Tool Chunks
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {"id": tc.id, "name": "", "args": ""}
                        
                        if tc.function:
                            if tc.function.name:
                                tool_call_chunks[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_chunks[idx]["args"] += tc.function.arguments
            
            finish_stream()
            
            # Format tool calls for history
            formatted_tc = []
            for idx in sorted(tool_call_chunks.keys()):
                chunks = tool_call_chunks[idx]
                formatted_tc.append({
                    "id": chunks["id"],
                    "type": "function",
                    "function": {"name": chunks["name"], "arguments": chunks["args"]}
                })

            # Add to history
            msg_obj = {"role": "assistant", "content": assistant_text or None}
            if formatted_tc:
                msg_obj["tool_calls"] = formatted_tc
            messages.append(msg_obj)

            if not formatted_tc:
                final_response = assistant_text
                break

            # Execute Tools
            for tc in formatted_tc:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                log(f"  [TOOL] {name}({args})")
                
                result = tool_executor.execute(name, args)
                result_str = json.dumps(result)
                if len(result_str) > 8000: result_str = result_str[:8000] + "... (truncated)"
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result_str
                })

    return LoopResult(
        content=final_response,
        input_tokens=total_usage["input"],
        output_tokens=total_usage["output"],
        total_tokens=total_usage["input"] + total_usage["output"]
    )
