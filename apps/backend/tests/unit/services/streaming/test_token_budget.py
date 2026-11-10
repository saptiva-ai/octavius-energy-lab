"""
Unit tests for token_budget module.

Tests:
- TokenBudgetResult dataclass
- TokenBudgetManager methods
"""

import pytest

from src.services.streaming.token_budget import (
    TokenBudgetManager,
    TokenBudgetResult,
)

pytestmark = [pytest.mark.unit]


class TestTokenBudgetResult:
    """Test TokenBudgetResult dataclass."""

    def test_create_result(self):
        """Test creating result object."""
        result = TokenBudgetResult(
            max_tokens=1000,
            estimated_prompt_tokens=500,
            total_chars=2000,
            messages_truncated=2,
            will_exceed_limit=False,
        )

        assert result.max_tokens == 1000
        assert result.estimated_prompt_tokens == 500
        assert result.total_chars == 2000
        assert result.messages_truncated == 2
        assert result.will_exceed_limit is False


class TestTokenBudgetManagerConstants:
    """Test TokenBudgetManager constants."""

    def test_default_model_limit(self):
        """Test default model limit."""
        assert TokenBudgetManager.DEFAULT_MODEL_LIMIT == 8192

    def test_chars_per_token(self):
        """Test chars per token estimate."""
        assert TokenBudgetManager.CHARS_PER_TOKEN == 4

    def test_truncation_threshold(self):
        """Test truncation threshold."""
        assert TokenBudgetManager.TRUNCATION_THRESHOLD == 6000

    def test_critical_threshold(self):
        """Test critical threshold."""
        assert TokenBudgetManager.CRITICAL_THRESHOLD == 7500


class TestEstimateTokens:
    """Test estimate_tokens method."""

    def test_empty_messages(self):
        """Test empty message list."""
        tokens = TokenBudgetManager.estimate_tokens([])
        assert tokens == 0

    def test_single_message(self):
        """Test single message estimation."""
        messages = [{"content": "Hello World"}]  # 11 chars

        tokens = TokenBudgetManager.estimate_tokens(messages)

        # 11 / 4 = 2
        assert tokens == 2

    def test_multiple_messages(self):
        """Test multiple messages."""
        messages = [
            {"content": "First message"},  # 13 chars
            {"content": "Second message"},  # 14 chars
        ]

        tokens = TokenBudgetManager.estimate_tokens(messages)

        # (13 + 14) / 4 = 6
        assert tokens == 6

    def test_missing_content(self):
        """Test message without content key."""
        messages = [{"role": "user"}]

        tokens = TokenBudgetManager.estimate_tokens(messages)

        assert tokens == 0

    def test_large_message(self):
        """Test large message."""
        messages = [{"content": "x" * 1000}]

        tokens = TokenBudgetManager.estimate_tokens(messages)

        assert tokens == 250  # 1000 / 4


class TestCalculateDynamicMaxTokens:
    """Test calculate_dynamic_max_tokens method."""

    def test_small_prompt_gets_max_tokens(self):
        """Test small prompt gets maximum response tokens."""
        messages = [{"content": "Hi"}]

        max_tokens = TokenBudgetManager.calculate_dynamic_max_tokens(
            messages, model_limit=8192, max_tokens=3000
        )

        assert max_tokens == 3000

    def test_large_prompt_reduces_max_tokens(self):
        """Test large prompt reduces available response tokens."""
        # Create large prompt (7000 chars = 1750 tokens)
        messages = [{"content": "x" * 7000}]

        max_tokens = TokenBudgetManager.calculate_dynamic_max_tokens(
            messages, model_limit=8192, max_tokens=3000
        )

        # Available = 8192 - 1750 - 100 (safety) = 6342
        # But capped at max_tokens=3000
        assert max_tokens == 3000

    def test_very_large_prompt_gets_min_tokens(self):
        """Test very large prompt still gets minimum tokens."""
        # Create huge prompt (32000 chars = 8000 tokens > model limit)
        messages = [{"content": "x" * 32000}]

        max_tokens = TokenBudgetManager.calculate_dynamic_max_tokens(
            messages, model_limit=8192, min_tokens=500
        )

        # Even if available is negative, clamp to min_tokens
        assert max_tokens >= 500

    def test_custom_model_limit(self):
        """Test custom model limit."""
        messages = [{"content": "Test"}]

        max_tokens = TokenBudgetManager.calculate_dynamic_max_tokens(
            messages, model_limit=4096, max_tokens=2000
        )

        assert max_tokens <= 2000


class TestTruncateMessagesIfNeeded:
    """Test truncate_messages_if_needed method."""

    def test_no_truncation_needed(self):
        """Test no truncation when under threshold."""
        messages = [
            {"content": "System prompt"},
            {"content": "User message"},
        ]

        result, count = TokenBudgetManager.truncate_messages_if_needed(
            messages, threshold=6000
        )

        assert count == 0
        assert len(result) == 2

    def test_truncates_when_over_threshold(self):
        """Test truncation when over threshold."""
        messages = [
            {"content": "System"},  # Keep this (index 0)
            {"content": "x" * 10000},  # Remove this first
            {"content": "x" * 10000},  # Then this
            {"content": "Current"},  # Keep this (last)
        ]

        result, count = TokenBudgetManager.truncate_messages_if_needed(
            messages.copy(), threshold=100
        )

        # Should remove middle messages
        assert count > 0

    def test_keeps_system_prompt_and_current(self):
        """Test system prompt and current message are preserved."""
        messages = [
            {"content": "System prompt - keep this"},
            {"content": "x" * 30000},
            {"content": "Current message - keep this"},
        ]

        result, _ = TokenBudgetManager.truncate_messages_if_needed(
            messages.copy(), threshold=100
        )

        # Should keep at least 2 messages
        assert len(result) >= 2

    def test_minimum_two_messages(self):
        """Test at least 2 messages are always kept."""
        messages = [
            {"content": "System"},
            {"content": "x" * 100000},  # Huge
        ]

        result, _ = TokenBudgetManager.truncate_messages_if_needed(
            messages.copy(), threshold=10
        )

        # Can't truncate below 2 messages
        assert len(result) == 2


class TestCheckTokenOverflow:
    """Test check_token_overflow method."""

    def test_no_overflow(self):
        """Test no overflow for small prompt."""
        messages = [{"content": "Small prompt"}]

        will_exceed = TokenBudgetManager.check_token_overflow(
            messages, model_limit=8192, critical_threshold=7500
        )

        assert will_exceed is False

    def test_detects_overflow(self):
        """Test detects overflow for huge prompt."""
        # 32000 chars = 8000 tokens > 7500 threshold
        messages = [{"content": "x" * 32000}]

        will_exceed = TokenBudgetManager.check_token_overflow(
            messages, model_limit=8192, critical_threshold=7500
        )

        assert will_exceed is True

    def test_custom_threshold(self):
        """Test custom critical threshold."""
        messages = [{"content": "x" * 2000}]  # 500 tokens

        will_exceed = TokenBudgetManager.check_token_overflow(
            messages, critical_threshold=400
        )

        assert will_exceed is True


class TestPrepareMessagesForApi:
    """Test prepare_messages_for_api method."""

    def test_returns_token_budget_result(self):
        """Test returns TokenBudgetResult."""
        messages = [{"content": "Test message"}]

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert isinstance(result, TokenBudgetResult)

    def test_calculates_max_tokens(self):
        """Test max_tokens is calculated."""
        messages = [{"content": "Test"}]

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert result.max_tokens > 0
        assert result.max_tokens <= TokenBudgetManager.DEFAULT_MAX_TOKENS

    def test_estimates_prompt_tokens(self):
        """Test prompt tokens are estimated."""
        messages = [{"content": "x" * 100}]  # 25 tokens

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert result.estimated_prompt_tokens == 25

    def test_tracks_total_chars(self):
        """Test total chars are tracked."""
        messages = [{"content": "Hello"}]

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert result.total_chars == 5

    def test_counts_truncated_messages(self):
        """Test truncated message count."""
        # Small messages - no truncation needed
        messages = [{"content": "Short"}]

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert result.messages_truncated == 0

    def test_reports_overflow_status(self):
        """Test overflow status is reported."""
        messages = [{"content": "Normal size message"}]

        result = TokenBudgetManager.prepare_messages_for_api(messages)

        assert result.will_exceed_limit is False

    def test_custom_parameters(self):
        """Test custom parameters are respected."""
        messages = [{"content": "Test"}]

        result = TokenBudgetManager.prepare_messages_for_api(
            messages,
            model_limit=4096,
            min_tokens=100,
            max_tokens=1000,
        )

        assert result.max_tokens <= 1000
        assert result.max_tokens >= 100


class TestTurnoActualIntacto:
    """Producción, 2026-11-04: un resultado de alertas de 48 mil caracteres
    pasó del umbral y el recorte borró la pregunta y el resultado de la tool;
    el narrador recibió solo los dos mensajes de system y contestó un saludo."""

    def _turno(self):
        return [
            {"role": "system", "content": "sistema"},
            {"role": "user", "content": "x" * 8000},
            {"role": "assistant", "content": "y" * 8000},
            {"role": "user", "content": "¿qué está en riesgo?"},
            {"role": "system", "content": "datos " + "z" * 48000},
            {"role": "system", "content": "instrucciones"},
        ]

    def test_no_borra_la_pregunta_ni_lo_que_sigue(self):
        mensajes, quitados = TokenBudgetManager.truncate_messages_if_needed(self._turno())
        assert quitados == 2
        assert [m["role"] for m in mensajes] == ["system", "user", "system", "system"]
        assert mensajes[1]["content"] == "¿qué está en riesgo?"
        assert mensajes[2]["content"].startswith("datos")

    def test_sin_historial_no_quita_nada(self):
        turno = self._turno()
        del turno[1:3]
        mensajes, quitados = TokenBudgetManager.truncate_messages_if_needed(turno)
        assert quitados == 0 and len(mensajes) == 4
