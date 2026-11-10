"""
Unit tests for ChatResponseBuilder.

Tests the Builder Pattern implementation for constructing chat responses.
"""

import pytest
from datetime import datetime
from fastapi.responses import JSONResponse

from src.domain.chat_response_builder import ChatResponseBuilder, StreamingResponseBuilder


class TestChatResponseBuilder:
    """Test suite for ChatResponseBuilder class."""

    def test_builder_initializes_with_defaults(self):
        """Test that builder initializes with sensible defaults."""
        builder = ChatResponseBuilder()

        # Access internal data (normally would use build())
        assert builder._data["type"] == "chat"
        assert builder._data["content"] == ""
        assert builder._data["chat_id"] is None
        assert builder._data["message_id"] is None
        assert "timestamp" in builder._data

    def test_builder_with_chat_id(self):
        """Test setting chat ID."""
        builder = ChatResponseBuilder()
        result = builder.with_chat_id("chat-123")

        # Should return self for chaining
        assert result is builder
        assert builder._data["chat_id"] == "chat-123"

    def test_builder_with_message(self):
        """Test setting message content."""
        builder = ChatResponseBuilder()
        builder.with_message("Hello, world!", sanitized=True)

        assert builder._data["content"] == "Hello, world!"
        assert builder._data.get("sanitized") is True

    def test_builder_with_message_not_sanitized(self):
        """Test setting message without sanitization flag."""
        builder = ChatResponseBuilder()
        builder.with_message("Raw content", sanitized=False)

        assert builder._data["content"] == "Raw content"
        assert "sanitized" not in builder._data

    def test_builder_with_message_id(self):
        """Test setting message ID."""
        builder = ChatResponseBuilder()
        builder.with_message_id("msg-456")

        assert builder._data["message_id"] == "msg-456"

    def test_builder_with_model(self):
        """Test setting model name."""
        builder = ChatResponseBuilder()
        builder.with_model("Saptiva Turbo")

        assert builder._data["model"] == "Saptiva Turbo"

    def test_builder_with_tokens(self):
        """Test setting token usage."""
        builder = ChatResponseBuilder()
        builder.with_tokens(prompt_tokens=100, completion_tokens=50)

        assert builder._data["tokens"]["prompt"] == 100
        assert builder._data["tokens"]["completion"] == 50
        assert builder._data["tokens"]["total"] == 150

    def test_builder_with_latency(self):
        """Test setting latency."""
        builder = ChatResponseBuilder()
        builder.with_latency(234.56789)

        # Should be rounded to 2 decimal places
        assert builder._data["latency_ms"] == 234.57

    def test_builder_with_decision(self):
        """Test setting decision metadata."""
        builder = ChatResponseBuilder()
        decision = {
            "strategy": "deep_research",
            "confidence": 0.95,
            "reasoning": "Complex query detected"
        }
        builder.with_decision(decision)

        assert builder._data["decision"] == decision
        assert builder._data["decision"]["strategy"] == "deep_research"

    def test_builder_with_research_task(self):
        """Test setting research task ID."""
        builder = ChatResponseBuilder()
        builder.with_research_task("task-789")

        assert builder._data["task_id"] == "task-789"
        assert builder._data["research_triggered"] is True

    def test_builder_with_session_title(self):
        """Test setting session title."""
        builder = ChatResponseBuilder()
        builder.with_session_title("New Chat Session")

        assert builder._data["session_title"] == "New Chat Session"

    def test_builder_with_metadata(self):
        """Test adding custom metadata."""
        builder = ChatResponseBuilder()
        builder.with_metadata("custom_key", "custom_value")
        builder.with_metadata("another_key", 123)

        assert builder._metadata["custom_key"] == "custom_value"
        assert builder._metadata["another_key"] == 123

    def test_builder_method_chaining(self):
        """Test that builder methods can be chained fluently."""
        builder = (ChatResponseBuilder()
            .with_chat_id("chat-123")
            .with_message_id("msg-456")
            .with_message("AI response")
            .with_model("Saptiva Turbo")
            .with_tokens(100, 50)
            .with_latency(234.5)
            .with_metadata("test_key", "test_value"))

        assert builder._data["chat_id"] == "chat-123"
        assert builder._data["message_id"] == "msg-456"
        assert builder._data["content"] == "AI response"
        assert builder._data["model"] == "Saptiva Turbo"
        assert builder._data["tokens"]["total"] == 150
        assert builder._data["latency_ms"] == 234.5
        assert builder._metadata["test_key"] == "test_value"

    def test_builder_build_returns_json_response(self):
        """Test that build() returns a FastAPI JSONResponse."""
        builder = (ChatResponseBuilder()
            .with_chat_id("chat-123")
            .with_message("Hello!")
            .with_model("Saptiva Turbo"))

        response = builder.build()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 200

    def test_builder_build_includes_cache_headers(self):
        """Test that build() includes no-cache headers."""
        builder = ChatResponseBuilder().with_message("Test")
        response = builder.build()

        # Check cache control headers
        assert "cache-control" in response.headers
        assert "no-store" in response.headers["cache-control"].lower()

    def test_builder_reusability(self):
        """Test that a new builder instance is independent."""
        builder1 = ChatResponseBuilder().with_chat_id("chat-1")
        builder2 = ChatResponseBuilder().with_chat_id("chat-2")

        assert builder1._data["chat_id"] == "chat-1"
        assert builder2._data["chat_id"] == "chat-2"
        assert builder1._data["chat_id"] != builder2._data["chat_id"]

    def test_builder_with_all_fields(self):
        """Test builder with all possible fields set."""
        builder = (ChatResponseBuilder()
            .with_chat_id("chat-full")
            .with_message_id("msg-full")
            .with_message("Complete response", sanitized=True)
            .with_model("Saptiva Cortex")
            .with_tokens(150, 75)
            .with_latency(456.78)
            .with_decision({"strategy": "standard"})
            .with_research_task("task-research")
            .with_session_title("Full Test Session")
            .with_metadata("custom1", "value1")
            .with_metadata("custom2", 42))

        response = builder.build()

        assert response.status_code == 200
        assert builder._data["chat_id"] == "chat-full"
        assert builder._data["model"] == "Saptiva Cortex"
        assert builder._data["tokens"]["total"] == 225
        assert builder._metadata["custom1"] == "value1"


class TestStreamingResponseBuilder:
    """Test suite for StreamingResponseBuilder class."""

    def test_streaming_builder_exists(self):
        """Test that StreamingResponseBuilder class exists."""
        # Just verify the class can be imported and instantiated
        builder = StreamingResponseBuilder()
        assert builder is not None

    def test_streaming_builder_has_different_behavior(self):
        """Test that StreamingResponseBuilder is distinct from ChatResponseBuilder."""
        streaming = StreamingResponseBuilder()
        regular = ChatResponseBuilder()

        # They should be different types
        assert type(streaming) != type(regular)


class TestBuilderPatternPrinciples:
    """Test that Builder Pattern principles are followed."""

    def test_builder_provides_fluent_interface(self):
        """Test that all builder methods return self for chaining."""
        builder = ChatResponseBuilder()

        # All with_* methods should return the builder instance
        assert builder.with_chat_id("test") is builder
        assert builder.with_message("test") is builder
        assert builder.with_message_id("test") is builder
        assert builder.with_model("test") is builder
        assert builder.with_tokens(10, 10) is builder
        assert builder.with_latency(100.0) is builder
        assert builder.with_metadata("key", "value") is builder

    def test_builder_encapsulates_construction_complexity(self):
        """Test that builder hides internal complexity."""
        # Complex response can be built step by step
        builder = ChatResponseBuilder()

        # Step 1: Basic info
        builder.with_chat_id("chat-1").with_message("Response")

        # Step 2: Add model info
        builder.with_model("Saptiva Turbo")

        # Step 3: Add metrics
        builder.with_tokens(100, 50).with_latency(200.5)

        # Final: Build
        response = builder.build()

        assert response.status_code == 200

    def test_builder_allows_partial_construction(self):
        """Test that builder works with minimal fields."""
        # Should work with just a message
        builder = ChatResponseBuilder().with_message("Minimal response")
        response = builder.build()

        assert response.status_code == 200
