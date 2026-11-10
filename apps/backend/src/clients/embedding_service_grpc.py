"""
gRPC client for the embedding-service plugin.

Provides high-performance embedding operations via gRPC (HTTP/2).
Falls back to HTTP client if gRPC is unavailable.

Usage:
    client = await get_embedding_grpc_client()
    embeddings = await client.encode(texts)
    chunks = await client.chunk_and_embed(text)
"""

import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

import grpc
import structlog

logger = structlog.get_logger(__name__)

# Try to import generated proto modules
try:
    from ..proto_stubs.generated import (
        embedding_service_pb2,
        embedding_service_pb2_grpc,
    )

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    embedding_service_pb2 = None
    embedding_service_pb2_grpc = None
    logger.warning(
        "Embedding gRPC modules not available, falling back to HTTP",
        hint="Copy proto generated files from plugins/public/embedding-service/src/grpc/generated/",
    )


@dataclass
class EmbeddedChunk:
    """A text chunk with its embedding."""

    chunk_id: int
    text: str
    embedding: List[float]
    page: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Embedding model information."""

    model_name: str
    dimension: int
    device: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    cache_size: int
    cache_used: int = 0


class EmbeddingServiceGrpcClient:
    """
    gRPC client for the embedding-service plugin.

    Provides high-performance embedding operations via gRPC.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """
        Initialize gRPC client.

        Args:
            host: gRPC server host (default: EMBEDDING_SERVICE_GRPC_HOST or embedding-service)
            port: gRPC server port (default: EMBEDDING_SERVICE_GRPC_PORT or 50053)
        """
        self.host = host or os.getenv(
            "EMBEDDING_SERVICE_GRPC_HOST", "embedding-service"
        )
        self.port = port or int(os.getenv("EMBEDDING_SERVICE_GRPC_PORT", "50053"))
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub = None

        logger.info(
            "EmbeddingServiceGrpcClient initialized",
            host=self.host,
            port=self.port,
            grpc_available=GRPC_AVAILABLE,
        )

    async def _get_stub(self):
        """Get or create gRPC stub."""
        if not GRPC_AVAILABLE:
            raise RuntimeError("gRPC modules not available")

        if (
            self._channel is None
            or self._channel.get_state() == grpc.ChannelConnectivity.SHUTDOWN
        ):
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", 50 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                    ("grpc.keepalive_timeout_ms", 10000),
                ],
            )
            self._stub = embedding_service_pb2_grpc.EmbeddingServiceStub(self._channel)

            logger.debug("gRPC channel created", target=target)

        return self._stub

    async def health_check(self) -> dict:
        """
        Check embedding service health.

        Returns:
            Dict with status, model_loaded, model_name, dimension
        """
        stub = await self._get_stub()
        request = embedding_service_pb2.HealthRequest()
        response = await stub.Health(request)

        return {
            "status": response.status,
            "model_loaded": response.model_loaded,
            "model_name": response.model_name,
            "dimension": response.dimension,
            "model_load_time_ms": response.model_load_time_ms,
        }

    async def encode(
        self,
        texts: List[str],
        batch_size: int = 32,
    ) -> List[List[float]]:
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

        stub = await self._get_stub()
        request = embedding_service_pb2.EncodeRequest(
            texts=texts,
            batch_size=batch_size,
        )

        start = time.time()
        response = await stub.Encode(request)
        elapsed_ms = int((time.time() - start) * 1000)

        embeddings = [list(emb.values) for emb in response.embeddings]

        logger.debug(
            "gRPC Encode completed",
            count=len(embeddings),
            dimension=response.dimension,
            elapsed_ms=elapsed_ms,
            server_time_ms=response.processing_time_ms,
        )

        return embeddings

    async def encode_single(
        self,
        text: str,
        use_cache: bool = True,
    ) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            use_cache: Use query cache

        Returns:
            Embedding vector
        """
        stub = await self._get_stub()
        request = embedding_service_pb2.EncodeSingleRequest(
            text=text,
            use_cache=use_cache,
        )

        response = await stub.EncodeSingle(request)

        logger.debug(
            "gRPC EncodeSingle completed",
            cached=response.cached,
            dimension=response.embedding.dimension,
        )

        return list(response.embedding.values)

    async def chunk_and_embed(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[dict] = None,
        batch_size: int = 32,
    ) -> List[dict]:
        """
        Chunk text and generate embeddings.

        Args:
            text: Text to chunk and embed
            page: Page number for metadata
            metadata: Additional metadata
            batch_size: Batch size

        Returns:
            List of dicts with chunk_id, text, embedding, page, metadata
        """
        if not text or not text.strip():
            return []

        stub = await self._get_stub()

        # Convert metadata to protobuf map
        proto_metadata = {}
        if metadata:
            proto_metadata = {k: str(v) for k, v in metadata.items()}

        request = embedding_service_pb2.ChunkAndEmbedRequest(
            text=text,
            page=page,
            metadata=proto_metadata,
            batch_size=batch_size,
        )

        start = time.time()
        response = await stub.ChunkAndEmbed(request)
        elapsed_ms = int((time.time() - start) * 1000)

        # Convert to dict format
        chunks = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "embedding": list(chunk.embedding.values),
                "page": chunk.page,
                "metadata": dict(chunk.metadata) if chunk.metadata else {},
            }
            for chunk in response.chunks
        ]

        logger.info(
            "gRPC ChunkAndEmbed completed",
            text_length=len(text),
            chunks_count=response.total_chunks,
            dimension=response.dimension,
            elapsed_ms=elapsed_ms,
            server_time_ms=response.processing_time_ms,
        )

        return chunks

    async def batch_chunk_and_embed(
        self,
        documents: List[dict],
        batch_size: int = 32,
    ) -> AsyncIterator[dict]:
        """
        Process multiple documents, streaming results.

        Args:
            documents: List of dicts with id, text, page, metadata
            batch_size: Batch size

        Yields:
            Dict with document_id, chunks, success, error
        """
        stub = await self._get_stub()

        # Convert to protobuf documents
        proto_docs = [
            embedding_service_pb2.Document(
                id=doc.get("id", ""),
                text=doc.get("text", ""),
                page=doc.get("page", 0),
                metadata={k: str(v) for k, v in doc.get("metadata", {}).items()},
            )
            for doc in documents
        ]

        request = embedding_service_pb2.BatchChunkAndEmbedRequest(
            documents=proto_docs,
            batch_size=batch_size,
        )

        async for result in stub.BatchChunkAndEmbed(request):
            chunks = [
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "embedding": list(chunk.embedding.values),
                    "page": chunk.page,
                    "metadata": dict(chunk.metadata) if chunk.metadata else {},
                }
                for chunk in result.chunks
            ]

            yield {
                "document_id": result.document_id,
                "chunks": chunks,
                "success": result.success,
                "error": result.error,
            }

    async def get_model_info(self) -> ModelInfo:
        """Get embedding model information."""
        stub = await self._get_stub()
        request = embedding_service_pb2.ModelInfoRequest()
        response = await stub.GetModelInfo(request)

        return ModelInfo(
            model_name=response.model_name,
            dimension=response.dimension,
            device=response.device,
            chunk_size_tokens=response.chunk_size_tokens,
            chunk_overlap_tokens=response.chunk_overlap_tokens,
            cache_size=response.cache_size,
            cache_used=response.cache_used,
        )

    async def clear_cache(self) -> int:
        """
        Clear query embedding cache.

        Returns:
            Number of entries removed
        """
        stub = await self._get_stub()
        request = embedding_service_pb2.ClearCacheRequest()
        response = await stub.ClearCache(request)
        return response.entries_removed

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.debug("gRPC channel closed")


# =============================================================================
# Singleton and Factory
# =============================================================================

_grpc_client: Optional[EmbeddingServiceGrpcClient] = None


async def get_embedding_grpc_client() -> EmbeddingServiceGrpcClient:
    """
    Get the global EmbeddingServiceGrpcClient instance.

    Returns:
        EmbeddingServiceGrpcClient instance
    """
    global _grpc_client
    if _grpc_client is None:
        _grpc_client = EmbeddingServiceGrpcClient()
    return _grpc_client


async def close_embedding_grpc_client() -> None:
    """Close the global gRPC client."""
    global _grpc_client
    if _grpc_client:
        await _grpc_client.close()
        _grpc_client = None


def is_grpc_available() -> bool:
    """Check if gRPC is available."""
    return GRPC_AVAILABLE
