"""
gRPC service implementation for Embedding Service.

Maps gRPC calls to existing embedding service methods.
"""

import time
from typing import AsyncIterator

import grpc
import structlog

from ..config import get_settings
from ..services.embedding import get_embedding_service

# Import generated protobuf modules
try:
    from .generated import embedding_service_pb2, embedding_service_pb2_grpc

    GRPC_GENERATED = True
except ImportError:
    GRPC_GENERATED = False
    embedding_service_pb2 = None
    embedding_service_pb2_grpc = None

logger = structlog.get_logger(__name__)
settings = get_settings()


class EmbeddingServicer(embedding_service_pb2_grpc.EmbeddingServiceServicer):
    """
    gRPC service implementation for embedding operations.

    Provides high-performance text embedding generation.
    """

    def __init__(self):
        """Initialize servicer."""
        self._service = None
        self._model_load_time_ms = 0
        logger.info("EmbeddingServicer initialized")

    def _get_service(self):
        """Get embedding service (lazy loading)."""
        if self._service is None:
            start = time.time()
            self._service = get_embedding_service()
            # Trigger model loading
            _ = self._service.embedding_dim
            self._model_load_time_ms = int((time.time() - start) * 1000)
        return self._service

    # =========================================================================
    # Health Check
    # =========================================================================

    async def Health(
        self,
        request: "embedding_service_pb2.HealthRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.HealthResponse":
        """Service health check."""
        service = self._get_service()

        return embedding_service_pb2.HealthResponse(
            status="healthy",
            model_loaded=service._model is not None,
            model_name=settings.model_name,
            dimension=service._embedding_dim or 0,
            model_load_time_ms=self._model_load_time_ms,
        )

    # =========================================================================
    # Encoding Operations
    # =========================================================================

    async def Encode(
        self,
        request: "embedding_service_pb2.EncodeRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.EncodeResponse":
        """
        Encode multiple texts into embeddings.
        """
        start = time.time()
        service = self._get_service()

        texts = list(request.texts)
        batch_size = request.batch_size or 32

        if not texts:
            return embedding_service_pb2.EncodeResponse(
                embeddings=[],
                dimension=service.embedding_dim,
                count=0,
                processing_time_ms=0,
            )

        logger.debug("gRPC Encode", text_count=len(texts), batch_size=batch_size)

        embeddings_list = service.encode(texts, batch_size=batch_size)

        # Convert to protobuf format
        embeddings = [
            embedding_service_pb2.Embedding(
                values=emb,
                dimension=len(emb),
            )
            for emb in embeddings_list
        ]

        processing_time_ms = int((time.time() - start) * 1000)

        return embedding_service_pb2.EncodeResponse(
            embeddings=embeddings,
            dimension=service.embedding_dim,
            count=len(embeddings),
            processing_time_ms=processing_time_ms,
        )

    async def EncodeSingle(
        self,
        request: "embedding_service_pb2.EncodeSingleRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.EncodeSingleResponse":
        """
        Encode a single text with caching.
        """
        start = time.time()
        service = self._get_service()

        text = request.text
        use_cache = request.use_cache if request.HasField("use_cache") else True

        # Check if cached
        cached = False
        if use_cache:
            cache_key = service._get_cache_key(text)
            cached = cache_key in service._query_cache

        embedding = service.encode_single(text, use_cache=use_cache)

        processing_time_ms = int((time.time() - start) * 1000)

        return embedding_service_pb2.EncodeSingleResponse(
            embedding=embedding_service_pb2.Embedding(
                values=embedding,
                dimension=len(embedding),
            ),
            cached=cached,
            processing_time_ms=processing_time_ms,
        )

    # =========================================================================
    # RAG Ingestion Operations
    # =========================================================================

    async def ChunkAndEmbed(
        self,
        request: "embedding_service_pb2.ChunkAndEmbedRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.ChunkAndEmbedResponse":
        """
        Chunk text and generate embeddings.
        """
        start = time.time()
        service = self._get_service()

        text = request.text
        page = request.page
        metadata = dict(request.metadata) if request.metadata else None
        batch_size = request.batch_size or 32

        if not text or not text.strip():
            return embedding_service_pb2.ChunkAndEmbedResponse(
                chunks=[],
                total_chunks=0,
                dimension=service.embedding_dim,
                processing_time_ms=0,
            )

        logger.debug(
            "gRPC ChunkAndEmbed",
            text_length=len(text),
            page=page,
            batch_size=batch_size,
        )

        results = service.chunk_and_embed(
            text=text,
            page=page,
            metadata=metadata,
            batch_size=batch_size,
        )

        # Convert to protobuf format
        chunks = [
            embedding_service_pb2.EmbeddedChunk(
                chunk_id=r["chunk_id"],
                text=r["text"],
                embedding=embedding_service_pb2.Embedding(
                    values=r["embedding"],
                    dimension=len(r["embedding"]),
                ),
                page=r["page"],
                metadata=r["metadata"] or {},
            )
            for r in results
        ]

        processing_time_ms = int((time.time() - start) * 1000)

        return embedding_service_pb2.ChunkAndEmbedResponse(
            chunks=chunks,
            total_chunks=len(chunks),
            dimension=service.embedding_dim,
            processing_time_ms=processing_time_ms,
        )

    async def BatchChunkAndEmbed(
        self,
        request: "embedding_service_pb2.BatchChunkAndEmbedRequest",
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator["embedding_service_pb2.DocumentResult"]:
        """
        Process multiple documents, streaming results.
        """
        service = self._get_service()
        batch_size = request.batch_size or 32

        for doc in request.documents:
            try:
                results = service.chunk_and_embed(
                    text=doc.text,
                    page=doc.page,
                    metadata=dict(doc.metadata) if doc.metadata else None,
                    batch_size=batch_size,
                )

                chunks = [
                    embedding_service_pb2.EmbeddedChunk(
                        chunk_id=r["chunk_id"],
                        text=r["text"],
                        embedding=embedding_service_pb2.Embedding(
                            values=r["embedding"],
                            dimension=len(r["embedding"]),
                        ),
                        page=r["page"],
                        metadata=r["metadata"] or {},
                    )
                    for r in results
                ]

                yield embedding_service_pb2.DocumentResult(
                    document_id=doc.id,
                    chunks=chunks,
                    success=True,
                    error="",
                )

            except Exception as e:
                logger.error(
                    "BatchChunkAndEmbed document failed",
                    document_id=doc.id,
                    error=str(e),
                )
                yield embedding_service_pb2.DocumentResult(
                    document_id=doc.id,
                    chunks=[],
                    success=False,
                    error=str(e),
                )

    # =========================================================================
    # Model & Cache Management
    # =========================================================================

    async def GetModelInfo(
        self,
        request: "embedding_service_pb2.ModelInfoRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.ModelInfoResponse":
        """Get model information."""
        service = self._get_service()

        return embedding_service_pb2.ModelInfoResponse(
            model_name=settings.model_name,
            dimension=service.embedding_dim,
            device=settings.device,
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens,
            cache_size=settings.query_cache_size,
            cache_used=len(service._query_cache),
        )

    async def ClearCache(
        self,
        request: "embedding_service_pb2.ClearCacheRequest",
        context: grpc.aio.ServicerContext,
    ) -> "embedding_service_pb2.ClearCacheResponse":
        """Clear query embedding cache."""
        service = self._get_service()

        entries = len(service._query_cache)
        service.clear_query_cache()

        return embedding_service_pb2.ClearCacheResponse(
            entries_removed=entries,
        )
