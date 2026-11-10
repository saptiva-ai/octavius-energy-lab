"""
Unit tests for chunk_emitter module.

Tests:
- ChunkEmitter.split_text
- ChunkEmitter.build_chunk_event
- ChunkEmitter.emit_chunks
- ChunkEmitter.emit_text_as_chunks
"""

import asyncio
import json

import pytest

from src.services.streaming.chunk_emitter import ChunkEmitter

pytestmark = [pytest.mark.unit]


class TestSplitText:
    """Test ChunkEmitter.split_text method."""

    def test_splits_text_into_chunks(self):
        """Test text is split into correct chunk sizes."""
        text = "Hello World"
        chunks = ChunkEmitter.split_text(text, chunk_size=5)

        assert chunks == ["Hello", " Worl", "d"]

    def test_single_chunk_if_smaller_than_size(self):
        """Test short text returns single chunk."""
        text = "Hi"
        chunks = ChunkEmitter.split_text(text, chunk_size=10)

        assert chunks == ["Hi"]

    def test_exact_chunk_size(self):
        """Test text exactly matching chunk size."""
        text = "12345"
        chunks = ChunkEmitter.split_text(text, chunk_size=5)

        assert chunks == ["12345"]

    def test_empty_string_returns_empty_list(self):
        """Test empty string returns empty list."""
        chunks = ChunkEmitter.split_text("", chunk_size=5)

        assert chunks == []

    def test_none_returns_empty_list(self):
        """Test None returns empty list."""
        chunks = ChunkEmitter.split_text(None, chunk_size=5)

        assert chunks == []

    def test_default_chunk_size(self):
        """Test default chunk size is used."""
        text = "x" * 100
        chunks = ChunkEmitter.split_text(text)

        # Default is 50 chars
        assert chunks[0] == "x" * 50
        assert chunks[1] == "x" * 50

    def test_unicode_text(self):
        """Test unicode text is handled correctly."""
        text = "Hola México 日本"
        chunks = ChunkEmitter.split_text(text, chunk_size=6)

        # Should split by character count
        assert len(chunks) > 1

    def test_large_text(self):
        """Test large text is split correctly."""
        text = "a" * 500
        chunks = ChunkEmitter.split_text(text, chunk_size=100)

        assert len(chunks) == 5
        assert all(len(c) == 100 for c in chunks)


class TestBuildChunkEvent:
    """Test ChunkEmitter.build_chunk_event method."""

    def test_builds_event_structure(self):
        """Test event has correct structure."""
        event = ChunkEmitter.build_chunk_event("Hello")

        assert event["event"] == "chunk"
        assert "data" in event

    def test_data_is_json(self):
        """Test data is valid JSON."""
        event = ChunkEmitter.build_chunk_event("Test content")

        data = json.loads(event["data"])
        assert data["content"] == "Test content"

    def test_empty_content(self):
        """Test empty content is handled."""
        event = ChunkEmitter.build_chunk_event("")

        data = json.loads(event["data"])
        assert data["content"] == ""

    def test_special_characters(self):
        """Test special characters are properly escaped."""
        content = 'Quote: "test" \n newline'
        event = ChunkEmitter.build_chunk_event(content)

        data = json.loads(event["data"])
        assert data["content"] == content


class TestEmitChunks:
    """Test ChunkEmitter.emit_chunks method."""

    @pytest.mark.asyncio
    async def test_emits_chunks_to_queue(self):
        """Test chunks are emitted to queue."""
        queue = asyncio.Queue()
        text = "Hello World"

        count = await ChunkEmitter.emit_chunks(text, queue, chunk_size=5)

        assert count == 3
        assert queue.qsize() == 3

    @pytest.mark.asyncio
    async def test_empty_text_returns_zero(self):
        """Test empty text returns 0 and emits nothing."""
        queue = asyncio.Queue()

        count = await ChunkEmitter.emit_chunks("", queue, chunk_size=5)

        assert count == 0
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_chunks_are_proper_events(self):
        """Test emitted chunks are proper SSE events."""
        queue = asyncio.Queue()
        text = "Test"

        await ChunkEmitter.emit_chunks(text, queue, chunk_size=10)

        event = await queue.get()
        assert event["event"] == "chunk"
        data = json.loads(event["data"])
        assert data["content"] == "Test"

    @pytest.mark.asyncio
    async def test_custom_chunk_size(self):
        """Test custom chunk size is respected."""
        queue = asyncio.Queue()
        text = "123456789"

        count = await ChunkEmitter.emit_chunks(text, queue, chunk_size=3)

        assert count == 3
        events = [await queue.get() for _ in range(3)]
        contents = [json.loads(e["data"])["content"] for e in events]
        assert contents == ["123", "456", "789"]

    @pytest.mark.asyncio
    async def test_with_logging_enabled(self):
        """Test log_progress parameter doesn't cause errors."""
        queue = asyncio.Queue()
        text = "Hello"

        # Should not raise
        count = await ChunkEmitter.emit_chunks(
            text, queue, chunk_size=5, log_progress=True
        )

        assert count == 1


class TestEmitTextAsChunks:
    """Test ChunkEmitter.emit_text_as_chunks method."""

    @pytest.mark.asyncio
    async def test_returns_original_text(self):
        """Test method returns original text."""
        queue = asyncio.Queue()
        text = "Original text content"

        result = await ChunkEmitter.emit_text_as_chunks(text, queue, chunk_size=10)

        assert result == text

    @pytest.mark.asyncio
    async def test_emits_chunks(self):
        """Test chunks are emitted to queue."""
        queue = asyncio.Queue()
        text = "1234567890"

        await ChunkEmitter.emit_text_as_chunks(text, queue, chunk_size=5)

        assert queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_empty_text(self):
        """Test empty text returns empty and emits nothing."""
        queue = asyncio.Queue()

        result = await ChunkEmitter.emit_text_as_chunks("", queue)

        assert result == ""
        assert queue.empty()


class TestConstants:
    """Test ChunkEmitter constants."""

    def test_default_chunk_size(self):
        """Test default chunk size is reasonable."""
        assert ChunkEmitter.DEFAULT_CHUNK_SIZE == 50
