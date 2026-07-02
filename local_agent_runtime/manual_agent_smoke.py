"""Manual smoke runner for the legacy SingleAgent implementation."""

from dotenv import load_dotenv

from local_agent_runtime.agent import SingleAgent

load_dotenv()


def main():
    print("\n=== Local Agent Runtime Smoke ===")
    task = input("Enter task: ").strip()

    if not task:
        task = "Open Spotify and play some music"
        print(f"Using default: {task}")

    agent = SingleAgent(model="gemini-2.0-flash")
    result = agent.run(task, max_turns=20)

    print("\n=== FINAL RESULT ===")
    print(result)


if __name__ == "__main__":
    main()
