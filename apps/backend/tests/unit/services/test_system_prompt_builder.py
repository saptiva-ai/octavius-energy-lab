"""
Unit tests for SystemPromptBuilder - System prompt construction service.

Tests cover:
- Building tools markdown
- Building complete system prompts
- Handling document context
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.streaming.system_prompt_builder import (
    PromptBuildResult,
    SystemPromptBuilder,
)


@pytest.mark.unit
class TestPromptBuildResult:
    """Tests for PromptBuildResult dataclass."""

    def test_creation(self):
        """Should create PromptBuildResult with all fields."""
        result = PromptBuildResult(
            system_prompt="You are a helpful assistant",
            model_params={"temperature": 0.7},
            is_clarification=False,
        )

        assert result.system_prompt == "You are a helpful assistant"
        assert result.model_params == {"temperature": 0.7}
        assert result.is_clarification is False

    def test_with_clarification_flag(self):
        """Should handle clarification flag."""
        result = PromptBuildResult(
            system_prompt="Prompt",
            model_params={},
            is_clarification=True,
        )

        assert result.is_clarification is True


@pytest.mark.unit
class TestBuildToolsMarkdown:
    """Tests for build_tools_markdown method."""

    def test_returns_none_without_documents(self):
        """Should return None when no documents available."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=False)
        assert result is None

    def test_returns_markdown_with_documents(self):
        """Should return tools markdown when documents available."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=True)

        assert result is not None
        assert "get_relevant_segments" in result
        assert "conversation_id" in result
        assert "question" in result
        assert "max_segments" in result

    def test_markdown_includes_usage_guidance(self):
        """Should include when to use guidance."""
        result = SystemPromptBuilder.build_tools_markdown(has_documents=True)

        assert "Use when" in result
        assert "uploaded documents" in result


@pytest.mark.unit
class TestBuild:
    """Tests for build method."""

    @pytest.fixture
    def mock_prompt_registry(self):
        """Create mock prompt registry."""
        mock_registry = MagicMock()
        mock_registry.resolve.return_value = (
            "Base system prompt",
            {"temperature": 0.7, "max_tokens": 3000}
        )
        return mock_registry

    def test_build_minimal_prompt(self, mock_prompt_registry):
        """Should build minimal prompt without extra context."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            result = SystemPromptBuilder.build(
                model="saptiva-1",
                document_context=None,
                document_ids=None,
            )

            assert isinstance(result, PromptBuildResult)
            assert result.system_prompt == "Base system prompt"
            assert result.model_params == {"temperature": 0.7, "max_tokens": 3000}
            assert result.is_clarification is False

    def test_build_with_document_context(self, mock_prompt_registry):
        """Should append document context to system prompt."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            result = SystemPromptBuilder.build(
                model="saptiva-1",
                document_context="Document content here",
                document_ids=["doc-1"],
            )

            assert "CONTEXTO DOCUMENTAL" in result.system_prompt
            assert "Document content here" in result.system_prompt

    def test_build_resolves_prompt_for_model(self, mock_prompt_registry):
        """Should resolve prompt with correct model."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            SystemPromptBuilder.build(
                model="gpt-4",
                document_context=None,
                document_ids=None,
            )

            mock_prompt_registry.resolve.assert_called_once()
            call_kwargs = mock_prompt_registry.resolve.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4"
            assert call_kwargs["channel"] == "chat"

    def test_build_passes_tools_markdown_when_documents(self, mock_prompt_registry):
        """Should pass tools markdown to registry when documents available."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            SystemPromptBuilder.build(
                model="saptiva-1",
                document_context="Some context",
                document_ids=["doc-1"],
            )

            call_kwargs = mock_prompt_registry.resolve.call_args.kwargs
            assert call_kwargs["tools_markdown"] is not None
            assert "get_relevant_segments" in call_kwargs["tools_markdown"]

    def test_build_no_tools_markdown_without_documents(self, mock_prompt_registry):
        """Should not pass tools markdown when no documents."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            SystemPromptBuilder.build(
                model="saptiva-1",
                document_context=None,
                document_ids=None,
            )

            call_kwargs = mock_prompt_registry.resolve.call_args.kwargs
            assert call_kwargs["tools_markdown"] is None

    def test_build_document_ids_without_context(self, mock_prompt_registry):
        """Should treat document_ids as having documents even without context."""
        with patch(
            'src.core.prompt_registry.get_prompt_registry',
            return_value=mock_prompt_registry
        ):
            SystemPromptBuilder.build(
                model="saptiva-1",
                document_context=None,
                document_ids=["doc-1"],  # Has document_ids but no context
            )

            # Should still include tools_markdown
            call_kwargs = mock_prompt_registry.resolve.call_args.kwargs
            assert call_kwargs["tools_markdown"] is not None
