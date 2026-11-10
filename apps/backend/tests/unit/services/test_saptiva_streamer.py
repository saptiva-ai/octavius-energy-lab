"""
Unit tests for SaptivaStreamer - LLM interaction abstraction service.

Tests cover:
- Content extraction from various response formats (dict, object, string)
- Chunk content extraction for streaming
- Non-streaming completion
- Streaming completion
- Error handling
- Saptiva Cortex reasoning_content fallback
"""

from dataclasses import dataclass
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.streaming.saptiva_streamer import (
    CompletionResult,
    SaptivaStreamer,
    StreamerConfig,
)


@pytest.fixture
def default_config():
    """Create default StreamerConfig."""
    return StreamerConfig(
        model="gpt-4",
        temperature=0.7,
        max_tokens=3000,
        timeout=120,
    )


@pytest.mark.unit
class TestStreamerConfig:
    """Tests for StreamerConfig dataclass."""

    def test_config_with_defaults(self):
        """Should create config with default values."""
        config = StreamerConfig(model="gpt-4")

        assert config.model == "gpt-4"
        assert config.temperature == 0.7
        assert config.max_tokens == 3000
        assert config.timeout == 120

    def test_config_with_custom_values(self):
        """Should create config with custom values."""
        config = StreamerConfig(
            model="custom-model",
            temperature=0.5,
            max_tokens=1000,
            timeout=60,
        )

        assert config.model == "custom-model"
        assert config.temperature == 0.5
        assert config.max_tokens == 1000
        assert config.timeout == 60


@pytest.mark.unit
class TestCompletionResult:
    """Tests for CompletionResult dataclass."""

    def test_result_creation(self):
        """Should create CompletionResult with all fields."""
        result = CompletionResult(
            content="Hello world",
            has_reasoning=False,
            raw_response={"choices": []},
        )

        assert result.content == "Hello world"
        assert result.has_reasoning is False
        assert result.raw_response == {"choices": []}

    def test_result_with_reasoning(self):
        """Should create result with reasoning flag."""
        result = CompletionResult(
            content="Reasoned response",
            has_reasoning=True,
        )

        assert result.has_reasoning is True
        assert result.raw_response is None


@pytest.mark.unit
class TestExtractContentFromResponse:
    """Tests for extract_content_from_response method."""

    def test_extract_from_none_response(self):
        """Should return empty string for None response."""
        content, has_reasoning = SaptivaStreamer.extract_content_from_response(None)

        assert content == ""
        assert has_reasoning is False

    def test_extract_from_string_response(self):
        """Should handle raw string response."""
        content, has_reasoning = SaptivaStreamer.extract_content_from_response(
            "Raw string response"
        )

        assert content == "Raw string response"
        assert has_reasoning is False

    def test_extract_from_dict_style_response(self):
        """Should extract content from dict-style response."""
        response = MagicMock()
        response.choices = [{"message": {"content": "Dict content"}}]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == "Dict content"
        assert has_reasoning is False

    def test_extract_from_object_style_response(self):
        """Should extract content from object-style response."""

        class ObjectMessage:
            content = "Object content"
            reasoning_content = ""

        class ObjectChoice:
            message = ObjectMessage()

        class ObjectResponse:
            choices = [ObjectChoice()]

        response = ObjectResponse()

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == "Object content"
        assert has_reasoning is False

    def test_extract_with_reasoning_content_fallback_dict(self):
        """Should use reasoning_content when content is empty (dict style)."""
        response = MagicMock()
        response.choices = [
            {"message": {"content": "", "reasoning_content": "Reasoned output"}}
        ]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == "Reasoned output"
        assert has_reasoning is True

    def test_extract_with_reasoning_content_fallback_object(self):
        """Should use reasoning_content when content is empty (object style)."""
        message = MagicMock()
        message.content = ""
        message.reasoning_content = "Object reasoned output"

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == "Object reasoned output"
        assert has_reasoning is True

    def test_extract_empty_choices(self):
        """Should return empty for response with no choices."""
        response = MagicMock()
        response.choices = []

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == ""
        assert has_reasoning is False

    def test_extract_none_choices(self):
        """Should return empty for response with None choices."""
        response = MagicMock()
        response.choices = None

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == ""
        assert has_reasoning is False

    def test_extract_with_none_content(self):
        """Should handle None content in dict response."""
        response = MagicMock()
        response.choices = [{"message": {"content": None}}]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == ""
        assert has_reasoning is False

    def test_extract_with_none_message_dict(self):
        """Should handle None message in dict response."""
        response = MagicMock()
        response.choices = [{"message": None}]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == ""
        assert has_reasoning is False

    def test_extract_non_dict_message_in_dict_choice(self):
        """Should handle non-dict message value in dict choice."""
        response = MagicMock()
        response.choices = [{"message": "not a dict"}]

        content, has_reasoning = SaptivaStreamer.extract_content_from_response(response)

        assert content == ""
        assert has_reasoning is False


@pytest.mark.unit
class TestExtractChunkContent:
    """Tests for extract_chunk_content method."""

    def test_extract_from_none_chunk(self):
        """Should return empty for None chunk."""
        content = SaptivaStreamer.extract_chunk_content(None)
        assert content == ""

    def test_extract_from_dict_style_chunk(self):
        """Should extract content from dict-style chunk."""
        chunk = MagicMock()
        chunk.choices = [{"delta": {"content": "Chunk content"}}]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == "Chunk content"

    def test_extract_from_object_style_chunk(self):
        """Should extract content from object-style chunk."""
        delta = MagicMock()
        delta.content = "Object chunk"

        choice = MagicMock()
        choice.delta = delta

        chunk = MagicMock()
        chunk.choices = [choice]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == "Object chunk"

    def test_extract_empty_choices_chunk(self):
        """Should return empty for chunk with no choices."""
        chunk = MagicMock()
        chunk.choices = []

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""

    def test_extract_none_choices_chunk(self):
        """Should return empty for chunk with None choices."""
        chunk = MagicMock()
        chunk.choices = None

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""

    def test_extract_none_content_in_chunk(self):
        """Should handle None content in chunk delta."""
        chunk = MagicMock()
        chunk.choices = [{"delta": {"content": None}}]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""

    def test_extract_empty_delta_dict(self):
        """Should handle empty delta dict."""
        chunk = MagicMock()
        chunk.choices = [{"delta": {}}]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""

    def test_extract_non_dict_delta(self):
        """Should handle non-dict delta value."""
        chunk = MagicMock()
        chunk.choices = [{"delta": "not a dict"}]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""

    def test_extract_choice_without_delta_attribute(self):
        """Should return empty when choice has no delta (neither dict nor object)."""
        # Create a choice object that is not a dict and has no delta attribute
        class BareChoice:
            pass

        chunk = MagicMock()
        chunk.choices = [BareChoice()]

        content = SaptivaStreamer.extract_chunk_content(chunk)

        assert content == ""


@pytest.mark.unit
class TestGetCompletion:
    """Tests for get_completion method."""

    @pytest.mark.asyncio
    async def test_completion_success(self, default_config):
        """Should return CompletionResult on success."""
        mock_client = AsyncMock()
        response = MagicMock()
        response.choices = [{"message": {"content": "Completion response"}}]
        mock_client.chat_completion.return_value = response

        messages = [{"role": "user", "content": "Hello"}]

        result = await SaptivaStreamer.get_completion(
            mock_client, messages, default_config
        )

        assert isinstance(result, CompletionResult)
        assert result.content == "Completion response"
        assert result.has_reasoning is False
        assert result.raw_response == response

    @pytest.mark.asyncio
    async def test_completion_with_reasoning(self, default_config):
        """Should flag reasoning_content when used."""
        mock_client = AsyncMock()
        response = MagicMock()
        response.choices = [
            {"message": {"content": "", "reasoning_content": "Reasoned"}}
        ]
        mock_client.chat_completion.return_value = response

        messages = [{"role": "user", "content": "Think about this"}]

        result = await SaptivaStreamer.get_completion(
            mock_client, messages, default_config
        )

        assert result.content == "Reasoned"
        assert result.has_reasoning is True

    @pytest.mark.asyncio
    async def test_completion_uses_config(self, default_config):
        """Should pass config values to client."""
        mock_client = AsyncMock()
        response = MagicMock()
        response.choices = [{"message": {"content": "Response"}}]
        mock_client.chat_completion.return_value = response

        messages = [{"role": "user", "content": "Hello"}]

        await SaptivaStreamer.get_completion(mock_client, messages, default_config)

        mock_client.chat_completion.assert_called_once_with(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=3000,
        )

    @pytest.mark.asyncio
    async def test_completion_error_propagates(self, default_config):
        """Should propagate client errors."""
        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = Exception("API Error")

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception, match="API Error"):
            await SaptivaStreamer.get_completion(mock_client, messages, default_config)


@pytest.mark.unit
class TestStreamCompletion:
    """Tests for stream_completion method."""

    @pytest.mark.asyncio
    async def test_stream_yields_content(self, default_config):
        """Should yield content from chunks."""
        # Create async generator mock that accepts kwargs
        async def mock_stream(**kwargs):
            for content in ["Hello ", "world", "!"]:
                chunk = MagicMock()
                chunk.choices = [{"delta": {"content": content}}]
                yield chunk

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        results = []
        async for content in SaptivaStreamer.stream_completion(
            mock_client, messages, default_config
        ):
            results.append(content)

        assert results == ["Hello ", "world", "!"]

    @pytest.mark.asyncio
    async def test_stream_filters_empty_content(self, default_config):
        """Should not yield empty content."""
        async def mock_stream(**kwargs):
            for content in ["Content", "", "More", None]:
                chunk = MagicMock()
                chunk.choices = [{"delta": {"content": content}}]
                yield chunk

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        results = []
        async for content in SaptivaStreamer.stream_completion(
            mock_client, messages, default_config
        ):
            results.append(content)

        assert results == ["Content", "More"]

    @pytest.mark.asyncio
    async def test_stream_uses_config(self, default_config):
        """Should pass config values to client."""
        call_args = {}

        async def mock_stream(**kwargs):
            call_args.update(kwargs)
            if False:
                yield  # Make it a generator

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        async for _ in SaptivaStreamer.stream_completion(
            mock_client, messages, default_config
        ):
            pass

        assert call_args["model"] == "gpt-4"
        assert call_args["temperature"] == 0.7
        assert call_args["max_tokens"] == 3000
        assert call_args["timeout"] == 120

    @pytest.mark.asyncio
    async def test_stream_error_propagates(self, default_config):
        """Should propagate streaming errors."""
        async def mock_stream(**kwargs):
            yield MagicMock(choices=[{"delta": {"content": "Start"}}])
            raise Exception("Stream error")

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception, match="Stream error"):
            async for _ in SaptivaStreamer.stream_completion(
                mock_client, messages, default_config
            ):
                pass


@pytest.mark.unit
class TestGetFullStreamedResponse:
    """Tests for get_full_streamed_response method."""

    @pytest.mark.asyncio
    async def test_accumulates_full_response(self, default_config):
        """Should accumulate all chunks into full response."""
        async def mock_stream(**kwargs):
            for content in ["Hello ", "beautiful ", "world!"]:
                chunk = MagicMock()
                chunk.choices = [{"delta": {"content": content}}]
                yield chunk

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        result = await SaptivaStreamer.get_full_streamed_response(
            mock_client, messages, default_config
        )

        assert result == "Hello beautiful world!"

    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_string(self, default_config):
        """Should return empty string for empty stream."""
        async def mock_stream(**kwargs):
            if False:
                yield  # Empty generator

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        result = await SaptivaStreamer.get_full_streamed_response(
            mock_client, messages, default_config
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_error_propagates(self, default_config):
        """Should propagate errors from stream."""
        async def mock_stream(**kwargs):
            raise Exception("Full stream error")
            yield  # type: ignore

        mock_client = MagicMock()
        mock_client.chat_completion_stream = mock_stream

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception, match="Full stream error"):
            await SaptivaStreamer.get_full_streamed_response(
                mock_client, messages, default_config
            )
