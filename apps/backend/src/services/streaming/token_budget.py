"""
Token Budget Manager Service.

Extracted from streaming_handler.py for better testability.
Handles token estimation, dynamic max_tokens calculation, and message truncation.

REFACTOR-001: Phase 4 extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenBudgetResult:
    """Result of token budget calculation."""

    max_tokens: int
    estimated_prompt_tokens: int
    total_chars: int
    messages_truncated: int
    will_exceed_limit: bool


class TokenBudgetManager:
    """
    Service for managing token budgets in LLM API calls.

    Responsibilities:
        - Estimate token count from messages
        - Calculate optimal max_tokens dynamically
        - Truncate message history when exceeding limits
        - Detect and warn about potential token overflows
    """

    # Default configuration
    DEFAULT_MODEL_LIMIT = 8192  # Saptiva Turbo limit
    DEFAULT_MIN_TOKENS = 500
    DEFAULT_MAX_TOKENS = 3000
    DEFAULT_SAFETY_MARGIN = 100
    CHARS_PER_TOKEN = 4  # Conservative GPT-style estimate
    TRUNCATION_THRESHOLD = 6000  # Start truncating at this token count
    CRITICAL_THRESHOLD = 7500  # Log error above this

    @staticmethod
    def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
        """
        Estimate token count from message list.

        Uses conservative GPT-style tokenization: ~1 token per 4 characters.

        Args:
            messages: List of message dicts with 'content' key

        Returns:
            Estimated token count
        """
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        return total_chars // TokenBudgetManager.CHARS_PER_TOKEN

    @staticmethod
    def calculate_dynamic_max_tokens(
        messages: List[Dict[str, Any]],
        model_limit: int = DEFAULT_MODEL_LIMIT,
        min_tokens: int = DEFAULT_MIN_TOKENS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        safety_margin: int = DEFAULT_SAFETY_MARGIN,
    ) -> int:
        """
        Calculate optimal max_tokens based on actual prompt size.

        This prevents context length errors by dynamically adjusting the response
        budget based on how much space the prompt takes.

        Args:
            messages: List of message dicts with 'content' key
            model_limit: Total token limit for the model
            min_tokens: Minimum tokens to allow for response
            max_tokens: Maximum tokens to allow for response
            safety_margin: Extra buffer to prevent edge cases

        Returns:
            Optimal max_tokens value that fits within model limits
        """
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        estimated_prompt_tokens = total_chars // TokenBudgetManager.CHARS_PER_TOKEN

        # Calculate available space for response
        available_tokens = model_limit - estimated_prompt_tokens - safety_margin

        # Clamp to reasonable bounds
        optimal_tokens = max(min_tokens, min(available_tokens, max_tokens))

        logger.debug(
            "token_budget.calculated",
            prompt_chars=total_chars,
            estimated_prompt_tokens=estimated_prompt_tokens,
            available_tokens=available_tokens,
            optimal_max_tokens=optimal_tokens,
            model_limit=model_limit,
        )

        return optimal_tokens

    @staticmethod
    def truncate_messages_if_needed(
        messages: List[Dict[str, Any]],
        threshold: int = TRUNCATION_THRESHOLD,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Truncate message history if it exceeds token threshold.

        Keeps system prompt (index 0) and the current turn: the last user
        message and everything after it (tool results, instructions). Without
        them the narrator answers without question or data (producción,
        2026-11-04). Removes oldest history until under threshold; if the
        current turn alone exceeds it, nothing else is removed.

        Performance: Uses incremental token subtraction instead of
        recalculating entire list after each removal.

        Args:
            messages: List of message dicts (will be modified in place)
            threshold: Token threshold to start truncating

        Returns:
            Tuple of (truncated_messages, count_removed)
        """
        # Calculate initial token estimate once
        estimated_tokens = TokenBudgetManager.estimate_tokens(messages)
        messages_truncated = 0

        # Keep removing oldest messages (after system prompt) until under threshold
        turno_actual = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if messages[i].get("role") == "user"
            ),
            len(messages) - 1,
        )
        while estimated_tokens > threshold and turno_actual > 1:
            # Get token count of message to be removed BEFORE removing
            removed_msg = messages[1]
            removed_chars = len(str(removed_msg.get("content", "")))
            removed_tokens = removed_chars // TokenBudgetManager.CHARS_PER_TOKEN

            # Remove the oldest message (index 1, after system prompt)
            messages.pop(1)
            messages_truncated += 1
            turno_actual -= 1

            # Subtract removed tokens instead of recalculating entire list
            estimated_tokens -= removed_tokens

        if messages_truncated > 0:
            logger.warning(
                "token_budget.messages_truncated",
                messages_removed=messages_truncated,
                remaining_messages=len(messages),
                estimated_tokens=estimated_tokens,
            )

        return messages, messages_truncated

    @staticmethod
    def check_token_overflow(
        messages: List[Dict[str, Any]],
        model_limit: int = DEFAULT_MODEL_LIMIT,
        critical_threshold: int = CRITICAL_THRESHOLD,
    ) -> bool:
        """
        Check if prompt is likely to exceed model limits.

        Args:
            messages: List of message dicts
            model_limit: Total token limit for the model
            critical_threshold: Threshold for critical warning

        Returns:
            True if overflow is likely, False otherwise
        """
        estimated_tokens = TokenBudgetManager.estimate_tokens(messages)

        if estimated_tokens > critical_threshold:
            logger.error(
                "token_budget.overflow_likely",
                estimated_prompt_tokens=estimated_tokens,
                model_limit=model_limit,
                critical_threshold=critical_threshold,
            )
            return True

        return False

    @staticmethod
    def prepare_messages_for_api(
        messages: List[Dict[str, Any]],
        model_limit: int = DEFAULT_MODEL_LIMIT,
        min_tokens: int = DEFAULT_MIN_TOKENS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> TokenBudgetResult:
        """
        Prepare messages for API call with full token budget management.

        Performs:
        1. Calculate dynamic max_tokens
        2. Truncate if needed
        3. Check for overflow warnings

        Args:
            messages: List of message dicts (will be modified in place)
            model_limit: Total token limit for the model
            min_tokens: Minimum tokens for response
            max_tokens: Maximum tokens for response

        Returns:
            TokenBudgetResult with all budget information
        """
        # Step 1: Calculate initial token estimate
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        initial_tokens = total_chars // TokenBudgetManager.CHARS_PER_TOKEN

        # Step 2: Calculate dynamic max_tokens
        dynamic_max = TokenBudgetManager.calculate_dynamic_max_tokens(
            messages=messages,
            model_limit=model_limit,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
        )

        # Step 3: Truncate if needed
        messages, truncated_count = TokenBudgetManager.truncate_messages_if_needed(
            messages=messages,
            threshold=TokenBudgetManager.TRUNCATION_THRESHOLD,
        )

        # Step 4: Final token estimate after truncation
        final_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        final_tokens = final_chars // TokenBudgetManager.CHARS_PER_TOKEN

        # Step 5: Check for overflow
        will_exceed = TokenBudgetManager.check_token_overflow(
            messages=messages,
            model_limit=model_limit,
        )

        # Log full budget calculation
        logger.info(
            "token_budget.prepared",
            prompt_chars=final_chars,
            estimated_prompt_tokens=final_tokens,
            dynamic_max_tokens=dynamic_max,
            total_estimated=final_tokens + dynamic_max,
            model_limit=model_limit,
            messages_truncated=truncated_count,
            will_exceed=will_exceed,
        )

        return TokenBudgetResult(
            max_tokens=dynamic_max,
            estimated_prompt_tokens=final_tokens,
            total_chars=final_chars,
            messages_truncated=truncated_count,
            will_exceed_limit=will_exceed,
        )
