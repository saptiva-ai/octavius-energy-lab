"""
Unit tests for EmbeddingService with delegation to embedding-service plugin.

OPTIMIZATION 2026-01: Tests for the refactored embedding service that delegates
to embedding-service plugin via gRPC/HTTP instead of using local sentence-transformers.

Test Categories:
1. Chunking logic (local, no delegation)
2. gRPC delegation
3. HTTP fallback
4. Caching behavior
5. Error handling
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Module under test - use absolute import
from src.services.embedding_service import (
    EmbeddingService,
    TextChunk,
    get_embedding_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def embedding_service():
    """Create a fresh embedding service instance for each test."""
    # Reset singleton
    import src.services.embedding_service as module

    module._embedding_service = None
    return EmbeddingService()


@pytest.fixture
def mock_grpc_client():
    """Mock gRPC client for embedding-service."""
    client = AsyncMock()
    client.encode = AsyncMock(
        return_value=[[0.1] * 384, [0.2] * 384]  # 384-dim embeddings
    )
    return client


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for embedding-service."""
    client = AsyncMock()
    # Client returns embeddings list directly (not a dict)
    client.encode = AsyncMock(
        return_value=[[0.1] * 384, [0.2] * 384]
    )
    return client


# =============================================================================
# Test: Chunking Logic (Local - No Delegation)
# =============================================================================


class TestChunkText:
    """Tests for text chunking - runs locally, no delegation needed."""

    def test_empty_text_returns_empty_list(self, embedding_service):
        """Empty or whitespace text should return no chunks."""
        assert embedding_service.chunk_text("") == []
        assert embedding_service.chunk_text("   ") == []
        assert embedding_service.chunk_text("\n\t\n") == []

    def test_short_text_single_chunk(self, embedding_service):
        """Text shorter than chunk_size should produce single chunk."""
        text = "Este es un texto corto para probar."
        chunks = embedding_service.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0].chunk_id == 0
        assert chunks[0].text == text
        assert chunks[0].start_char == 0
        assert chunks[0].page == 0

    def test_long_text_multiple_chunks(self, embedding_service):
        """Long text should be split into multiple overlapping chunks."""
        # Create text longer than default chunk size (500 tokens * 4 chars = 2000 chars)
        text = "palabra " * 600  # ~4800 chars
        chunks = embedding_service.chunk_text(text)

        assert len(chunks) > 1
        # Verify sequential chunk IDs
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == i

    def test_chunks_have_overlap(self, embedding_service):
        """Consecutive chunks should have overlapping content."""
        text = "palabra " * 600
        chunks = embedding_service.chunk_text(text)

        if len(chunks) >= 2:
            # Check overlap by verifying end of chunk N appears in start of chunk N+1
            chunk1_end = chunks[0].text[-100:]  # Last 100 chars
            chunk2_start = chunks[1].text[:200]  # First 200 chars
            # Some overlap should exist
            assert any(
                word in chunk2_start for word in chunk1_end.split() if len(word) > 3
            )

    def test_chunks_preserve_word_boundaries(self, embedding_service):
        """Chunks should prefer breaking at word boundaries."""
        # Use shorter words that fit well within chunk boundaries
        text = "testing word boundaries " * 200
        chunks = embedding_service.chunk_text(text)

        # Most words should be complete (not cut in the middle)
        # Allow some tolerance at chunk boundaries
        total_words = 0
        complete_words = 0
        for chunk in chunks:
            words = chunk.text.split()
            total_words += len(words)
            for word in words:
                if word in ("testing", "word", "boundaries"):
                    complete_words += 1

        # At least 90% of words should be complete
        assert complete_words / total_words > 0.9, (
            f"Too many words cut: {complete_words}/{total_words}"
        )

    def test_chunk_metadata_passed_through(self, embedding_service):
        """Metadata should be attached to all chunks."""
        text = "Test text for metadata."
        metadata = {"filename": "test.pdf", "source": "upload"}
        chunks = embedding_service.chunk_text(text, page=5, metadata=metadata)

        assert chunks[0].page == 5
        assert chunks[0].metadata == metadata

    def test_estimate_tokens(self, embedding_service):
        """Token estimation should approximate 4 chars per token."""
        text = "word " * 100  # 500 chars
        tokens = embedding_service.estimate_tokens(text)
        assert tokens == 125  # 500 / 4


# =============================================================================
# Test: gRPC Delegation
# =============================================================================


class TestGrpcDelegation:
    """Tests for embedding generation via gRPC delegation."""

    @pytest.mark.asyncio
    async def test_encode_async_uses_grpc_first(
        self, embedding_service, mock_grpc_client
    ):
        """encode_async should try gRPC client first."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            result = await embedding_service.encode_async(["text1", "text2"])

            mock_grpc_client.encode.assert_called_once_with(
                ["text1", "text2"], batch_size=32
            )
            assert len(result) == 2
            assert len(result[0]) == 384

    @pytest.mark.asyncio
    async def test_encode_async_updates_embedding_dim(
        self, embedding_service, mock_grpc_client
    ):
        """Embedding dimension should be updated from gRPC response."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            await embedding_service.encode_async(["test"])

            assert embedding_service._embedding_dim == 384

    @pytest.mark.asyncio
    async def test_encode_empty_list_returns_empty(self, embedding_service):
        """Empty text list should return empty without calling client."""
        result = await embedding_service.encode_async([])
        assert result == []


# =============================================================================
# Test: HTTP Fallback
# =============================================================================


class TestHttpFallback:
    """Tests for HTTP fallback when gRPC fails."""

    @pytest.mark.asyncio
    async def test_falls_back_to_http_on_grpc_failure(
        self, embedding_service, mock_http_client
    ):
        """Should fall back to HTTP when gRPC fails."""
        # Create a gRPC client mock where .encode() raises exception
        failing_grpc_client = AsyncMock()
        failing_grpc_client.encode = AsyncMock(
            side_effect=Exception("gRPC unavailable")
        )

        with patch.object(
            embedding_service, "_get_grpc_client", return_value=failing_grpc_client
        ):
            with patch.object(
                embedding_service, "_get_http_client", return_value=mock_http_client
            ):
                result = await embedding_service.encode_async(["test"])

                # HTTP should have been called as fallback
                mock_http_client.encode.assert_called_once()
                assert len(result) == 2

    @pytest.mark.asyncio
    async def test_raises_when_both_fail(self, embedding_service):
        """Should raise RuntimeError when both gRPC and HTTP fail."""
        # Create clients where .encode() method raises exceptions
        failing_grpc_client = AsyncMock()
        failing_grpc_client.encode = AsyncMock(side_effect=Exception("gRPC down"))

        failing_http_client = AsyncMock()
        failing_http_client.encode = AsyncMock(side_effect=Exception("HTTP down"))

        with patch.object(
            embedding_service, "_get_grpc_client", return_value=failing_grpc_client
        ):
            with patch.object(
                embedding_service, "_get_http_client", return_value=failing_http_client
            ):
                with pytest.raises(RuntimeError, match="Embedding generation failed"):
                    await embedding_service.encode_async(["test"])


# =============================================================================
# Test: Caching
# =============================================================================


class TestQueryCache:
    """Tests for query embedding cache."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_embedding(
        self, embedding_service, mock_grpc_client
    ):
        """Second call with same text should return cached result."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            # First call - should hit gRPC
            result1 = await embedding_service.encode_single_async("test query")
            assert mock_grpc_client.encode.call_count == 1

            # Second call - should hit cache
            result2 = await embedding_service.encode_single_async("test query")
            # gRPC should NOT be called again
            assert mock_grpc_client.encode.call_count == 1

            # Results should be identical
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_cache_miss_for_different_text(
        self, embedding_service, mock_grpc_client
    ):
        """Different text should not hit cache."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            await embedding_service.encode_single_async("text1")
            await embedding_service.encode_single_async("text2")

            assert mock_grpc_client.encode.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_disabled_when_requested(
        self, embedding_service, mock_grpc_client
    ):
        """use_cache=False should bypass cache."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            await embedding_service.encode_single_async("test", use_cache=False)
            await embedding_service.encode_single_async("test", use_cache=False)

            # Both calls should hit gRPC
            assert mock_grpc_client.encode.call_count == 2

    def test_clear_cache(self, embedding_service):
        """clear_query_cache should empty the cache."""
        # Add something to cache
        embedding_service._query_cache["key"] = [0.1] * 384

        embedding_service.clear_query_cache()

        assert len(embedding_service._query_cache) == 0

    def test_cache_key_normalization(self, embedding_service):
        """Cache keys should be normalized (lowercase, no punctuation)."""
        key1 = embedding_service._get_cache_key("Hello World!")
        key2 = embedding_service._get_cache_key("hello world")
        key3 = embedding_service._get_cache_key("HELLO WORLD??")

        # All should produce same key
        assert key1 == key2 == key3


# =============================================================================
# Test: Chunk and Embed
# =============================================================================


class TestChunkAndEmbed:
    """Tests for combined chunk_and_embed operation."""

    @pytest.mark.asyncio
    async def test_chunk_and_embed_returns_combined_results(
        self, embedding_service, mock_grpc_client
    ):
        """chunk_and_embed should return chunks with embeddings."""
        text = "Este es un texto de prueba para chunking y embedding."

        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            # Mock to return one embedding per chunk
            mock_grpc_client.encode = AsyncMock(return_value=[[0.1] * 384])

            result = await embedding_service.chunk_and_embed_async(text)

            assert len(result) == 1
            assert "chunk_id" in result[0]
            assert "text" in result[0]
            assert "embedding" in result[0]
            assert "page" in result[0]
            assert len(result[0]["embedding"]) == 384

    @pytest.mark.asyncio
    async def test_chunk_and_embed_empty_text(self, embedding_service):
        """Empty text should return empty list without calling encoder."""
        result = await embedding_service.chunk_and_embed_async("")
        assert result == []


# =============================================================================
# Test: Singleton
# =============================================================================


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_embedding_service_returns_same_instance(self):
        """get_embedding_service should return singleton."""
        import src.services.embedding_service as module

        module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2


# =============================================================================
# Test: Sync Wrapper
# =============================================================================


class TestSyncWrapper:
    """Tests for synchronous encode wrapper."""

    def test_encode_sync_wrapper_works(self, embedding_service, mock_grpc_client):
        """Sync encode should work via async wrapper."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            with patch.object(
                embedding_service,
                "encode_async",
                new_callable=lambda: AsyncMock(return_value=[[0.1] * 384]),
            ):
                result = embedding_service.encode(["test"])
                assert len(result) == 1

    def test_encode_empty_list_returns_empty(self, embedding_service):
        """Empty list should return empty without calling client."""
        result = embedding_service.encode([])
        assert result == []


# =============================================================================
# Test: Client Initialization
# =============================================================================


class TestClientInitialization:
    """Tests for gRPC and HTTP client lazy initialization."""

    @pytest.mark.asyncio
    async def test_get_grpc_client_lazy_init(self, embedding_service):
        """Should lazily initialize gRPC client."""
        mock_client = AsyncMock()

        # Patch at the import source (lazy import inside method)
        with patch(
            "src.clients.embedding_service_grpc.get_embedding_grpc_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            client = await embedding_service._get_grpc_client()
            assert client is mock_client
            # Second call should return cached client
            client2 = await embedding_service._get_grpc_client()
            assert client2 is client

    @pytest.mark.asyncio
    async def test_get_grpc_client_handles_import_error(self, embedding_service):
        """Should return None when gRPC client import fails."""
        # Patch the import mechanism to raise ImportError
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "embedding_service_grpc" in name:
                raise ImportError("No gRPC module")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            client = await embedding_service._get_grpc_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_get_http_client_lazy_init(self, embedding_service):
        """Should lazily initialize HTTP client."""
        mock_client = AsyncMock()

        # Patch at the import source (lazy import inside method)
        with patch(
            "src.clients.embedding_service.get_embedding_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            client = await embedding_service._get_http_client()
            assert client is mock_client

    @pytest.mark.asyncio
    async def test_get_http_client_handles_error(self, embedding_service):
        """Should return None when HTTP client init fails."""
        # Patch the import mechanism to raise Exception
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "embedding_service" in name and "grpc" not in name:
                raise Exception("HTTP client error")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            client = await embedding_service._get_http_client()
            assert client is None


# =============================================================================
# Test: Encode Via Methods
# =============================================================================


class TestEncodeViaMethods:
    """Tests for _encode_via_grpc and _encode_via_http."""

    @pytest.mark.asyncio
    async def test_encode_via_grpc_raises_when_no_client(self, embedding_service):
        """Should raise RuntimeError when gRPC client is None."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=None
        ):
            with pytest.raises(RuntimeError, match="gRPC client not available"):
                await embedding_service._encode_via_grpc(["test"])

    @pytest.mark.asyncio
    async def test_encode_via_grpc_updates_embedding_dim(
        self, embedding_service, mock_grpc_client
    ):
        """Should update embedding dimension from response."""
        with patch.object(
            embedding_service, "_get_grpc_client", return_value=mock_grpc_client
        ):
            await embedding_service._encode_via_grpc(["test"])
            assert embedding_service._embedding_dim == 384

    @pytest.mark.asyncio
    async def test_encode_via_http_raises_when_no_client(self, embedding_service):
        """Should raise RuntimeError when HTTP client is None."""
        with patch.object(
            embedding_service, "_get_http_client", return_value=None
        ):
            with pytest.raises(RuntimeError, match="HTTP client not available"):
                await embedding_service._encode_via_http(["test"])

    @pytest.mark.asyncio
    async def test_encode_via_http_updates_embedding_dim(
        self, embedding_service, mock_http_client
    ):
        """Should update embedding dimension from response."""
        with patch.object(
            embedding_service, "_get_http_client", return_value=mock_http_client
        ):
            await embedding_service._encode_via_http(["test"])
            assert embedding_service._embedding_dim == 384


# =============================================================================
# Test: Embedding Dimension Property
# =============================================================================


class TestEmbeddingDimProperty:
    """Tests for embedding_dim property."""

    def test_embedding_dim_default(self, embedding_service):
        """Should return default 384 when not set."""
        assert embedding_service.embedding_dim == 384

    def test_embedding_dim_cached(self, embedding_service):
        """Should return cached value when set."""
        embedding_service._embedding_dim = 768
        assert embedding_service.embedding_dim == 768


# =============================================================================
# Test: Encode Single Sync
# =============================================================================


class TestEncodeSingleSync:
    """Tests for encode_single synchronous method."""

    def test_encode_single_with_cache_hit(self, embedding_service):
        """Should return cached embedding on cache hit."""
        # Pre-populate cache
        cache_key = embedding_service._get_cache_key("test query")
        cached_embedding = [0.5] * 384
        embedding_service._query_cache[cache_key] = cached_embedding

        result = embedding_service.encode_single("test query", use_cache=True)

        assert result == cached_embedding

    def test_encode_single_with_cache_miss(self, embedding_service, mock_grpc_client):
        """Should generate embedding on cache miss."""
        with patch.object(
            embedding_service,
            "encode",
            return_value=[[0.1] * 384],
        ):
            result = embedding_service.encode_single("new query", use_cache=True)

            assert len(result) == 384
            # Should be cached now
            cache_key = embedding_service._get_cache_key("new query")
            assert cache_key in embedding_service._query_cache

    def test_encode_single_without_cache(self, embedding_service):
        """Should not use cache when use_cache=False."""
        with patch.object(
            embedding_service,
            "encode",
            return_value=[[0.2] * 384],
        ):
            result = embedding_service.encode_single("test", use_cache=False)

            assert len(result) == 384
            # Should NOT be cached
            cache_key = embedding_service._get_cache_key("test")
            assert cache_key not in embedding_service._query_cache


# =============================================================================
# Test: Cache LRU Eviction
# =============================================================================


class TestCacheLRUEviction:
    """Tests for cache LRU eviction behavior."""

    def test_update_cache_evicts_oldest(self, embedding_service):
        """Should evict oldest entry when cache is full."""
        # Set small cache size
        embedding_service._query_cache_size = 2

        # Fill cache
        embedding_service._update_cache("text1", [0.1] * 384)
        embedding_service._update_cache("text2", [0.2] * 384)

        key1 = embedding_service._get_cache_key("text1")
        key2 = embedding_service._get_cache_key("text2")

        assert key1 in embedding_service._query_cache
        assert key2 in embedding_service._query_cache

        # Add third entry - should evict first
        embedding_service._update_cache("text3", [0.3] * 384)

        key3 = embedding_service._get_cache_key("text3")

        assert key1 not in embedding_service._query_cache  # Evicted
        assert key2 in embedding_service._query_cache
        assert key3 in embedding_service._query_cache


# =============================================================================
# Test: Chunk and Embed Sync
# =============================================================================


class TestChunkAndEmbedSync:
    """Tests for chunk_and_embed synchronous method."""

    def test_chunk_and_embed_sync(self, embedding_service):
        """Should chunk and embed text synchronously."""
        text = "Test text for chunking."

        with patch.object(
            embedding_service,
            "encode",
            return_value=[[0.1] * 384],
        ):
            result = embedding_service.chunk_and_embed(text, page=3)

            assert len(result) == 1
            assert result[0]["page"] == 3
            assert len(result[0]["embedding"]) == 384

    def test_chunk_and_embed_empty_text(self, embedding_service):
        """Empty text should return empty list."""
        result = embedding_service.chunk_and_embed("")
        assert result == []

    def test_chunk_and_embed_with_metadata(self, embedding_service):
        """Should pass metadata to chunks."""
        text = "Test text."
        metadata = {"source": "test"}

        with patch.object(
            embedding_service,
            "encode",
            return_value=[[0.1] * 384],
        ):
            result = embedding_service.chunk_and_embed(text, metadata=metadata)

            assert result[0]["metadata"] == metadata


# =============================================================================
# Test: Initialization
# =============================================================================


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization."""

    def test_default_init_values(self):
        """Should initialize with default values."""
        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            service = EmbeddingService()

            assert service.chunk_size_tokens == 500
            assert service.chunk_overlap_tokens == 100
            assert service.chars_per_token == 4
            assert service._embedding_dim is None
            assert service._grpc_client is None
            assert service._http_client is None

    def test_custom_env_values(self):
        """Should read custom values from environment."""
        with patch.dict(
            "os.environ",
            {
                "CHUNK_SIZE_TOKENS": "1000",
                "CHUNK_OVERLAP_TOKENS": "200",
                "QUERY_EMBEDDING_CACHE_SIZE": "500",
                "EMBEDDING_MODEL_NAME": "custom-model",
            },
        ):
            service = EmbeddingService()

            assert service.chunk_size_tokens == 1000
            assert service.chunk_overlap_tokens == 200
            assert service._query_cache_size == 500
            assert service.model_name == "custom-model"


# =============================================================================
# Test: TextChunk Dataclass
# =============================================================================


class TestTextChunk:
    """Tests for TextChunk dataclass."""

    def test_textchunk_defaults(self):
        """Should have correct default values."""
        chunk = TextChunk(
            chunk_id=0,
            text="Test",
            start_char=0,
            end_char=4,
        )

        assert chunk.page == 0
        assert chunk.metadata is None

    def test_textchunk_with_all_fields(self):
        """Should store all fields correctly."""
        metadata = {"key": "value"}
        chunk = TextChunk(
            chunk_id=5,
            text="Sample text",
            start_char=100,
            end_char=111,
            page=3,
            metadata=metadata,
        )

        assert chunk.chunk_id == 5
        assert chunk.text == "Sample text"
        assert chunk.start_char == 100
        assert chunk.end_char == 111
        assert chunk.page == 3
        assert chunk.metadata == metadata


# =============================================================================
# Test: Cache Key Edge Cases
# =============================================================================


class TestCacheKeyEdgeCases:
    """Tests for cache key normalization edge cases."""

    def test_cache_key_with_accents(self, embedding_service):
        """Should normalize accented characters."""
        key1 = embedding_service._get_cache_key("café")
        key2 = embedding_service._get_cache_key("cafe")

        assert key1 == key2

    def test_cache_key_with_extra_whitespace(self, embedding_service):
        """Should normalize whitespace."""
        key1 = embedding_service._get_cache_key("hello   world")
        key2 = embedding_service._get_cache_key("hello world")

        assert key1 == key2

    def test_cache_key_with_special_chars(self, embedding_service):
        """Should remove special characters."""
        key1 = embedding_service._get_cache_key("hello@world#test!")
        key2 = embedding_service._get_cache_key("helloworldtest")

        assert key1 == key2


# =============================================================================
# Paragraph-Aware Chunking Tests
# =============================================================================


class TestChunkTextByParagraphs:
    """Tests for paragraph-aware chunking strategy."""

    def test_respects_paragraph_boundaries(self, embedding_service):
        """Chunks should not split paragraphs across boundaries."""
        paragraphs = [
            "Primer párrafo sobre ingresos bancarios del periodo.",
            "Segundo párrafo con datos de EBITDA y utilidad neta.",
            "Tercer párrafo sobre regulación y cumplimiento.",
        ]
        text = "\n\n".join(paragraphs)

        chunks = embedding_service.chunk_text_by_paragraphs(text)

        # With default 2000 char budget, all 3 short paragraphs fit in 1 chunk
        assert len(chunks) == 1
        assert "Primer párrafo" in chunks[0].text
        assert "Tercer párrafo" in chunks[0].text
        # Paragraph separator preserved within chunk
        assert "\n\n" in chunks[0].text

    def test_splits_when_budget_exceeded(self, embedding_service):
        """Should create multiple chunks when paragraphs exceed budget."""
        # Create paragraphs that exceed 2000 char budget
        para_a = "A" * 800
        para_b = "B" * 800
        para_c = "C" * 800
        text = f"{para_a}\n\n{para_b}\n\n{para_c}"

        chunks = embedding_service.chunk_text_by_paragraphs(text)

        # 800*3 = 2400 > 2000 budget → should be 2+ chunks
        assert len(chunks) >= 2
        # Each chunk is a complete paragraph (not mid-split)
        for chunk in chunks:
            # Should not contain partial lines of repeated chars
            unique_chars = set(chunk.text.strip())
            # Each chunk has coherent content (all A's, or all B's, etc.)
            assert len(unique_chars) <= 3  # char + possible \n

    def test_oversized_paragraph_falls_back_to_sliding_window(self, embedding_service):
        """A single paragraph > budget should use sliding window fallback."""
        giant_paragraph = "X" * 5000  # way over 2000 char budget
        text = f"Short intro.\n\n{giant_paragraph}\n\nShort conclusion."

        chunks = embedding_service.chunk_text_by_paragraphs(text)

        # Should have: 1 chunk for intro, 2-3 chunks for giant para, 1 for conclusion
        assert len(chunks) >= 3
        # Intro should be its own chunk (or merged with something)
        assert any("Short intro" in c.text for c in chunks)

    def test_preserves_page_number(self, embedding_service):
        """Page number should be passed through to all chunks."""
        text = "Párrafo uno.\n\nPárrafo dos."
        chunks = embedding_service.chunk_text_by_paragraphs(text, page=5)

        for chunk in chunks:
            assert chunk.page == 5

    def test_empty_text_returns_empty(self, embedding_service):
        """Empty text should return empty list."""
        assert embedding_service.chunk_text_by_paragraphs("") == []
        assert embedding_service.chunk_text_by_paragraphs("   ") == []

    def test_single_paragraph_falls_back_to_sliding(self, embedding_service):
        """Text without paragraph breaks uses sliding window."""
        text = "No paragraph breaks in this text at all " * 100
        chunks = embedding_service.chunk_text_by_paragraphs(text)

        # Should still produce chunks via sliding window fallback
        assert len(chunks) >= 1

    def test_metadata_passed_through(self, embedding_service):
        """Metadata should be attached to all chunks."""
        text = "Párrafo uno.\n\nPárrafo dos."
        meta = {"filename": "test.pdf"}
        chunks = embedding_service.chunk_text_by_paragraphs(text, metadata=meta)

        for chunk in chunks:
            assert chunk.metadata == {"filename": "test.pdf"}

    def test_chunk_ids_sequential(self, embedding_service):
        """Chunk IDs should be sequential starting from 0."""
        paras = [f"Párrafo {i} con contenido." for i in range(10)]
        text = "\n\n".join(paras)
        chunks = embedding_service.chunk_text_by_paragraphs(text)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == i
