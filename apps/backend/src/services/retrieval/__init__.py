"""
Retrieval Strategy Module - Adaptive Document Retrieval

Implements Strategy Pattern for different retrieval approaches:
- OverviewRetrieval: For generic document questions
- SemanticSearch: For specific fact-finding
- HybridRetrieval: BM25 + Semantic (best of both worlds)

Architecture:
- Strategy Pattern: Different strategies for different query types
- Adaptive Orchestrator: Selects strategy based on query analysis
- Observable: Detailed logging and metrics
"""

from .adaptive_orchestrator import AdaptiveRetrievalOrchestrator
from .overview_strategy import OverviewRetrievalStrategy
from .retrieval_strategy import RetrievalStrategy
from .semantic_search_strategy import SemanticSearchStrategy
from .types import RetrievalResult, Segment

__all__ = [
    "Segment",
    "RetrievalResult",
    "RetrievalStrategy",
    "OverviewRetrievalStrategy",
    "SemanticSearchStrategy",
    "AdaptiveRetrievalOrchestrator",
]
