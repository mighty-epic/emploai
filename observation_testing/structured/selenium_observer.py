"""
Selenium-based observation for browser environments.
Extracts DOM elements, their properties, and positions.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List, Dict, Any, Optional
import json


class SeleniumObserver:
    """Observes browser state via Selenium WebDriver."""
    
    def __init__(self, driver: Optional[webdriver.Chrome] = None):
        self.driver = driver
    
    def attach(self, driver: webdriver.Chrome) -> None:
        """Attach to an existing WebDriver instance."""
        self.driver = driver
    
    def get_current_url(self) -> str:
        """Get the current page URL."""
        if not self.driver:
            raise RuntimeError("No WebDriver attached")
        return self.driver.current_url
    
    def get_page_title(self) -> str:
        """Get the current page title."""
        if not self.driver:
            raise RuntimeError("No WebDriver attached")
        return self.driver.title
    
    def get_visible_elements(self) -> List[Dict[str, Any]]:
        """
        Extract all visible, potentially interactive elements.
        Returns normalized element descriptors.
        """
        if not self.driver:
            raise RuntimeError("No WebDriver attached")
        
        # CSS selector for interactive elements
        interactive_selectors = [
            "a", "button", "input", "select", "textarea",
            "[role='button']", "[role='link']", "[role='textbox']",
            "[onclick]", "[tabindex]"
        ]
        
        elements = []
        seen_ids = set()
        
        for selector in interactive_selectors:
            try:
                found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in found:
                    if not el.is_displayed():
                        continue
                    
                    el_id = id(el)
                    if el_id in seen_ids:
                        continue
                    seen_ids.add(el_id)
                    
                    elements.append(self._element_to_descriptor(el))
            except Exception:
                continue
        
        return elements
    
    def _element_to_descriptor(self, el: WebElement) -> Dict[str, Any]:
        """Convert a WebElement to a normalized descriptor."""
        rect = el.rect
        
        return {
            "tag": el.tag_name,
            "text": el.text[:100] if el.text else "",
            "role": el.get_attribute("role") or self._infer_role(el),
            "id": el.get_attribute("id") or None,
            "name": el.get_attribute("name") or None,
            "type": el.get_attribute("type") or None,
            "placeholder": el.get_attribute("placeholder") or None,
            "aria_label": el.get_attribute("aria-label") or None,
            "href": el.get_attribute("href") if el.tag_name == "a" else None,
            "bbox": {
                "x": rect["x"],
                "y": rect["y"],
                "width": rect["width"],
                "height": rect["height"]
            },
            "is_enabled": el.is_enabled(),
            "is_selected": el.is_selected() if el.tag_name in ["input", "option"] else None,
            "confidence": 1.0  # Structured observation has full confidence
        }
    
    def _infer_role(self, el: WebElement) -> str:
        """Infer semantic role from element properties."""
        tag = el.tag_name.lower()
        el_type = (el.get_attribute("type") or "").lower()
        
        role_map = {
            "a": "link",
            "button": "button",
            "select": "dropdown",
            "textarea": "textbox",
            "img": "image",
            "h1": "heading",
            "h2": "heading",
            "h3": "heading",
        }
        
        if tag == "input":
            input_roles = {
                "text": "textbox",
                "password": "textbox",
                "email": "textbox",
                "search": "searchbox",
                "submit": "button",
                "button": "button",
                "checkbox": "checkbox",
                "radio": "radio",
            }
            return input_roles.get(el_type, "input")
        
        return role_map.get(tag, "generic")
    
    def get_focused_element(self) -> Optional[Dict[str, Any]]:
        """Get the currently focused element."""
        if not self.driver:
            raise RuntimeError("No WebDriver attached")
        
        try:
            active = self.driver.switch_to.active_element
            if active and active.tag_name != "body":
                return self._element_to_descriptor(active)
        except Exception:
            pass
        
        return None
    
    def capture_screenshot(self) -> bytes:
        """Capture current page screenshot as PNG bytes."""
        if not self.driver:
            raise RuntimeError("No WebDriver attached")
        return self.driver.get_screenshot_as_png()
    
    def get_observation_snapshot(self) -> Dict[str, Any]:
        """
        Get complete observation snapshot.
        This is the main output of the observation layer.
        """
        return {
            "source": "selenium",
            "url": self.get_current_url(),
            "title": self.get_page_title(),
            "elements": self.get_visible_elements(),
            "focused_element": self.get_focused_element(),
            "metadata": {
                "window_size": self.driver.get_window_size() if self.driver else None
            }
        }
