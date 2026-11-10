"""
Unit tests for EmbeddingServiceClient (HTTP client for embedding-service plugin).

Tests encode, chunk_and_embed, and other embedding operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Skip all tests if import fails due to proto version mismatch
try:
    from src.clients.embedding_service import (
        EmbeddingServiceClient,
        EncodeResponse,
        EncodeSingleResponse,
        ChunkResult,
        ChunkAndEmbedResponse,
        ModelInfoResponse,
        get_embedding_client,
        close_embedding_client,
    )
    CLIENT_IMPORT_AVAILABLE = True
except Exception:
    CLIENT_IMPORT_AVAILABLE = False
    # Dummy imports to avoid NameError
    EmbeddingServiceClient = None
    EncodeResponse = None
    EncodeSingleResponse = None
    ChunkResult = None
    ChunkAndEmbedResponse = None
    ModelInfoResponse = None
    get_embedding_client = None
    close_embedding_client = None

pytestmark = pytest.mark.skipif(
    not CLIENT_IMPORT_AVAILABLE,
    reason="Protobuf version mismatch - regenerate protos"
)


class TestResponseModels:
    """Tests for response Pydantic models."""

    def test_encode_response(self):
        """Test EncodeResponse model."""
        response = EncodeResponse(
            embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            dimension=3,
            count=2,
        )

        assert len(response.embeddings) == 2
        assert response.dimension == 3
        assert response.count == 2

    def test_encode_single_response(self):
        """Test EncodeSingleResponse model."""
        response = EncodeSingleResponse(
            embedding=[0.1, 0.2, 0.3],
            dimension=3,
            cached=True,
        )

        assert len(response.embedding) == 3
        assert response.cached is True

    def test_encode_single_response_default_cached(self):
        """Test EncodeSingleResponse default cached value."""
        response = EncodeSingleResponse(
            embedding=[0.1],
            dimension=1,
        )

        assert response.cached is False

    def test_chunk_result(self):
        """Test ChunkResult model."""
        chunk = ChunkResult(
            chunk_id=0,
            text="Sample chunk text",
            embedding=[0.1, 0.2],
            page=1,
            metadata={"source": "test"},
        )

        assert chunk.chunk_id == 0
        assert chunk.page == 1
        assert chunk.metadata["source"] == "test"

    def test_chunk_result_none_metadata(self):
        """Test ChunkResult with None metadata."""
        chunk = ChunkResult(
            chunk_id=0,
            text="Sample",
            embedding=[0.1],
            page=0,
            metadata=None,
        )

        assert chunk.metadata is None

    def test_chunk_and_embed_response(self):
        """Test ChunkAndEmbedResponse model."""
        chunks = [
            ChunkResult(
                chunk_id=0,
                text="Chunk 1",
                embedding=[0.1],
                page=0,
                metadata=None,
            ),
            ChunkResult(
                chunk_id=1,
                text="Chunk 2",
                embedding=[0.2],
                page=0,
                metadata=None,
            ),
        ]

        response = ChunkAndEmbedResponse(
            chunks=chunks,
            total_chunks=2,
            dimension=1,
        )

        assert len(response.chunks) == 2
        assert response.total_chunks == 2

    def test_model_info_response(self):
        """Test ModelInfoResponse model."""
        info = ModelInfoResponse(
            model_name="all-MiniLM-L6-v2",
            dimension=384,
            device="cpu",
            chunk_size_tokens=512,
            chunk_overlap_tokens=50,
            cache_size=1000,
        )

        assert info.model_name == "all-MiniLM-L6-v2"
        assert info.dimension == 384


class TestEmbeddingServiceClientInit:
    """Tests for EmbeddingServiceClient initialization."""

    def test_init_with_default_url(self):
        """Test initialization with default URL."""
        with patch.dict("os.environ", {}, clear=True):
            client = EmbeddingServiceClient()
            assert "embedding-service" in client.base_url

    def test_init_with_env_url(self):
        """Test initialization with environment variable URL."""
        with patch.dict("os.environ", {"EMBEDDING_SERVICE_URL": "http://custom:9000"}):
            client = EmbeddingServiceClient()
            assert client.base_url == "http://custom:9000"

    def test_init_with_explicit_url(self):
        """Test initialization with explicit URL."""
        client = EmbeddingServiceClient(base_url="http://localhost:8080")
        assert client.base_url == "http://localhost:8080"

    def test_init_client_is_none(self):
        """Test that _client starts as None."""
        client = EmbeddingServiceClient()
        assert client._client is None
        assert client._available is None


class TestEmbeddingServiceClientGetClient:
    """Tests for _get_client method."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self):
        """Test that _get_client creates a new client when None."""
        client = EmbeddingServiceClient()

        http_client = await client._get_client()

        assert http_client is not None
        assert client._client is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_reuses_existing(self):
        """Test that _get_client reuses existing client."""
        client = EmbeddingServiceClient()

        http_client1 = await client._get_client()
        http_client2 = await client._get_client()

        assert http_client1 is http_client2

        await client.close()


class TestEmbeddingServiceClientIsAvailable:
    """Tests for is_available method."""

    @pytest.mark.asyncio
    async def test_is_available_returns_cached(self):
        """Test that is_available returns cached result."""
        client = EmbeddingServiceClient()
        client._available = True

        result = await client.is_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_checks_health(self):
        """Test that is_available checks health when not cached."""
        client = EmbeddingServiceClient()

        with patch.object(client, "health_check", return_value={"status": "ok"}):
            result = await client.is_available()

        assert result is True
        assert client._available is True

    @pytest.mark.asyncio
    async def test_is_available_handles_error(self):
        """Test that is_available handles health check failure."""
        client = EmbeddingServiceClient()

        with patch.object(
            client, "health_check", side_effect=Exception("Connection error")
        ):
            result = await client.is_available()

        assert result is False
        assert client._available is False


class TestEmbeddingServiceClientHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy", "model": "loaded"}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.health_check()

        assert result["status"] == "healthy"
        mock_http_client.get.assert_called_once_with("/health")


class TestEmbeddingServiceClientEncode:
    """Tests for encode method."""

    @pytest.mark.asyncio
    async def test_encode_empty_list(self):
        """Test encoding empty list returns empty."""
        client = EmbeddingServiceClient()

        result = await client.encode([])

        assert result == []

    @pytest.mark.asyncio
    async def test_encode_success(self):
        """Test successful encoding."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            "dimension": 2,
            "count": 2,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.encode(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_encode_with_batch_size(self):
        """Test encoding with custom batch size."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embeddings": [[0.1]],
            "dimension": 1,
            "count": 1,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.encode(["text"], batch_size=16)

        call_args = mock_http_client.post.call_args
        assert call_args[1]["json"]["batch_size"] == 16


class TestEmbeddingServiceClientEncodeSingle:
    """Tests for encode_single method."""

    @pytest.mark.asyncio
    async def test_encode_single_success(self):
        """Test successful single text encoding."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embedding": [0.1, 0.2, 0.3],
            "dimension": 3,
            "cached": False,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.encode_single("test text")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_encode_single_from_cache(self):
        """Test single text encoding from cache."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embedding": [0.1],
            "dimension": 1,
            "cached": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.encode_single("test", use_cache=True)

        call_args = mock_http_client.post.call_args
        assert call_args[1]["json"]["use_cache"] is True


class TestEmbeddingServiceClientChunkAndEmbed:
    """Tests for chunk_and_embed method."""

    @pytest.mark.asyncio
    async def test_chunk_and_embed_empty_text(self):
        """Test chunk_and_embed with empty text returns empty."""
        client = EmbeddingServiceClient()

        result = await client.chunk_and_embed("")
        assert result == []

    @pytest.mark.asyncio
    async def test_chunk_and_embed_whitespace_only(self):
        """Test chunk_and_embed with whitespace returns empty."""
        client = EmbeddingServiceClient()

        result = await client.chunk_and_embed("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_chunk_and_embed_success(self):
        """Test successful chunk and embed."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {
                    "chunk_id": 0,
                    "text": "Chunk 1",
                    "embedding": [0.1, 0.2],
                    "page": 0,
                    "metadata": None,
                },
                {
                    "chunk_id": 1,
                    "text": "Chunk 2",
                    "embedding": [0.3, 0.4],
                    "page": 0,
                    "metadata": None,
                },
            ],
            "total_chunks": 2,
            "dimension": 2,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.chunk_and_embed("Sample text to chunk")

        assert len(result) == 2
        assert result[0]["chunk_id"] == 0
        assert result[0]["text"] == "Chunk 1"
        assert result[0]["embedding"] == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_chunk_and_embed_with_metadata(self):
        """Test chunk_and_embed with metadata."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {
                    "chunk_id": 0,
                    "text": "Chunk",
                    "embedding": [0.1],
                    "page": 5,
                    "metadata": {"source": "doc1"},
                },
            ],
            "total_chunks": 1,
            "dimension": 1,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.chunk_and_embed(
                "Text",
                page=5,
                metadata={"source": "doc1"},
            )

        assert result[0]["page"] == 5
        assert result[0]["metadata"] == {"source": "doc1"}


class TestEmbeddingServiceClientGetModelInfo:
    """Tests for get_model_info method."""

    @pytest.mark.asyncio
    async def test_get_model_info_success(self):
        """Test successful model info retrieval."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "model_name": "all-MiniLM-L6-v2",
            "dimension": 384,
            "device": "cuda",
            "chunk_size_tokens": 512,
            "chunk_overlap_tokens": 50,
            "cache_size": 1000,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.get_model_info()

        assert isinstance(result, ModelInfoResponse)
        assert result.model_name == "all-MiniLM-L6-v2"
        assert result.dimension == 384


class TestEmbeddingServiceClientClearCache:
    """Tests for clear_cache method."""

    @pytest.mark.asyncio
    async def test_clear_cache_success(self):
        """Test successful cache clear."""
        client = EmbeddingServiceClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"cleared": True, "entries": 100}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.delete.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.clear_cache()

        assert result["cleared"] is True
        mock_http_client.delete.assert_called_once_with("/embeddings/cache")


class TestEmbeddingServiceClientClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_when_client_exists(self):
        """Test closing when client exists."""
        client = EmbeddingServiceClient()

        # Create the internal client
        await client._get_client()
        assert client._client is not None

        await client.close()

        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_client_is_none(self):
        """Test closing when client is already None."""
        client = EmbeddingServiceClient()
        assert client._client is None

        # Should not raise
        await client.close()

        assert client._client is None


class TestSingletonFunctions:
    """Tests for singleton getter/closer functions."""

    @pytest.mark.asyncio
    async def test_get_embedding_client_creates_instance(self):
        """Test that get_embedding_client creates singleton."""
        import src.clients.embedding_service as es_module

        es_module._client = None

        client = await get_embedding_client()

        assert client is not None
        assert es_module._client is client

        # Clean up
        await close_embedding_client()

    @pytest.mark.asyncio
    async def test_get_embedding_client_returns_same_instance(self):
        """Test that get_embedding_client returns same instance."""
        import src.clients.embedding_service as es_module

        es_module._client = None

        client1 = await get_embedding_client()
        client2 = await get_embedding_client()

        assert client1 is client2

        await close_embedding_client()

    @pytest.mark.asyncio
    async def test_close_embedding_client_clears_singleton(self):
        """Test that close_embedding_client clears singleton."""
        import src.clients.embedding_service as es_module

        es_module._client = None

        await get_embedding_client()
        assert es_module._client is not None

        await close_embedding_client()

        assert es_module._client is None

    @pytest.mark.asyncio
    async def test_close_embedding_client_when_none(self):
        """Test close when singleton is None."""
        import src.clients.embedding_service as es_module

        es_module._client = None

        # Should not raise
        await close_embedding_client()

        assert es_module._client is None
