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
| **OpenRouter / Orb**| | | | |
| `orb-gpt-4o` | OpenRouter| `openai/gpt-4o` | 128k | No |
| `orb-claude-3.5-sonnet`| OpenRouter| `anthropic/claude-3.5-sonnet` | 200k | No |