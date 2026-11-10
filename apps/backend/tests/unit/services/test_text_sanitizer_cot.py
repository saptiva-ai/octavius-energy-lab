"""
Unit tests for chain-of-thought stripping in text_sanitizer.

BUG-2026-01-30: Tests the strip_chain_of_thought function that removes
internal reasoning patterns that leak into LLM responses.
"""

import pytest
from src.services.text_sanitizer import strip_chain_of_thought, sanitize_response_content


class TestStripChainOfThought:
    """Tests for strip_chain_of_thought function."""

    def test_strips_okay_lets_see(self):
        """Should strip 'Okay, let's see' pattern."""
        text = "Okay, let's see. The ICAP of BBVA is 20.05%."
        result = strip_chain_of_thought(text)
        assert "Okay" not in result
        assert "let's see" not in result
        assert "ICAP" in result
        assert "20.05%" in result

    def test_strips_let_me_check(self):
        """Should strip 'Let me check' pattern."""
        text = "Let me check the data. El ICAP es 20%."
        result = strip_chain_of_thought(text)
        assert "Let me check" not in result
        assert "El ICAP es 20%" in result

    def test_strips_wait_but(self):
        """Should strip 'Wait, but' pattern."""
        text = "Wait, but that's not right. El valor correcto es 19.5%."
        result = strip_chain_of_thought(text)
        assert "Wait" not in result
        assert "El valor correcto es 19.5%" in result

    def test_strips_user_is_asking(self):
        """Should strip 'The user is asking' meta-commentary."""
        text = "The user is asking about ICAP. El ICAP de BBVA es 20%."
        result = strip_chain_of_thought(text)
        assert "The user is asking" not in result
        assert "El ICAP de BBVA es 20%" in result

    def test_strips_hmm_actually(self):
        """Should strip 'Hmm, actually' pattern."""
        text = "Hmm, actually let me reconsider. El dato correcto es 18%."
        result = strip_chain_of_thought(text)
        assert "Hmm" not in result
        assert "actually" not in result
        assert "El dato correcto es 18%" in result

    def test_strips_on_second_thought(self):
        """Should strip 'On second thought' pattern."""
        text = "On second thought, I should verify. La tendencia es creciente."
        result = strip_chain_of_thought(text)
        assert "On second thought" not in result
        assert "La tendencia es creciente" in result

    def test_preserves_valid_content(self):
        """Should preserve content without CoT patterns."""
        text = "El ICAP de BBVA es 20.05% al cierre de octubre 2025."
        result = strip_chain_of_thought(text)
        assert result == text

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_chain_of_thought("") == ""

    def test_handles_none(self):
        """Should handle None by returning empty string or None."""
        result = strip_chain_of_thought(None)
        assert result is None or result == ""

    def test_multiple_patterns(self):
        """Should strip multiple CoT patterns in same text."""
        text = (
            "Okay, let's see. The user is asking about ICAP. "
            "Wait, but I need to check. El ICAP es 20%."
        )
        result = strip_chain_of_thought(text)
        assert "Okay" not in result
        assert "The user is asking" not in result
        assert "Wait" not in result
        assert "El ICAP es 20%" in result

    def test_case_insensitive(self):
        """Should be case insensitive."""
        text = "OKAY, LET'S SEE. El dato es 20%."
        result = strip_chain_of_thought(text)
        assert "OKAY" not in result
        assert "El dato es 20%" in result


class TestSanitizeResponseContentWithCot:
    """Tests for sanitize_response_content with CoT stripping."""

    def test_strips_cot_before_other_sanitization(self):
        """Should strip CoT patterns as part of full sanitization."""
        text = "Okay, let's see. **Resumen:**\nEl ICAP es 20%."
        result = sanitize_response_content(text)
        assert "Okay" not in result
        assert "Resumen" not in result  # Section heading also stripped
        assert "El ICAP es 20%" in result

    def test_disabled_sanitization_preserves_cot(self):
        """When sanitization disabled, should preserve CoT."""
        text = "Okay, let's see. El dato es 20%."
        result = sanitize_response_content(text, enable_sanitization=False)
        assert result == text

    def test_full_pipeline(self):
        """Test full sanitization pipeline with realistic input."""
        text = (
            "Let me check the data. "
            "**Resumen:**\n"
            "El ICAP de BBVA es **20.05%** al cierre de octubre.\n"
            "```sql\nSELECT * FROM banks;\n```"
        )
        result = sanitize_response_content(text)
        # CoT stripped
        assert "Let me check" not in result
        # Section heading stripped
        assert "Resumen" not in result
        # SQL stripped
        assert "SELECT" not in result
        # Actual content preserved
        assert "ICAP" in result
        assert "20.05%" in result
