"""Context Manager for dual-model orchestration.

Monitors and compresses conversation context to prevent overflow.
Uses provider tokenizers when available and falls back to rough counting
and local summarization when a provider tokenizer or summarizer is missing.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cli.tui_constants import MODEL_CONFIGS

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional dependency
    tiktoken = None

logger = logging.getLogger(__name__)

# Default context sizes by provider/model prefix.
DEFAULT_CONTEXT_SIZES = {
    "gemini": 1000000,   # Gemini models: 1M tokens
    "gpt": 400000,       # GPT models: 400K tokens
    "claude": 200000,    # Claude models: 200K tokens
    "grok": 2000000,     # Grok models: 2M tokens
    "deepseek": 64000,   # DeepSeek models: 64K tokens
}


@dataclass
class CompactionResult:
    """Result of a single compaction pass."""

    applied: bool
    reason: str
    model_id: str
    provider: str
    before_tokens: int
    after_tokens: int
    before_usage_percent: float
    after_usage_percent: float
    preserved_user_messages: int
    preserved_agent_messages: int
    summary_source_messages: int
    summary_tokens: int
    summary_strategy: str
    summary_message: str
    message: str
    threshold_percent: float = 40.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "reason": self.reason,
            "model_id": self.model_id,
            "provider": self.provider,
            "before_tokens": self.before_tokens,
            "after_tokens": self.after_tokens,
            "before_usage_percent": self.before_usage_percent,
            "after_usage_percent": self.after_usage_percent,
            "preserved_user_messages": self.preserved_user_messages,
            "preserved_agent_messages": self.preserved_agent_messages,
            "summary_source_messages": self.summary_source_messages,
            "summary_tokens": self.summary_tokens,
            "summary_strategy": self.summary_strategy,
            "summary_message": self.summary_message,
            "message": self.message,
            "threshold_percent": self.threshold_percent,
            "created_at": self.created_at,
        }


class ContextManager:
    """
    Monitors and compresses context to stay under capacity threshold.

    Strategy:
    - At 40% capacity: Trigger compression
    - Preserve the last 5 user messages and last 20 agent messages
    - Summarize everything outside that preserved tail into a single block
      capped at 2000 tokens
    """

    COMPRESSION_THRESHOLD = 0.40
    SUMMARY_TOKEN_LIMIT = 2000

    def __init__(
        self,
        model_context_sizes: Dict[str, int],
        compression_client: Any = None,
        compression_model: str = "gemini-2.0-flash",
        provider_clients: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the context manager.

        Args:
            model_context_sizes: Dict mapping model names to their context sizes.
            compression_client: OpenAI-compatible client for summarization.
            compression_model: Model ID to use for compression.
            provider_clients: Optional provider client map for exact token counting.
        """
        self.model_sizes = model_context_sizes
        self.compression_client = compression_client
        self.compression_model = compression_model
        self.provider_clients = provider_clients or {}
        self._compression_count = 0

    def _model_config(self, model_id: str) -> Dict[str, Any]:
        return MODEL_CONFIGS.get(model_id, {})

    def _provider_for_model(self, model_id: str) -> str:
        provider = str(self._model_config(model_id).get("provider") or "").strip().lower()
        if provider:
            return provider

        model_lower = model_id.lower()
        for prefix in DEFAULT_CONTEXT_SIZES:
            if prefix in model_lower:
                return prefix
        return "unknown"

    def _canonical_model_id(self, model_id: str) -> str:
        config = self._model_config(model_id)
        canonical = str(config.get("id") or model_id).strip()
        return canonical or model_id

    def _openai_like_model_id(self, model_id: str) -> str:
        canonical = self._canonical_model_id(model_id)
        return canonical.split("/", 1)[-1]

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        parts.append(str(block.get("text", "")))
                    elif block_type == "tool_result":
                        parts.append(str(block.get("content", "")))
                    elif block_type == "tool_use":
                        parts.append(json.dumps(block, ensure_ascii=False))
                    else:
                        parts.append(json.dumps(block, ensure_ascii=False))
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        return str(content)

    def _message_preview(self, message: Dict[str, Any], *, limit: int = 180) -> str:
        content = self._content_to_text(message.get("content", ""))
        content = content.replace("\n", " ").strip()
        if len(content) > limit:
            content = content[: limit - 3].rstrip() + "..."
        role = str(message.get("role", "user")).upper()
        return f"{role}: {content}"

    def _format_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for msg in messages:
            role = str(msg.get("role", "user")).upper()
            content = self._content_to_text(msg.get("content", ""))
            content = content.replace("\n", " ").strip()
            if len(content) > 500:
                content = content[:500].rstrip() + f"... ({len(content)} chars total)"
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _encoding_for_model(self, model_id: str):
        if tiktoken is None:
            return None

        openai_like_model = self._openai_like_model_id(model_id)
        try:
            return tiktoken.encoding_for_model(openai_like_model)
        except Exception:
            if any(prefix in openai_like_model for prefix in ("gpt-5", "gpt-4o", "gpt-4.1", "gpt-4.5")):
                return tiktoken.get_encoding("o200k_base")
            return tiktoken.get_encoding("cl100k_base")

    def _count_tokens_with_tiktoken(self, messages: List[Dict[str, Any]], model_id: str) -> Optional[int]:
        encoding = self._encoding_for_model(model_id)
        if encoding is None:
            return None

        total = 0
        for message in messages:
            total += 3
            total += len(encoding.encode(str(message.get("role", "user"))))
            content = message.get("content", "")
            if isinstance(content, list):
                for block in content:
                    total += len(encoding.encode(json.dumps(block, ensure_ascii=False)))
            else:
                total += len(encoding.encode(self._content_to_text(content)))
            name = message.get("name")
            if name:
                total += 1 + len(encoding.encode(str(name)))

        total += 3
        return total

    def _extract_token_count(self, response: Any) -> Optional[int]:
        if response is None:
            return None

        for key in ("total_tokens", "token_count", "input_tokens", "prompt_tokens"):
            value = getattr(response, key, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)

        if isinstance(response, dict):
            for key in ("total_tokens", "token_count", "input_tokens", "prompt_tokens"):
                value = response.get(key)
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)

        usage = getattr(response, "usage", None)
        if usage is not None:
            for key in ("total_tokens", "input_tokens", "prompt_tokens"):
                value = getattr(usage, key, None)
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)

        return None

    def _count_tokens_with_provider(self, messages: List[Dict[str, Any]], model_id: str) -> Tuple[Optional[int], str]:
        provider = self._provider_for_model(model_id)
        canonical_model = self._canonical_model_id(model_id)
        provider_client = self.provider_clients.get(provider)
        tokenizer_family = provider

        if provider == "openrouter":
            lower_canonical = canonical_model.lower()
            if lower_canonical.startswith("anthropic/"):
                tokenizer_family = "anthropic"
                provider_client = self.provider_clients.get("anthropic")
                canonical_model = canonical_model.split("/", 1)[-1]
            elif lower_canonical.startswith("google/"):
                tokenizer_family = "google"
                provider_client = self.provider_clients.get("google")
                canonical_model = canonical_model.split("/", 1)[-1]
            elif lower_canonical.startswith("openai/"):
                tokenizer_family = "openai"
                canonical_model = canonical_model.split("/", 1)[-1]
            else:
                tokenizer_family = "openai"
                canonical_model = canonical_model.split("/", 1)[-1]

        if tokenizer_family == "anthropic" and provider_client is not None:
            message_payload = [
                {"role": msg.get("role", "user"), "content": self._content_to_text(msg.get("content", ""))}
                for msg in messages
            ]
            callables = []
            if hasattr(provider_client, "messages") and hasattr(provider_client.messages, "count_tokens"):
                callables.append(
                    lambda: provider_client.messages.count_tokens(
                        model=canonical_model,
                        messages=message_payload,
                    )
                )
            if hasattr(provider_client, "count_tokens"):
                callables.append(
                    lambda: provider_client.count_tokens(
                        model=canonical_model,
                        messages=message_payload,
                    )
                )
            for call in callables:
                try:
                    response = call()
                    count = self._extract_token_count(response)
                    if count is not None:
                        return count, "anthropic-api"
                except Exception:
                    continue

        if tokenizer_family == "google" and provider_client is not None:
            text = self._format_for_summary(messages)
            callables = []
            if hasattr(provider_client, "models") and hasattr(provider_client.models, "count_tokens"):
                callables.append(
                    lambda: provider_client.models.count_tokens(
                        model=canonical_model,
                        contents=text,
                    )
                )
            if hasattr(provider_client, "GenerativeModel"):
                try:
                    generative_model = provider_client.GenerativeModel(canonical_model)
                    if hasattr(generative_model, "count_tokens"):
                        callables.append(lambda: generative_model.count_tokens(text))
                except Exception:
                    pass
            if hasattr(provider_client, "count_tokens"):
                callables.append(
                    lambda: provider_client.count_tokens(
                        model=canonical_model,
                        contents=text,
                    )
                )
            for call in callables:
                try:
                    response = call()
                    count = self._extract_token_count(response)
                    if count is not None:
                        return count, "google-api"
                except Exception:
                    continue

        if tokenizer_family in {"openai", "xai", "deepseek"} and tiktoken is not None:
            count = self._count_tokens_with_tiktoken(messages, model_id)
            if count is not None:
                return count, "tiktoken"

        return None, "rough"

    def _count_tokens_rough(self, messages: List[Dict[str, Any]]) -> int:
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                total_chars += len(json.dumps(content, ensure_ascii=False))
            else:
                total_chars += len(self._content_to_text(content))
        return max(1, total_chars // 4)

    def count_tokens(self, messages: List[Dict[str, Any]], model_id: str) -> int:
        count, _ = self.count_tokens_with_strategy(messages, model_id)
        return count

    def count_tokens_with_strategy(self, messages: List[Dict[str, Any]], model_id: str) -> Tuple[int, str]:
        provider_count, strategy = self._count_tokens_with_provider(messages, model_id)
        if provider_count is not None:
            return provider_count, strategy
        return self._count_tokens_rough(messages), strategy

    def _trim_text_to_token_limit(self, text: str, model_id: str, max_tokens: int) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        encoding = self._encoding_for_model(model_id)
        if encoding is not None:
            encoded = encoding.encode(cleaned)
            if len(encoded) <= max_tokens:
                return cleaned
            return encoding.decode(encoded[:max_tokens]).rstrip()

        rough_limit = max_tokens * 4
        if len(cleaned) <= rough_limit:
            return cleaned
        return cleaned[:rough_limit].rstrip()

    def get_context_size(self, model_id: str) -> int:
        """Get the context size for a model."""
        if model_id in self.model_sizes:
            return self.model_sizes[model_id]

        config = self._model_config(model_id)
        canonical_model = str(config.get("id") or "").strip()
        if canonical_model in self.model_sizes:
            return self.model_sizes[canonical_model]

        model_lower = model_id.lower()
        for prefix, size in DEFAULT_CONTEXT_SIZES.items():
            if prefix in model_lower:
                return size

        return 128000

    def get_usage_snapshot(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        *,
        last_compaction: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        max_tokens = self.get_context_size(model_id)
        used_tokens, strategy = self.count_tokens_with_strategy(messages, model_id)
        usage_percent = (used_tokens / max_tokens) * 100 if max_tokens > 0 else 0.0
        threshold_percent = self.COMPRESSION_THRESHOLD * 100
        needs_compaction = usage_percent >= threshold_percent

        compaction_state = "ok"
        if needs_compaction:
            compaction_state = "needs_compaction"
        elif last_compaction and last_compaction.get("applied"):
            compaction_state = "compacted"

        snapshot = {
            "model": model_id,
            "max_tokens": max_tokens,
            "estimated_tokens": used_tokens,
            "usage_percent": round(usage_percent, 2),
            "message_count": len(messages),
            "threshold_percent": threshold_percent,
            "needs_compaction": needs_compaction,
            "compaction_state": compaction_state,
            "token_strategy": strategy,
            "last_compaction": last_compaction,
        }

        if last_compaction:
            snapshot["last_compaction"] = last_compaction

        return snapshot

    def needs_compression(self, messages: List[Dict[str, Any]], model_id: str) -> bool:
        """Check if context usage exceeds the compression threshold."""
        usage = self.get_usage_snapshot(messages, model_id)
        should_compress = bool(usage["needs_compaction"])

        if should_compress:
            logger.info(
                f"[ContextManager] Compression needed: {usage['estimated_tokens']:,} / {usage['max_tokens']:,} tokens "
                f"({usage['usage_percent']:.1f}% >= {self.COMPRESSION_THRESHOLD * 100:.0f}%)"
            )

        return should_compress

    def _summary_source_indices(
        self,
        messages: List[Dict[str, Any]],
        *,
        preserve_user_messages: int,
        preserve_agent_messages: int,
    ) -> tuple[set[int], List[int]]:
        user_indices: set[int] = set()
        agent_indices: set[int] = set()

        user_seen = 0
        agent_seen = 0
        for index in range(len(messages) - 1, -1, -1):
            role = str(messages[index].get("role", "user")).lower()
            if role == "user":
                if user_seen < preserve_user_messages:
                    user_indices.add(index)
                    user_seen += 1
            else:
                if agent_seen < preserve_agent_messages:
                    agent_indices.add(index)
                    agent_seen += 1

        pinned = user_indices | agent_indices
        omitted_indices = [index for index in range(len(messages)) if index not in pinned]
        return pinned, omitted_indices

    def _generate_summary(self, messages: List[Dict[str, Any]], model_id: str, *, max_tokens: int) -> Tuple[str, str]:
        """Generate a summary of the messages using the compression model or a local fallback."""
        formatted = self._format_for_summary(messages)

        if self.compression_client is not None:
            summary_prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are a conversation summarizer. Summarize the following conversation "
                        "history concisely. Focus on:\n"
                        "1. Key decisions made\n"
                        "2. Tools used and their results\n"
                        "3. Current progress/state\n"
                        "4. Any errors encountered and how they were resolved\n\n"
                        f"Keep the summary under {max_tokens} tokens. Use bullet points for clarity."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Summarize this conversation:\n\n{formatted}",
                },
            ]

            try:
                response = self.compression_client.chat.completions.create(
                    model=self.compression_model,
                    messages=summary_prompt,
                    max_tokens=max_tokens,
                )
                summary = response.choices[0].message.content or ""
                summary = self._trim_text_to_token_limit(str(summary), model_id, max_tokens)
                return summary.strip(), "provider"
            except Exception as exc:
                logger.warning(f"[ContextManager] Provider summary failed, falling back locally: {exc}")

        summary = self._generate_local_summary(messages, model_id, max_tokens=max_tokens)
        return summary.strip(), "local"

    def _generate_local_summary(self, messages: List[Dict[str, Any]], model_id: str, *, max_tokens: int) -> str:
        if not messages:
            return "No earlier context to summarize."

        lines = [
            f"Earlier context summary ({len(messages)} messages).",
            "This block replaces older history that was outside the preserved tail.",
            "",
        ]

        if len(messages) <= 12:
            sample = messages
        else:
            sample = messages[:4] + messages[-8:]
            lines.append(f"Omitted middle messages: {len(messages) - len(sample)}")
            lines.append("")

        for msg in sample:
            lines.append(f"- {self._message_preview(msg)}")

        summary = "\n".join(lines)
        return self._trim_text_to_token_limit(summary, model_id, max_tokens)

    def compact(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        *,
        reason: str = "manual",
        preserve_user_messages: int = 5,
        preserve_agent_messages: int = 20,
        summary_token_limit: int = SUMMARY_TOKEN_LIMIT,
    ) -> CompactionResult:
        """
        Compact the message history by summarizing everything outside the preserved tail.
        """
        before_tokens, before_strategy = self.count_tokens_with_strategy(messages, model_id)
        before_usage = self.get_usage_snapshot(messages, model_id)
        pinned_indices, omitted_indices = self._summary_source_indices(
            messages,
            preserve_user_messages=preserve_user_messages,
            preserve_agent_messages=preserve_agent_messages,
        )

        if not omitted_indices:
            message = "Nothing to compact yet."
            return CompactionResult(
                applied=False,
                reason=reason,
                model_id=model_id,
                provider=self._provider_for_model(model_id),
                before_tokens=before_tokens,
                after_tokens=before_tokens,
                before_usage_percent=before_usage["usage_percent"],
                after_usage_percent=before_usage["usage_percent"],
                preserved_user_messages=preserve_user_messages,
                preserved_agent_messages=preserve_agent_messages,
                summary_source_messages=0,
                summary_tokens=0,
                summary_strategy=before_strategy,
                summary_message="",
                message=message,
            )

        summary_source = [messages[index] for index in omitted_indices]
        summary_text, summary_strategy = self._generate_summary(
            summary_source,
            model_id,
            max_tokens=summary_token_limit,
        )
        summary_text = summary_text.strip()
        if not summary_text:
            summary_text = self._generate_local_summary(
                summary_source,
                model_id,
                max_tokens=summary_token_limit,
            ).strip()
            summary_strategy = "local"

        summary_content = (
            "[COMPRESSED HISTORY]\n"
            f"Earlier context summarized from {len(summary_source)} message(s).\n"
            f"Preserved exactly: last {preserve_user_messages} user messages and last {preserve_agent_messages} agent messages.\n"
            f"Summary budget: {summary_token_limit} tokens max.\n\n"
            f"{summary_text}"
        )
        summary_content = self._trim_text_to_token_limit(summary_content, model_id, summary_token_limit)

        summary_message = {
            "role": "assistant",
            "content": summary_content,
            "timestamp": datetime.now().isoformat(),
            "context_compacted": True,
            "context_compaction_reason": reason,
        }

        compressed_messages: List[Dict[str, Any]] = []
        summary_inserted = False
        first_omitted_index = omitted_indices[0]
        for index, message in enumerate(messages):
            if not summary_inserted and index == first_omitted_index:
                compressed_messages.append(summary_message)
                summary_inserted = True
            if index in pinned_indices:
                compressed_messages.append(copy.deepcopy(message))

        if not summary_inserted:
            compressed_messages.append(summary_message)

        after_tokens, _ = self.count_tokens_with_strategy(compressed_messages, model_id)
        after_usage = self.get_usage_snapshot(compressed_messages, model_id)

        if after_tokens >= before_tokens:
            logger.info(
                "[ContextManager] Compaction applied but token count did not shrink enough: "
                f"{before_tokens:,} -> {after_tokens:,} tokens"
            )

        self._compression_count += 1

        message = (
            f"Context compacted: {before_tokens:,} -> {after_tokens:,} tokens "
            f"({before_usage['usage_percent']:.1f}% -> {after_usage['usage_percent']:.1f}%). "
            f"Preserved the last {preserve_user_messages} user messages and the last {preserve_agent_messages} agent messages."
        )

        return CompactionResult(
            applied=True,
            reason=reason,
            model_id=model_id,
            provider=self._provider_for_model(model_id),
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            before_usage_percent=before_usage["usage_percent"],
            after_usage_percent=after_usage["usage_percent"],
            preserved_user_messages=preserve_user_messages,
            preserved_agent_messages=preserve_agent_messages,
            summary_source_messages=len(summary_source),
            summary_tokens=self.count_tokens(
                [
                    {
                        "role": "assistant",
                        "content": summary_content,
                    }
                ],
                model_id,
            ),
            summary_strategy=summary_strategy,
            summary_message=summary_content,
            message=message,
            messages=compressed_messages,
        )

    def compress(self, messages: List[Dict[str, Any]], model_id: str, *, reason: str = "manual") -> List[Dict[str, Any]]:
        """
        Backwards-compatible wrapper that returns only the compacted messages.
        """
        result = self.compact(messages, model_id, reason=reason)
        return result.messages if result.applied else messages

    def get_compression_count(self) -> int:
        """Get the number of compressions performed."""
        return self._compression_count
