"""
System Prompt Builder Service - Resolves and enhances system prompts for chat.

Domain-agnostic prompt assembly: resolves the base system prompt from the
registry, optionally describes the RAG retrieval tool, and appends document
context for grounded answers.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PromptBuildResult:
    """Result of system prompt building."""

    system_prompt: str
    model_params: Dict[str, Any]
    is_clarification: bool = False


class SystemPromptBuilder:
    """
    Builds and enhances system prompts for chat streaming.

    This service handles:
    1. Resolving base system prompt from registry
    2. Building tools markdown for RAG
    3. Adding document context
    """

    @staticmethod
    def build_tools_markdown(has_documents: bool) -> Optional[str]:
        """
        Build a markdown section describing available tools.

        Args:
            has_documents: Whether documents are available for RAG

        Returns:
            Markdown-formatted tools documentation or None
        """
        sections = []

        # RAG tool (when documents available)
        if has_documents:
            sections.append(
                "* **get_relevant_segments** — Retrieve relevant document segments for RAG\n"
                "  - Parameters: conversation_id (string), question (string), max_segments (int)\n"
                "  - Use when: User asks about uploaded documents\n"
                "  - conversation_id: use the active chat/session id\n"
                "  - question: user question as-is\n"
                "  - max_segments: default 2"
            )

        return "\n\n".join(sections) if sections else None

    @classmethod
    def build(
        cls,
        model: str,
        document_context: Optional[str],
        document_ids: Optional[List[str]],
        user_query: str = "",
    ) -> PromptBuildResult:
        """
        Build the complete system prompt with all enhancements.

        Args:
            model: The model identifier (e.g., "saptiva-1")
            document_context: RAG document context string
            document_ids: List of document IDs attached
            user_query: The user's original question

        Returns:
            PromptBuildResult with system_prompt and model_params
        """
        # Lazy import to avoid circular dependencies
        from ...core.prompt_registry import get_prompt_registry

        prompt_registry = get_prompt_registry()

        # Determine if documents are available
        has_docs_available = bool(document_context or document_ids)

        # Resolve base system prompt
        system_prompt, model_params = prompt_registry.resolve(
            model=model,
            tools_markdown=cls.build_tools_markdown(has_documents=has_docs_available),
            channel="chat",
        )

        # Add document context if available (structured RAG template)
        if document_context:
            from .document_context import DocumentContextBuilder

            system_prompt += DocumentContextBuilder.format_for_prompt(document_context)

        return PromptBuildResult(
            system_prompt=system_prompt,
            model_params=model_params,
            is_clarification=False,
        )
