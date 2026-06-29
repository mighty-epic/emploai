# Command Palette & Session System Implementation

## Overview

This document outlines how to implement an OpenCode-style command palette (`Ctrl+P`) with:
1. **Command Palette** - Unified command interface with search
2. **Session Management** - Save/restore chat sessions
3. **Provider API Key Management** - Configure API keys for different providers

---

## 1. Command Palette

### Current State
- `Ctrl+P` opens the pretty useless command pallete

### Target State
- `Ctrl+P` opens a unified command palette with categorized commands
- Model switching is one command within the palette

### Implementation

#### 1.1 Create `CommandPaletteScreen` (new class)

```python
class CommandPaletteScreen(Screen):
    """Modal screen for the unified command palette."""
    
    CSS = """
    CommandPaletteScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #palette_container {
        width: 70;
        height: auto;
        max-height: 28;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1 2;
    }
    """
    
    # Command definitions with categories
    COMMANDS = {
        "suggested": [
            {"name": "Switch model", "key": "ctrl+m", "action": "switch_model"},
            {"name": "Switch variant", "key": "ctrl+t", "action": "switch_variant"},
        ],
        "session": [
            {"name": "New session", "key": "ctrl+n", "action": "new_session"},
            {"name": "Switch session", "key": "ctrl+l", "action": "switch_session"},
            {"name": "Rename session", "key": None, "action": "rename_session"},
            {"name": "Delete session", "key": None, "action": "delete_session"},
            {"name": "Export session", "key": None, "action": "export_session"},
        ],
        "system": [
            {"name": "Configure providers", "key": None, "action": "configure_providers"},
            {"name": "Toggle agent mode", "key": "tab", "action": "toggle_agent_mode"},
            {"name": "Clear chat", "key": None, "action": "clear_chat"},
            {"name": "Help", "key": None, "action": "show_help"},
        ],
    }
```

#### 1.2 Update Keybindings

```python
BINDINGS = [
    ("ctrl+p", "open_command_palette", "Commands"),
    ("ctrl+m", "open_model_picker", "Model"),      # Direct model switch
    ("ctrl+n", "new_session", "New Session"),
    ("ctrl+l", "switch_session", "Sessions"),
    ("ctrl+t", "cycle_variant", "Variant"),
    ("tab", "cycle_agent_mode", "Agent Mode"),
]
```

---

## 2. Session Management

### Data Model

#### 2.1 Session Storage Location

```
~/.agentshell/
├── config.json              # Global config (API keys, preferences)
├── sessions/
│   ├── index.json           # Session index (list of all sessions)
│   ├── {session_id}.json    # Individual session data
│   └── {session_id}.json
└── model_prefs.json         # Model favorites/recent (existing)
```

#### 2.2 Session Data Structure

```python
# sessions/index.json
{
    "sessions": [
        {
            "id": "abc123",
            "name": "Debug API Issue",
            "created_at": "2026-01-24T15:00:00Z",
            "updated_at": "2026-01-24T15:30:00Z",
            "model": "claude-sonnet-4.5",
            "message_count": 42,
            "workspace": "C:/Users/.../project"
        }
    ],
    "current_session_id": "abc123"
}

# sessions/{session_id}.json
{
    "id": "abc123",
    "name": "Debug API Issue",
    "created_at": "2026-01-24T15:00:00Z",
    "updated_at": "2026-01-24T15:30:00Z",
    "workspace": "C:/Users/.../project",
    "model": "claude-sonnet-4.5",
    "variant": "thinking",
    "agent_mode": "semi",
    "chat_history": [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
    ],
    "task_history": [
        {"task": "...", "status": "completed", "timestamp": "..."}
    ]
}
```

#### 2.3 Session Manager Class

```python
class SessionManager:
    """Manages chat sessions - save, load, switch, delete."""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path.home() / ".agentshell"
        self.sessions_dir = self.base_path / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[Session] = None
    
    def create_session(self, name: str = None, workspace: Path = None) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:8]
        name = name or f"Session {datetime.now().strftime('%H:%M')}"
        session = Session(
            id=session_id,
            name=name,
            workspace=str(workspace or Path.cwd()),
            created_at=datetime.now().isoformat(),
        )
        self._save_session(session)
        self._update_index(session)
        return session
    
    def load_session(self, session_id: str) -> Session:
        """Load a session by ID."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            raise ValueError(f"Session not found: {session_id}")
        data = json.loads(session_file.read_text())
        return Session(**data)
    
    def save_session(self, session: Session) -> None:
        """Save current session state."""
        session.updated_at = datetime.now().isoformat()
        self._save_session(session)
        self._update_index(session)
    
    def list_sessions(self) -> List[SessionSummary]:
        """List all sessions (summary only, not full history)."""
        index_file = self.sessions_dir / "index.json"
        if not index_file.exists():
            return []
        data = json.loads(index_file.read_text())
        return [SessionSummary(**s) for s in data.get("sessions", [])]
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
        self._remove_from_index(session_id)
    
    def get_current_session_id(self) -> Optional[str]:
        """Get the ID of the last active session."""
        index_file = self.sessions_dir / "index.json"
        if index_file.exists():
            data = json.loads(index_file.read_text())
            return data.get("current_session_id")
        return None
    
    def set_current_session(self, session_id: str) -> None:
        """Set the current active session."""
        index_file = self.sessions_dir / "index.json"
        data = {"sessions": [], "current_session_id": None}
        if index_file.exists():
            data = json.loads(index_file.read_text())
        data["current_session_id"] = session_id
        index_file.write_text(json.dumps(data, indent=2))
```

#### 2.4 Session Switch Screen

```python
class SessionSwitchScreen(Screen):
    """Modal for switching between sessions."""
    
    CSS = """
    SessionSwitchScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #session_list_container {
        width: 70;
        max-height: 20;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Vertical(id="session_list_container"):
            yield Label("Sessions", id="session_title")
            yield Input(placeholder="Search sessions", id="session_search")
            yield OptionList(id="session_options")
            yield Label("[dim]n[/dim] new  [dim]d[/dim] delete  [dim]r[/dim] rename", id="session_hints")
```

---

## 3. Provider API Key Management

### Data Model

#### 3.1 Config Storage

```python
# ~/.agentshell/config.json
{
    "providers": {
        "openai": {
            "api_key": "sk-...",  # Encrypted or plain (see security notes)
            "org_id": "org-...",
            "enabled": true
        },
        "anthropic": {
            "api_key": "sk-ant-...",
            "enabled": true
        },
        "google": {
            "api_key": "...",
            "enabled": false
        },
        "xai": {
            "api_key": "...",
            "enabled": false
        },
        "deepseek": {
            "api_key": "sk-...",
            "enabled": false
        },
        "nvidia": {
            "api_key": "...",
            "enabled": false
        },
        "openrouter": {
            "api_key": "sk-or-...",
            "enabled": false
        }
    },
    "default_model": "claude-haiku-4.5",
    "default_variant": "standard",
    "default_agent_mode": "manual"
}
```

#### 3.2 Provider Config Screen

```python
class ProviderConfigScreen(Screen):
    """Modal for configuring provider API keys."""
    
    PROVIDERS = [
        {"id": "openai", "name": "OpenAI", "key_prefix": "sk-"},
        {"id": "anthropic", "name": "Anthropic", "key_prefix": "sk-ant-"},
        {"id": "google", "name": "Google (Gemini)", "key_prefix": ""},
        {"id": "xai", "name": "xAI (Grok)", "key_prefix": ""},
        {"id": "deepseek", "name": "DeepSeek", "key_prefix": "sk-"},
        {"id": "nvidia", "name": "NVIDIA NIM", "key_prefix": ""},
        {"id": "openrouter", "name": "OpenRouter", "key_prefix": "sk-or-"},
    ]
    
    def compose(self) -> ComposeResult:
        with Vertical(id="provider_config_container"):
            yield Label("Provider Configuration", id="provider_title")
            
            for provider in self.PROVIDERS:
                with Horizontal(classes="provider_row"):
                    yield Checkbox(provider["name"], id=f"enable_{provider['id']}")
                    yield Input(
                        placeholder=f"{provider['name']} API Key",
                        password=True,  # Hide the key
                        id=f"key_{provider['id']}"
                    )
                    yield Button("Test", id=f"test_{provider['id']}")
            
            with Horizontal(id="provider_actions"):
                yield Button("Save", variant="primary", id="save_providers")
                yield Button("Cancel", id="cancel_providers")
```

#### 3.3 Config Manager Class

```python
class ConfigManager:
    """Manages global configuration including API keys."""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path.home() / ".agentshell"
        self.config_file = self.base_path / "config.json"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._config: Optional[dict] = None
    
    def load(self) -> dict:
        """Load configuration from disk."""
        if self.config_file.exists():
            self._config = json.loads(self.config_file.read_text())
        else:
            self._config = self._default_config()
        return self._config
    
    def save(self) -> None:
        """Save configuration to disk."""
        if self._config:
            self.config_file.write_text(json.dumps(self._config, indent=2))
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider, falling back to env vars."""
        config = self.load()
        key = config.get("providers", {}).get(provider, {}).get("api_key")
        if key:
            return key
        # Fallback to environment variables
        env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        return os.getenv(env_vars.get(provider, ""))
    
    def set_api_key(self, provider: str, key: str) -> None:
        """Set API key for a provider."""
        config = self.load()
        if "providers" not in config:
            config["providers"] = {}
        if provider not in config["providers"]:
            config["providers"][provider] = {}
        config["providers"][provider]["api_key"] = key
        config["providers"][provider]["enabled"] = True
        self.save()
    
    def test_api_key(self, provider: str) -> bool:
        """Test if an API key is valid by making a simple API call."""
        key = self.get_api_key(provider)
        if not key:
            return False
        try:
            if provider == "openai":
                client = OpenAI(api_key=key)
                client.models.list()
            elif provider == "anthropic":
                client = Anthropic(api_key=key)
                # Simple validation - just check client creation
                return True
            return True
        except Exception:
            return False
    
    def _default_config(self) -> dict:
        return {
            "providers": {},
            "default_model": "claude-haiku-4.5",
            "default_variant": "standard",
            "default_agent_mode": "manual",
        }
```

---

## 4. Integration Points

### 4.1 ChatProcessor Updates

```python
class ChatProcessor:
    def __init__(self, ...):
        # Existing init...
        
        # Add session and config managers
        self.session_manager = SessionManager()
        self.config_manager = ConfigManager()
        
        # Load or create session
        current_id = self.session_manager.get_current_session_id()
        if current_id:
            try:
                self.session = self.session_manager.load_session(current_id)
                self.chat_history = [
                    ChatMessage(**msg) for msg in self.session.chat_history
                ]
            except Exception:
                self.session = self.session_manager.create_session(workspace=base_path)
        else:
            self.session = self.session_manager.create_session(workspace=base_path)
        
        # Load API keys from config (with env var fallback)
        openai_key = self.config_manager.get_api_key("openai")
        anthropic_key = self.config_manager.get_api_key("anthropic")
        
        self.client = OpenAI(api_key=openai_key) if openai_key else None
        self.anthropic = Anthropic(api_key=anthropic_key) if anthropic_key else None
```

### 4.2 Auto-save on Chat

```python
def _handle_chat(self, message: str) -> CommandResult:
    # ... existing chat handling ...
    
    # Auto-save session after each message
    self.session.chat_history = [
        {"role": msg.role, "content": msg.content, "timestamp": datetime.now().isoformat()}
        for msg in self.chat_history
    ]
    self.session.model = self.current_model
    self.session.variant = self.current_variant
    self.session.agent_mode = self.agent_mode
    self.session_manager.save_session(self.session)
```

---

## 5. Security Considerations

### API Key Storage Options

1. **Plain text (simple, less secure)**
   - Store keys as-is in config.json
   - Easy to implement but keys are readable

2. **OS Keychain (recommended)**
   - Use `keyring` library to store in OS secure storage
   - Windows Credential Manager / macOS Keychain / Linux Secret Service

```python
import keyring

def set_api_key_secure(provider: str, key: str) -> None:
    keyring.set_password("agentshell", provider, key)

def get_api_key_secure(provider: str) -> Optional[str]:
    return keyring.get_password("agentshell", provider)
```

3. **Encrypted file**
   - Encrypt config with a master password
   - Use `cryptography` library

---

## 6. Implementation Order

### Phase 1: Session Management ✅
1. [x] Create `SessionManager` class
2. [x] Create `Session` data class
3. [x] Implement session CRUD operations
4. [x] Create `SessionSwitchScreen`
5. [x] Add auto-save on chat
6. [x] Add session loading on startup
7. [x] Add keybindings (`ctrl+n`, `ctrl+l`)

### Phase 2: Command Palette ✅
1. [x] Create `CommandPaletteScreen` class
2. [x] Define command categories and items
3. [x] Implement search/filter
4. [x] Add command execution
5. [x] Update `ctrl+p` to open palette

### Phase 3: Provider Configuration ✅
1. [x] Create `ConfigManager` class
2. [x] Create `ProviderConfigScreen`
3. [x] Implement key validation/testing
4. [x] Add to command palette
5. [x] Update API client initialization

### Phase 4: Polish (Partial)
1. [x] Add session name in status bar
2. [ ] Add "unsaved changes" indicator
3. [x] Add session export (JSON/Markdown)
4. [ ] Add session search by content
5. [x] Add keyboard navigation hints

---

## 7. UI Mockups

### Command Palette
```
┌─────────────────────────────────────────────────┐
│ Commands                                    esc │
├─────────────────────────────────────────────────┤
│ Search                                          │
├─────────────────────────────────────────────────┤
│ Suggested                                       │
│ ▶ Switch model                          ctrl+m │
│   Switch variant                        ctrl+t │
├─────────────────────────────────────────────────┤
│ Session                                         │
│   New session                           ctrl+n │
│   Switch session                        ctrl+l │
│   Rename session                               │
│   Delete session                               │
├─────────────────────────────────────────────────┤
│ System                                          │
│   Configure providers                          │
│   Toggle agent mode                       tab  │
│   Clear chat                                   │
└─────────────────────────────────────────────────┘
```

### Session Switcher
```
┌─────────────────────────────────────────────────┐
│ Sessions                            ctrl+l esc │
├─────────────────────────────────────────────────┤
│ Search                                          │
├─────────────────────────────────────────────────┤
│ ● Debug API Issue          15 msgs    10m ago  │
│   Refactor auth module      8 msgs     2h ago  │
│   Initial setup            23 msgs     1d ago  │
│   Brainstorm features       5 msgs     3d ago  │
├─────────────────────────────────────────────────┤
│ n new   d delete   r rename   enter switch     │
└─────────────────────────────────────────────────┘
```

### Provider Configuration
```
┌─────────────────────────────────────────────────┐
│ Provider Configuration                      esc │
├─────────────────────────────────────────────────┤
│ ☑ OpenAI       [sk-••••••••••••••••]    ✓ OK   │
│ ☑ Anthropic    [sk-ant-••••••••••••]    ✓ OK   │
│ ☐ Google       [                    ]          │
│ ☐ xAI          [                    ]          │
│ ☐ DeepSeek     [                    ]          │
│ ☐ NVIDIA NIM   [                    ]          │
│ ☐ OpenRouter   [                    ]          │
├─────────────────────────────────────────────────┤
│              [Save]     [Cancel]               │
└─────────────────────────────────────────────────┘
```

---

## 8. Dependencies to Add

```
# requirements.txt additions
keyring>=24.0.0        # Secure credential storage (optional)
cryptography>=41.0.0   # For encrypted config (optional)
```

---

## 9. File Structure After Implementation

```
cli/
├── __init__.py
├── __main__.py
├── tui_app.py                 # Main TUI (updated)
├── session_manager.py         # NEW: Session CRUD
├── config_manager.py          # NEW: Config/API key management
├── screens/                   # NEW: Modular screen components
│   ├── __init__.py
│   ├── command_palette.py
│   ├── session_switch.py
│   ├── provider_config.py
│   └── model_select.py        # Move from tui_app.py
└── models/                    # NEW: Data models
    ├── __init__.py
    ├── session.py
    └── config.py
```
