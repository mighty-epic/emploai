# Unified Agentic System

A disciplined control system for reliable AI-driven automation across browsers and desktop environments.

## Architecture

The system is organized around core components:

### 1. Brain Layer (`brain_testing/`)
Decision-making using MAD decomposition and MAKER voting.
- **Orchestrator**: High-level LLM maintaining full plan context
- **Micro-agents**: Low-level LLMs proposing atomic actions
- **Voting**: First-to-ahead-by-K voting with red-flagging

### 2. Agent Core (`agent/`, `single_agent/`)
Unified agent logic and automation capabilities.

### 3. CLI (`cli/`)
Textual TUI for interacting with the system.

## Core Principles

- **Maximal Agentic Decomposition (MAD)**: Every task decomposed to atomic actions
- **MAKER Voting**: Multiple proposals, red-flagging, consensus voting
- **Tight Loop**: Observe → Decide → Act → Verify on every step
- **Error Correction**: Failures detected and recovered immediately

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Additional setup is handled per component as needed.
```

## Development Status

🚧 **Active Development** - Focused on the CLI, agent core, and brain tests.
