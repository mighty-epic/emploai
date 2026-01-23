"""
Interactive Chat with Single Agent.
A continuous conversation where the agent can use tools when needed.
"""

from agent import SingleAgent, AGENT_TOOLS, SYSTEM_PROMPT
from dotenv import load_dotenv
load_dotenv()

import os
import json
from openai import OpenAI

def main():
    print("\n" + "="*50)
    print("  SINGLE AGENT CHAT")
    print("  Type 'quit' or 'exit' to end the conversation")
    print("="*50 + "\n")
    
    # Initialize
    agent = SingleAgent(model="gemini-3-flash-preview")
    
    client = OpenAI(
        api_key=os.getenv("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while True:
        # Get user input
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
            print("\nGoodbye!")
            break
        
        # Add user message
        messages.append({"role": "user", "content": user_input})
        
        # Agent loop - runs until complete or interrupted with Ctrl+C
        while True:
            try:
                response = client.chat.completions.create(
                    model="gemini-3-flash-preview",
                    messages=messages,
                    tools=AGENT_TOOLS,
                    max_tokens=2000
                )
                
                message = response.choices[0].message
                
                # If no tool calls, print response and break
                if not message.tool_calls:
                    if message.content:
                        print(f"\nAgent: {message.content}")
                    messages.append({"role": "assistant", "content": message.content or ""})
                    break
                
                # Execute tool calls
                messages.append(message)
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    
                    print(f"  [{func_name}]")
                    result = agent._execute_tool(func_name, args)
                    
                    # Show brief result
                    if "description" in result:
                        print(f"    -> {str(result.get('description', ''))[:80]}...")
                    elif "error" in result:
                        print(f"    -> Error: {result['error']}")
                    elif "success" in result:
                        print(f"    -> OK")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result) if isinstance(result, dict) else str(result)
                    })
                
            except KeyboardInterrupt:
                print("\n  [Interrupted - press Ctrl+C again to exit, or type to continue]")
                messages.append({"role": "user", "content": "The user interrupted. Stop and wait for instructions."})
                break
            except Exception as e:
                print(f"\n[Error: {e}]")
                break

if __name__ == "__main__":
    main()
