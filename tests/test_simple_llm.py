"""
Simple LLM Reasoning Test
Shows how the LLM reasons and makes tool calls.
"""

from dotenv import load_dotenv
load_dotenv()

import json
from openai import OpenAI

def run_simple_test():
    print("=" * 60)
    print("LLM REASONING TEST")
    print("=" * 60)
    
    client = OpenAI()
    
    # Simple tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "observe_screen",
                "description": "Get current screen elements",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click an element by ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "ID of element to click"}
                    },
                    "required": ["element_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "Type text into focused element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "task_complete",
                "description": "Signal task is done",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "summary": {"type": "string"}
                    },
                    "required": ["success"]
                }
            }
        }
    ]
    
    # Mock observation (simulating what Selenium would return)
    observation = {
        "url": "https://google.com",
        "elements": [
            {"id": "search_input", "type": "input", "text": "", "placeholder": "Search Google", "x": 500, "y": 300},
            {"id": "search_btn", "type": "button", "text": "Google Search", "x": 450, "y": 360},
            {"id": "lucky_btn", "type": "button", "text": "I'm Feeling Lucky", "x": 580, "y": 360},
            {"id": "gmail_link", "type": "link", "text": "Gmail", "x": 850, "y": 50},
            {"id": "images_link", "type": "link", "text": "Images", "x": 800, "y": 50}
        ]
    }
    
    task = "Click on the search input field, then type 'hello world'"
    
    print(f"\n[TASK]: {task}")
    print(f"\n[OBSERVATION]:")
    print(f"  URL: {observation['url']}")
    print(f"  Elements: {len(observation['elements'])}")
    for el in observation['elements']:
        print(f"    - [{el['type']}] {el['id']}: '{el.get('text') or el.get('placeholder', '')}'")
    
    messages = [
        {
            "role": "system", 
            "content": """You are an AI agent controlling a computer. 
Use the provided tools to complete tasks step by step.
Always observe, think, then act.
When done, call task_complete."""
        },
        {
            "role": "user", 
            "content": f"Current screen state:\n{json.dumps(observation, indent=2)}\n\nTask: {task}"
        }
    ]
    
    print(f"\n[LLM REASONING]:")
    
    # Step 1
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    
    if msg.content:
        print(f"\n  Thinking: {msg.content}")
    
    if msg.tool_calls:
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            print(f"\n  Tool Call: {tc.function.name}({json.dumps(args)})")
            
            # Simulate tool response
            if tc.function.name == "click":
                tool_response = {"success": True, "clicked": args.get("element_id")}
            elif tc.function.name == "type_text":
                tool_response = {"success": True, "typed": args.get("text")}
            elif tc.function.name == "observe_screen":
                tool_response = observation
            else:
                tool_response = {"success": True}
            
            # Add to conversation
            messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_response)
            })
    
    # Step 2 - Continue
    print("\n  [Continuing...]")
    
    response2 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    msg2 = response2.choices[0].message
    
    if msg2.content:
        print(f"\n  Thinking: {msg2.content}")
    
    if msg2.tool_calls:
        for tc in msg2.tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            print(f"\n  Tool Call: {tc.function.name}({json.dumps(args)})")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_simple_test()
