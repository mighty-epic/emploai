"""
pywinauto-based observation for desktop applications.
Extracts UI Automation elements, their properties, and positions.
"""

from typing import List, Dict, Any, Optional
import sys

# pywinauto is Windows-only
if sys.platform == "win32":
    from pywinauto import Desktop, Application
    from pywinauto.controls.uiawrapper import UIAWrapper
    PYWINAUTO_AVAILABLE = True
else:
    PYWINAUTO_AVAILABLE = False


class PywinautoObserver:
    """Observes desktop application state via pywinauto/UI Automation."""
    
    def __init__(self):
        if not PYWINAUTO_AVAILABLE:
            raise RuntimeError("pywinauto is only available on Windows")
        self.desktop = Desktop(backend="uia")
        self._target_app: Optional[Application] = None
    
    def attach_to_window(self, title: str = None, process: int = None) -> bool:
        """
        Attach to a specific window by title or process ID.
        Returns True if successful.
        """
        try:
            if process:
                self._target_app = Application(backend="uia").connect(process=process)
            elif title:
                self._target_app = Application(backend="uia").connect(title_re=f".*{title}.*")
            return True
        except Exception as e:
            print(f"Failed to attach: {e}")
            return False
    
    def get_active_window_info(self) -> Dict[str, Any]:
        """Get information about the currently active window."""
        try:
            windows = self.desktop.windows()
            for win in windows:
                if win.is_active():
                    rect = win.rectangle()
                    return {
                        "title": win.window_text(),
                        "class_name": win.class_name(),
                        "process_id": win.process_id(),
                        "bbox": {
                            "x": rect.left,
                            "y": rect.top,
                            "width": rect.width(),
                            "height": rect.height()
                        },
                        "is_active": True
                    }
        except Exception:
            pass
        return {}
    
    def get_visible_elements(self, window=None) -> List[Dict[str, Any]]:
        """
        Extract all visible UI elements from target window.
        Returns normalized element descriptors.
        """
        elements = []
        
        try:
            if window is None and self._target_app:
                window = self._target_app.top_window()
            elif window is None:
                # Use active window
                for win in self.desktop.windows():
                    if win.is_active():
                        window = win
                        break
            
            if window is None:
                return elements
            
            # Recursively walk the control tree
            self._walk_controls(window, elements, depth=0, max_depth=10)
            
        except Exception as e:
            print(f"Error getting elements: {e}")
        
        return elements
    
    def _walk_controls(self, control, elements: List, depth: int, max_depth: int):
        """Recursively walk control tree and extract element info."""
        if depth > max_depth:
            return
        
        try:
            # Skip invisible controls
            if not control.is_visible():
                return
            
            rect = control.rectangle()
            
            # Skip zero-size elements
            if rect.width() <= 0 or rect.height() <= 0:
                return
            
            control_type = control.element_info.control_type or "Unknown"
            
            # Only include interactive/meaningful controls
            interactive_types = [
                "Button", "Edit", "ComboBox", "CheckBox", "RadioButton",
                "ListItem", "MenuItem", "TabItem", "Hyperlink", "Text",
                "List", "Tree", "TreeItem", "DataGrid", "DataItem"
            ]
            
            if control_type in interactive_types:
                elements.append(self._control_to_descriptor(control))
            
            # Recurse into children
            for child in control.children():
                self._walk_controls(child, elements, depth + 1, max_depth)
                
        except Exception:
            pass
    
    def _control_to_descriptor(self, control) -> Dict[str, Any]:
        """Convert a pywinauto control to a normalized descriptor."""
        try:
            rect = control.rectangle()
            control_type = control.element_info.control_type or "Unknown"
            
            return {
                "control_type": control_type,
                "role": self._map_control_type_to_role(control_type),
                "text": control.window_text()[:100] if control.window_text() else "",
                "name": control.element_info.name or None,
                "automation_id": control.element_info.automation_id or None,
                "class_name": control.element_info.class_name or None,
                "bbox": {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.width(),
                    "height": rect.height()
                },
                "is_enabled": control.is_enabled(),
                "is_focused": control.has_focus() if hasattr(control, 'has_focus') else None,
                "confidence": 1.0  # Structured observation has full confidence
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _map_control_type_to_role(self, control_type: str) -> str:
        """Map Windows control types to semantic roles."""
        role_map = {
            "Button": "button",
            "Edit": "textbox",
            "ComboBox": "dropdown",
            "CheckBox": "checkbox",
            "RadioButton": "radio",
            "ListItem": "listitem",
            "MenuItem": "menuitem",
            "TabItem": "tab",
            "Hyperlink": "link",
            "Text": "label",
            "List": "list",
            "Tree": "tree",
            "TreeItem": "treeitem",
            "DataGrid": "grid",
            "DataItem": "gridcell",
        }
        return role_map.get(control_type, "generic")
    
    def get_focused_element(self) -> Optional[Dict[str, Any]]:
        """Get the currently focused element."""
        try:
            if self._target_app:
                window = self._target_app.top_window()
            else:
                window = None
                for win in self.desktop.windows():
                    if win.is_active():
                        window = win
                        break
            
            if window:
                focused = window.get_focus()
                if focused:
                    return self._control_to_descriptor(focused)
        except Exception:
            pass
        
        return None
    
    def get_observation_snapshot(self) -> Dict[str, Any]:
        """
        Get complete observation snapshot.
        This is the main output of the observation layer.
        """
        active_window = self.get_active_window_info()
        
        return {
            "source": "pywinauto",
            "active_window": active_window,
            "elements": self.get_visible_elements(),
            "focused_element": self.get_focused_element(),
            "metadata": {
                "platform": "windows"
            }
        }
