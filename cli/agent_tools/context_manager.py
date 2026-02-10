"""Context Manager for dual-model orchestration.

Monitors and compresses conversation context to prevent overflow.
Uses a fast model (Gemini 3 Flash) for summarization.
"""

from typing import List, Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Default context sizes by provider/model prefix
DEFAULT_CONTEXT_SIZES = {
    "gemini": 1000000,   # Gemini models: 1M tokens
    "gpt": 400000,       # GPT models: 400K tokens
    "claude": 200000,    # Claude models: 200K tokens
    "grok": 128000,      # Grok models: 128K tokens
    "deepseek": 64000,   # DeepSeek models: 64K tokens
}


class ContextManager:
    """
    Monitors and compresses context to stay under capacity threshold.
    
    Strategy:
    - At 50% capacity: Trigger compression
    - Compress down to ~15% of capacity
    - Pin: System prompt, first user message, last 5 messages
    - Summarize: Everything in between
    """
    
    COMPRESSION_THRESHOLD = 0.50  # 50% - trigger compression
    TARGET_AFTER_COMPRESSION = 0.15  # 15% - target after compression
    
    def __init__(
        self,
        model_context_sizes: Dict[str, int],
        compression_client: Any,
        compression_model: str = "gemini-3-flash"
    ):
        """
        Initialize the context manager.
        
        Args:
            model_context_sizes: Dict mapping model names to their context sizes
            compression_client: OpenAI-compatible client for summarization (Gemini)
            compression_model: Model ID to use for compression
        """
        self.model_sizes = model_context_sizes
        self.compression_client = compression_client
        self.compression_model = compression_model
        self._compression_count = 0
    
    def estimate_tokens(self, messages: List[Dict]) -> int:
        """
        Estimate token count from messages.
        Uses rough heuristic: 4 characters = 1 token.
        """
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # Handle structured content (e.g., Anthropic tool_result blocks)
                for block in content:
                    if isinstance(block, dict):
                        block_str = json.dumps(block)
                        total_chars += len(block_str)
                    else:
                        total_chars += len(str(block))
            else:
                total_chars += len(str(content))
        
        return total_chars // 4
    
    def get_context_size(self, model_id: str) -> int:
        """Get the context size for a model."""
        # Check exact match first
        if model_id in self.model_sizes:
            return self.model_sizes[model_id]
        
        # Check prefix matches
        model_lower = model_id.lower()
        for prefix, size in DEFAULT_CONTEXT_SIZES.items():
            if prefix in model_lower:
                return size
        
        # Default fallback
        return 128000
    
    def get_usage_percentage(self, messages: List[Dict], model_id: str) -> float:
        """Get current context usage as a percentage."""
        max_tokens = self.get_context_size(model_id)
        used_tokens = self.estimate_tokens(messages)
        return (used_tokens / max_tokens) * 100 if max_tokens > 0 else 0
    
    def needs_compression(self, messages: List[Dict], model_id: str) -> bool:
        """Check if context usage exceeds the compression threshold."""
        max_tokens = self.get_context_size(model_id)
        used_tokens = self.estimate_tokens(messages)
        usage_ratio = used_tokens / max_tokens if max_tokens > 0 else 0
        
        should_compress = usage_ratio >= self.COMPRESSION_THRESHOLD
        
        if should_compress:
            logger.info(
                f"[ContextManager] Compression needed: {used_tokens:,} / {max_tokens:,} tokens "
                f"({usage_ratio * 100:.1f}% >= {self.COMPRESSION_THRESHOLD * 100:.0f}%)"
            )
        
        return should_compress
    
    def compress(self, messages: List[Dict]) -> List[Dict]:
        """
        Compress the message history by summarizing the middle portion.
        
        Pinned messages:
        - Index 0: System prompt
        - Index 1: First user message
        - Last 5 messages: Recent context
        
        Everything else is summarized.
        """
        if len(messages) < 8:
            # Not enough messages to compress meaningfully
            logger.info("[ContextManager] Not enough messages to compress")
            return messages
        
        # Pin start: system + first user message
        pinned_start = messages[:2]
        
        # Pin end: last 5 messages
        pinned_end = messages[-5:]
        
        # Middle: everything to compress
        middle = messages[2:-5]
        
        if len(middle) < 3:
            logger.info("[ContextManager] Middle section too small to compress")
            return messages
        
        try:
            # Generate summary using compression client
            summary = self._generate_summary(middle)
            
            # Build compressed message list
            compressed = pinned_start + [
                {
                    "role": "system",
                    "content": f"[COMPRESSED HISTORY - {len(middle)} messages summarized]\n{summary}"
                }
            ] + pinned_end
            
            self._compression_count += 1
            
            # Log compression stats
            original_tokens = self.estimate_tokens(messages)
            compressed_tokens = self.estimate_tokens(compressed)
            savings = ((original_tokens - compressed_tokens) / original_tokens) * 100
            
            logger.info(
                f"[ContextManager] Compression #{self._compression_count}: "
                f"{original_tokens:,} -> {compressed_tokens:,} tokens ({savings:.1f}% reduction)"
            )
            
            return compressed
            
        except Exception as e:
            logger.error(f"[ContextManager] Compression failed: {e}")
            # Fallback: Just keep pinned messages without summary
            return self._emergency_trim(messages)
    
    def _generate_summary(self, messages: List[Dict]) -> str:
        """Generate a summary of the messages using the compression model."""
        # Format messages for summarization
        formatted = self._format_for_summary(messages)
        
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
                    "Keep the summary under 500 words. Use bullet points for clarity."
                )
            },
            {
                "role": "user",
                "content": f"Summarize this conversation:\n\n{formatted}"
            }
        ]
        
        # Use OpenAI-compatible API
        response = self.compression_client.chat.completions.create(
            model=self.compression_model,
            messages=summary_prompt,
            max_tokens=600
        )
        
        return response.choices[0].message.content
    
    def _format_for_summary(self, messages: List[Dict]) -> str:
        """Format messages into a readable string for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            
            # Handle different content types
            if isinstance(content, str):
                # Truncate very long content
                if len(content) > 500:
                    content = content[:500] + f"... ({len(content)} chars total)"
            elif isinstance(content, list):
                # Handle structured content
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            parts.append(f"[Tool Result: {block.get('content', '')[:200]}...]")
                        elif block.get("type") == "tool_use":
                            parts.append(f"[Tool Call: {block.get('name', 'unknown')}]")
                        elif block.get("type") == "text":
                            parts.append(block.get("text", "")[:200])
                        else:
                            parts.append(str(block)[:200])
                content = " | ".join(parts)
            else:
                content = str(content)[:500]
            
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    
    def _emergency_trim(self, messages: List[Dict]) -> List[Dict]:
        """
        Emergency fallback: Keep only essential messages when compression fails.
        """
        logger.warning("[ContextManager] Using emergency trim fallback")
        
        # Keep system prompt + first user + last 10 messages
        if len(messages) <= 12:
            return messages
        
        return messages[:2] + messages[-10:]
    
    def get_compression_count(self) -> int:
        """Get the number of compressions performed."""
        return self._compression_count
