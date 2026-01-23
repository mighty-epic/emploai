"""
MOCK TOOL EXECUTOR
Simulates tool execution and returns mock responses for testing.
"""

from typing import Dict, Any, List, Optional
import json
import time


class MockToolExecutor:
    """Executes tools in a simulated environment."""
    
    def __init__(self):
        self.execution_log = []
        self.state = {
            "url": "https://example.com/login",
            "elements": [
                {"id": "input_username", "role": "textbox", "text": "", "label": "Username", 
                 "bbox": {"x": 100, "y": 100, "width": 200, "height": 30}},
                {"id": "input_password", "role": "textbox", "text": "", "label": "Password",
                 "bbox": {"x": 100, "y": 150, "width": 200, "height": 30}},
                {"id": "btn_login", "role": "button", "text": "Login", "label": "",
                 "bbox": {"x": 100, "y": 200, "width": 100, "height": 35}},
            ],
            "focused_element": None,
            "typed_text": {},
        }
    
    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        self.execution_log.append({
            "tool": tool_name,
            "arguments": arguments,
            "timestamp": time.time()
        })
        
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler:
            return handler(arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    # Observation tools
    def _handle_get_screen_state(self, args: Dict) -> Dict:
        return {
            "success": True,
            "url": self.state["url"],
            "elements": self.state["elements"],
            "focused_element": self.state["focused_element"],
            "element_count": len(self.state["elements"])
        }
    
    def _handle_find_element(self, args: Dict) -> Dict:
        text = args.get("text", "").lower()
        role = args.get("role", "").lower()
        label = args.get("label", "").lower()
        
        for el in self.state["elements"]:
            if text and text in el.get("text", "").lower():
                return {"success": True, "element": el}
            if text and text in el.get("label", "").lower():
                return {"success": True, "element": el}
            if role and role == el.get("role", "").lower():
                if not text and not label:
                    return {"success": True, "element": el}
        
        return {"success": False, "error": "Element not found"}
    
    def _handle_get_focused_element(self, args: Dict) -> Dict:
        if self.state["focused_element"]:
            return {"success": True, "element": self.state["focused_element"]}
        return {"success": False, "element": None}
    
    def _handle_capture_screenshot(self, args: Dict) -> Dict:
        return {"success": True, "path": "/tmp/screenshot.png"}
    
    # Action tools
    def _handle_click_element(self, args: Dict) -> Dict:
        element_id = args.get("element_id")
        text = args.get("text", "").lower()
        
        target = None
        for el in self.state["elements"]:
            if element_id and el["id"] == element_id:
                target = el
                break
            if text and text in el.get("text", "").lower():
                target = el
                break
        
        if target:
            self.state["focused_element"] = target
            
            # Simulate login success
            if target["id"] == "btn_login":
                self.state["url"] = "https://example.com/dashboard"
                self.state["elements"] = [
                    {"id": "welcome", "role": "text", "text": "Welcome!", "label": ""},
                    {"id": "btn_logout", "role": "button", "text": "Logout", "label": ""},
                ]
            
            return {"success": True, "clicked": target["id"]}
        
        return {"success": False, "error": "Element not found"}
    
    def _handle_type_text(self, args: Dict) -> Dict:
        text = args.get("text", "")
        element_id = args.get("element_id")
        
        if element_id:
            self.state["typed_text"][element_id] = text
        elif self.state["focused_element"]:
            self.state["typed_text"][self.state["focused_element"]["id"]] = text
        else:
            return {"success": False, "error": "No element focused"}
        
        return {"success": True, "typed": text}
    
    def _handle_press_key(self, args: Dict) -> Dict:
        key = args.get("key", "")
        return {"success": True, "key_pressed": key}
    
    def _handle_scroll(self, args: Dict) -> Dict:
        direction = args.get("direction", "down")
        return {"success": True, "scrolled": direction}
    
    def _handle_navigate(self, args: Dict) -> Dict:
        url = args.get("url", "")
        self.state["url"] = url
        return {"success": True, "navigated_to": url}
    
    # System tools
    def _handle_wait(self, args: Dict) -> Dict:
        return {"success": True, "waited": args.get("seconds", 1)}
    
    def _handle_verify_state(self, args: Dict) -> Dict:
        results = {}
        
        if "url_contains" in args:
            results["url_match"] = args["url_contains"] in self.state["url"]
        
        if "element_exists" in args:
            found = any(el["id"] == args["element_exists"] for el in self.state["elements"])
            results["element_exists"] = found
        
        if "text_visible" in args:
            text = args["text_visible"].lower()
            found = any(text in el.get("text", "").lower() for el in self.state["elements"])
            results["text_visible"] = found
        
        success = all(results.values()) if results else True
        return {"success": success, "results": results}
    
    def _handle_report_completion(self, args: Dict) -> Dict:
        return {"success": True, "status": args.get("status"), "message": args.get("message")}
    
    def _handle_request_human_help(self, args: Dict) -> Dict:
        return {"success": True, "human_notified": True, "reason": args.get("reason")}
    
    # Orchestrator tools
    def _handle_decompose_task(self, args: Dict) -> Dict:
        task = args.get("task", "")
        # Simulate decomposition
        steps = ["Step 1", "Step 2", "Step 3"]
        return {"success": True, "steps": steps}
    
    def _handle_issue_micro_step(self, args: Dict) -> Dict:
        return {"success": True, "step_issued": args.get("step_description")}
    
    def _handle_adapt_plan(self, args: Dict) -> Dict:
        return {"success": True, "reason": args.get("reason"), "adapted": True}
    
    def get_log(self) -> List[Dict]:
        """Get the execution log."""
        return self.execution_log
    
    def reset(self):
        """Reset to initial state."""
        self.__init__()
