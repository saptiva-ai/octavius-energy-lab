"""
Embeddings router - API endpoints for embedding generation.

Endpoints:
- POST /encode: Generate embeddings for multiple texts
- POST /encode-single: Generate embedding for a single text
- POST /chunk-and-embed: Chunk text and generate embeddings
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services.embedding import get_embedding_service

router = APIRouter()
logger = structlog.get_logger(__name__)
settings = get_settings()


# =============================================================================
# Request/Response Models
# =============================================================================


class EncodeRequest(BaseModel):
    """Request for batch embedding generation."""

    texts: list[str] = Field(..., min_length=1, description="List of texts to embed")
    batch_size: int = Field(default=32, ge=1, le=128, description="Batch size")


class EncodeResponse(BaseModel):
    """Response with embeddings."""

    embeddings: list[list[float]]
    dimension: int
    count: int


class EncodeSingleRequest(BaseModel):
    """Request for single text embedding."""

    text: str = Field(..., min_length=1, description="Text to embed")
    use_cache: bool = Field(default=True, description="Use embedding cache")


class EncodeSingleResponse(BaseModel):
    """Response with single embedding."""

    embedding: list[float]
    dimension: int
    cached: bool = False


class ChunkAndEmbedRequest(BaseModel):
    """Request for chunking and embedding text."""

    text: str = Field(..., min_length=1, description="Text to chunk and embed")
    page: int = Field(default=0, ge=0, description="Page number for metadata")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")
    batch_size: int = Field(default=32, ge=1, le=128, description="Batch size")


class ChunkResult(BaseModel):
    """Single chunk with embedding."""

    chunk_id: int
    text: str
    embedding: list[float]
    page: int
    metadata: dict[str, Any] | None


class ChunkAndEmbedResponse(BaseModel):
    """Response with chunked and embedded text."""

    chunks: list[ChunkResult]
    total_chunks: int
    dimension: int


class ModelInfoResponse(BaseModel):
    """Model information response."""

    model_name: str
    dimension: int
    device: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    cache_size: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/encode", response_model=EncodeResponse)
async def encode_texts(request: EncodeRequest) -> EncodeResponse:
    """
    Generate embeddings for multiple texts.

    Args:
        request: EncodeRequest with list of texts

    Returns:
        EncodeResponse with embeddings
    """
    try:
        service = get_embedding_service()
        embeddings = service.encode(request.texts, batch_size=request.batch_size)

        logger.info(
            "Texts encoded",
            count=len(request.texts),
            dimension=len(embeddings[0]) if embeddings else 0,
        )

        return EncodeResponse(
            embeddings=embeddings,
            dimension=len(embeddings[0]) if embeddings else 0,
            count=len(embeddings),
        )

    except Exception as e:
        logger.error("Encoding failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Encoding failed: {e}")


@router.post("/encode-single", response_model=EncodeSingleResponse)
async def encode_single_text(request: EncodeSingleRequest) -> EncodeSingleResponse:
    """
    Generate embedding for a single text.

    Uses caching by default for repeated queries.

    Args:
        request: EncodeSingleRequest with text

    Returns:
        EncodeSingleResponse with embedding
    """
    try:
        service = get_embedding_service()

        # Check if cached (for response metadata)
        cached = False
        if request.use_cache:
            cache_key = service._get_cache_key(request.text)
            cached = cache_key in service._query_cache

        embedding = service.encode_single(request.text, use_cache=request.use_cache)

        logger.debug(
            "Single text encoded",
            text_preview=request.text[:50],
            cached=cached,
        )

        return EncodeSingleResponse(
            embedding=embedding,
            dimension=len(embedding),
            cached=cached,
        )

    except Exception as e:
        logger.error("Single encoding failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Encoding failed: {e}")


@router.post("/chunk-and-embed", response_model=ChunkAndEmbedResponse)
async def chunk_and_embed_text(request: ChunkAndEmbedRequest) -> ChunkAndEmbedResponse:
    """
    Chunk text and generate embeddings for each chunk.

    This is the main method for document ingestion in RAG systems.

    Args:
        request: ChunkAndEmbedRequest with text

    Returns:
        ChunkAndEmbedResponse with chunks and embeddings
    """
    try:
        service = get_embedding_service()
        results = service.chunk_and_embed(
            text=request.text,
            page=request.page,
            metadata=request.metadata,
            batch_size=request.batch_size,
        )

        chunks = [
            ChunkResult(
                chunk_id=r["chunk_id"],
                text=r["text"],
                embedding=r["embedding"],
                page=r["page"],
                metadata=r["metadata"],
            )
            for r in results
        ]

        logger.info(
            "Text chunked and embedded",
            text_length=len(request.text),
            chunks_count=len(chunks),
        )

        return ChunkAndEmbedResponse(
            chunks=chunks,
            total_chunks=len(chunks),
            dimension=len(chunks[0].embedding) if chunks else 0,
        )

    except Exception as e:
        logger.error("Chunk and embed failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chunk and embed failed: {e}")


@router.get("/info", response_model=ModelInfoResponse)
async def get_model_info() -> ModelInfoResponse:
    """
    Get embedding model information.

    Returns model configuration and current settings.
    """
    service = get_embedding_service()

    # Trigger model load if not loaded (to get dimension)
    _ = service.embedding_dim

    return ModelInfoResponse(
        model_name=settings.model_name,
        dimension=service.embedding_dim,
        device=settings.device,
        chunk_size_tokens=settings.chunk_size_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
        cache_size=settings.query_cache_size,
    )


@router.delete("/cache")
async def clear_cache():
    """
    Clear the query embedding cache.

    Useful for testing or memory management.
    """
    service = get_embedding_service()
    cache_size = len(service._query_cache)
    service.clear_query_cache()

    return {"message": "Cache cleared", "entries_removed": cache_size}
