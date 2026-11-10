"""
Unit tests for ChatStreamProducer service.

Tests cover:
- Producer configuration
- Metadata event emission
- Knowledge path handling
- RAG context path handling
- Streaming path handling
- Error handling
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from asyncio import Queue

from src.services.streaming.chat_stream_producer import (
    ChatStreamProducer,
    ProducerConfig,
    ProducerContext,
    ProducerResult,
)


@pytest.fixture(autouse=True)
def entorno_sin_overrides(monkeypatch):
    """ProducerConfig lee el entorno: sin limpiar estas variables, los asserts
    de defaults dependerían de lo que traiga envs/.env (e.g. 32768 en local)."""
    for variable in (
        "CHAT_MODEL_CONTEXT_LIMIT",
        "CHAT_MIN_RESPONSE_TOKENS",
        "CHAT_MAX_RESPONSE_TOKENS",
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def mock_event_queue():
    """Create async queue for events."""
    return asyncio.Queue(maxsize=100)


@pytest.fixture
def mock_chat_context():
    """Create mock ChatContext."""
    context = MagicMock()
    context.model = "saptiva-turbo"
    context.user_id = "user-123"
    context.temperature = 0.7
    context.message = "Test message"
    context.document_ids = []
    return context


@pytest.fixture
def mock_chat_session():
    """Create mock ChatSession."""
    session = MagicMock()
    session.id = "session-456"
    return session


@pytest.fixture
def mock_user_message():
    """Create mock user message."""
    msg = MagicMock()
    msg.id = "msg-789"
    return msg


@pytest.fixture
def mock_saptiva_client():
    """Create mock Saptiva client."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value={
        "choices": [{"message": {"content": "Test response"}}]
    })
    return client


@pytest.fixture
def mock_chat_service():
    """Create mock ChatService."""
    service = AsyncMock()
    service.build_message_context_with_memory = AsyncMock(return_value=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ])
    service.settings = MagicMock()
    service.settings.memory_enabled = True
    return service


@pytest.fixture
def producer_context(
    mock_event_queue,
    mock_chat_context,
    mock_chat_session,
    mock_user_message,
    mock_saptiva_client,
    mock_chat_service,
):
    """Create ProducerContext with mocks."""
    return ProducerContext(
        event_queue=mock_event_queue,
        context=mock_chat_context,
        chat_session=mock_chat_session,
        user_message=mock_user_message,
        saptiva_client=mock_saptiva_client,
        chat_service=mock_chat_service,
        system_prompt="Test system prompt",
        model_params={"temperature": 0.7, "max_tokens": 3000},
        document_context=None,
    )


@pytest.mark.unit
class TestProducerConfig:
    """Tests for ProducerConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = ProducerConfig()

        assert config.model_limit == 8192
        assert config.min_tokens == 500
        assert config.default_max_tokens == 3000

    def test_custom_values(self):
        """Should accept custom values."""
        config = ProducerConfig(
            model_limit=16000,
            min_tokens=1000,
            default_max_tokens=5000,
        )

        assert config.model_limit == 16000
        assert config.min_tokens == 1000
        assert config.default_max_tokens == 5000

    def test_respeta_variables_de_entorno(self, monkeypatch):
        """Con las variables puestas, ProducerConfig las respeta."""
        monkeypatch.setenv("CHAT_MODEL_CONTEXT_LIMIT", "32768")
        monkeypatch.setenv("CHAT_MIN_RESPONSE_TOKENS", "800")
        monkeypatch.setenv("CHAT_MAX_RESPONSE_TOKENS", "4000")

        config = ProducerConfig()

        assert config.model_limit == 32768
        assert config.min_tokens == 800
        assert config.default_max_tokens == 4000

    def test_valor_invalido_cae_al_default(self, monkeypatch):
        """Un valor no numérico cae al default histórico sin lanzar."""
        monkeypatch.setenv("CHAT_MODEL_CONTEXT_LIMIT", "no-es-numero")
        monkeypatch.setenv("CHAT_MIN_RESPONSE_TOKENS", "3.5")
        monkeypatch.setenv("CHAT_MAX_RESPONSE_TOKENS", "")

        config = ProducerConfig()

        assert config.model_limit == 8192
        assert config.min_tokens == 500
        assert config.default_max_tokens == 3000


@pytest.mark.unit
class TestProducerResult:
    """Tests for ProducerResult dataclass."""

    def test_default_values(self):
        """Should have correct defaults."""
        result = ProducerResult()

        assert result.full_response == ""
        assert result.error is None
        assert result.completed is False
        assert result.path_taken == ""

    def test_custom_values(self):
        """Should accept custom values."""
        error = Exception("Test error")
        result = ProducerResult(
            full_response="Hello",
            error=error,
            completed=True,
            path_taken="knowledge",
        )

        assert result.full_response == "Hello"
        assert result.error is error
        assert result.completed is True
        assert result.path_taken == "knowledge"


@pytest.mark.unit
class TestProducerContext:
    """Tests for ProducerContext dataclass."""

    def test_all_fields(self, producer_context):
        """Should contain all required fields."""
        assert producer_context.event_queue is not None
        assert producer_context.context is not None
        assert producer_context.chat_session is not None
        assert producer_context.user_message is not None
        assert producer_context.saptiva_client is not None
        assert producer_context.chat_service is not None
        assert producer_context.system_prompt == "Test system prompt"


@pytest.mark.unit
class TestChatStreamProducerInit:
    """Tests for ChatStreamProducer initialization."""

    def test_default_config(self):
        """Should use default config when none provided."""
        producer = ChatStreamProducer()

        assert producer.config.model_limit == 8192

    def test_custom_config(self):
        """Should use provided config."""
        config = ProducerConfig(model_limit=10000)
        producer = ChatStreamProducer(config=config)

        assert producer.config.model_limit == 10000


@pytest.mark.unit
class TestEmitMetadataEvent:
    """Tests for _emit_metadata_event method."""

    @pytest.mark.asyncio
    async def test_emits_meta_event(self, producer_context):
        """Should emit metadata event with correct data."""
        producer = ChatStreamProducer()

        await producer._emit_metadata_event(producer_context)

        event = await producer_context.event_queue.get()

        assert event["event"] == "meta"
        data = json.loads(event["data"])
        assert data["chat_id"] == "session-456"
        assert data["user_message_id"] == "msg-789"
        assert data["model"] == "saptiva-turbo"


@pytest.mark.unit
class TestRagContextPath:
    """Tests for _handle_rag_context_path method."""

    @pytest.mark.asyncio
    async def test_calls_chat_completion(self, producer_context, mock_saptiva_client):
        """Should call Saptiva chat completion."""
        producer = ChatStreamProducer()
        result = ProducerResult()
        messages = [{"role": "user", "content": "Test"}]

        with patch(
            "src.services.streaming.chat_stream_producer.SaptivaStreamer.extract_content_from_response",
            return_value=("Response content", False),
        ), patch(
            "src.services.streaming.chat_stream_producer.ensure_non_empty_content",
            return_value="Response content",
        ), patch(
            "src.services.streaming.chat_stream_producer.ChunkEmitter.emit_chunks",
            new_callable=AsyncMock,
        ):
            result = await producer._handle_rag_context_path(
                producer_context, result, messages, 3000
            )

        mock_saptiva_client.chat_completion.assert_called_once()
        assert result.path_taken == "rag_context"
        assert result.full_response == "Response content"

    @pytest.mark.asyncio
    async def test_handles_api_error(self, producer_context, mock_saptiva_client):
        """Should propagate API errors."""
        producer = ChatStreamProducer()
        result = ProducerResult()
        messages = [{"role": "user", "content": "Test"}]

        mock_saptiva_client.chat_completion.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            await producer._handle_rag_context_path(
                producer_context, result, messages, 3000
            )


@pytest.mark.unit
class TestStreamingPath:
    """Tests for _handle_streaming_path method."""

    @pytest.mark.asyncio
    async def test_streams_chunks(self, producer_context, mock_saptiva_client):
        """Should stream chunks to queue."""
        producer = ChatStreamProducer()
        result = ProducerResult()
        messages = [{"role": "user", "content": "Test"}]

        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            for chunk in ["Hello", " ", "World"]:
                yield {"choices": [{"delta": {"content": chunk}}]}

        mock_saptiva_client.chat_completion_stream = mock_stream

        with patch(
            "src.services.streaming.chat_stream_producer.SaptivaStreamer.extract_chunk_content",
            side_effect=lambda c: c["choices"][0]["delta"].get("content", ""),
        ):
            result = await producer._handle_streaming_path(
                producer_context, result, messages, 3000
            )

        assert result.path_taken == "streaming"
        assert result.full_response == "Hello World"

        # Check queue has chunk events
        events = []
        while not producer_context.event_queue.empty():
            events.append(await producer_context.event_queue.get())

        assert len(events) >= 2


@pytest.mark.unit
class TestProducerProduce:
    """Tests for main produce method."""

    @pytest.mark.asyncio
    async def test_full_flow_without_chart(self, producer_context, mock_chat_service):
        """Should complete full flow without chart data."""
        producer = ChatStreamProducer()

        # Mock streaming path
        async def mock_stream(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "Test response"}}]}

        producer_context.saptiva_client.chat_completion_stream = mock_stream

        with patch(
            "src.services.streaming.chat_stream_producer.TokenBudgetManager.prepare_messages_for_api"
        ) as mock_budget, patch(
            "src.services.streaming.chat_stream_producer.SaptivaStreamer.extract_chunk_content",
            return_value="Test response",
        ):
            mock_budget.return_value = MagicMock(max_tokens=3000)

            result = await producer.produce(producer_context)

        assert result.completed is True
        assert result.path_taken == "streaming"

    @pytest.mark.asyncio
    async def test_handles_cancellation(self, producer_context, mock_chat_service):
        """Should handle timeout/cancellation gracefully."""
        producer = ChatStreamProducer()

        async def slow_build(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        mock_chat_service.build_message_context_with_memory = slow_build

        # asyncio.wait_for raises TimeoutError, not CancelledError
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await asyncio.wait_for(
                producer.produce(producer_context),
                timeout=0.05,
            )

    @pytest.mark.asyncio
    async def test_handles_producer_error(self, producer_context, mock_chat_service):
        """Should capture errors in result."""
        producer = ChatStreamProducer()

        mock_chat_service.build_message_context_with_memory.side_effect = Exception(
            "Build failed"
        )

        result = await producer.produce(producer_context)

        assert result.error is not None
        assert "Build failed" in str(result.error)
        assert result.completed is False

    @pytest.mark.asyncio
    async def test_signals_end_of_stream(self, producer_context, mock_chat_service):
        """Should put None in queue to signal end."""
        producer = ChatStreamProducer()

        async def mock_stream(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "Done"}}]}

        producer_context.saptiva_client.chat_completion_stream = mock_stream

        with patch(
            "src.services.streaming.chat_stream_producer.TokenBudgetManager.prepare_messages_for_api"
        ) as mock_budget, patch(
            "src.services.streaming.chat_stream_producer.SaptivaStreamer.extract_chunk_content",
            return_value="Done",
        ):
            mock_budget.return_value = MagicMock(max_tokens=3000)

            await producer.produce(producer_context)

        # Drain queue to find None
        found_none = False
        while not producer_context.event_queue.empty():
            item = await producer_context.event_queue.get()
            if item is None:
                found_none = True
                break

        assert found_none


@pytest.mark.unit
class TestProducerWithDocuments:
    """Tests for producer with document context."""

    @pytest.mark.asyncio
    async def test_rag_path_with_documents(self, producer_context, mock_chat_service):
        """Should use RAG path when documents present."""
        producer = ChatStreamProducer()

        producer_context.context.document_ids = ["doc-1", "doc-2"]

        with patch(
            "src.services.streaming.chat_stream_producer.TokenBudgetManager.prepare_messages_for_api"
        ) as mock_budget, patch(
            "src.services.streaming.chat_stream_producer.SaptivaStreamer.extract_content_from_response",
            return_value=("Doc response", False),
        ), patch(
            "src.services.streaming.chat_stream_producer.ensure_non_empty_content",
            return_value="Doc response",
        ), patch(
            "src.services.streaming.chat_stream_producer.ChunkEmitter.emit_chunks",
            new_callable=AsyncMock,
        ):
            mock_budget.return_value = MagicMock(max_tokens=3000)

            result = await producer.produce(producer_context)

        assert result.path_taken == "rag_context"
