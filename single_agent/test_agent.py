"""
Test script for Single Agent.
"""

from agent import SingleAgent
from dotenv import load_dotenv
load_dotenv()

def main():
    print("\n=== Single Agent Test ===")
    task = input("Enter task: ").strip()
    
    if not task:
        task = "Open Spotify and play some music"
        print(f"Using default: {task}")
    
    agent = SingleAgent(model="gemini-2.0-flash")
    result = agent.run(task, max_turns=20)
    
    print(f"\n=== FINAL RESULT ===")
    print(result)

if __name__ == "__main__":
    main()
