"""
Simple Memory Service

Extracts facts via regex, stores as JSON in ChatSession,
and builds context for LLM with memory + recent messages.
"""

from typing import Dict, List, Optional

import structlog

from ...core.config import get_settings

# Match existing import pattern from chat_service.py
from ...models.chat import (
    ChatMessage as ChatMessageModel,
)
from ...models.chat import (
    ChatSession as ChatSessionModel,
)
from .fact_extractor import extract_all

logger = structlog.get_logger(__name__)


class MemoryService:
    """
    Service for managing conversation memory.

    Extracts domain facts from messages using regex patterns
    and provides memory-enhanced context for LLM prompts.

    IMPORTANT - Extraction Flow:
    - User messages: Extract CONTEXT (entity, period) - users ASK questions
    - AI responses: Extract FACTS (numbers) - AI PROVIDES data from DB/RAG

    This is called from two places:
    1. build_message_context_with_memory() - for user messages (context)
    2. add_assistant_message() - for AI responses (facts)
    """

    def __init__(self):
        self.settings = get_settings()

    async def process_message(self, session_id: str, message: str) -> None:
        """
        Extract facts from message and save to session.

        Call this on every user message to accumulate facts.

        Args:
            session_id: Chat session ID
            message: User message content
        """
        if not self.settings.memory_enabled:
            return

        session = await ChatSessionModel.get(session_id)
        if not session:
            logger.warning("memory.session_not_found", session_id=session_id)
            return

        # Extract facts using current context
        new_facts, new_context = extract_all(
            text=message, current_context=session.memory_context
        )

        # Update session if we found anything
        should_save = False

        if new_facts:
            # Merge new facts into existing
            session.memory_facts.update(new_facts)

            # Limit total facts to prevent unbounded growth
            if len(session.memory_facts) > self.settings.memory_max_facts:
                # Keep most recent facts (dict preserves insertion order in Python 3.7+)
                items = list(session.memory_facts.items())
                session.memory_facts = dict(items[-self.settings.memory_max_facts :])

            logger.info(
                "memory.facts_saved",
                session_id=session_id,
                new_facts=new_facts,
                total_facts=len(session.memory_facts),
            )
            should_save = True

        # Update context if changed
        if new_context != session.memory_context:
            session.memory_context = new_context
            logger.info(
                "memory.context_updated", session_id=session_id, context=new_context
            )
            should_save = True

        if should_save:
            await session.save()

    async def get_context_for_llm(
        self, session_id: str, system_prompt: str = ""
    ) -> List[Dict[str, str]]:
        """
        Build message list for LLM with memory context.

        Returns a list of messages including:
        1. System prompt (if provided)
        2. Memory facts (formatted for LLM)
        3. Recent conversation messages

        Args:
            session_id: Chat session ID
            system_prompt: Optional system prompt to prepend

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        session = await ChatSessionModel.get(session_id)
        if not session:
            # Fallback: just return system prompt
            if system_prompt:
                return [{"role": "system", "content": system_prompt}]
            return []

        messages = []

        # 1. System prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 2. Memory context (if we have facts)
        if session.memory_facts:
            memory_text = self._format_facts_for_llm(
                facts=session.memory_facts, context=session.memory_context
            )
            messages.append({"role": "system", "content": memory_text})

        # 3. Recent messages from conversation history
        # CRITICAL FIX: Skip the most recent message (current user message)
        # because it was already saved to DB before get_context_for_llm() is called,
        # and build_message_context_with_memory() adds it manually at line 260.
        # We fetch memory_recent_messages + 1, skip the first one (most recent),
        # and use the next memory_recent_messages as history.
        all_recent = (
            await ChatMessageModel.find(ChatMessageModel.chat_id == session_id)
            .sort(-ChatMessageModel.created_at)
            .limit(self.settings.memory_recent_messages + 1)
            .to_list()
        )

        # Skip the first message (most recent = current user message just saved)
        recent = all_recent[1:] if len(all_recent) > 0 else []

        # Reverse to chronological order (oldest first)
        for msg in reversed(recent):
            messages.append({"role": msg.role.value, "content": msg.content})

        logger.info(
            "🔍 [MEMORY DEBUG] Added conversation history to context",
            session_id=session_id,
            history_count=len(recent),
            total_fetched=len(all_recent),
            skipped_current=len(all_recent) > 0,
            recent_messages_preview=[
                f"{msg.role.value}: {msg.content[:50]}..." for msg in reversed(recent)
            ][:3],
        )

        return messages

    def _format_facts_for_llm(
        self, facts: Dict[str, str], context: Dict[str, str]
    ) -> str:
        """
        Format facts nicely for LLM consumption.

        Groups facts by bank.period scope and formats them
        in a readable markdown-like structure.

        Args:
            facts: Dict of fact keys to values
            context: Current conversation context

        Returns:
            Formatted string for LLM system message
        """
        # Group facts by bank.period scope
        grouped: Dict[str, Dict[str, str]] = {}
        ungrouped: Dict[str, str] = {}

        for key, value in facts.items():
            parts = key.rsplit(".", 1)
            if len(parts) == 2:
                scope, metric = parts
                if scope not in grouped:
                    grouped[scope] = {}
                grouped[scope][metric] = value
            else:
                ungrouped[key] = value

        # Build output
        lines = ["## Conversation Memory", ""]

        # Current context section
        if context:
            lines.append("**Current Focus:**")
            if context.get("bank"):
                lines.append(f"  Bank: {context['bank'].upper()}")
            if context.get("period"):
                lines.append(f"  Period: {context['period']}")
            if context.get("metric"):
                lines.append(f"  Metric: {context['metric'].upper()}")
            lines.append("")

        # Grouped facts by scope
        for scope, metrics in sorted(grouped.items()):
            scope_label = scope.replace(".", " ").replace("_", " ").upper()
            lines.append(f"**{scope_label}:**")
            for metric, value in sorted(metrics.items()):
                metric_label = metric.replace("_", " ").upper()
                lines.append(f"  {metric_label}: {value}")
            lines.append("")

        # Ungrouped facts
        if ungrouped:
            lines.append("**Other Facts:**")
            for key, value in ungrouped.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        lines.append(
            "Use these facts to answer questions about previously mentioned numbers."
        )

        return "\n".join(lines)

    async def get_facts(self, session_id: str) -> Dict[str, str]:
        """
        Get all facts for a session.

        Args:
            session_id: Chat session ID

        Returns:
            Dict of fact keys to values
        """
        session = await ChatSessionModel.get(session_id)
        if not session:
            return {}
        return session.memory_facts

    async def get_context(self, session_id: str) -> Dict[str, str]:
        """
        Get current context for a session.

        Args:
            session_id: Chat session ID

        Returns:
            Context dict with bank, period, metric keys
        """
        session = await ChatSessionModel.get(session_id)
        if not session:
            return {}
        return session.memory_context

    async def clear_memory(self, session_id: str) -> bool:
        """
        Clear all memory for a session.

        Args:
            session_id: Chat session ID

        Returns:
            True if cleared, False if session not found
        """
        session = await ChatSessionModel.get(session_id)
        if not session:
            return False

        session.memory_facts = {}
        session.memory_context = {}
        await session.save()

        logger.info("memory.cleared", session_id=session_id)
        return True


# Singleton (matches pattern from artifact_service.py)
_memory_service_instance: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """
    Get singleton MemoryService instance.

    Used as FastAPI dependency:
        memory_svc: MemoryService = Depends(get_memory_service)

    Returns:
        MemoryService singleton instance
    """
    global _memory_service_instance
    if _memory_service_instance is None:
        _memory_service_instance = MemoryService()
    return _memory_service_instance
