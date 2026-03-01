"""Unified tool-calling loop for multiple LLM providers."""

import json
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Callable
from cli.tui_constants import ChatMessage, SYSTEM_PROMPT, RESPONSE_MAX_TOKENS
from .adapters import get_tools_for_provider
from .definitions import TOOL_RUN_COMMAND

# Try to import verbose tool logger (only available in telegram_bot context)
VERBOSE_LOGGING = False
try:
    from telegram_bot.tool_logger import log_tool_call, log_tool_result, log_conversation_turn, log_model_response
    VERBOSE_LOGGING = True
except ImportError:
    try:
        # Alternative import path when running from telegram_bot directory
        from tool_logger import log_tool_call, log_tool_result, log_conversation_turn, log_model_response
        VERBOSE_LOGGING = True
    except ImportError:
        pass

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
    custom_system_prompt: str = None,
    api_type: str = "chat"  # kept for signature compatibility, but unused
) -> LoopResult:
    """
    Executes a multi-turn conversation loop where the model can call tools.
    Simplified to use only OpenAI-compatible streaming protocol for all providers.
    """
    log = callbacks.get("log", lambda *args: None)
    log_inline = callbacks.get("log_inline", lambda *args: None)
    append_stream = callbacks.get("append_stream", lambda *args: None)
    begin_stream = callbacks.get("begin_stream", lambda *args: None)
    finish_stream = callbacks.get("finish_stream", lambda *args: None)
    
    max_turns = 100
    total_usage = {"input": 0, "output": 0}
    final_response = ""
    assistant_text = ""
    
    # 0. System Prompt Injection
    effective_system = custom_system_prompt or SYSTEM_PROMPT
    if messages:
        if messages[0]["role"] == "system":
            messages[0]["content"] = effective_system
        else:
            messages.insert(0, {"role": "system", "content": effective_system})
    else:
        messages.append({"role": "system", "content": effective_system})

    for turn in range(max_turns):
        # Check for interruption at start of turn
        if tool_executor.check_interruption and tool_executor.check_interruption():
            # Get the interrupting message if available
            interrupt_msg = None
            if hasattr(tool_executor, 'get_interrupt_message') and tool_executor.get_interrupt_message:
                interrupt_msg = tool_executor.get_interrupt_message()
            
            if interrupt_msg:
                # Inject the user's interrupt message into messages
                messages.append({"role": "user", "content": f"[USER INTERRUPT] {interrupt_msg}"})
                # Reset the interrupt flag so we can continue processing
                if hasattr(tool_executor, 'clear_interrupt') and tool_executor.clear_interrupt:
                    tool_executor.clear_interrupt()
            else:
                # No message, just stop
                final_response = assistant_text + "\n\n[Interrupted by user]"
                break
            
        if provider == "anthropic":
            tools = get_tools_for_provider("anthropic")
            if extra_tools:
                from .adapters import to_anthropic_format
                tools.extend(to_anthropic_format(extra_tools))
        else:
            tools = get_tools_for_provider("openai")
            if extra_tools:
                tools.extend(extra_tools)
            
        assistant_text = ""
        # Because streaming tool calls are chunks, we must accumulate them
        # Format: {index: {"name": str, "args": str, "id": str}}
        tool_call_chunks = {}
        
        begin_stream()
        
        interrupted_stream = False
        try:
            if provider == "anthropic":
                # Convert ALL messages in history to Anthropic format
                system_text = ""
                anthropic_messages = []
                
                for m in messages:
                    role = m.get("role")
                    content = m.get("content")
                    
                    if role == "system":
                        # Anthropic handles system separately, but we only take the LAST one
                        # found or more likely the first one from the header
                        system_text = content
                        continue
                    
                    if role == "tool":
                        # Orphaned tool result - wrap in user message
                        # (Anthropic requires tool results to follow assistant tool_use)
                        anthropic_messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result", 
                                "tool_use_id": m.get("tool_call_id"), 
                                "content": content
                            }]
                        })
                    elif role == "assistant" and m.get("tool_calls"):
                        # Convert assistant tool_calls to blocks
                        content_list = []
                        if content:
                            content_list.append({"type": "text", "text": content})
                        for tc in m["tool_calls"]:
                            try:
                                args_obj = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                            except:
                                args_obj = {}
                            content_list.append({
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": args_obj
                            })
                        anthropic_messages.append({"role": "assistant", "content": content_list})
                    elif role == "user" and isinstance(content, list) and any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
                        # Already in anthropic format (internal turn results)
                        anthropic_messages.append(m)
                    else:
                        # Standard message
                        anthropic_messages.append({"role": role, "content": content})

                with client.messages.stream(
                    model=model_id,
                    max_tokens=4096,
                    system=system_text,
                    messages=anthropic_messages,
                    tools=tools if tools else None
                ) as stream:
                    # Track current content block for tool calls
                    current_tool_block = None
                    current_tool_index = None
                    
                    for event in stream:
                        if tool_executor.check_interruption and tool_executor.check_interruption():
                             interrupted_stream = True
                             break
                        
                        # Track content block starts (including tool_use)
                        if event.type == "content_block_start":
                            if hasattr(event, 'content_block') and event.content_block.type == "tool_use":
                                # New tool call starting
                                current_tool_index = event.index
                                current_tool_block = event.content_block
                                tool_call_chunks[current_tool_index] = {
                                    "id": current_tool_block.id,
                                    "name": current_tool_block.name,
                                    "args": ""
                                }
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                assistant_text += event.delta.text
                                append_stream(event.delta.text)
                            elif event.delta.type == "input_json_delta":
                                # Tool call argument delta - use tracked index
                                if current_tool_index is not None and current_tool_index in tool_call_chunks:
                                    tool_call_chunks[current_tool_index]["args"] += event.delta.partial_json
                        elif event.type == "content_block_stop":
                            # Content block finished
                            pass
            elif provider == "google":
                # Google Gemini Branch
                import google.generativeai as genai
                
                # Convert history for Gemini
                gemini_history = []
                system_text = ""
                for m in messages[:-1]:
                    role = m.get("role")
                    content = m.get("content")
                    if role == "system":
                        system_text = content
                        continue
                    
                    # Gemini roles are 'user' and 'model'
                    gemini_role = "user" if role in ["user", "tool"] else "model"
                    
                    if isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                parts.append(part.get("text", ""))
                        content = " ".join(parts)
                    
                    gemini_history.append({"role": gemini_role, "parts": [str(content)]})
                
                # Create model
                model = client.GenerativeModel(
                    model_name=model_id,
                    system_instruction=system_text if system_text else None,
                    tools=tools if tools else None
                )
                
                chat = model.start_chat(history=gemini_history)
                
                last_msg = messages[-1]["content"]
                if isinstance(last_msg, list):
                    last_msg = " ".join([p.get("text", "") for p in last_msg if isinstance(p, dict) and p.get("type") == "text"])
                
                response_stream = chat.send_message(last_msg, stream=True)
                
                for chunk in response_stream:
                    if tool_executor.check_interruption and tool_executor.check_interruption():
                         interrupted_stream = True
                         break
                    
                    if chunk.text:
                        assistant_text += chunk.text
                        append_stream(chunk.text)
                    
                    # Tool handling for Gemini
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        for cand in chunk.candidates:
                            if hasattr(cand.content, "parts"):
                                for part in cand.content.parts:
                                    if hasattr(part, "function_call") and part.function_call:
                                        fn = part.function_call
                                        idx = len(tool_call_chunks)
                                        # Use a special ID format for Gemini
                                        tid = f"gemini_{int(time.time())}_{idx}"
                                        tool_call_chunks[idx] = {
                                            "id": tid,
                                            "name": fn.name,
                                            "args": json.dumps(dict(fn.args))
                                        }
            else:
                # OpenAI Streaming Logic
                kwargs = {
                    "model": model_id,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }
                
                if variant in ["low", "medium", "high", "xhigh"] and provider == "openai":
                    kwargs["reasoning_effort"] = variant if variant != "xhigh" else "high"

                response_stream = client.chat.completions.create(**kwargs)
                
                for chunk in response_stream:
                    if tool_executor.check_interruption and tool_executor.check_interruption():
                         interrupted_stream = True
                         break

                    if not chunk.choices:
                        if hasattr(chunk, "usage") and chunk.usage:
                            total_usage["input"] += chunk.usage.prompt_tokens
                            total_usage["output"] += chunk.usage.completion_tokens
                        continue
                        
                    delta = chunk.choices[0].delta
                    
                    if hasattr(delta, "content") and delta.content:
                        assistant_text += delta.content
                        append_stream(delta.content)
                    
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        append_stream(f"[dim]{reasoning}[/dim]")

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
            
            if interrupted_stream:
                log("  🛑 Stream interrupted by user.")
                if assistant_text:
                    assistant_text += "\n\n[USER INTERRUPT: Output Truncated]"
                else:
                    assistant_text = "[USER INTERRUPT: Output Truncated]"

        except Exception as e:
            return LoopResult(content=f"Error in model generation: {str(e)}")
        
        finish_stream()
        
        # Format tool calls for history
        formatted_tc = []
        for idx in sorted(tool_call_chunks.keys()):
            chunks = tool_call_chunks[idx]
            if chunks["name"]:
                formatted_tc.append({
                    "id": chunks["id"],
                    "type": "function",
                    "function": {"name": chunks["name"], "arguments": chunks["args"]}
                })

        # --- ASSISTANT MESSAGE APPEND ---
        if provider == "anthropic":
            # For Anthropic, if there are tool calls, content must be a list
            content_list = []
            if assistant_text:
                content_list.append({"type": "text", "text": assistant_text})
            
            for tc in formatted_tc:
                try:
                    args_obj = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except Exception:
                    args_obj = {}
                content_list.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": args_obj
                })
            
            # If no text AND no tools, Anthropic might complain, but tool loop logic handles break
            if content_list:
                messages.append({"role": "assistant", "content": content_list})
            elif assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        else:
            # OpenAI / Generic
            msg_obj = {"role": "assistant", "content": assistant_text or None}
            if formatted_tc:
                msg_obj["tool_calls"] = formatted_tc
            messages.append(msg_obj)

        if not formatted_tc:
            final_response = assistant_text
            if interrupted_stream:
                continue 
            break

        # --- EXECUTE TOOLS ---
        interrupted_batch = False
        batch_results = []
        
        for i, tc in enumerate(formatted_tc):
            if tool_executor.check_interruption and tool_executor.check_interruption():
                log(f"  🛑 Interruption detected. Skipping remaining tool calls.")
                interrupted_batch = True
                
            name = tc["function"]["name"]
            
            if interrupted_batch:
                batch_results.append({
                    "id": tc["id"],
                    "name": name,
                    "content": json.dumps({"error": "Operation cancelled by user interrupt.", "interrupted": True})
                })
                continue
            
            try:
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            except json.JSONDecodeError:
                args = {} 
            
            # Verbose logging for tool call
            if VERBOSE_LOGGING:
                log_tool_call(name, args, provider)
            else:
                log_args = args.copy() if args else {}
                if 'content' in log_args and len(str(log_args.get('content', ''))) > 100:
                    log_args['content'] = str(log_args['content'])[:100] + "..."
                log(f"  [TOOL] {name}({log_args})")
            
            start_time = time.time()
            try:
                result = tool_executor.execute(name, args)
                if isinstance(result, dict) and result.get("interrupted"):
                    interrupted_batch = True
            except Exception as e:
                result = {"error": f"Tool execution failed: {str(e)}"}
                log(f"  ❌ ERROR: {str(e)}")
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Verbose logging for tool result
            if VERBOSE_LOGGING:
                log_tool_result(name, result, duration_ms)

            # Notify external callback (e.g. Telegram verbose mode)
            on_tool_use_cb = callbacks.get("on_tool_use")
            if on_tool_use_cb:
                on_tool_use_cb(name, args, result, duration_ms)

            # Group result
            batch_results.append({
                "id": tc["id"],
                "name": name,
                "content": json.dumps(result) if not isinstance(result, str) else result,
                "image_data": result.get("image_base64") if isinstance(result, dict) else None
            })

        # --- TOOL RESULTS APPEND ---
        # Helper to strip base64 data from content (it's passed via vision API separately)
        def strip_base64_from_result(content_str: str) -> str:
            """Strip base64 data from tool result content to avoid token bloat."""
            try:
                data = json.loads(content_str)
                if isinstance(data, dict):
                    # Remove base64 fields but keep metadata
                    for key in ["image_base64", "base64", "image_data", "data"]:
                        if key in data and isinstance(data[key], str) and len(data[key]) > 500:
                            data[key] = f"[IMAGE_DATA - {len(data[key])} chars - passed via vision API]"
                    return json.dumps(data)
            except (json.JSONDecodeError, TypeError):
                pass
            return content_str
        
        if provider == "anthropic":
            # Anthropic expects tool results in a SINGLE user message as a list
            result_content = []
            for res in batch_results:
                clean_content = strip_base64_from_result(res["content"])
                if len(clean_content) > 8000: clean_content = clean_content[:8000] + "..."
                
                result_content.append({
                    "type": "tool_result",
                    "tool_use_id": res["id"],
                    "content": clean_content
                })
            
            if result_content:
                messages.append({"role": "user", "content": result_content})
        else:
            # OpenAI style - one message per tool
            for res in batch_results:
                clean_content = strip_base64_from_result(res["content"])
                if len(clean_content) > 8000: clean_content = clean_content[:8000] + "..."
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": res["id"],
                    "name": res["name"],
                    "content": clean_content
                })

        # --- VISION UPDATE HANDLER ---
        for res in batch_results:
            if res.get("image_data"):
                if provider == "anthropic":
                    # Anthropic format for images
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"[Vision Update from {res['name']}] Please analyze this image:"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": res["image_data"]
                                }
                            }
                        ]
                    })
                else:
                    # OpenAI format for images
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"[Vision Update from {res['name']}]"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{res['image_data']}"}}
                        ]
                    })

    return LoopResult(
        content=final_response,
        input_tokens=total_usage["input"],
        output_tokens=total_usage["output"],
        total_tokens=total_usage["input"] + total_usage["output"]
    )
