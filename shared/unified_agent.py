"""
Unified Multi-Model Agent - Works with ANY model provider
Combines CLI tools + Browser tools + Desktop tools into one agent
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass

from cli.agent_tools.adapters import normalize_provider, to_anthropic_format, to_google_format, to_openai_format
from shared.openai_api import create_openai_completion

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    name: str
    provider: str  # anthropic, openai, openai-codex, google, xai, deepseek, openrouter, nvidia
    model_id: str
    supports_thinking: bool = False
    supports_tools: bool = True
    max_context: int = 128000
    api_type: str = "chat"
    

class UnifiedToolRegistry:
    """
    Registry of ALL tools that work across all model providers.
    Automatically adapts tool definitions to each provider's format.
    """
    
    def __init__(self):
        self.tools: Dict[str, Dict] = {}
        self._init_unified_tools()
    
    def _init_unified_tools(self):
        """Initialize unified tool definitions."""
        # File Operations
        self.tools['read_file'] = {
            'name': 'read_file',
            'description': 'Read contents of a file',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Path to file'},
                    'start_line': {'type': 'integer', 'description': 'Optional start line'},
                    'end_line': {'type': 'integer', 'description': 'Optional end line'}
                },
                'required': ['path']
            }
        }
        
        self.tools['write_file'] = {
            'name': 'write_file',
            'description': 'Write content to a file',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Path to file'},
                    'content': {'type': 'string', 'description': 'Content to write'}
                },
                'required': ['path', 'content']
            }
        }
        
        self.tools['edit_file'] = {
            'name': 'edit_file',
            'description': 'Edit a file by replacing text',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Path to file'},
                    'old_text': {'type': 'string', 'description': 'Text to replace'},
                    'new_text': {'type': 'string', 'description': 'Replacement text'}
                },
                'required': ['path', 'old_text', 'new_text']
            }
        }
        
        self.tools['list_files'] = {
            'name': 'list_files',
            'description': 'List files in a directory',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Directory path'},
                    'recursive': {'type': 'boolean', 'description': 'Recursive search'}
                },
                'required': ['path']
            }
        }
        
        # Terminal
        self.tools['execute_command'] = {
            'name': 'execute_command',
            'description': 'Execute a shell command',
            'parameters': {
                'type': 'object',
                'properties': {
                    'command': {'type': 'string', 'description': 'Command to execute'},
                    'cwd': {'type': 'string', 'description': 'Working directory'}
                },
                'required': ['command']
            }
        }
        
        # Web
        self.tools['web_search'] = {
            'name': 'web_search',
            'description': 'Search the web',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Search query'},
                    'num_results': {'type': 'integer', 'description': 'Number of results'}
                },
                'required': ['query']
            }
        }
        
        self.tools['fetch_url'] = {
            'name': 'fetch_url',
            'description': 'Fetch content from a URL',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'description': 'URL to fetch'}
                },
                'required': ['url']
            }
        }
        
        # Browser Automation
        self.tools['browser_navigate'] = {
            'name': 'browser_navigate',
            'description': 'Navigate browser to URL',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'description': 'URL to navigate to'}
                },
                'required': ['url']
            }
        }
        
        # DISABLED: browser_click removed in favor of browser_click_ref (more reliable ARIA-based clicking)
        # self.tools['browser_click'] = {
        #     'name': 'browser_click',
        #     'description': 'Click an element on the page',
        #     'parameters': {
        #         'type': 'object',
        #         'properties': {
        #             'selector': {'type': 'string', 'description': 'CSS selector or text'},
        #             'role': {'type': 'string', 'description': 'ARIA role (button, link, etc)'}
        #         },
        #         'required': ['selector']
        #     }
        # }
        
        self.tools['browser_type'] = {
            'name': 'browser_type',
            'description': 'Type text into the focused input, or into a specific snapshot ref when provided. Prefer ref-based typing for reliable long tasks.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string', 'description': 'Text to type'},
                    'ref': {'type': 'integer', 'description': 'Optional ARIA ref from browser_snapshot'},
                    'clear_first': {'type': 'boolean', 'description': 'Clear the field before typing'}
                },
                'required': ['text']
            }
        }

        self.tools['browser_clear_ref'] = {
            'name': 'browser_clear_ref',
            'description': 'Clear a specific input field by its ARIA ref before typing new content',
            'parameters': {
                'type': 'object',
                'properties': {
                    'ref': {'type': 'integer', 'description': 'Input ref from browser_snapshot'}
                },
                'required': ['ref']
            }
        }

        self.tools['browser_select_option_ref'] = {
            'name': 'browser_select_option_ref',
            'description': 'Select an option on a native <select> element by ref using visible text, value, or index',
            'parameters': {
                'type': 'object',
                'properties': {
                    'ref': {'type': 'integer', 'description': 'Select ref from browser_snapshot'},
                    'text': {'type': 'string', 'description': 'Visible option text to select'},
                    'value': {'type': 'string', 'description': 'Option value to select'},
                    'index': {'type': 'integer', 'description': 'Zero-based option index to select'}
                },
                'required': ['ref']
            }
        }
        
        self.tools['browser_screenshot'] = {
            'name': 'browser_screenshot',
            'description': 'Take a screenshot of the current browser page. When you need visual interpretation, ask a precise question about what should be visible.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'full_page': {'type': 'boolean', 'description': 'Capture full page'},
                    'question': {'type': 'string', 'description': 'Optional precise visual question about the current browser page, file, dialog, or error state.'}
                }
            }
        }
        
        self.tools['browser_snapshot'] = {
            'name': 'browser_snapshot',
            'description': 'Get ARIA snapshot of interactive elements on the page (refs)',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['browser_wait_for'] = {
            'name': 'browser_wait_for',
            'description': 'Wait for a URL, title, or page text condition on the current task tab instead of using blind delays',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url_contains': {'type': 'string'},
                    'title_contains': {'type': 'string'},
                    'text_contains': {'type': 'string'},
                    'timeout_seconds': {'type': 'number', 'description': 'Maximum wait time in seconds'}
                }
            }
        }

        self.tools['browser_click_ref'] = {
            'name': 'browser_click_ref',
            'description': 'Click a browser element by its reference ID (ref=N)',
            'parameters': {
                'type': 'object',
                'properties': {
                    'ref': {'type': 'integer'}
                },
                'required': ['ref']
            }
        }

        self.tools['browser_back'] = {
            'name': 'browser_back',
            'description': 'Go back in browser history',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['browser_forward'] = {
            'name': 'browser_forward',
            'description': 'Go forward in browser history',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['browser_switch_tab'] = {
            'name': 'browser_switch_tab',
            'description': 'Switch to a browser tab by index',
            'parameters': {
                'type': 'object',
                'properties': {
                    'index': {'type': 'integer'}
                },
                'required': ['index']
            }
        }

        self.tools['browser_close_tab'] = {
            'name': 'browser_close_tab',
            'description': 'Close current browser tab',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['browser_stop'] = {
            'name': 'browser_stop',
            'description': 'Close the browser completely',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['browser_extension_toggle'] = {
            'name': 'browser_extension_toggle',
            'description': 'Toggle between headless Selenium and the Native Extension Bridge',
            'parameters': {
                'type': 'object',
                'properties': {
                    'enable': {
                        'type': 'boolean',
                        'description': 'True to use Native extension, False for Selenium'
                    }
                },
                'required': ['enable']
            }
        }
        
        # Memory
        self.tools['search_memory'] = {
            'name': 'search_memory',
            'description': 'Search long-term memory',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Search query'},
                    'max_results': {'type': 'integer', 'description': 'Max results'}
                },
                'required': ['query']
            }
        }
        
        self.tools['update_memory'] = {
            'name': 'update_memory',
            'description': 'Update long-term memory',
            'parameters': {
                'type': 'object',
                'properties': {
                    'section': {'type': 'string', 'description': 'Memory section'},
                    'content': {'type': 'string', 'description': 'Content to add'}
                },
                'required': ['section', 'content']
            }
        }
        
        self.tools['change_directory'] = {
            'name': 'change_directory',
            'description': 'Change the current working directory for all subsequent operations',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Path to switch to (relative or absolute)'}
                },
                'required': ['path']
            }
        }

        # vision & basic desktop
        self.tools['describe_screen'] = {
            'name': 'describe_screen',
            'description': 'Take a screenshot and get an AI vision description of the current screen. Ask a precise question about what you need verified whenever possible.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string', 'description': 'Optional precise question about the screen, such as whether an app opened, an error dialog appeared, or which control should be used next.'}
                }
            }
        }

        self.tools['ocr_screen'] = {
            'name': 'ocr_screen',
            'description': 'Extract text and coordinates from the screen using OCR',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['observe_desktop'] = {
            'name': 'observe_desktop',
            'description': 'List open windows and their titles',
            'parameters': {'type': 'object', 'properties': {}}
        }

        # input automation
        self.tools['click'] = {
            'name': 'click',
            'description': 'Primary click at coordinates (x, y)',
            'parameters': {
                'type': 'object',
                'properties': {
                    'x': {'type': 'integer'},
                    'y': {'type': 'integer'}
                },
                'required': ['x', 'y']
            }
        }

        self.tools['right_click'] = {
            'name': 'right_click',
            'description': 'Right click at coordinates (x, y)',
            'parameters': {
                'type': 'object',
                'properties': {
                    'x': {'type': 'integer'},
                    'y': {'type': 'integer'}
                },
                'required': ['x', 'y']
            }
        }

        self.tools['double_click'] = {
            'name': 'double_click',
            'description': 'Double click at coordinates (x, y)',
            'parameters': {
                'type': 'object',
                'properties': {
                    'x': {'type': 'integer'},
                    'y': {'type': 'integer'}
                },
                'required': ['x', 'y']
            }
        }

        self.tools['type_text'] = {
            'name': 'type_text',
            'description': 'Type text into focused element',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string', 'description': 'Text to type'}
                },
                'required': ['text']
            }
        }

        self.tools['press_key'] = {
            'name': 'press_key',
            'description': 'Press a specific keyboard key',
            'parameters': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'description': 'Key name (e.g. enter, tab)'}
                },
                'required': ['key']
            }
        }

        self.tools['hotkey'] = {
            'name': 'hotkey',
            'description': 'Press a key combination',
            'parameters': {
                'type': 'object',
                'properties': {
                    'keys': {'type': 'string', 'description': 'Keys combined with +, e.g. ctrl+v'}
                },
                'required': ['keys']
            }
        }

        self.tools['scroll'] = {
            'name': 'scroll',
            'description': 'Scroll the screen',
            'parameters': {
                'type': 'object',
                'properties': {
                    'direction': {'type': 'string', 'enum': ['up', 'down']},
                    'amount': {'type': 'integer', 'default': 3}
                },
                'required': ['direction']
            }
        }

        # window management
        self.tools['open_app'] = {
            'name': 'open_app',
            'description': 'Open a desktop application by name',
            'parameters': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'description': 'App name or command'}
                },
                'required': ['name']
            }
        }

        self.tools['focus_window'] = {
            'name': 'focus_window',
            'description': 'Focus a window by title',
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string'}
                },
                'required': ['title']
            }
        }

        # clipboard
        self.tools['get_clipboard'] = {
            'name': 'get_clipboard',
            'description': 'Read current clipboard content',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['set_clipboard'] = {
            'name': 'set_clipboard',
            'description': 'Set current clipboard content',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'}
                },
                'required': ['text']
            }
        }
        
        self.tools['spawn_sub_agent'] = {
            'name': 'spawn_sub_agent',
            'description': 'Spawn a sub-agent to perform a task in the background',
            'parameters': {
                'type': 'object',
                'properties': {
                    'prompt': {'type': 'string', 'description': 'The task for the sub-agent'},
                    'headless': {'type': 'boolean', 'default': True}
                },
                'required': ['prompt']
            }
        }

        self.tools['list_sub_agents'] = {
            'name': 'list_sub_agents',
            'description': 'List all running background sub-agents',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['schedule_job'] = {
            'name': 'schedule_job',
            'description': 'Schedule a recurring task (e.g. "every 5 minutes")',
            'parameters': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'description': 'Name of the job'},
                    'prompt': {'type': 'string', 'description': 'Task to perform'},
                    'schedule': {'type': 'string', 'description': 'Schedule string, e.g. "every 1 hour"'}
                },
                'required': ['name', 'prompt', 'schedule']
            }
        }

        self.tools['list_scheduled_jobs'] = {
            'name': 'list_scheduled_jobs',
            'description': 'View all scheduled recurring tasks',
            'parameters': {'type': 'object', 'properties': {}}
        }

        self.tools['get_scheduled_job'] = {
            'name': 'get_scheduled_job',
            'description': 'View details for one scheduled recurring task',
            'parameters': {
                'type': 'object',
                'properties': {
                    'job_id': {'type': 'string'}
                },
                'required': ['job_id']
            }
        }

        self.tools['update_scheduled_job'] = {
            'name': 'update_scheduled_job',
            'description': 'Update a scheduled recurring task',
            'parameters': {
                'type': 'object',
                'properties': {
                    'job_id': {'type': 'string'},
                    'name': {'type': 'string'},
                    'prompt': {'type': 'string'},
                    'schedule': {'type': 'string'},
                    'enabled': {'type': 'boolean'}
                },
                'required': ['job_id']
            }
        }

        self.tools['run_scheduled_job_now'] = {
            'name': 'run_scheduled_job_now',
            'description': 'Queue a scheduled recurring task to run on the next scheduler check',
            'parameters': {
                'type': 'object',
                'properties': {
                    'job_id': {'type': 'string'}
                },
                'required': ['job_id']
            }
        }

        self.tools['remove_scheduled_job'] = {
            'name': 'remove_scheduled_job',
            'description': 'Delete a scheduled recurring task',
            'parameters': {
                'type': 'object',
                'properties': {
                    'job_id': {'type': 'string'}
                },
                'required': ['job_id']
            }
        }
    
    def get_tools_for_provider(self, provider: str) -> List[Dict]:
        """Get tool definitions formatted for specific provider."""
        provider = normalize_provider(provider)
        tools = list(self.tools.values())
        if provider == 'anthropic':
            return to_anthropic_format(tools)
        if provider == 'google':
            return to_google_format(tools)
        return to_openai_format(tools)
    
    def _format_for_anthropic(self) -> List[Dict]:
        """Format tools for Anthropic API."""
        return [
            {
                'name': tool['name'],
                'description': tool['description'],
                'input_schema': tool['parameters']
            }
            for tool in self.tools.values()
        ]
    
    def _format_for_openai(self) -> List[Dict]:
        """Format tools for OpenAI API (also works for XAI, DeepSeek, OpenRouter, NVIDIA)."""
        return [
            {
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool['description'],
                    'parameters': tool['parameters']
                }
            }
            for tool in self.tools.values()
        ]
    
    def _format_for_google(self) -> List[Dict]:
        """Format tools for Google Gemini API."""
        from google.generativeai.types import FunctionDeclaration, Tool
        
        functions = []
        for tool in self.tools.values():
            functions.append(
                FunctionDeclaration(
                    name=tool['name'],
                    description=tool['description'],
                    parameters=tool['parameters']
                )
            )
        
        return [Tool(function_declarations=functions)]


class UnifiedAgent:
    """
    Unified agent that works with ANY model provider.
    Handles tool execution and response parsing automatically.
    """
    
    def __init__(
        self,
        model_config: ModelConfig,
        client: Any,
        tool_executor: Callable[[str, Dict], Any],
        workspace: Path,
        logger_func: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize unified agent.
        
        Args:
            model_config: Configuration for the model
            client: LLM client (OpenAI, Anthropic, or Gemini client)
            tool_executor: Function to execute tools
            workspace: Workspace path
            logger_func: Optional logging callback
        """
        self.model_config = model_config
        self.client = client
        self.tool_executor = tool_executor
        self.workspace = workspace
        self.logger = logger_func or print
        
        self.tool_registry = UnifiedToolRegistry()
        self.conversation_history = []
        self.current_task = None
        self._should_stop = False
        self._should_pause = False
    
    def run(self, prompt: str, max_turns: int = 100) -> str:
        """
        Run the agent with unified tool loop.
        Works across all model providers.
        """
        self.current_task = prompt
        self._should_stop = False
        self._should_pause = False
        
        # Add user message
        self.conversation_history.append({
            'role': 'user',
            'content': prompt
        })
        
        # Get tools for this provider
        tools = self.tool_registry.get_tools_for_provider(self.model_config.provider)
        
        # Main loop
        for turn in range(max_turns):
            if self._should_stop:
                self.logger("[STOPPED] Agent stopped by user")
                break
            
            if self._should_pause:
                self.logger("[PAUSED] Agent paused - use continue to resume")
                return "Task paused. Use /continue to resume."
            
            self.logger(f"[Turn {turn + 1}/{max_turns}]")
            
            try:
                # Call model with provider-specific logic
                if self.model_config.provider == 'anthropic':
                    response = self._call_anthropic(tools)
                elif self.model_config.provider in ['openai', 'openai-codex', 'xai', 'deepseek', 'openrouter', 'nvidia']:
                    response = self._call_openai_compatible(tools)
                elif self.model_config.provider == 'google':
                    response = self._call_google(tools)
                else:
                    raise ValueError(f"Unsupported provider: {self.model_config.provider}")
                
                # Check if we're done
                if self._is_task_complete(response):
                    final_message = self._extract_final_message(response)
                    self.logger(f"[COMPLETE] {final_message}")
                    return final_message
                
                # Execute any tool calls
                if not self._execute_tool_calls(response):
                    # No tools called, we're done
                    final_message = self._extract_final_message(response)
                    return final_message
                
            except Exception as e:
                self.logger(f"[ERROR] {str(e)}")
                return f"Error: {str(e)}"
        
        return f"Max turns ({max_turns}) reached. Task may be incomplete."
    
    def _call_anthropic(self, tools: List[Dict]) -> Any:
        """Call Anthropic API with correct message formatting."""
        system_parts = []
        anthropic_messages = []
        
        for m in self.conversation_history:
            role = m.get("role")
            content = m.get("content")
            
            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue
            
            if role == "assistant" and m.get("tool_calls"):
                content_list = []
                if content:
                    content_list.append({"type": "text", "text": content})
                for tc in m["tool_calls"]:
                    try:
                        args_obj = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    except:
                        args_obj = {}
                    content_list.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args_obj
                    })
                anthropic_messages.append({"role": "assistant", "content": content_list})
            elif role == "tool":
                # Convert tool result to user message block
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id"),
                        "content": str(content)
                    }]
                })
            else:
                anthropic_messages.append({"role": role, "content": content})

        response = self.client.messages.create(
            model=self.model_config.model_id,
            max_tokens=4096,
            system="\n\n".join(system_parts) if system_parts else None,
            tools=tools if tools else None,
            messages=anthropic_messages
        )
        
        # Add to history (store in generic format)
        tool_calls = []
        assistant_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                assistant_text += block.text
            if hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {"name": block.name, "arguments": json.dumps(block.input)}
                })

        self.conversation_history.append({
            'role': 'assistant',
            'content': assistant_text or None,
            'tool_calls': tool_calls if tool_calls else None
        })
        
        return response
    
    def _call_openai_compatible(self, tools: List[Dict]) -> Any:
        """Call OpenAI-compatible API (OpenAI, XAI, DeepSeek, OpenRouter)."""
        response = create_openai_completion(
            self.client,
            model_name=getattr(self.model_config, "name", None),
            model_id=self.model_config.model_id,
            messages=self.conversation_history,
            tools=tools if tools else None,
            tool_choice='auto' if tools else None,
            explicit_api_type=getattr(self.model_config, "api_type", None),
        )
        
        message = response.choices[0].message
        
        # Add to history
        self.conversation_history.append({
            'role': 'assistant',
            'content': message.content,
            'tool_calls': message.tool_calls if hasattr(message, 'tool_calls') else None
        })
        
        return response
    
    def _call_google(self, tools: List[Any]) -> Any:
        """Call Google Gemini API."""
        import google.generativeai as genai
        
        model = genai.GenerativeModel(
            model_name=self.model_config.model_id,
            tools=tools if tools else None
        )
        
        # Convert conversation history to Gemini format
        history = self._convert_history_for_gemini()
        
        chat = model.start_chat(history=history[:-1] if history else None)
        response = chat.send_message(history[-1]['parts'] if history else "")
        
        # Add to history
        self.conversation_history.append({
            'role': 'assistant',
            'content': response.text if hasattr(response, 'text') else str(response)
        })
        
        return response
    
    def _convert_history_for_gemini(self) -> List[Dict]:
        """Convert conversation history to Gemini format."""
        gemini_history = []
        for msg in self.conversation_history:
            role = 'user' if msg['role'] == 'user' else 'model'
            content = msg['content']
            if isinstance(content, str):
                gemini_history.append({
                    'role': role,
                    'parts': [content]
                })
        return gemini_history
    
    def _is_task_complete(self, response: Any) -> bool:
        """Check if the task is complete (no more tool calls)."""
        if self.model_config.provider == 'anthropic':
            return response.stop_reason == 'end_turn'
        elif self.model_config.provider in ['openai', 'openai-codex', 'xai', 'deepseek', 'openrouter', 'nvidia']:
            message = response.choices[0].message
            return not hasattr(message, 'tool_calls') or message.tool_calls is None
        elif self.model_config.provider == 'google':
            return not hasattr(response, 'function_calls')
        return True
    
    def _extract_final_message(self, response: Any) -> str:
        """Extract final text message from response."""
        if self.model_config.provider == 'anthropic':
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
            return str(response.content)
        elif self.model_config.provider in ['openai', 'openai-codex', 'xai', 'deepseek', 'openrouter', 'nvidia']:
            return response.choices[0].message.content or "Task completed"
        elif self.model_config.provider == 'google':
            return response.text if hasattr(response, 'text') else str(response)
        return "Task completed"
    
    def _execute_tool_calls(self, response: Any) -> bool:
        """Execute tool calls from response. Returns True if tools were called."""
        tool_calls = self._extract_tool_calls(response)
        
        if not tool_calls:
            return False
        
        # Execute each tool call
        tool_results = []
        interrupted = False
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            
            # Check for interruption before EACH tool
            if self._should_stop or self._should_pause:
                interrupted = True
                
            if interrupted:
                # Still must add results for model history to prevent API protocol errors
                tool_results.append({
                    'tool_call_id': tool_call.get('id'),
                    'name': tool_name,
                    'result': "Error: Operation cancelled by user interrupt."
                })
                continue

            self.logger(f"[TOOL] {tool_name}({tool_args})")
            
            try:
                result = self.tool_executor(tool_name, tool_args)
                
                # Check if tool itself returned an interruption status
                if isinstance(result, dict) and result.get("interrupted"):
                    interrupted = True
                
                tool_results.append({
                    'tool_call_id': tool_call.get('id'),
                    'name': tool_name,
                    'result': result
                })
                self.logger(f"[RESULT] {str(result)[:200]}")
            except Exception as e:
                tool_results.append({
                    'tool_call_id': tool_call.get('id'),
                    'name': tool_name,
                    'result': f"Error: {str(e)}"
                })
                self.logger(f"[ERROR] {str(e)}")
        
        # Add tool results to history
        self._add_tool_results_to_history(tool_results)
        
        return True
    
    def _extract_tool_calls(self, response: Any) -> List[Dict]:
        """Extract tool calls from response (provider-agnostic)."""
        if self.model_config.provider == 'anthropic':
            tool_calls = []
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_calls.append({
                        'id': block.id,
                        'name': block.name,
                        'args': block.input
                    })
            return tool_calls
        
        elif self.model_config.provider in ['openai', 'openai-codex', 'xai', 'deepseek', 'openrouter', 'nvidia']:
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                return [
                    {
                        'id': tc.id,
                        'name': tc.function.name,
                        'args': json.loads(tc.function.arguments)
                    }
                    for tc in message.tool_calls
                ]
        
        elif self.model_config.provider == 'google':
            if hasattr(response, 'function_calls'):
                return [
                    {
                        'name': fc.name,
                        'args': dict(fc.args)
                    }
                    for fc in response.function_calls
                ]
        
        return []
    
    def _add_tool_results_to_history(self, tool_results: List[Dict]):
        """Add tool results to conversation history (provider-specific format)."""
        if self.model_config.provider == 'anthropic':
            content = []
            for result in tool_results:
                content.append({
                    'type': 'tool_result',
                    'tool_use_id': result['tool_call_id'],
                    'content': str(result['result'])
                })
            self.conversation_history.append({
                'role': 'user',
                'content': content
            })
        
        elif self.model_config.provider in ['openai', 'openai-codex', 'xai', 'deepseek', 'openrouter', 'nvidia']:
            for result in tool_results:
                self.conversation_history.append({
                    'role': 'tool',
                    'tool_call_id': result['tool_call_id'],
                    'name': result['name'],
                    'content': str(result['result'])
                })
        
        elif self.model_config.provider == 'google':
            # Gemini handles this differently - results go in next user message
            pass
    
    def stop(self):
        """Stop the agent."""
        self._should_stop = True
    
    def pause(self):
        """Pause the agent."""
        self._should_pause = True
    
    def continue_task(self, max_turns: int = 100) -> str:
        """Continue a paused task."""
        self._should_pause = False
        return self.run(self.current_task, max_turns)


# Helper to create unified agent
def create_unified_agent(
    model_name: str,
    client: Any,
    tool_executor: Callable,
    workspace: Path,
    logger_func: Optional[Callable] = None,
    system_prompt: Optional[str] = None
) -> Any:
    """
    Create a specialized unified agent for the chosen provider.
    
    Args:
        model_name: Model identifier
        client: LLM client instance
        tool_executor: Tool execution function
        workspace: Workspace path
        logger_func: Optional logger
    
    Returns:
        Configured Provider-specific Agent (OpenAIsAgent, AnthropicAgent, or GoogleAgent)
    """
    # Map model names to configs
    model_configs = {
        "gpt-5": ModelConfig(name="gpt-5", provider="openai", model_id="gpt-5", max_context=400000),
        "gpt-5.1": ModelConfig(name="gpt-5.1", provider="openai", model_id="gpt-5.1-2025-11-13", max_context=400000),
        "gpt-5.2": ModelConfig(name="gpt-5.2", provider="openai", model_id="gpt-5.2-2025-12-11", max_context=400000),
        "gpt-5.5": ModelConfig(name="gpt-5.5", provider="openai", model_id="gpt-5.5", max_context=1000000, api_type="responses"),
        "gpt-5.4": ModelConfig(name="gpt-5.4", provider="openai", model_id="gpt-5.4-2026-03-05", max_context=1050000, api_type="responses"),
        "gpt-5.4-mini": ModelConfig(name="gpt-5.4-mini", provider="openai", model_id="gpt-5.4-mini", max_context=400000, api_type="responses"),
        "chatgpt/gpt-5.5": ModelConfig(name="chatgpt/gpt-5.5", provider="openai-codex", model_id="gpt-5.5", max_context=1000000, api_type="responses"),
        "chatgpt/gpt-5.4": ModelConfig(name="chatgpt/gpt-5.4", provider="openai-codex", model_id="gpt-5.4", max_context=1050000, api_type="responses"),
        "chatgpt/gpt-5.4-mini": ModelConfig(name="chatgpt/gpt-5.4-mini", provider="openai-codex", model_id="gpt-5.4-mini", max_context=400000, api_type="responses"),
        "gpt-5.1-codex-max": ModelConfig(name="gpt-5.1-codex-max", provider="openai-codex", model_id="gpt-5.1-codex-max", max_context=400000, api_type="responses"),
        "gpt-5.2-codex": ModelConfig(name="gpt-5.2-codex", provider="openai-codex", model_id="gpt-5.2-codex", max_context=400000, api_type="responses"),
        "gpt-4.1": ModelConfig(name="gpt-4.1", provider="openai", model_id="gpt-4.1", max_context=1047576),
        "gpt-4o": ModelConfig(name="gpt-4o", provider="openai", model_id="gpt-4o", max_context=128000),
        "gpt-4o-mini": ModelConfig(name="gpt-4o-mini", provider="openai", model_id="gpt-4o-mini", max_context=128000),
        "claude-sonnet-4.5": ModelConfig(name="claude-sonnet-4.5", provider="anthropic", model_id="claude-sonnet-4-5-20250929", max_context=200000),
        "claude-opus-4.5": ModelConfig(name="claude-opus-4.5", provider="anthropic", model_id="claude-opus-4-5-20250929", max_context=200000),
        "claude-sonnet-4.6": ModelConfig(name="claude-sonnet-4.6", provider="anthropic", model_id="claude-sonnet-4-6", max_context=1000000),
        "claude-opus-4.6": ModelConfig(name="claude-opus-4.6", provider="anthropic", model_id="claude-opus-4-6", max_context=1000000),
        "claude-opus-4.7": ModelConfig(name="claude-opus-4.7", provider="anthropic", model_id="claude-opus-4-7", max_context=1000000),
        "claude-haiku-4.5": ModelConfig(name="claude-haiku-4.5", provider="anthropic", model_id="claude-haiku-4-5-20251001", max_context=200000),
        "claude-sonnet-4": ModelConfig(name="claude-sonnet-4", provider="anthropic", model_id="claude-sonnet-4-20250514", max_context=200000),
        "claude-opus-4": ModelConfig(name="claude-opus-4", provider="anthropic", model_id="claude-opus-4-20250514", max_context=200000),
        "claude-haiku-4": ModelConfig(name="claude-haiku-4", provider="anthropic", model_id="claude-haiku-4-5-20251001", max_context=200000),
        "gemini-3.5-flash": ModelConfig(name="gemini-3.5-flash", provider="google", model_id="gemini-3.5-flash", max_context=1048576),
        "gemini-3.1-pro-preview": ModelConfig(name="gemini-3.1-pro-preview", provider="google", model_id="gemini-3.1-pro-preview", max_context=1048576),
        "gemini-3.1-pro-preview-customtools": ModelConfig(name="gemini-3.1-pro-preview-customtools", provider="google", model_id="gemini-3.1-pro-preview-customtools", max_context=1048576),
        "gemini-3-flash-preview": ModelConfig(name="gemini-3-flash-preview", provider="google", model_id="gemini-3-flash-preview", max_context=1048576),
        "gemini-3.1-flash-lite": ModelConfig(name="gemini-3.1-flash-lite", provider="google", model_id="gemini-3.1-flash-lite", max_context=1048576),
        "gemini-2.5-pro": ModelConfig(name="gemini-2.5-pro", provider="google", model_id="gemini-2.5-pro", max_context=1048576),
        "gemini-2.5-flash": ModelConfig(name="gemini-2.5-flash", provider="google", model_id="gemini-2.5-flash", max_context=1048576),
        "gemini-2.5-flash-lite": ModelConfig(name="gemini-2.5-flash-lite", provider="google", model_id="gemini-2.5-flash-lite", max_context=1048576),
        "grok-4.1-fast-reasoning": ModelConfig(name="grok-4.1-fast-reasoning", provider="xai", model_id="grok-4-1-fast-reasoning", max_context=2000000),
        "grok-4.1-fast-non-reasoning": ModelConfig(name="grok-4.1-fast-non-reasoning", provider="xai", model_id="grok-4-1-fast-non-reasoning", max_context=2000000),
        "grok-code-fast-1": ModelConfig(name="grok-code-fast-1", provider="xai", model_id="grok-code-fast-1", max_context=256000),
        "grok-4-fast-reasoning": ModelConfig(name="grok-4-fast-reasoning", provider="xai", model_id="grok-4-fast-reasoning", max_context=2000000),
        "grok-4-fast-non-reasoning": ModelConfig(name="grok-4-fast-non-reasoning", provider="xai", model_id="grok-4-fast-non-reasoning", max_context=2000000),
        "grok-4-0709": ModelConfig(name="grok-4-0709", provider="xai", model_id="grok-4-0709", max_context=256000),
        "grok-3-mini": ModelConfig(name="grok-3-mini", provider="xai", model_id="grok-3-mini", max_context=131072),
        "grok-3": ModelConfig(name="grok-3", provider="xai", model_id="grok-3", max_context=131072),
        "grok-2-vision-1212": ModelConfig(name="grok-2-vision-1212", provider="xai", model_id="grok-2-vision-1212", max_context=32768),
        "grok-2": ModelConfig(name="grok-2", provider="xai", model_id="grok-2-latest", max_context=128000),
        "grok-beta": ModelConfig(name="grok-beta", provider="xai", model_id="grok-beta", max_context=128000),
        "deepseek-chat": ModelConfig(name="deepseek-chat", provider="deepseek", model_id="deepseek-chat", max_context=128000),
        "deepseek-reasoner": ModelConfig(name="deepseek-reasoner", provider="deepseek", model_id="deepseek-reasoner", max_context=128000),
        "orb-gpt-4o": ModelConfig(name="orb-gpt-4o", provider="openai", model_id="openai/gpt-4o", max_context=128000),
        "orb-claude-3.5-sonnet": ModelConfig(name="orb-claude-3.5-sonnet", provider="openai", model_id="anthropic/claude-3.5-sonnet", max_context=200000),
    }
    
    config = model_configs.get(model_name)
    if not config:
        registry_config = None
        try:
            from cli.tui_constants import MODEL_CONFIGS

            registry_config = MODEL_CONFIGS.get(model_name)
        except Exception:
            registry_config = None

        if registry_config:
            config = ModelConfig(
                name=model_name,
                provider=str(registry_config.get("provider", "openai")),
                model_id=str(registry_config.get("id", model_name)),
                supports_thinking=bool(registry_config.get("reasoning", False)),
                max_context=int(registry_config.get("context", 128000) or 128000),
                api_type=str(registry_config.get("api", "chat") or "chat"),
            )
        else:
            config = ModelConfig(
                name=model_name,
                provider='openai',
                model_id=model_name,
                max_context=128000
            )
    
    provider = config.provider
    
    if provider == 'anthropic':
        from .agents.anthropic_agent import AnthropicAgent
        return AnthropicAgent(config, client, tool_executor, workspace, logger_func, system_prompt)
    elif provider == 'google':
        from .agents.google_agent import GoogleAgent
        return GoogleAgent(config, client, tool_executor, workspace, logger_func, system_prompt)
    else:
        from .agents.openai_agent import OpenAIsAgent
        return OpenAIsAgent(config, client, tool_executor, workspace, logger_func, system_prompt)
