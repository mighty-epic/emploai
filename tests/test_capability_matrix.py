"""
LLM Capability Test Matrix
Tests LLM decision-making across two dimensions:
- Step Diff: Number/complexity of steps within one context
- Adapt Degree: Number of different contexts/pages to handle

Example:
  Step Diff 1, Adapt 1 = Click one button on one page
  Step Diff 3, Adapt 1 = Fill 3 fields and submit on one page
  Step Diff 1, Adapt 3 = Simple action on 3 different pages
  Step Diff 3, Adapt 3 = Complex actions across 3 page transitions
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from openai import OpenAI


@dataclass
class TestScenario:
    name: str
    step_diff: int      # Steps within one context
    adapt_degree: int   # Number of context changes
    description: str
    contexts: List[Dict]  # Simulated page states
    expected_actions: List[str]


# ============================================================
# TOOLS
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click an element by ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string"}
                },
                "required": ["element_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into focused field",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate to a URL or page",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal task complete",
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


# ============================================================
# TEST SCENARIOS
# ============================================================

SCENARIOS = {
    # STEP DIFF 1, ADAPT 1 - Simplest possible
    "sd1_ad1": TestScenario(
        name="Simple Click",
        step_diff=1,
        adapt_degree=1,
        description="Click the login button on a login page",
        contexts=[
            {
                "page": "login",
                "url": "https://example.com/login",
                "elements": [
                    {"id": "username", "type": "input", "text": "", "placeholder": "Username"},
                    {"id": "password", "type": "input", "text": "", "placeholder": "Password"},
                    {"id": "login_btn", "type": "button", "text": "Login"}
                ]
            }
        ],
        expected_actions=["click:login_btn"]
    ),
    
    # STEP DIFF 3, ADAPT 1 - Multiple steps, single page
    "sd3_ad1": TestScenario(
        name="Fill Form",
        step_diff=3,
        adapt_degree=1,
        description="Enter username 'testuser', password 'pass123', and click login",
        contexts=[
            {
                "page": "login",
                "url": "https://example.com/login",
                "elements": [
                    {"id": "username", "type": "input", "text": "", "placeholder": "Username"},
                    {"id": "password", "type": "input", "text": "", "placeholder": "Password"},
                    {"id": "login_btn", "type": "button", "text": "Login"},
                    {"id": "forgot_link", "type": "link", "text": "Forgot Password?"}
                ]
            }
        ],
        expected_actions=["click:username", "type:testuser", "click:password", "type:pass123", "click:login_btn"]
    ),
    
    # STEP DIFF 1, ADAPT 3 - Simple action across 3 pages
    "sd1_ad3": TestScenario(
        name="Multi-Page Navigation",
        step_diff=1,
        adapt_degree=3,
        description="Click 'Next' on each of 3 pages to complete wizard",
        contexts=[
            {
                "page": "wizard_step1",
                "url": "https://example.com/setup/step1",
                "elements": [
                    {"id": "title", "type": "text", "text": "Step 1: Welcome"},
                    {"id": "next_btn", "type": "button", "text": "Next"},
                    {"id": "cancel_btn", "type": "button", "text": "Cancel"}
                ]
            },
            {
                "page": "wizard_step2",
                "url": "https://example.com/setup/step2",
                "elements": [
                    {"id": "title", "type": "text", "text": "Step 2: Configure"},
                    {"id": "back_btn", "type": "button", "text": "Back"},
                    {"id": "next_btn", "type": "button", "text": "Next"}
                ]
            },
            {
                "page": "wizard_step3",
                "url": "https://example.com/setup/step3",
                "elements": [
                    {"id": "title", "type": "text", "text": "Step 3: Finish"},
                    {"id": "back_btn", "type": "button", "text": "Back"},
                    {"id": "finish_btn", "type": "button", "text": "Finish"}
                ]
            }
        ],
        expected_actions=["click:next_btn", "click:next_btn", "click:finish_btn"]
    ),
    
    # STEP DIFF 3, ADAPT 3 - Complex multi-step across 3 pages
    "sd3_ad3": TestScenario(
        name="Full Registration Flow",
        step_diff=3,
        adapt_degree=3,
        description="Complete registration: 1) Fill login form, 2) Fill profile, 3) Confirm and submit",
        contexts=[
            {
                "page": "registration_credentials",
                "url": "https://example.com/register/step1",
                "elements": [
                    {"id": "email", "type": "input", "text": "", "placeholder": "Email"},
                    {"id": "password", "type": "input", "text": "", "placeholder": "Password"},
                    {"id": "confirm_password", "type": "input", "text": "", "placeholder": "Confirm Password"},
                    {"id": "continue_btn", "type": "button", "text": "Continue"}
                ]
            },
            {
                "page": "registration_profile",
                "url": "https://example.com/register/step2",
                "elements": [
                    {"id": "first_name", "type": "input", "text": "", "placeholder": "First Name"},
                    {"id": "last_name", "type": "input", "text": "", "placeholder": "Last Name"},
                    {"id": "phone", "type": "input", "text": "", "placeholder": "Phone"},
                    {"id": "continue_btn", "type": "button", "text": "Continue"},
                    {"id": "back_btn", "type": "button", "text": "Back"}
                ]
            },
            {
                "page": "registration_confirm",
                "url": "https://example.com/register/step3",
                "elements": [
                    {"id": "summary", "type": "text", "text": "Review your information"},
                    {"id": "terms_checkbox", "type": "checkbox", "text": "I agree to terms"},
                    {"id": "submit_btn", "type": "button", "text": "Create Account"},
                    {"id": "back_btn", "type": "button", "text": "Back"}
                ]
            }
        ],
        expected_actions=["fill credentials", "continue", "fill profile", "continue", "accept terms", "submit"]
    ),
    
    # STEP DIFF 5, ADAPT 1 - Many steps, single complex form
    "sd5_ad1": TestScenario(
        name="Complex Form",
        step_diff=5,
        adapt_degree=1,
        description="Fill out a job application: name, email, phone, upload resume link, select position, add cover letter, submit",
        contexts=[
            {
                "page": "job_application",
                "url": "https://example.com/careers/apply",
                "elements": [
                    {"id": "full_name", "type": "input", "placeholder": "Full Name"},
                    {"id": "email", "type": "input", "placeholder": "Email"},
                    {"id": "phone", "type": "input", "placeholder": "Phone"},
                    {"id": "resume_url", "type": "input", "placeholder": "Link to Resume"},
                    {"id": "position_dropdown", "type": "select", "text": "Select Position"},
                    {"id": "cover_letter", "type": "textarea", "placeholder": "Cover Letter"},
                    {"id": "submit_btn", "type": "button", "text": "Submit Application"}
                ]
            }
        ],
        expected_actions=["fill all fields", "submit"]
    ),
    
    # STEP DIFF 2, ADAPT 5 - Navigate through 5 different page types
    "sd2_ad5": TestScenario(
        name="E-commerce Flow",
        step_diff=2,
        adapt_degree=5,
        description="Browse product, add to cart, proceed to checkout, enter shipping, confirm order",
        contexts=[
            {
                "page": "product_listing",
                "url": "https://shop.com/products",
                "elements": [
                    {"id": "product_1", "type": "card", "text": "Laptop - $999"},
                    {"id": "product_2", "type": "card", "text": "Phone - $599"},
                    {"id": "view_btn_1", "type": "button", "text": "View Details"}
                ]
            },
            {
                "page": "product_detail",
                "url": "https://shop.com/products/laptop",
                "elements": [
                    {"id": "title", "type": "text", "text": "Laptop - $999"},
                    {"id": "add_to_cart", "type": "button", "text": "Add to Cart"},
                    {"id": "quantity", "type": "input", "text": "1"}
                ]
            },
            {
                "page": "cart",
                "url": "https://shop.com/cart",
                "elements": [
                    {"id": "item_1", "type": "text", "text": "Laptop x1 - $999"},
                    {"id": "checkout_btn", "type": "button", "text": "Proceed to Checkout"},
                    {"id": "continue_shopping", "type": "button", "text": "Continue Shopping"}
                ]
            },
            {
                "page": "shipping",
                "url": "https://shop.com/checkout/shipping",
                "elements": [
                    {"id": "address", "type": "input", "placeholder": "Address"},
                    {"id": "city", "type": "input", "placeholder": "City"},
                    {"id": "continue_btn", "type": "button", "text": "Continue to Payment"}
                ]
            },
            {
                "page": "confirmation",
                "url": "https://shop.com/checkout/confirm",
                "elements": [
                    {"id": "order_summary", "type": "text", "text": "Order Total: $999"},
                    {"id": "place_order", "type": "button", "text": "Place Order"},
                    {"id": "edit_btn", "type": "button", "text": "Edit Order"}
                ]
            }
        ],
        expected_actions=["view product", "add to cart", "checkout", "enter shipping", "place order"]
    )
}


# ============================================================
# TEST RUNNER
# ============================================================

class CapabilityTester:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = OpenAI()
    
    def run_scenario(self, scenario: TestScenario, verbose: bool = True) -> Dict:
        """Run a single test scenario."""
        if verbose:
            print(f"\n{'='*60}")
            print(f"SCENARIO: {scenario.name}")
            print(f"Step Diff: {scenario.step_diff} | Adapt Degree: {scenario.adapt_degree}")
            print(f"{'='*60}")
            print(f"Task: {scenario.description}")
        
        all_tool_calls = []
        total_tokens = 0
        context_switches = 0
        
        system_prompt = f"""You are an AI agent controlling a web browser.
Complete the task by using the provided tools.
Think step by step. When moving between pages, the screen state will update.
Task: {scenario.description}"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        start_time = time.time()
        
        # Process each context (page)
        for ctx_idx, context in enumerate(scenario.contexts):
            if verbose:
                print(f"\n--- Context {ctx_idx + 1}/{len(scenario.contexts)}: {context['page']} ---")
            
            # Send current context
            messages.append({
                "role": "user",
                "content": f"Current page: {context['url']}\nElements:\n{json.dumps(context['elements'], indent=2)}"
            })
            
            # Get LLM response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            total_tokens += response.usage.total_tokens if response.usage else 0
            
            if verbose and msg.content:
                print(f"Thinking: {msg.content[:100]}...")
            
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    tool_call = {"name": tc.function.name, "args": args, "context": context["page"]}
                    all_tool_calls.append(tool_call)
                    
                    if verbose:
                        print(f"  -> {tc.function.name}({json.dumps(args)})")
                    
                    # Simulate response
                    if tc.function.name == "done":
                        break
                    
                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"success": True})
                    })
                
                # Check if done
                if any(tc["name"] == "done" for tc in all_tool_calls):
                    break
            
            context_switches += 1
        
        duration = time.time() - start_time
        
        result = {
            "scenario": scenario.name,
            "step_diff": scenario.step_diff,
            "adapt_degree": scenario.adapt_degree,
            "tool_calls": len(all_tool_calls),
            "context_switches": context_switches,
            "duration_seconds": round(duration, 2),
            "tokens_used": total_tokens,
            "actions": all_tool_calls
        }
        
        if verbose:
            print(f"\n[RESULT]")
            print(f"  Tool calls: {result['tool_calls']}")
            print(f"  Context switches: {result['context_switches']}")
            print(f"  Duration: {result['duration_seconds']}s")
            print(f"  Tokens: {result['tokens_used']}")
        
        return result
    
    def run_matrix(self) -> Dict[str, Dict]:
        """Run all scenarios and create capability matrix."""
        print("\n" + "=" * 70)
        print("LLM CAPABILITY TEST MATRIX")
        print("=" * 70)
        
        results = {}
        for key, scenario in SCENARIOS.items():
            results[key] = self.run_scenario(scenario)
        
        # Summary matrix
        print("\n" + "=" * 70)
        print("CAPABILITY MATRIX SUMMARY")
        print("=" * 70)
        print(f"\n{'Scenario':<20} {'Step':<6} {'Adapt':<6} {'Calls':<8} {'Time':<8} {'Tokens'}")
        print("-" * 60)
        
        for key, result in results.items():
            print(f"{result['scenario']:<20} {result['step_diff']:<6} {result['adapt_degree']:<6} "
                  f"{result['tool_calls']:<8} {result['duration_seconds']:<8} {result['tokens_used']}")
        
        return results


def run_single(scenario_key: str):
    """Run a single scenario by key."""
    if scenario_key not in SCENARIOS:
        print(f"Unknown scenario: {scenario_key}")
        print(f"Available: {list(SCENARIOS.keys())}")
        return
    
    tester = CapabilityTester()
    return tester.run_scenario(SCENARIOS[scenario_key])


def run_matrix():
    """Run full test matrix."""
    tester = CapabilityTester()
    return tester.run_matrix()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        run_single(sys.argv[1])
    else:
        run_matrix()
