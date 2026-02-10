"""
Browser Tool - Selenium wrapper with ARIA snapshots.
Inspired by Moltbot's pw-role-snapshot.ts
Supports headless/headed mode via HEADLESS env var.
"""

import os
import time
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


# JavaScript for ARIA snapshot - mimics Moltbot's INTERACTIVE_ROLES filter
ARIA_SNAPSHOT_JS = """
function getAriaSnapshot() {
    const INTERACTIVE_ROLES = [
        'button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'option', 'tab', 'treeitem',
        'searchbox', 'spinbutton', 'switch', 'combobox', 'slider', 'input'
    ];
    
    const results = [];
    let refCounter = 1;
    
    function traverse(node, depth = 0) {
        if (!node || depth > 50) return;
        
        // Check if element is interactive
        const role = node.getAttribute('role') || node.tagName.toLowerCase();
        const isInteractive = INTERACTIVE_ROLES.includes(role) ||
            node.tagName === 'BUTTON' ||
            node.tagName === 'A' ||
            node.tagName === 'INPUT' ||
            node.tagName === 'TEXTAREA' ||
            node.tagName === 'SELECT';
        
        if (isInteractive && node.isVisible && node.isVisible()) {
            const text = node.textContent || 
                        node.getAttribute('aria-label') || 
                        node.getAttribute('placeholder') ||
                        node.getAttribute('value') ||
                        '';
            
            // Clean up text
            const cleanText = text.trim().substring(0, 100);
            
            if (cleanText || node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
                const ref = refCounter++;
                node.setAttribute('data-aria-ref', ref.toString());
                
                results.push({
                    ref: ref,
                    role: role,
                    name: cleanText,
                    enabled: !node.disabled,
                    checked: node.checked || false
                });
            }
        }
        
        // Traverse children
        for (const child of node.children) {
            traverse(child, depth + 1);
        }
    }
    
    traverse(document.body);
    return results;
}

// Polyfill for isVisible if not available
if (!Element.prototype.isVisible) {
    Element.prototype.isVisible = function() {
        const style = window.getComputedStyle(this);
        return style.display !== 'none' && 
               style.visibility !== 'hidden' && 
               style.opacity !== '0' &&
               this.offsetWidth > 0 &&
               this.offsetHeight > 0;
    };
}

return getAriaSnapshot();
"""


class BrowserTool:
    """Selenium-based browser tool with ARIA snapshots."""
    
    def __init__(self, headless: Optional[bool] = None):
        """
        Initialize browser tool.
        
        Args:
            headless: If None, reads from HEADLESS env var. 
                     If True/False, forces that mode.
        """
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = self._get_headless_mode(headless)
        self.snapshot_cache: Optional[List[Dict]] = None
        self.last_url: Optional[str] = None
    
    def _get_headless_mode(self, headless: Optional[bool]) -> bool:
        """Determine headless mode from env var or explicit setting."""
        if headless is not None:
            return headless
        
        env_headless = os.getenv('HEADLESS', '').lower()
        if env_headless in ('true', '1', 'yes', 'on'):
            return True
        elif env_headless in ('false', '0', 'no', 'off'):
            return False
        return True  # Default to headless
    
    def start(self) -> Dict[str, Any]:
        """Start the browser driver."""
        if not SELENIUM_AVAILABLE:
            return {"error": "Selenium not available. Install: pip install selenium webdriver-manager"}
        
        if self.driver:
            return {"status": "already_running"}
        
        try:
            options = Options()
            
            if self.headless:
                options.add_argument("--headless=new")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-logging")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            mode = "headless" if self.headless else "headed"
            return {"status": "started", "mode": mode}
        except Exception as e:
            return {"error": str(e)}
    
    def stop(self) -> Dict[str, Any]:
        """Stop the browser driver."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        return {"status": "stopped"}
    
    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        if not self.driver:
            result = self.start()
            if "error" in result:
                return result
        
        try:
            self.driver.get(url)
            self.last_url = url
            time.sleep(0.5)  # Brief wait for initial load
            return {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "mode": "headless" if self.headless else "headed"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def snapshot(self) -> Dict[str, Any]:
        """
        Get ARIA snapshot of interactive elements.
        Returns structured list of interactive elements with refs.
        """
        if not self.driver:
            return {"error": "No browser open. Use navigate() first."}
        
        try:
            elements = self.driver.execute_script(ARIA_SNAPSHOT_JS)
            self.snapshot_cache = elements
            
            # Format as readable text
            lines = [f"- {el['role']} \"{el['name']}\" [ref={el['ref']}]" 
                     for el in elements if el['name']]
            
            return {
                "elements": elements,
                "formatted": "\n".join(lines) if lines else "No interactive elements found",
                "count": len(elements),
                "url": self.driver.current_url,
                "title": self.driver.title
            }
        except Exception as e:
            return {"error": str(e)}
    
    def click_by_ref(self, ref: int) -> Dict[str, Any]:
        """Click element by ARIA reference ID."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            # Find element with matching ref attribute
            selector = f"[data-aria-ref='{ref}']"
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            
            # Scroll into view and click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.1)
            element.click()
            
            return {
                "success": True,
                "clicked_ref": ref,
                "url": self.driver.current_url,
                "title": self.driver.title
            }
        except Exception as e:
            return {"error": f"Failed to click ref={ref}: {str(e)}"}
    
    def click(self, target: str) -> Dict[str, Any]:
        """
        Click element by text, aria-label, or CSS selector.
        Tries multiple strategies.
        """
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            # Strategy 1: Try as CSS selector first
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, target)
                if element.is_displayed():
                    element.click()
                    return {"success": True, "method": "css_selector"}
            except:
                pass
            
            # Strategy 2: Comprehensive XPath search
            xpath = (
                f"//*[contains(text(), '{target}') or "
                f"contains(@aria-label, '{target}') or "
                f"contains(@placeholder, '{target}') or "
                f"contains(@title, '{target}') or "
                f"contains(@value, '{target}') or "
                f"@id='{target}' or "
                f"@name='{target}']"
            )
            
            elements = self.driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed():
                    el.click()
                    return {"success": True, "method": "xpath", "matched": target}
            
            return {"error": f"Element not found: '{target}'"}
        except Exception as e:
            return {"error": str(e)}
    
    def type(self, text: str, clear_first: bool = False) -> Dict[str, Any]:
        """Type text into focused element."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            active = self.driver.switch_to.active_element
            if clear_first:
                active.clear()
            active.send_keys(text)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}
    
    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a key (enter, tab, escape, etc)."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            key_map = {
                'enter': Keys.ENTER,
                'tab': Keys.TAB,
                'escape': Keys.ESCAPE,
                'backspace': Keys.BACKSPACE,
                'delete': Keys.DELETE,
                'arrow_up': Keys.ARROW_UP,
                'arrow_down': Keys.ARROW_DOWN,
                'arrow_left': Keys.ARROW_LEFT,
                'arrow_right': Keys.ARROW_RIGHT
            }
            
            active = self.driver.switch_to.active_element
            active.send_keys(key_map.get(key.lower(), key))
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"error": str(e)}
    
    def scroll(self, direction: str = "down", amount: int = 300) -> Dict[str, Any]:
        """Scroll the page."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            scroll_amount = -amount if direction == "up" else amount
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get basic page information."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            return {
                "url": self.driver.current_url,
                "title": self.driver.title
            }
        except Exception as e:
            return {"error": str(e)}
    
    def back(self) -> Dict[str, Any]:
        """Go back in browser history."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            self.driver.back()
            return {"success": True, "url": self.driver.current_url}
        except Exception as e:
            return {"error": str(e)}
    
    def forward(self) -> Dict[str, Any]:
        """Go forward in browser history."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            self.driver.forward()
            return {"success": True, "url": self.driver.current_url}
        except Exception as e:
            return {"error": str(e)}
    
    def switch_tab(self, index: int) -> Dict[str, Any]:
        """Switch to tab by index."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            handles = self.driver.window_handles
            if index < len(handles):
                self.driver.switch_to.window(handles[index])
                return {"success": True, "tab": index, "title": self.driver.title}
            else:
                return {"error": f"Tab index {index} out of range. Only {len(handles)} tabs open."}
        except Exception as e:
            return {"error": str(e)}
    
    def close_tab(self) -> Dict[str, Any]:
        """Close current tab."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            self.driver.close()
            if self.driver.window_handles:
                self.driver.switch_to.window(self.driver.window_handles[0])
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def wait_for_element(self, selector: str, timeout: int = 10) -> Dict[str, Any]:
        """Wait for element to be present."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return {"success": True, "found": selector}
        except Exception as e:
            return {"error": f"Timeout waiting for {selector}: {str(e)}"}
    
    def execute_script(self, script: str) -> Dict[str, Any]:
        """Execute arbitrary JavaScript."""
        if not self.driver:
            return {"error": "No browser open"}
        
        try:
            result = self.driver.execute_script(script)
            return {"success": True, "result": result}
        except Exception as e:
            return {"error": str(e)}
    
    def get_current_mode(self) -> str:
        """Get current browser mode (headless/headed)."""
        return "headless" if self.headless else "headed"


# Tool definitions for agent integration
BROWSER_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate browser to a URL. Auto-starts browser if not running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Get ARIA snapshot of interactive elements on the page. Returns clean list of buttons, links, inputs with [ref=N] IDs.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_ref",
            "description": "Click element by its ARIA reference ID (e.g., ref=5). Use after snapshot to reliably click elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Reference ID from snapshot"}
                },
                "required": ["ref"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click element by text content or CSS selector. Prefers snapshot+click_ref for reliability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Text content or CSS selector"}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into the focused element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "clear_first": {"type": "boolean", "default": False}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a key (enter, tab, escape, arrow_up, arrow_down, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                    "amount": {"type": "integer", "default": 300}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Navigate back in browser history.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_forward",
            "description": "Navigate forward in browser history.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_switch_tab",
            "description": "Switch to a browser tab by index (0-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"}
                },
                "required": ["index"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_tab",
            "description": "Close the current browser tab.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_stop",
            "description": "Stop and close the browser.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


# Convenience function for creating a browser tool instance
def create_browser_tool(headless: Optional[bool] = None) -> BrowserTool:
    """Factory function to create a BrowserTool instance."""
    return BrowserTool(headless=headless)
