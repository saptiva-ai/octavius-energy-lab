"""
Embedding Service - Text to Vector Conversion.

Migrated from apps/backend/src/services/embedding_service.py

Architecture Decision Record (ADR):
-----------------------------------
1. **Model: paraphrase-multilingual-MiniLM-L12-v2**
   - Dimension: 384 (compact, fast)
   - Languages: 50+ including Spanish and English
   - Performance: ~50ms per chunk on CPU

2. **Chunking Strategy: Sliding Window with Overlap**
   - Chunk size: 500 tokens (~2000 chars)
   - Overlap: 100 tokens (~400 chars)

3. **Caching: LRU for frequent queries**
   - Cache size: 1000 queries = ~384 KB
   - Benefit: <1ms vs ~50ms for cached queries
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


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
    metadata: Optional[dict[str, Any]] = None


class EmbeddingService:
    """
    Service for generating embeddings and chunking text for RAG.

    Responsibilities:
    - Load and manage sentence-transformer model
    - Generate embeddings from text chunks
    - Chunk long text with sliding window strategy
    - Provide token estimation utilities

    Thread-safety: sentence-transformers is thread-safe after model loading.
    """

    def __init__(self):
        """Initialize embedding service."""
        self.model_name = settings.model_name
        self.device = settings.device

        # Chunking parameters
        self.chunk_size_tokens = settings.chunk_size_tokens
        self.chunk_overlap_tokens = settings.chunk_overlap_tokens

        # Approximate chars per token (GPT-style estimation)
        self.chars_per_token = 4

        logger.info(
            "Initializing embedding service",
            model=self.model_name,
            device=self.device,
            chunk_size=self.chunk_size_tokens,
            chunk_overlap=self.chunk_overlap_tokens,
        )

        # Load model (lazy - only when first needed)
        self._model = None
        self._embedding_dim = None

        # Query embedding cache (LRU)
        self._query_cache_size = settings.query_cache_size
        self._query_cache: dict[str, list[float]] = {}

    def _load_model(self):
        """Load sentence-transformer model (lazy initialization)."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model (this may take a few seconds)...")

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )

            self._embedding_dim = self._model.get_sentence_embedding_dimension()

            logger.info(
                "Embedding model loaded successfully",
                model=self.model_name,
                dimension=self._embedding_dim,
                device=self.device,
            )

        except Exception as e:
            logger.error(
                "Failed to load embedding model",
                model=self.model_name,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Embedding model loading failed: {e}") from e

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension."""
        if self._embedding_dim is None:
            self._load_model()
        return self._embedding_dim

    def encode(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self._load_model()

        try:
            logger.debug(
                "Generating embeddings",
                text_count=len(texts),
                batch_size=batch_size,
            )

            embeddings = self._model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

            embeddings_list = [emb.tolist() for emb in embeddings]

            logger.debug(
                "Embeddings generated",
                text_count=len(texts),
                embedding_dim=len(embeddings_list[0]) if embeddings_list else 0,
            )

            return embeddings_list

        except Exception as e:
            logger.error(
                "Failed to generate embeddings",
                text_count=len(texts),
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def encode_single(self, text: str, use_cache: bool = True) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            use_cache: Whether to use query cache

        Returns:
            Embedding vector
        """
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._query_cache:
                logger.debug("Query embedding cache hit", query_preview=text[:50])
                return self._query_cache[cache_key]

        embedding = self.encode([text])[0]

        if use_cache:
            self._update_cache(text, embedding)

        return embedding

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text using SHA256."""
        # Remove accents
        text_nfd = unicodedata.normalize("NFD", text)
        text_no_accents = "".join(
            char for char in text_nfd if unicodedata.category(char) != "Mn"
        )

        # Normalize
        normalized = re.sub(r"[^\w\s]", "", text_no_accents.lower().strip())
        normalized = re.sub(r"\s+", " ", normalized)

        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _update_cache(self, text: str, embedding: list[float]) -> None:
        """Update query embedding cache with LRU eviction."""
        cache_key = self._get_cache_key(text)

        if len(self._query_cache) >= self._query_cache_size:
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]
            logger.debug("Query cache eviction", cache_size=len(self._query_cache))

        self._query_cache[cache_key] = embedding
        logger.debug(
            "Query embedding cached",
            cache_size=len(self._query_cache),
            query_preview=text[:50],
        )

    def clear_query_cache(self) -> None:
        """Clear query embedding cache."""
        cache_size = len(self._query_cache)
        self._query_cache.clear()
        logger.info("Query embedding cache cleared", entries_removed=cache_size)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (~4 chars/token)."""
        return len(text) // self.chars_per_token

    def chunk_text(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[TextChunk]:
        """
        Chunk text using sliding window with overlap.

        Args:
            text: Input text to chunk
            page: Page number (for metadata)
            metadata: Additional metadata

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []

        chunk_size_chars = self.chunk_size_tokens * self.chars_per_token
        overlap_chars = self.chunk_overlap_tokens * self.chars_per_token

        text = re.sub(r"\s+", " ", text.strip())

        chunks = []
        chunk_id = 0
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size_chars, text_length)

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

            if start <= chunks[-1].start_char if chunks else False:
                start = end

        logger.debug(
            "Text chunked",
            text_length=text_length,
            chunks_created=len(chunks),
            avg_chunk_size=sum(len(c.text) for c in chunks) // len(chunks)
            if chunks
            else 0,
        )

        return chunks

    def chunk_and_embed(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> list[dict[str, Any]]:
        """
        Chunk text and generate embeddings in one step.

        This is the main method for document ingestion.

        Args:
            text: Input text to chunk and embed
            page: Page number
            metadata: Additional metadata
            batch_size: Batch size for embedding generation

        Returns:
            List of dicts with chunk_id, text, embedding, page, metadata
        """
        chunks = self.chunk_text(text, page=page, metadata=metadata)

        if not chunks:
            logger.warning("No chunks generated from text", text_length=len(text))
            return []

        chunk_texts = [c.text for c in chunks]
        embeddings = self.encode(chunk_texts, batch_size=batch_size)

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


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create singleton embedding service instance."""
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = EmbeddingService()

    return _embedding_service
