"""
Main test script for the improved Dual Agent.
Run this script to test specific tasks with different models.
"""

import os
from runner import DualAgentRunner
from dotenv import load_dotenv

load_dotenv()

def test_spotify_task():
    memory_model = "gemini-3-pro-preview"
    executor_model = "gemini-3-flash-preview"
    
    print("\n--- Dual-Agent Interaction Test ---")
    task = input("Enter the task for the agent: ")
    if not task.strip():
        task = "Play some music on Spotify." # Default
        print(f"Using default task: {task}")
    
    print(f"--- Starting Test with Memory: {memory_model} | Executor: {executor_model} ---")
    
    runner = DualAgentRunner(
        memory_model=memory_model,
        executor_model=executor_model
    )
    
    runner.run(task, max_cycles=15)

if __name__ == "__main__":
    test_spotify_task()
