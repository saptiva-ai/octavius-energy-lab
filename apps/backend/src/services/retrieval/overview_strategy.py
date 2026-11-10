"""
Overview Retrieval Strategy - For generic document questions.

Used when user asks vague/general questions like:
- "¿Qué es esto?"
- "¿De qué trata?"
- "Resume el documento"

Strategy:
- Retrieve first N chunks from each document (provides context)
- No semantic search needed (user wants overview, not specific facts)
- Can optionally include document metadata
"""

from typing import Any, List

import structlog

from ...services.weaviate_service import get_weaviate_service
from .retrieval_strategy import RetrievalStrategy
from .types import Segment

logger = structlog.get_logger(__name__)


class OverviewRetrievalStrategy(RetrievalStrategy):
    """
    Retrieve document overview by returning first chunks.

    Best for:
    - Vague queries ("¿Qué es esto?")
    - Summary requests ("Resume el documento")
    - General exploration

    Rationale:
    - First chunks typically contain document intro/summary
    - No need for semantic search (we want breadth, not precision)
    - Fast and deterministic
    """

    def __init__(self, chunks_per_doc: int = 3):
        """
        Initialize strategy.

        Args:
            chunks_per_doc: Number of first chunks to retrieve per document
        """
        self.chunks_per_doc = chunks_per_doc

    async def retrieve(
        self,
        query: str,
        session_id: str,
        documents: List[Any],
        max_segments: int,
        **kwargs,
    ) -> List[Segment]:
        """
        Retrieve first N chunks from each document.

        Args:
            query: User query (used for logging only)
            session_id: Session ID
            documents: List of ready documents
            max_segments: Maximum total segments to return

        Returns:
            List of Segment objects (first chunks from each doc)
        """

        logger.info(
            "Retrieving overview segments",
            query_preview=query[:50],
            session_id=session_id,
            documents_count=len(documents),
            chunks_per_doc=self.chunks_per_doc,
        )

        weaviate_service = get_weaviate_service()
        all_segments = []

        # Get first N chunks from each document
        for doc in documents:
            # Fetch objects from Weaviate
            try:
                from weaviate.classes.query import Filter, Sort

                if not weaviate_service.client.is_connected():
                    weaviate_service._connect()

                collection = weaviate_service.client.collections.get(
                    weaviate_service.collection_name
                )

                # Fetch chunks filtered by session and document, sorted by chunk_id
                response = collection.query.fetch_objects(
                    filters=(
                        Filter.by_property("session_id").equal(session_id)
                        & Filter.by_property("document_id").equal(str(doc.id))
                    ),
                    limit=self.chunks_per_doc,
                    sort=Sort.by_property("chunk_id", ascending=True),
                    return_properties=["chunk_id", "text", "page", "metadata_json"],
                )

                for obj in response.objects:
                    # Parse metadata if present
                    meta = {}
                    if obj.properties.get("metadata_json"):
                        import json

                        try:
                            meta = json.loads(obj.properties["metadata_json"])
                        except:
                            pass

                    segment = Segment(
                        doc_id=str(doc.id),
                        doc_name=doc.filename,
                        chunk_id=obj.properties.get("chunk_id", 0),
                        text=obj.properties.get("text", ""),
                        score=1.0,  # Overview chunks all have same score
                        page=obj.properties.get("page", 0),
                        metadata=meta,
                    )
                    all_segments.append(segment)

            except Exception as e:
                logger.error(
                    "Failed to retrieve overview chunks for document",
                    doc_id=str(doc.id),
                    error=str(e),
                    exc_info=True,
                )
                continue

        # Limit to max_segments
        segments = all_segments[:max_segments]

        self._log_retrieval(
            strategy_name="OverviewRetrievalStrategy",
            query=query,
            segments_count=len(segments),
            max_score=1.0,
            documents_processed=len(documents),
        )

        return segments
