# Unified Agentic System

A disciplined control system for reliable AI-driven automation across browsers and desktop environments.

## Architecture

The system is organized around four tightly coupled layers:

### 1. Observation Layer (`observation_testing/`)
Transforms screen state into structured, machine-readable descriptions.
- **Structured sources**: Selenium (browser), pywinauto (desktop)
- **Vision-based**: OmniParser for screenshot parsing
- **Output**: Normalized `ObservationSnapshot` with elements, focus state, and metadata

### 2. Brain Layer (`brain_testing/`)
Decision-making using MAD decomposition and MAKER voting.
- **Orchestrator**: High-level LLM maintaining full plan context
- **Micro-agents**: Low-level LLMs proposing atomic actions
- **Voting**: First-to-ahead-by-K voting with red-flagging

### 3. Hands Layer (`hands_testing/`)
Executes atomic actions and returns execution evidence.
- **Executors**: pyautogui, Selenium, pywinauto action handlers
- **Coordinate utils**: DPI scaling, window offsets, geometry

### 4. Platform Layer (`platform_testing/`)
Tauri shell providing the application body.
- **Frontend**: Chat/debug UI in HTML/CSS/JS
- **Backend**: Rust/Tauri for native OS integration
- **Bridge**: IPC between Tauri and Python backend

## Core Principles

- **Maximal Agentic Decomposition (MAD)**: Every task decomposed to atomic actions
- **MAKER Voting**: Multiple proposals, red-flagging, consensus voting
- **Tight Loop**: Observe → Decide → Act → Verify on every step
- **Error Correction**: Failures detected and recovered immediately

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Clone OmniParser (in observation_testing/)
cd observation_testing
git clone https://github.com/microsoft/OmniParser.git omniparser

# Initialize Tauri (in platform_testing/)
cd platform_testing
npm create tauri-app@latest .
```

## Development Status

🚧 **Testing Phase** - Each layer is being developed and tested independently.
