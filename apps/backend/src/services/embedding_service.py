"""
Embedding Service for RAG - Text to Vector Conversion

OPTIMIZATION 2026-01: Delegates to embedding-service plugin via gRPC.
This removes ~7GB of dependencies (torch, nvidia, sentence-transformers) from backend.

Architecture:
- Delegates encode/encode_single to embedding-service plugin via gRPC
- Chunking logic remains local (doesn't need ML model)
- Falls back to HTTP client if gRPC unavailable
- Feature flag: DELEGATE_EMBEDDINGS (default: true)

Chunking Strategy: Sliding Window with Overlap
- Chunk size: 500 tokens (~2000 chars)
- Overlap: 100 tokens (~400 chars)
- Token Counting: Approximate (chars / 4)
"""

import asyncio
import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# Feature flag for delegation
DELEGATE_EMBEDDINGS = os.getenv("DELEGATE_EMBEDDINGS", "true").lower() == "true"


@dataclass
class TextChunk:
    """
    Represents a chunk of text with its metadata.

    Attributes:
        chunk_id: Sequential index within document (0, 1, 2, ...)
        text: The actual chunk text
        start_char: Starting character position in original text
        end_char: Ending character position in original text
        page: Page number (if applicable, otherwise 0)
        metadata: Additional metadata (filename, etc.)
    """

    chunk_id: int
    text: str
    start_char: int
    end_char: int
    page: int = 0
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingService:
    """
    Service for generating embeddings and chunking text for RAG.

    Delegates embedding generation to embedding-service plugin via gRPC.
    Chunking logic remains local for efficiency.

    Thread-safety: Uses async clients for network operations.
    This service uses a singleton pattern.
    """

    def __init__(self):
        """
        Initialize embedding service.

        Environment variables:
        - DELEGATE_EMBEDDINGS: Delegate to embedding-service (default: true)
        - EMBEDDING_MODEL_NAME: Model name for reference (default: paraphrase-multilingual-MiniLM-L12-v2)
        """
        self.model_name = os.getenv(
            "EMBEDDING_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.delegate = DELEGATE_EMBEDDINGS

        # Chunking parameters
        self.chunk_size_tokens = int(os.getenv("CHUNK_SIZE_TOKENS", "500"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "100"))

        # Approximate chars per token (GPT-style estimation)
        self.chars_per_token = 4

        # Embedding dimension (will be fetched from service)
        self._embedding_dim: Optional[int] = None

        # Query embedding cache (LRU cache for frequently used queries)
        self._query_cache_size = int(os.getenv("QUERY_EMBEDDING_CACHE_SIZE", "1000"))
        self._query_cache: Dict[str, List[float]] = {}

        # Client instances (lazy initialization)
        self._grpc_client = None
        self._http_client = None

        logger.info(
            "Initializing embedding service",
            delegate=self.delegate,
            model=self.model_name,
            chunk_size=self.chunk_size_tokens,
            chunk_overlap=self.chunk_overlap_tokens,
        )

    async def _get_grpc_client(self):
        """Get or create gRPC client for embedding-service."""
        if self._grpc_client is None:
            try:
                from ..clients.embedding_service_grpc import get_embedding_grpc_client

                self._grpc_client = await get_embedding_grpc_client()
            except Exception as e:
                logger.warning(
                    "Failed to initialize gRPC client, will use HTTP fallback",
                    error=str(e),
                )
        return self._grpc_client

    async def _get_http_client(self):
        """Get or create HTTP client for embedding-service."""
        if self._http_client is None:
            try:
                from ..clients.embedding_service import get_embedding_client

                self._http_client = await get_embedding_client()
            except Exception as e:
                logger.warning(
                    "Failed to initialize HTTP client",
                    error=str(e),
                )
        return self._http_client

    @property
    def embedding_dim(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Embedding dimension (e.g., 384 for MiniLM)
        """
        if self._embedding_dim is None:
            # Default for paraphrase-multilingual-MiniLM-L12-v2
            self._embedding_dim = 384
        return self._embedding_dim

    async def _encode_via_grpc(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """Generate embeddings via gRPC client."""
        client = await self._get_grpc_client()
        if client is None:
            raise RuntimeError("gRPC client not available")

        embeddings = await client.encode(texts, batch_size=batch_size)

        # Update embedding dimension if we got results
        if embeddings and embeddings[0]:
            self._embedding_dim = len(embeddings[0])

        return embeddings

    async def _encode_via_http(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """Generate embeddings via HTTP client."""
        client = await self._get_http_client()
        if client is None:
            raise RuntimeError("HTTP client not available")

        # Client already returns embeddings list directly (not a dict)
        embeddings = await client.encode(texts)

        # Update embedding dimension
        if embeddings and embeddings[0]:
            self._embedding_dim = len(embeddings[0])

        return embeddings

    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for a list of texts (sync wrapper).

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing (default: 32)

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []

        # Run async method in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self.encode_async(texts, batch_size)
                    )
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(self.encode_async(texts, batch_size))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.encode_async(texts, batch_size))

    async def encode_async(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts (async).

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing (default: 32)

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []

        logger.debug(
            "Generating embeddings via delegation",
            text_count=len(texts),
            batch_size=batch_size,
        )

        # Try gRPC first
        try:
            embeddings = await self._encode_via_grpc(texts, batch_size)
            logger.debug(
                "Embeddings generated via gRPC",
                text_count=len(texts),
                embedding_dim=len(embeddings[0]) if embeddings else 0,
            )
            return embeddings
        except Exception as e:
            logger.warning(
                "gRPC encoding failed, trying HTTP fallback",
                error=str(e),
            )

        # Fallback to HTTP
        try:
            embeddings = await self._encode_via_http(texts, batch_size)
            logger.debug(
                "Embeddings generated via HTTP",
                text_count=len(texts),
                embedding_dim=len(embeddings[0]) if embeddings else 0,
            )
            return embeddings
        except Exception as e:
            logger.error(
                "All embedding methods failed",
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def encode_single(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text (sync convenience method).

        Args:
            text: Text to embed
            use_cache: Whether to use query cache (default: True)

        Returns:
            Embedding vector
        """
        # Check cache if enabled
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._query_cache:
                logger.debug("Query embedding cache hit", query_preview=text[:50])
                return self._query_cache[cache_key]

        # Generate embedding
        embedding = self.encode([text])[0]

        # Store in cache if enabled
        if use_cache:
            self._update_cache(text, embedding)

        return embedding

    async def encode_single_async(
        self, text: str, use_cache: bool = True
    ) -> List[float]:
        """
        Generate embedding for a single text (async).

        Args:
            text: Text to embed
            use_cache: Whether to use query cache (default: True)

        Returns:
            Embedding vector
        """
        # Check cache if enabled
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._query_cache:
                logger.debug("Query embedding cache hit", query_preview=text[:50])
                return self._query_cache[cache_key]

        # Generate embedding
        embeddings = await self.encode_async([text])
        embedding = embeddings[0]

        # Store in cache if enabled
        if use_cache:
            self._update_cache(text, embedding)

        return embedding

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key for text.

        Uses SHA256 hash to ensure consistent keys regardless of text length.
        """
        # Normalize: remove accents, lowercase, remove punctuation
        text_nfd = unicodedata.normalize("NFD", text)
        text_no_accents = "".join(
            char for char in text_nfd if unicodedata.category(char) != "Mn"
        )
        normalized = re.sub(r"[^\w\s]", "", text_no_accents.lower().strip())
        normalized = re.sub(r"\s+", " ", normalized)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _update_cache(self, text: str, embedding: List[float]) -> None:
        """Update query embedding cache with LRU eviction."""
        cache_key = self._get_cache_key(text)

        # If cache is full, evict oldest entry
        if len(self._query_cache) >= self._query_cache_size:
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]

        self._query_cache[cache_key] = embedding

    def clear_query_cache(self) -> None:
        """Clear query embedding cache."""
        cache_size = len(self._query_cache)
        self._query_cache.clear()
        logger.info("Query embedding cache cleared", entries_removed=cache_size)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses GPT-style approximation: 1 token ≈ 4 characters.
        """
        return len(text) // self.chars_per_token

    def chunk_text(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[TextChunk]:
        """
        Chunk text using sliding window with overlap.

        Strategy:
        1. Split text into chunks of ~chunk_size_tokens
        2. Use overlap of ~chunk_overlap_tokens between consecutive chunks
        3. Preserve word boundaries (don't split words)

        Args:
            text: Input text to chunk
            page: Page number (for metadata)
            metadata: Additional metadata to attach to chunks

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []

        # Convert token sizes to character sizes
        chunk_size_chars = self.chunk_size_tokens * self.chars_per_token
        overlap_chars = self.chunk_overlap_tokens * self.chars_per_token

        # Clean text: normalize whitespace
        text = re.sub(r"\s+", " ", text.strip())

        chunks = []
        chunk_id = 0
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size_chars, text_length)

            # Try to break at word boundary
            if end < text_length:
                last_space = text.rfind(" ", start, end)
                if last_space > start:
                    end = last_space

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    TextChunk(
                        chunk_id=chunk_id,
                        text=chunk_text,
                        start_char=start,
                        end_char=end,
                        page=page,
                        metadata=metadata or {},
                    )
                )
                chunk_id += 1

            if end >= text_length:
                break

            start = end - overlap_chars

            # Ensure progress
            if start <= chunks[-1].start_char if chunks else False:
                start = end

        logger.debug(
            "Text chunked",
            text_length=text_length,
            chunks_created=len(chunks),
        )

        return chunks

    def chunk_text_by_paragraphs(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[TextChunk]:
        """
        Chunk text using paragraph boundaries with merge.

        Instead of cutting at fixed character windows (which can split
        sentences and tables), this method:
        1. Splits text on double-newlines (paragraph boundaries).
        2. Merges consecutive short paragraphs until the chunk budget fills.
        3. Never splits a paragraph across two chunks.

        When a single paragraph exceeds the chunk budget, it falls back
        to the sliding-window strategy for that paragraph only.

        Args:
            text: Input text (should preserve paragraph breaks).
            page: Page number for metadata.
            metadata: Additional metadata to attach.

        Returns:
            List of TextChunk objects.
        """
        if not text or not text.strip():
            return []

        chunk_size_chars = self.chunk_size_tokens * self.chars_per_token
        overlap_chars = self.chunk_overlap_tokens * self.chars_per_token

        # Split into paragraphs preserving natural boundaries
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        # If no paragraph structure, fall back to sliding window
        if len(paragraphs) <= 1:
            return self.chunk_text(text, page=page, metadata=metadata)

        chunks: List[TextChunk] = []
        chunk_id = 0
        current_parts: List[str] = []
        current_chars = 0
        current_start = 0
        char_pos = 0  # track position in original text

        for para in paragraphs:
            para_len = len(para)

            # Single paragraph exceeds budget → split it with sliding window
            if para_len > chunk_size_chars:
                # Flush accumulated paragraphs first
                if current_parts:
                    merged = "\n\n".join(current_parts)
                    chunks.append(
                        TextChunk(
                            chunk_id=chunk_id,
                            text=merged,
                            start_char=current_start,
                            end_char=current_start + len(merged),
                            page=page,
                            metadata=metadata or {},
                        )
                    )
                    chunk_id += 1
                    current_parts = []
                    current_chars = 0

                # Split oversized paragraph with sliding window
                sub_chunks = self.chunk_text(para, page=page, metadata=metadata)
                for sc in sub_chunks:
                    sc.chunk_id = chunk_id
                    sc.start_char += char_pos
                    sc.end_char += char_pos
                    chunks.append(sc)
                    chunk_id += 1

                char_pos += para_len + 2  # +2 for the \n\n separator
                current_start = char_pos
                continue

            # Would adding this paragraph exceed the budget?
            separator_cost = 2 if current_parts else 0  # \n\n between parts
            if (
                current_chars + separator_cost + para_len > chunk_size_chars
                and current_parts
            ):
                # Flush current chunk
                merged = "\n\n".join(current_parts)
                chunks.append(
                    TextChunk(
                        chunk_id=chunk_id,
                        text=merged,
                        start_char=current_start,
                        end_char=current_start + len(merged),
                        page=page,
                        metadata=metadata or {},
                    )
                )
                chunk_id += 1

                # Start new chunk — carry over last paragraph as overlap context
                if current_parts and overlap_chars > 0:
                    last_part = current_parts[-1]
                    if len(last_part) <= overlap_chars:
                        current_parts = [last_part]
                        current_chars = len(last_part)
                        current_start = char_pos - len(last_part) - 2
                    else:
                        current_parts = []
                        current_chars = 0
                        current_start = char_pos
                else:
                    current_parts = []
                    current_chars = 0
                    current_start = char_pos

            # Accumulate paragraph
            if not current_parts:
                current_start = char_pos
            current_parts.append(para)
            current_chars += separator_cost + para_len
            char_pos += para_len + 2

        # Flush remaining paragraphs
        if current_parts:
            merged = "\n\n".join(current_parts)
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    text=merged,
                    start_char=current_start,
                    end_char=current_start + len(merged),
                    page=page,
                    metadata=metadata or {},
                )
            )

        logger.debug(
            "Text chunked by paragraphs",
            text_length=len(text),
            paragraphs_found=len(paragraphs),
            chunks_created=len(chunks),
        )

        return chunks

    def chunk_pages_and_embed(
        self,
        pages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> List[Dict[str, Any]]:
        """
        Chunk and embed document pages preserving page numbers.

        Instead of concatenating all pages into one string and losing page
        boundaries, this processes each page independently so every chunk
        records which page it came from.

        Args:
            pages: List of dicts with 'page' (int) and 'text' (str) keys.
            metadata: Additional metadata (e.g., filename).
            batch_size: Batch size for embedding generation.

        Returns:
            List of dicts with keys: chunk_id, text, embedding, page, metadata.
        """
        all_chunks: List[TextChunk] = []
        global_chunk_id = 0

        for page_data in pages:
            page_num = page_data.get("page", 0)
            page_text = page_data.get("text", "")

            if not page_text or not page_text.strip():
                continue

            page_chunks = self.chunk_text_by_paragraphs(
                text=page_text,
                page=page_num,
                metadata=metadata,
            )

            # Re-number chunk_ids globally across all pages
            for chunk in page_chunks:
                chunk.chunk_id = global_chunk_id
                global_chunk_id += 1
                all_chunks.append(chunk)

        if not all_chunks:
            logger.warning("No chunks generated from pages", pages_count=len(pages))
            return []

        # Generate embeddings for all chunks at once (batch efficiency)
        chunk_texts = [c.text for c in all_chunks]
        embeddings = self.encode(chunk_texts, batch_size=batch_size)

        result = []
        for chunk, embedding in zip(all_chunks, embeddings):
            result.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "embedding": embedding,
                    "page": chunk.page,
                    "metadata": chunk.metadata,
                }
            )

        logger.info(
            "Pages chunked by paragraphs and embedded",
            pages_count=len(pages),
            chunks_count=len(result),
            embedding_dim=len(embeddings[0]) if embeddings else 0,
        )

        return result

    def chunk_and_embed(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> List[Dict[str, Any]]:
        """
        Chunk text and generate embeddings in one step.

        Args:
            text: Input text to chunk and embed
            page: Page number
            metadata: Additional metadata
            batch_size: Batch size for embedding generation

        Returns:
            List of dicts with keys: chunk_id, text, embedding, page, metadata
        """
        # Step 1: Chunk text (local)
        chunks = self.chunk_text(text, page=page, metadata=metadata)

        if not chunks:
            logger.warning("No chunks generated from text", text_length=len(text))
            return []

        # Step 2: Generate embeddings (delegated)
        chunk_texts = [c.text for c in chunks]
        embeddings = self.encode(chunk_texts, batch_size=batch_size)

        # Step 3: Combine
        result = []
        for chunk, embedding in zip(chunks, embeddings):
            result.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "embedding": embedding,
                    "page": chunk.page,
                    "metadata": chunk.metadata,
                }
            )

        logger.info(
            "Text chunked and embedded",
            text_length=len(text),
            chunks_count=len(result),
            embedding_dim=len(embeddings[0]) if embeddings else 0,
        )

        return result

    async def chunk_and_embed_async(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> List[Dict[str, Any]]:
        """
        Chunk text and generate embeddings (async version).
        """
        chunks = self.chunk_text(text, page=page, metadata=metadata)

        if not chunks:
            return []

        chunk_texts = [c.text for c in chunks]
        embeddings = await self.encode_async(chunk_texts, batch_size=batch_size)

        result = []
        for chunk, embedding in zip(chunks, embeddings):
            result.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "embedding": embedding,
                    "page": chunk.page,
                    "metadata": chunk.metadata,
                }
            )

        return result


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get or create singleton embedding service instance.

    This is the preferred way to access EmbeddingService in the app.

    Returns:
        EmbeddingService instance
    """
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = EmbeddingService()

    return _embedding_service
