"""
HTTP client for the embedding-service plugin.

This client allows the Core (backend) to delegate embedding operations
to the embedding-service plugin, following the Plugin-First Architecture.

OPTIMIZATION 2026-01: Delegates sentence-transformers to plugin
- Saves ~1.15GB from backend image (torch + sentence-transformers)
- Backend becomes pure orchestrator (~400MB target)

Usage:
    client = await get_embedding_client()
    embeddings = await client.encode(texts)
    result = await client.chunk_and_embed(text)
"""

import os
from typing import Any, Optional

import httpx
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class EncodeResponse(BaseModel):
    """Response from /embeddings/encode endpoint."""

    embeddings: list[list[float]]
    dimension: int
    count: int


class EncodeSingleResponse(BaseModel):
    """Response from /embeddings/encode-single endpoint."""

    embedding: list[float]
    dimension: int
    cached: bool = False


class ChunkResult(BaseModel):
    """Single chunk with embedding."""

    chunk_id: int
    text: str
    embedding: list[float]
    page: int
    metadata: dict[str, Any] | None


class ChunkAndEmbedResponse(BaseModel):
    """Response from /embeddings/chunk-and-embed endpoint."""

    chunks: list[ChunkResult]
    total_chunks: int
    dimension: int


class ModelInfoResponse(BaseModel):
    """Response from /embeddings/info endpoint."""

    model_name: str
    dimension: int
    device: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    cache_size: int


# =============================================================================
# Client
# =============================================================================


class EmbeddingServiceClient:
    """
    HTTP client for the embedding-service plugin.

    Provides methods to generate embeddings and chunk text
    via the embedding-service microservice.

    Falls back to local embedding service if plugin is unavailable.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the embedding-service client.

        Args:
            base_url: Base URL of embedding-service.
                      Defaults to EMBEDDING_SERVICE_URL env var or http://embedding-service:8002
        """
        self.base_url = base_url or os.getenv(
            "EMBEDDING_SERVICE_URL", "http://embedding-service:8003"
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None

        logger.info("EmbeddingServiceClient initialized", base_url=self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    async def is_available(self) -> bool:
        """
        Check if embedding-service is available.

        Caches result for performance.
        """
        if self._available is not None:
            return self._available

        try:
            await self.health_check()
            self._available = True
            logger.info("Embedding-service is available", base_url=self.base_url)
            return True
        except Exception as e:
            self._available = False
            logger.warning(
                "Embedding-service not available, will use local fallback",
                base_url=self.base_url,
                error=str(e),
            )
            return False

    async def health_check(self) -> dict:
        """Check embedding-service health status."""
        client = await self._get_client()

        response = await client.get("/health")
        response.raise_for_status()

        return response.json()

    async def encode(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        client = await self._get_client()

        logger.debug(
            "Encoding texts via embedding-service",
            text_count=len(texts),
            batch_size=batch_size,
        )

        response = await client.post(
            "/embeddings/encode",
            json={"texts": texts, "batch_size": batch_size},
        )
        response.raise_for_status()

        result = EncodeResponse(**response.json())

        logger.debug(
            "Texts encoded via embedding-service",
            count=result.count,
            dimension=result.dimension,
        )

        return result.embeddings

    async def encode_single(
        self,
        text: str,
        use_cache: bool = True,
    ) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            use_cache: Whether to use query cache

        Returns:
            Embedding vector
        """
        client = await self._get_client()

        response = await client.post(
            "/embeddings/encode-single",
            json={"text": text, "use_cache": use_cache},
        )
        response.raise_for_status()

        result = EncodeSingleResponse(**response.json())

        logger.debug(
            "Single text encoded via embedding-service",
            cached=result.cached,
            dimension=result.dimension,
        )

        return result.embedding

    async def chunk_and_embed(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> list[dict[str, Any]]:
        """
        Chunk text and generate embeddings.

        This is the main method for document ingestion in RAG systems.

        Args:
            text: Text to chunk and embed
            page: Page number for metadata
            metadata: Additional metadata
            batch_size: Batch size for embedding

        Returns:
            List of dicts with chunk_id, text, embedding, page, metadata
        """
        if not text or not text.strip():
            return []

        client = await self._get_client()

        logger.debug(
            "Chunking and embedding text via embedding-service",
            text_length=len(text),
            page=page,
        )

        response = await client.post(
            "/embeddings/chunk-and-embed",
            json={
                "text": text,
                "page": page,
                "metadata": metadata,
                "batch_size": batch_size,
            },
        )
        response.raise_for_status()

        result = ChunkAndEmbedResponse(**response.json())

        # Convert to dict format (same as local service)
        chunks_dicts = [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "embedding": c.embedding,
                "page": c.page,
                "metadata": c.metadata,
            }
            for c in result.chunks
        ]

        logger.info(
            "Text chunked and embedded via embedding-service",
            text_length=len(text),
            chunks_count=result.total_chunks,
            dimension=result.dimension,
        )

        return chunks_dicts

    async def get_model_info(self) -> ModelInfoResponse:
        """Get embedding model information."""
        client = await self._get_client()

        response = await client.get("/embeddings/info")
        response.raise_for_status()

        return ModelInfoResponse(**response.json())

    async def clear_cache(self) -> dict:
        """Clear the query embedding cache."""
        client = await self._get_client()

        response = await client.delete("/embeddings/cache")
        response.raise_for_status()

        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# =============================================================================
# Singleton and Factory
# =============================================================================

_client: Optional[EmbeddingServiceClient] = None


async def get_embedding_client() -> EmbeddingServiceClient:
    """
    Get the global EmbeddingServiceClient instance.

    Returns:
        EmbeddingServiceClient instance
    """
    global _client
    if _client is None:
        _client = EmbeddingServiceClient()
    return _client


async def close_embedding_client() -> None:
    """Close the global EmbeddingServiceClient."""
    global _client
    if _client:
        await _client.close()
        _client = None
