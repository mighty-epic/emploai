# EmploAI Supported Model List

This document tracks all models supported by the Unified Agent and their configurations.

| Model Name | Provider | Model ID | Context Window | Reasoning? |
|------------|----------|----------|----------------|------------|
| **GPT-5 Series** | | | | |
| `gpt-5` | OpenAI | `gpt-5` | 400k | Yes |
| `gpt-5.1` | OpenAI | `gpt-5.1-2025-11-13` | 400k | Yes |
| `gpt-5.2` | OpenAI | `gpt-5.2-2025-12-11` | 400k | Yes |
| `gpt-5.1-codex-max` | OpenAI | `gpt-5.1-codex-max` | 400k | Yes |
| `gpt-5.2-codex` | OpenAI | `gpt-5.2-codex` | 400k | Yes |
| **GPT-4 Series** | | | | |
| `gpt-4.1` | OpenAI | `gpt-4.1` | 128k | No |
| `gpt-4o` | OpenAI | `gpt-4o` | 128k | No |
| `gpt-4o-mini` | OpenAI | `gpt-4o-mini` | 128k | No |
| **Claude 4.5 Series** | | | | |
| `claude-sonnet-4.5`| Anthropic| `claude-sonnet-4-5-20250929`| 200k | No (Vision) |
| `claude-opus-4.5` | Anthropic| `claude-opus-4-5-20250929` | 200k | No (Vision) |
| `claude-haiku-4.5`| Anthropic| `claude-haiku-4-5-20251001`| 200k | No |
| **Claude 4 Series** | | | | |
| `claude-sonnet-4` | Anthropic| `claude-sonnet-4-20250514` | 200k | No |
| `claude-opus-4`   | Anthropic| `claude-opus-4-20250514`   | 200k | No |
| `claude-haiku-4`  | Anthropic| `claude-haiku-4-20250514`  | 200k | No |
| **Gemini 3 / 2.5** | | | | |
| `gemini-3-pro`    | Google | `gemini-3-pro` | 2M | Yes |
| `gemini-3-flash`  | Google | `gemini-3-flash` | 1M | No |
| `gemini-2.5-pro`  | Google | `gemini-2.5-pro` | 2M | Yes |
| `gemini-2.5-flash`| Google | `gemini-2.5-flash` | 1M | No |
| `gemini-2.0-flash`| Google | `gemini-2.0-flash-exp` | 1M | No |
| **Grok 4.1 Series**| | | | |
| `grok-4.1-fast-reasoning` | xAI | `grok-4-1-fast-reasoning` | 2M | Yes |
| `grok-4.1-fast-non-reasoning` | xAI | `grok-4-1-fast-non-reasoning` | 2M | No |
| `grok-code-fast-1` | xAI | `grok-code-fast-1` | 256k | No |
| **Grok 4 Series** | | | | |
| `grok-4-fast-reasoning` | xAI | `grok-4-fast-reasoning` | 2M | Yes |
| `grok-4-fast-non-reasoning` | xAI | `grok-4-fast-non-reasoning` | 2M | No |
| `grok-4-0709` | xAI | `grok-4-0709` | 256k | No |
| **Grok 3 Series** | | | | |
| `grok-3` | xAI | `grok-3` | 131k | No |
| `grok-3-mini` | xAI | `grok-3-mini` | 131k | No |
| **DeepSeek** | | | | |
| `deepseek-chat` | DeepSeek | `deepseek-chat` | 64k | No |
| `deepseek-reasoner`| DeepSeek | `deepseek-reasoner` | 64k | Yes |
| **NVIDIA NIM** | | | | |
| `google/diffusiongemma-26b-a4b-it` | NVIDIA NIM | `google/diffusiongemma-26b-a4b-it` | 128k | No |
| `google/gemma-3n-e2b-it` | NVIDIA NIM | `google/gemma-3n-e2b-it` | 128k | No |
| `meta/llama-3.2-11b-vision-instruct` | NVIDIA NIM | `meta/llama-3.2-11b-vision-instruct` | 128k | No |
| `meta/llama-4-maverick-17b-128e-instruct` | NVIDIA NIM | `meta/llama-4-maverick-17b-128e-instruct` | 128k | No |
| `minimaxai/minimax-m3` | NVIDIA NIM | `minimaxai/minimax-m3` | 128k | No |
| `mistralai/ministral-14b-instruct-2512` | NVIDIA NIM | `mistralai/ministral-14b-instruct-2512` | 128k | No |
| `mistralai/mistral-large-3-675b-instruct-2512` | NVIDIA NIM | `mistralai/mistral-large-3-675b-instruct-2512` | 128k | No |
| `mistralai/mistral-medium-3.5-128b` | NVIDIA NIM | `mistralai/mistral-medium-3.5-128b` | 128k | No |
| `mistralai/mistral-small-4-119b-2603` | NVIDIA NIM | `mistralai/mistral-small-4-119b-2603` | 128k | No |
| `nvidia/nemotron-nano-12b-v2-vl` | NVIDIA NIM | `nvidia/nemotron-nano-12b-v2-vl` | 128k | No |
| `NVIDIA_MODEL_IDS` | NVIDIA NIM | See `cli/tui_constants.py` for the 10-model image-input and forced-tool verified chooser list filtered from NVIDIA's broader catalog | 128k | No |
| **OpenRouter / Orb**| | | | |
| `orb-gpt-4o` | OpenRouter| `openai/gpt-4o` | 128k | No |
| `orb-claude-3.5-sonnet`| OpenRouter| `anthropic/claude-3.5-sonnet` | 200k | No |
