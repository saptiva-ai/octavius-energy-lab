"""
Unit tests for system_prompt_builder module.

Tests:
- PromptBuildResult dataclass
- SystemPromptBuilder.build_tools_markdown
"""

import pytest

from src.services.streaming.system_prompt_builder import (
    PromptBuildResult,
    SystemPromptBuilder,
)

pytestmark = [pytest.mark.unit]


class TestPromptBuildResult:
    """Test PromptBuildResult dataclass."""

    def test_create_result(self):
        """Test creating result object."""
        result = PromptBuildResult(
            system_prompt="You are an assistant",
            model_params={"temperature": 0.7},
            is_clarification=False,
        )

        assert result.system_prompt == "You are an assistant"
        assert result.model_params == {"temperature": 0.7}
        assert result.is_clarification is False

    def test_with_clarification(self):
        """Test result with clarification flag."""
        result = PromptBuildResult(
            system_prompt="Clarify",
            model_params={},
            is_clarification=True,
        )

        assert result.is_clarification is True


class TestBuildToolsMarkdown:
    """Test SystemPromptBuilder.build_tools_markdown method."""

    def test_returns_none_when_no_documents(self):
        """Test returns None when has_documents is False."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=False)

        assert result is None

    def test_returns_markdown_when_documents_exist(self):
        """Test returns markdown when has_documents is True."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=True)

        assert result is not None
        assert "get_relevant_segments" in result

    def test_markdown_includes_parameters(self):
        """Test markdown includes parameter description."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=True)

        assert "conversation_id" in result
        assert "question" in result
        assert "max_segments" in result

    def test_markdown_includes_usage(self):
        """Test markdown includes usage guidance."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=True)

        assert "Use when" in result
        assert "document" in result.lower()
