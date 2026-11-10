"""
Type definitions for Retrieval module.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Segment:
    """
    A document segment/chunk retrieved for RAG.

    Attributes:
        doc_id: Document ID
        doc_name: Document filename
        chunk_id: Chunk index within document
        text: Chunk text content
        score: Relevance score (0.0 to 1.0)
        page: Page number (if applicable)
        metadata: Additional metadata
    """

    doc_id: str
    doc_name: str
    chunk_id: int
    text: str
    score: float
    page: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "index": self.chunk_id,  # Legacy field name
            "text": self.text,
            "score": self.score,
            "page": self.page,
            **self.metadata,
        }


@dataclass
class RetrievalResult:
    """
    Result of retrieval operation.

    Contains segments plus metadata about the retrieval process.
    """

    segments: List[Segment]
    strategy_used: str
    query_analysis: Optional[Any] = None  # QueryAnalysis
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def max_score(self) -> float:
        """Maximum relevance score among segments."""
        return max((s.score for s in self.segments), default=0.0)

    @property
    def avg_score(self) -> float:
        """Average relevance score across segments."""
        if not self.segments:
            return 0.0
        return sum(s.score for s in self.segments) / len(self.segments)
