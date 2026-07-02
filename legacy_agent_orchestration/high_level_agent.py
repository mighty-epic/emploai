"""
High-Level Agent (Planner)
- Decomposes task into subtasks
- Assigns subtasks to low-level agents
- Executes parallel subtasks when possible
- Aggregates results

No direct tool execution - only delegation.
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from anthropic import Anthropic


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Subtask:
    id: int
    instruction: str
    depends_on: List[int] = field(default_factory=list)  # IDs of subtasks this depends on
    agent_type: str = "browser"  # browser, desktop, or research
    status: str = "pending"  # pending, running, success, failed
    result: Optional[Dict] = None


@dataclass
class Plan:
    original_task: str
    subtasks: List[Subtask]
    parallel_groups: List[List[int]]  # Groups of subtask IDs that can run in parallel


# ============================================================
# MODELS CONFIG
# ============================================================

MODELS = {
    "gpt-5": {"provider": "openai", "id": "gpt-5"},
    "gpt-5.1": {"provider": "openai", "id": "gpt-5.1"},
    "gpt-5.2": {"provider": "openai", "id": "gpt-5.2"},
    "gpt-5.4": {"provider": "openai", "id": "gpt-5.4"},
    "gpt-5.5": {"provider": "openai", "id": "gpt-5.5"},
    "gpt-5.4-mini": {"provider": "openai", "id": "gpt-5.4-mini"},
    "gpt-4.1": {"provider": "openai", "id": "gpt-4.1"},
    "gpt-4o": {"provider": "openai", "id": "gpt-4o"},
    "gpt-4o-mini": {"provider": "openai", "id": "gpt-4o-mini"},
    "claude-sonnet-4.5": {"provider": "anthropic", "id": "claude-sonnet-4-5-20250929"},
    "claude-opus-4.5": {"provider": "anthropic", "id": "claude-opus-4-5-20250929"},
    "claude-sonnet-4.6": {"provider": "anthropic", "id": "claude-sonnet-4-6"},
    "claude-opus-4.6": {"provider": "anthropic", "id": "claude-opus-4-6"},
    "claude-opus-4.7": {"provider": "anthropic", "id": "claude-opus-4-7"},
    "claude-haiku-4.5": {"provider": "anthropic", "id": "claude-haiku-4-5-20251001"},
    "claude-opus": {"provider": "anthropic", "id": "claude-opus-4-20250514"},
    "claude-haiku": {"provider": "anthropic", "id": "claude-haiku-4-5-20251001"},
    "claude-sonnet-3.5": {"provider": "anthropic", "id": "claude-3-5-sonnet-20241022"},
}


# ============================================================
# HIGH-LEVEL AGENT
# ============================================================

class HighLevelAgent:
    """
    Planner agent that decomposes tasks and delegates to low-level agents.
    Does NOT execute tools directly.
    """

    def __init__(self, model: str = "gpt-4o-mini", event_callback=None):
        self.model = self._normalize_model(model)
        self.model_config = MODELS.get(self.model, MODELS["gpt-4o-mini"])
        self.openai = OpenAI()
        self.anthropic = Anthropic()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.event_callback = event_callback

    @staticmethod
    def _normalize_model(model: str) -> str:
        normalized = model.strip().lower().replace("_", "-").replace(" ", "-")
        aliases = {
            "claude-3-5-sonnet": "claude-sonnet-3.5",
            "claude-3.5-sonnet": "claude-sonnet-3.5",
            "claude-3-5-sonnet-20241022": "claude-sonnet-3.5",
            "claude-3-5-haiku": "claude-haiku-3.5",
            "claude-3-5-haiku-20241022": "claude-haiku-3.5",
            "claude-sonnet-4-5": "claude-sonnet-4.5",
            "claude-opus-4-5": "claude-opus-4.5",
            "claude-sonnet-4-6": "claude-sonnet-4.6",
            "claude-opus-4-6": "claude-opus-4.6",
            "claude-opus-4-7": "claude-opus-4.7",
            "claude-haiku-4": "claude-haiku-4.5",
            "gpt-5-5": "gpt-5.5",
            "gpt-5-4-mini": "gpt-5.4-mini",
            "chatgpt5.5": "gpt-5.5",
            "chatgpt-5.5": "gpt-5.5",
        }
        return aliases.get(normalized, normalized)

    
    def _emit(self, event_type: str, data: dict):
        """Emit event to callback if registered."""
        if self.event_callback:
            self.event_callback(event_type, data)
        print(f"[{event_type}] {data}")
    
    def execute_task(self, task: str) -> Dict:
        """Main entry point - plan and execute a task."""
        self._emit("high_level_start", {"task": task})
        
        # Step 1: Create plan
        self._emit("planning", {"status": "Creating plan..."})
        plan = self._create_plan(task)
        
        subtask_list = [
            {"id": st.id, "instruction": st.instruction, "agent_type": st.agent_type, "depends_on": st.depends_on}
            for st in plan.subtasks
        ]
        self._emit("plan_created", {"subtask_count": len(plan.subtasks), "subtasks": subtask_list})
        
        # Step 2: Execute plan
        self._emit("executing", {"status": "Executing plan..."})
        results = self._execute_plan(plan)
        
        # Step 3: Aggregate results
        final_result = self._aggregate_results(plan, results)
        self._emit("high_level_complete", {"success": final_result["success"], "summary": final_result["summary"]})
        
        return final_result
    
    def _create_plan(self, task: str) -> Plan:
        """Use LLM to decompose task into subtasks."""
        
        planning_prompt = """You are a task planning AI. Break down the user's task into specific subtasks.

For each subtask, specify:
1. A clear, actionable instruction
2. Which agent type should handle it: "browser" (web), "desktop" (apps), or "research" (info gathering)
3. Which previous subtask IDs it depends on (empty list if independent)

Output JSON format:
{
  "subtasks": [
    {"id": 1, "instruction": "...", "agent_type": "browser", "depends_on": []},
    {"id": 2, "instruction": "...", "agent_type": "browser", "depends_on": [1]},
    ...
  ],
  "parallel_groups": [[1], [2, 3], [4]]  // Groups that can run in parallel
}

CRITICAL RULES:

1. USE BROWSER for these services (NOT desktop app):
   - Spotify → open_browser("https://open.spotify.com")
   - YouTube → open_browser("https://youtube.com")  
   - Gmail → open_browser("https://mail.google.com")
   - WhatsApp → open_browser("https://web.whatsapp.com")
   - Twitter/X → open_browser("https://x.com")
   - ANY web-based service → use browser agent

2. USE DESKTOP only for:
   - Notepad, Calculator, File Explorer
   - Microsoft Office apps (Word, Excel)
   - Local applications without web versions

3. General rules:
   - Keep subtasks atomic and specific
   - Browser agent can: open URLs, click, type, scroll, take screenshots
   - Desktop agent can: open apps, click UI elements, type, menu navigation
   - Be efficient - don't over-decompose simple tasks

User task: """ + task

        response = self._call_llm(planning_prompt)
        
        try:
            # Parse JSON from response
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            data = json.loads(json_str)
            
            subtasks = [
                Subtask(
                    id=st["id"],
                    instruction=st["instruction"],
                    agent_type=st.get("agent_type", "browser"),
                    depends_on=st.get("depends_on", [])
                )
                for st in data["subtasks"]
            ]
            
            parallel_groups = data.get("parallel_groups", [[st.id] for st in subtasks])
            
            return Plan(
                original_task=task,
                subtasks=subtasks,
                parallel_groups=parallel_groups
            )
        except Exception as e:
            # Fallback: single subtask
            print(f"[WARN] Plan parsing failed: {e}")
            return Plan(
                original_task=task,
                subtasks=[Subtask(id=1, instruction=task, agent_type="browser")],
                parallel_groups=[[1]]
            )
    
    def _execute_plan(self, plan: Plan) -> Dict[int, Dict]:
        """Execute subtasks, respecting dependencies and parallelism."""
        results = {}
        
        for group in plan.parallel_groups:
            # Get subtasks for this group
            group_subtasks = [st for st in plan.subtasks if st.id in group]
            
            # Check if dependencies are satisfied
            ready_subtasks = []
            for st in group_subtasks:
                deps_satisfied = all(
                    dep_id in results and results[dep_id].get("success", False)
                    for dep_id in st.depends_on
                )
                if deps_satisfied:
                    ready_subtasks.append(st)
            
            if not ready_subtasks:
                continue
            
            # Execute in parallel if multiple
            if len(ready_subtasks) > 1:
                print(f"\n[PARALLEL] Executing subtasks {[st.id for st in ready_subtasks]}")
                futures = []
                for st in ready_subtasks:
                    context = {dep_id: results[dep_id] for dep_id in st.depends_on}
                    future = self.executor.submit(self._execute_subtask, st, context)
                    futures.append((st.id, future))
                
                for st_id, future in futures:
                    results[st_id] = future.result()
            else:
                # Execute single subtask
                st = ready_subtasks[0]
                context = {dep_id: results[dep_id] for dep_id in st.depends_on}
                results[st.id] = self._execute_subtask(st, context)
        
        return results
    
    def _execute_subtask(self, subtask: Subtask, context: Dict) -> Dict:
        """Execute a single subtask using the appropriate low-level agent."""
        self._emit("subtask_start", {
            "id": subtask.id,
            "instruction": subtask.instruction,
            "agent_type": subtask.agent_type
        })
        
        # Import low-level agent
        from legacy_agent_orchestration.orchestrator import AgentOrchestrator
        
        # Create context string from previous results
        context_str = ""
        if context:
            context_str = "\n\nContext from previous steps:\n"
            for dep_id, result in context.items():
                context_str += f"Step {dep_id}: {result.get('summary', 'completed')}\n"
        
        # Create low-level agent with event callback
        agent = AgentOrchestrator(model=self.model, event_callback=self.event_callback)
        
        # Execute subtask
        full_instruction = subtask.instruction + context_str
        result = agent.execute_task(full_instruction, max_steps=15)
        
        subtask.status = "success" if result.get("success") else "failed"
        subtask.result = result
        
        self._emit("subtask_complete", {
            "id": subtask.id,
            "success": result.get("success", False),
            "summary": result.get("summary", "")
        })
        
        return result
    
    def _aggregate_results(self, plan: Plan, results: Dict[int, Dict]) -> Dict:
        """Combine results from all subtasks into final result."""
        
        all_success = all(r.get("success", False) for r in results.values())
        all_screenshots = []
        all_actions = []
        summaries = []
        
        for st_id, result in sorted(results.items()):
            all_screenshots.extend(result.get("screenshots", []))
            all_actions.extend(result.get("actions", []))
            if result.get("summary"):
                summaries.append(f"Step {st_id}: {result['summary']}")
        
        return {
            "success": all_success,
            "summary": "\n".join(summaries) if summaries else "Task completed",
            "subtask_count": len(plan.subtasks),
            "completed_count": sum(1 for r in results.values() if r.get("success")),
            "screenshots": all_screenshots,
            "actions": all_actions,
            "subtask_results": results
        }
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM for planning (no tools)."""
        if self.model_config["provider"] == "openai":
            response = self.openai.chat.completions.create(
                model=self.model_config["id"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )
            return response.choices[0].message.content
        else:
            response = self.anthropic.messages.create(
                model=self.model_config["id"],
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Open Spotify and play a song"
    
    agent = HighLevelAgent(model="gpt-4o-mini")
    result = agent.execute_task(task)
    
    print("\n" + "="*60)
    print("FINAL RESULT")
    print("="*60)
    print(json.dumps(result, indent=2, default=str)[:2000])
