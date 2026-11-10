"""
Saptiva Streamer Service.

Extracted from streaming_handler.py for better testability.
Abstracts LLM interaction (streaming and non-streaming) with normalized response handling.

REFACTOR-001: Phase 5.2 extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class StreamerConfig:
    """Configuration for Saptiva streamer."""

    model: str
    temperature: float = 0.7
    max_tokens: int = 3000
    timeout: int = 120


@dataclass
class CompletionResult:
    """Result of a non-streaming completion."""

    content: str
    has_reasoning: bool
    raw_response: Optional[Any] = None


class SaptivaStreamer:
    """
    Service for abstracting Saptiva LLM interactions.

    Responsibilities:
        - Normalize response extraction (handles dict vs object access)
        - Provide unified streaming interface
        - Extract content from various response formats
        - Handle reasoning_content fallback (Saptiva Cortex)
    """

    @staticmethod
    def extract_content_from_response(response: Any) -> Tuple[str, bool]:
        """
        Extract content from a Saptiva response, handling various formats.

        Handles:
        - Raw string responses (edge cases)
        - Dict-style choices[0].message.content
        - Object-style choices[0].message.content
        - Saptiva Cortex reasoning_content fallback

        Args:
            response: The raw response from Saptiva API

        Returns:
            Tuple of (content, has_reasoning)
            - content: The extracted text content
            - has_reasoning: Whether reasoning_content was used
        """
        if not response:
            return "", False

        # Handle raw string response (edge cases/mocks)
        if isinstance(response, str):
            return response, False

        # Check for choices array
        choices = getattr(response, "choices", None)
        if not choices or len(choices) == 0:
            logger.warning(
                "saptiva_streamer.no_choices",
                response_type=type(response).__name__,
            )
            return "", False

        choice = choices[0]
        content = ""
        has_reasoning = False

        # Dict-style access (most common with Saptiva)
        if isinstance(choice, dict):
            message = choice.get("message", {}) or {}
            if isinstance(message, dict):
                content = message.get("content", "") or ""
                reasoning_content = message.get("reasoning_content", "") or ""
                # Saptiva Cortex sometimes sends reasoning_content only
                if not content and reasoning_content:
                    content = reasoning_content
                    has_reasoning = True
            else:
                content = ""
        else:
            # Object-style access (fallback)
            message = getattr(choice, "message", None)
            if message:
                content = getattr(message, "content", "") or ""
                reasoning_content = getattr(message, "reasoning_content", "") or ""
                if not content and reasoning_content:
                    content = reasoning_content
                    has_reasoning = True

        return content, has_reasoning

    @staticmethod
    def extract_chunk_content(chunk: Any) -> str:
        """
        Extract content from a streaming chunk.

        Args:
            chunk: A SaptivaStreamChunk object

        Returns:
            The content string from the chunk (may be empty)
        """
        if not chunk:
            return ""

        choices = getattr(chunk, "choices", None)
        if not choices or len(choices) == 0:
            return ""

        choice = choices[0]

        # Dict-style access
        if isinstance(choice, dict):
            delta = choice.get("delta", {})
            if isinstance(delta, dict):
                return delta.get("content", "") or ""
            return ""

        # Object-style access (fallback)
        delta = getattr(choice, "delta", None)
        if delta:
            return getattr(delta, "content", "") or ""

        return ""

    @staticmethod
    async def get_completion(
        saptiva_client,
        messages: List[Dict[str, Any]],
        config: StreamerConfig,
    ) -> CompletionResult:
        """
        Get a non-streaming completion from Saptiva.

        Args:
            saptiva_client: The Saptiva client instance
            messages: List of message dicts for the API
            config: Streamer configuration

        Returns:
            CompletionResult with extracted content
        """
        logger.info(
            "saptiva_streamer.completion_start",
            model=config.model,
            message_count=len(messages),
            max_tokens=config.max_tokens,
        )

        try:
            response = await saptiva_client.chat_completion(
                messages=messages,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

            content, has_reasoning = SaptivaStreamer.extract_content_from_response(
                response
            )

            logger.info(
                "saptiva_streamer.completion_done",
                content_length=len(content),
                has_reasoning=has_reasoning,
            )

            return CompletionResult(
                content=content,
                has_reasoning=has_reasoning,
                raw_response=response,
            )

        except Exception as e:
            logger.error(
                "saptiva_streamer.completion_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    @staticmethod
    async def stream_completion(
        saptiva_client,
        messages: List[Dict[str, Any]],
        config: StreamerConfig,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion chunks from Saptiva.

        Yields only non-empty content strings, abstracting away the
        chunk parsing logic.

        Args:
            saptiva_client: The Saptiva client instance
            messages: List of message dicts for the API
            config: Streamer configuration

        Yields:
            Content strings from each chunk
        """
        logger.info(
            "saptiva_streamer.stream_start",
            model=config.model,
            message_count=len(messages),
            max_tokens=config.max_tokens,
        )

        chunk_count = 0
        total_content_length = 0

        try:
            async for chunk in saptiva_client.chat_completion_stream(
                messages=messages,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
            ):
                content = SaptivaStreamer.extract_chunk_content(chunk)
                if content:
                    chunk_count += 1
                    total_content_length += len(content)
                    yield content

            logger.info(
                "saptiva_streamer.stream_done",
                chunk_count=chunk_count,
                total_content_length=total_content_length,
            )

        except Exception as e:
            logger.error(
                "saptiva_streamer.stream_error",
                error=str(e),
                error_type=type(e).__name__,
                chunks_before_error=chunk_count,
            )
            raise

    @staticmethod
    async def get_full_streamed_response(
        saptiva_client,
        messages: List[Dict[str, Any]],
        config: StreamerConfig,
    ) -> str:
        """
        Stream completion and return full accumulated response.

        Convenience method when you need the full response but still
        want to use streaming (e.g., for timeout handling).

        Args:
            saptiva_client: The Saptiva client instance
            messages: List of message dicts for the API
            config: Streamer configuration

        Returns:
            Full accumulated response string
        """
        full_response = ""
        async for content in SaptivaStreamer.stream_completion(
            saptiva_client, messages, config
        ):
            full_response += content

        return full_response
