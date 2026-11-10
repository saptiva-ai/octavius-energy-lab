"""
Abstract base class for retrieval strategies.

Defines interface that all retrieval strategies must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, List

import structlog

from .types import Segment

logger = structlog.get_logger(__name__)


class RetrievalStrategy(ABC):
    """
    Abstract base class for document retrieval strategies.

    Strategy Pattern: Each concrete strategy implements a different
    approach to retrieving relevant document segments.

    All strategies must implement the `retrieve` method.
    """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        session_id: str,
        documents: List[Any],  # List[Document]
        max_segments: int,
        **kwargs,
    ) -> List[Segment]:
        """
        Retrieve relevant segments for the given query.

        Args:
            query: User query (may be expanded)
            session_id: Conversation/session ID
            documents: List of ready documents
            max_segments: Maximum number of segments to return
            **kwargs: Additional strategy-specific parameters

        Returns:
            List of relevant segments, ordered by relevance

        Raises:
            Exception: On retrieval errors
        """
        pass

    def _log_retrieval(
        self,
        strategy_name: str,
        query: str,
        segments_count: int,
        max_score: float,
        **extra_fields,
    ):
        """
        Helper to log retrieval results consistently.

        Args:
            strategy_name: Name of the strategy
            query: User query
            segments_count: Number of segments retrieved
            max_score: Maximum relevance score
            **extra_fields: Additional fields to log
        """
        logger.info(
            "Retrieval completed",
            strategy=strategy_name,
            query_preview=query[:50],
            segments_count=segments_count,
            max_score=max_score,
            **extra_fields,
        )
