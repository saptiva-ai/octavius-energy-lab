"""
Semantic Search Strategy - Vector similarity search with adaptive threshold.

Used for specific factual questions that require precise retrieval:
- "¿Cuál es el precio?"
- "¿Quién es el CEO?"
- "¿Cuándo se fundó la empresa?"

Strategy:
- Generate embedding for query
- Perform cosine similarity search in Weaviate
- Adaptive threshold based on query characteristics
- Optional re-ranking with cross-encoder (future enhancement)
"""

from typing import Any, List

import structlog

from ...services.embedding_service import get_embedding_service
from ...services.weaviate_service import get_weaviate_service
from .retrieval_strategy import RetrievalStrategy
from .types import Segment

logger = structlog.get_logger(__name__)


class SemanticSearchStrategy(RetrievalStrategy):
    """
    Retrieve segments using semantic similarity search.

    Best for:
    - Specific fact-finding queries
    - Targeted information retrieval
    - Queries with clear information needs

    Features:
    - Adaptive score threshold (adjusts based on query/corpus)
    - Cosine similarity ranking
    - Session-based filtering (privacy/security)
    """

    def __init__(self, base_threshold: float = 0.3):
        """
        Initialize strategy.

        Args:
            base_threshold: Base similarity threshold (0.0 to 1.0)
                          Lower = more permissive, more results
                          Higher = stricter, fewer but more relevant results
        """
        self.base_threshold = base_threshold

    async def retrieve(
        self,
        query: str,
        session_id: str,
        documents: List[Any],
        max_segments: int,
        **kwargs,
    ) -> List[Segment]:
        """
        Perform semantic search to retrieve relevant segments.

        Args:
            query: User query (expanded if vague)
            session_id: Session ID for filtering
            documents: List of ready documents
            max_segments: Maximum segments to return
            **kwargs: Optional overrides (e.g., threshold_override)

        Returns:
            List of Segment objects, ranked by relevance
        """

        logger.info(
            "Performing semantic search",
            query_preview=query[:50],
            session_id=session_id,
            documents_count=len(documents),
            max_segments=max_segments,
        )

        # Step 1: Calculate adaptive threshold
        threshold = self._calculate_adaptive_threshold(
            query, documents, override=kwargs.get("threshold_override")
        )

        # Step 2: Generate query embedding
        embedding_service = get_embedding_service()
        query_vector = embedding_service.encode_single(query)

        logger.debug(
            "Query embedding generated",
            vector_dim=len(query_vector),
            threshold=threshold,
        )

        # Step 3: Perform Weaviate search (Adaptive/Hybrid)
        weaviate_service = get_weaviate_service()

        try:
            # We pass query_text to enable Hybrid Search and Adaptive Retrieval
            search_results = weaviate_service.search(
                session_id=session_id,
                query_vector=query_vector,
                top_k=max_segments * 2,  # Over-fetch for potential re-ranking
                score_threshold=threshold,
                query_text=query,
            )

            # Step 4: Convert to Segment objects
            segments = []
            for result in search_results[:max_segments]:
                # Find matching document for metadata
                doc = next(
                    (d for d in documents if str(d.id) == result["document_id"]), None
                )

                segment = Segment(
                    doc_id=result["document_id"],
                    doc_name=(
                        result.get("metadata", {}).get("filename", "Unknown")
                        if not doc
                        else doc.filename
                    ),
                    chunk_id=result["chunk_id"],
                    text=result["text"],
                    score=result["score"],
                    page=result.get("page", 0),
                    metadata=result.get("metadata", {}),
                )
                segments.append(segment)

            max_score = max((s.score for s in segments), default=0.0)

            self._log_retrieval(
                strategy_name="SemanticSearchStrategy",
                query=query,
                segments_count=len(segments),
                max_score=max_score,
                threshold=threshold,
                avg_score=(
                    sum(s.score for s in segments) / len(segments) if segments else 0.0
                ),
            )

            return segments

        except Exception as e:
            logger.error(
                "Semantic search failed",
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )
            # Return empty list on error (graceful degradation)
            return []

    def _calculate_adaptive_threshold(
        self, query: str, documents: List[Any], override: float | None = None
    ) -> float:
        """
        Calculate adaptive score threshold based on context.

        Factors considered:
        1. Query length (shorter queries → lower threshold)
        2. Corpus size (more docs → slightly higher threshold)
        3. Manual override (if provided)

        Args:
            query: User query
            documents: Available documents
            override: Manual threshold override

        Returns:
            Calculated threshold (0.0 to 1.0)
        """

        # If manual override provided, use it
        if override is not None:
            return max(0.0, min(1.0, override))

        threshold = self.base_threshold

        # Factor 1: Query length
        # Short queries (< 5 words) get lower threshold
        word_count = len(query.split())
        if word_count < 5:
            threshold -= 0.15
            logger.debug(
                "Lowering threshold for short query",
                word_count=word_count,
                adjustment=-0.15,
            )
        elif word_count > 15:
            threshold += 0.05
            logger.debug(
                "Raising threshold for long query",
                word_count=word_count,
                adjustment=+0.05,
            )

        # Factor 2: Corpus size
        # More documents → slightly stricter
        if len(documents) > 5:
            threshold += 0.05
            logger.debug(
                "Raising threshold for large corpus",
                doc_count=len(documents),
                adjustment=+0.05,
            )

        # Clamp to valid range
        final_threshold = max(0.0, min(0.8, threshold))

        logger.info(
            "Adaptive threshold calculated",
            base=self.base_threshold,
            final=final_threshold,
            query_length=word_count,
            corpus_size=len(documents),
        )

        return final_threshold
