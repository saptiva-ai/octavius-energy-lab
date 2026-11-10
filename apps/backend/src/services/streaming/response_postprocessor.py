"""
Response Post-Processor Service.

Domain-agnostic post-processing for LLM responses:
- Empty response fallback with contextual messaging
- Output sanitization (strips leaked internal patterns)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PostProcessResult:
    """Result of response post-processing."""

    content: str
    was_empty: bool
    was_sanitized: bool
    chars_removed: int
    fallback_scenario: Optional[str]


class ResponsePostProcessor:
    """
    Service for post-processing LLM responses before persistence.

    Responsibilities:
        - Handle empty responses with contextual fallbacks
        - Sanitize leaked internal patterns from responses
    """

    @staticmethod
    def handle_empty_response(
        response: str,
        *,
        has_documents: bool = False,
        doc_warnings: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        Handle empty or missing response with contextual fallback.

        Args:
            response: The response content (may be empty)
            has_documents: Whether documents were attached
            doc_warnings: Any document processing warnings
            context: Additional context for fallback message

        Returns:
            Tuple of (response_content, scenario_name)
            - response_content: Original or fallback message
            - scenario_name: None if not empty, else scenario identifier
        """
        if response and response.strip():
            return response, None

        # Import here to avoid circular imports
        from ..empty_response_handler import (
            EmptyResponseHandler,
            EmptyResponseScenario,
        )

        # Determine the most likely scenario
        if doc_warnings:
            scenario = EmptyResponseScenario.DOCS_PROCESSING
        elif has_documents:
            scenario = EmptyResponseScenario.DOCS_NOT_FOUND
        else:
            scenario = EmptyResponseScenario.STREAM_NO_CHUNKS

        # Get fallback message
        fallback = EmptyResponseHandler.get_fallback_message(
            scenario=scenario,
            context=context or {},
        )

        # Log the incident
        EmptyResponseHandler.log_empty_response_incident(
            scenario=scenario,
            context=context or {},
        )

        logger.warning(
            "response_postprocessor.empty_response_handled",
            scenario=scenario.name,
            has_documents=has_documents,
            has_warnings=bool(doc_warnings),
        )

        return fallback, scenario.name

    @staticmethod
    def sanitize(response: str) -> Tuple[str, int]:
        """
        Remove leaked internal patterns from response content.

        Args:
            response: The response content

        Returns:
            Tuple of (sanitized_content, chars_removed)
        """
        if not response:
            return response, 0

        # Import here to avoid circular imports
        from ..text_sanitizer import sanitize_response_content

        original_len = len(response)
        sanitized = sanitize_response_content(response) or ""
        chars_removed = original_len - len(sanitized)

        if chars_removed > 0:
            logger.info(
                "response_postprocessor.sanitized",
                original_length=original_len,
                sanitized_length=len(sanitized),
                chars_removed=chars_removed,
            )

        return sanitized, chars_removed

    @staticmethod
    def process(
        response: str,
        *,
        has_documents: bool = False,
        doc_warnings: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        sanitize: bool = True,
        model: str = "Saptiva Turbo",
    ) -> PostProcessResult:
        """
        Full post-processing pipeline for LLM responses.

        Performs in order:
        1. Handle empty response with fallback
        2. Sanitize leaked internal patterns

        Args:
            response: The response content
            has_documents: Whether documents were attached
            doc_warnings: Any document processing warnings
            context: Additional context for fallback message
            sanitize: Whether to sanitize (default: True)
            model: Model that generated this response (reserved)

        Returns:
            PostProcessResult with all processing details
        """
        current_response = response or ""
        chars_removed = 0
        was_sanitized = False

        # Step 1: Handle empty response
        current_response, fallback_scenario = (
            ResponsePostProcessor.handle_empty_response(
                current_response,
                has_documents=has_documents,
                doc_warnings=doc_warnings,
                context=context,
            )
        )
        was_empty = fallback_scenario is not None

        # Step 2: Sanitize
        if sanitize and current_response:
            current_response, chars_removed = ResponsePostProcessor.sanitize(
                current_response
            )
            was_sanitized = chars_removed > 0

        logger.info(
            "response_postprocessor.completed",
            was_empty=was_empty,
            was_sanitized=was_sanitized,
            chars_removed=chars_removed,
            final_length=len(current_response),
        )

        return PostProcessResult(
            content=current_response,
            was_empty=was_empty,
            was_sanitized=was_sanitized,
            chars_removed=chars_removed,
            fallback_scenario=fallback_scenario,
        )
