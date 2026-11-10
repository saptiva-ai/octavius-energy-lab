"""
Adaptive Retrieval Orchestrator - Intelligent Strategy Selection

Main orchestrator that:
1. Analyzes query (using QueryUnderstandingService)
2. Selects appropriate retrieval strategy
3. Executes retrieval
4. Post-processes results
5. Returns comprehensive RetrievalResult

Architecture:
- Strategy registry: Maps (intent, complexity) → strategy
- Fallback strategy: Default when no perfect match
- Observable: Detailed logging of decision process

Design Principles:
- SOLID: Depends on abstractions (RetrievalStrategy interface)
- Open/Closed: Easy to add new strategies without modifying orchestrator
- Single Responsibility: Only orchestrates, doesn't implement retrieval logic
"""

from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..query_understanding import (
    QueryComplexity,
    QueryContext,
    QueryIntent,
    QueryUnderstandingService,
    get_query_understanding_service,
)
from .overview_strategy import OverviewRetrievalStrategy
from .retrieval_strategy import RetrievalStrategy
from .semantic_search_strategy import SemanticSearchStrategy
from .types import RetrievalResult, Segment

logger = structlog.get_logger(__name__)


class AdaptiveRetrievalOrchestrator:
    """
    Orchestrate retrieval by selecting optimal strategy based on query analysis.

    Flow:
    1. Analyze query → (intent, complexity, expanded_query)
    2. Select strategy from registry
    3. Execute retrieval
    4. Post-process (fallbacks, quality checks)
    5. Return result with metadata
    """

    def __init__(
        self, query_understanding_service: Optional[QueryUnderstandingService] = None
    ):
        """
        Initialize orchestrator.

        Args:
            query_understanding_service: Custom service (defaults to singleton)
        """
        self.query_understanding = (
            query_understanding_service or get_query_understanding_service()
        )

        # Strategy registry: (intent, complexity) → strategy
        # Defines which strategy to use for each query type
        self.strategy_registry: Dict[
            Tuple[QueryIntent, QueryComplexity], RetrievalStrategy
        ] = {
            # Overview queries (vague or simple)
            (QueryIntent.OVERVIEW, QueryComplexity.VAGUE): OverviewRetrievalStrategy(
                chunks_per_doc=3
            ),
            (QueryIntent.OVERVIEW, QueryComplexity.SIMPLE): OverviewRetrievalStrategy(
                chunks_per_doc=2
            ),
            # Definitional queries (need precise retrieval)
            (QueryIntent.DEFINITIONAL, QueryComplexity.SIMPLE): SemanticSearchStrategy(
                base_threshold=0.4
            ),
            (QueryIntent.DEFINITIONAL, QueryComplexity.COMPLEX): SemanticSearchStrategy(
                base_threshold=0.3
            ),
            # Specific fact queries
            (QueryIntent.SPECIFIC_FACT, QueryComplexity.SIMPLE): SemanticSearchStrategy(
                base_threshold=0.35
            ),
            (
                QueryIntent.SPECIFIC_FACT,
                QueryComplexity.COMPLEX,
            ): SemanticSearchStrategy(base_threshold=0.25),
            (QueryIntent.SPECIFIC_FACT, QueryComplexity.VAGUE): SemanticSearchStrategy(
                base_threshold=0.2
            ),
            # Quantitative queries (numbers/amounts)
            (QueryIntent.QUANTITATIVE, QueryComplexity.SIMPLE): SemanticSearchStrategy(
                base_threshold=0.4
            ),
            (QueryIntent.QUANTITATIVE, QueryComplexity.COMPLEX): SemanticSearchStrategy(
                base_threshold=0.3
            ),
            # Procedural queries (how-to)
            (QueryIntent.PROCEDURAL, QueryComplexity.SIMPLE): SemanticSearchStrategy(
                base_threshold=0.35
            ),
            (QueryIntent.PROCEDURAL, QueryComplexity.COMPLEX): SemanticSearchStrategy(
                base_threshold=0.25
            ),
            # Analytical queries (why)
            (QueryIntent.ANALYTICAL, QueryComplexity.SIMPLE): SemanticSearchStrategy(
                base_threshold=0.3
            ),
            (QueryIntent.ANALYTICAL, QueryComplexity.COMPLEX): SemanticSearchStrategy(
                base_threshold=0.2
            ),
            # Comparison queries
            (QueryIntent.COMPARISON, QueryComplexity.COMPLEX): SemanticSearchStrategy(
                base_threshold=0.25
            ),
        }

        # Fallback strategy (when no specific match)
        self.fallback_strategy = SemanticSearchStrategy(base_threshold=0.3)

        logger.info(
            "AdaptiveRetrievalOrchestrator initialized",
            registered_strategies=len(self.strategy_registry),
            fallback="SemanticSearchStrategy(0.3)",
        )

    async def retrieve(
        self,
        query: str,
        session_id: str,
        documents: List[Any],
        max_segments: int,
        context: Optional[QueryContext] = None,
    ) -> RetrievalResult:
        """
        Main entry point: Analyze query and execute adaptive retrieval.

        Args:
            query: User query
            session_id: Session/conversation ID
            documents: List of ready documents
            max_segments: Maximum segments to return
            context: Optional query context (defaults to basic context)

        Returns:
            RetrievalResult with segments and metadata
        """

        # Build context if not provided
        if context is None:
            context = QueryContext(
                conversation_id=session_id,
                documents_count=len(documents),
                has_recent_entities=False,
                recent_entities=[],
            )

        logger.info(
            "Starting adaptive retrieval",
            query_preview=query[:50],
            session_id=session_id,
            documents_count=len(documents),
            max_segments=max_segments,
        )

        # Step 1: Analyze query
        analysis = await self.query_understanding.analyze_query(query, context)

        logger.info(
            "Query analyzed for retrieval",
            intent=analysis.intent.value,
            complexity=analysis.complexity.value,
            confidence=analysis.confidence,
            query_expanded=analysis.expanded_query != analysis.original_query,
        )

        # Step 2: Select strategy
        strategy = self._select_strategy(analysis.intent, analysis.complexity)

        logger.info(
            "Strategy selected",
            strategy=strategy.__class__.__name__,
            intent=analysis.intent.value,
            complexity=analysis.complexity.value,
        )

        # Step 3: Execute retrieval
        try:
            segments = await strategy.retrieve(
                query=analysis.expanded_query,  # Use expanded query
                session_id=session_id,
                documents=documents,
                max_segments=max_segments,
            )

            logger.info(
                "Retrieval executed",
                segments_count=len(segments),
                strategy=strategy.__class__.__name__,
                max_score=max((s.score for s in segments), default=0.0),
            )

        except Exception as e:
            logger.error(
                "Retrieval execution failed",
                strategy=strategy.__class__.__name__,
                error=str(e),
                exc_info=True,
            )
            # Return empty result on error
            segments = []

        # Step 4: Post-processing and fallbacks
        segments = await self._post_process(
            segments, analysis, query, session_id, documents, max_segments
        )

        # Step 5: Build result
        result = RetrievalResult(
            segments=segments,
            strategy_used=strategy.__class__.__name__,
            query_analysis=analysis,
            confidence=analysis.confidence,
            metadata={
                "intent": analysis.intent.value,
                "complexity": analysis.complexity.value,
                "query_expanded": analysis.expanded_query != analysis.original_query,
                "reasoning": analysis.reasoning,
            },
        )

        logger.info(
            "Adaptive retrieval complete",
            segments_count=len(segments),
            max_score=result.max_score,
            avg_score=result.avg_score,
            strategy=result.strategy_used,
            confidence=result.confidence,
        )

        return result

    def _select_strategy(
        self, intent: QueryIntent, complexity: QueryComplexity
    ) -> RetrievalStrategy:
        """
        Select retrieval strategy from registry.

        Args:
            intent: Query intent
            complexity: Query complexity

        Returns:
            RetrievalStrategy instance
        """

        key = (intent, complexity)

        # Try exact match
        if key in self.strategy_registry:
            return self.strategy_registry[key]

        # Try intent-only match (any complexity)
        for (reg_intent, reg_complexity), strategy in self.strategy_registry.items():
            if reg_intent == intent:
                logger.debug(
                    "Strategy selected (intent match only)",
                    intent=intent.value,
                    requested_complexity=complexity.value,
                    matched_complexity=reg_complexity.value,
                )
                return strategy

        # Fallback
        logger.debug(
            "Using fallback strategy",
            intent=intent.value,
            complexity=complexity.value,
            fallback=self.fallback_strategy.__class__.__name__,
        )
        return self.fallback_strategy

    async def _post_process(
        self,
        segments: List[Segment],
        analysis,
        query: str,
        session_id: str,
        documents: List[Any],
        max_segments: int,
    ) -> List[Segment]:
        """
        Post-process retrieval results.

        Fallbacks:
        - If overview query got 0 results → try getting first chunks
        - If semantic search got 0 results with high threshold → retry with lower threshold

        Args:
            segments: Initial retrieval results
            analysis: Query analysis
            query: Original query
            session_id: Session ID
            documents: Available documents
            max_segments: Max segments

        Returns:
            Post-processed segments
        """

        # Fallback 1: Overview query with no results
        if analysis.intent == QueryIntent.OVERVIEW and len(segments) == 0:
            logger.warning(
                "Overview query returned 0 segments, applying fallback",
                query_preview=query[:50],
            )

            # Fallback: Get first chunks
            fallback_strategy = OverviewRetrievalStrategy(chunks_per_doc=2)
            segments = await fallback_strategy.retrieve(
                query=query,
                session_id=session_id,
                documents=documents,
                max_segments=max_segments,
            )

            logger.info("Fallback applied (overview)", fallback_segments=len(segments))

        # Fallback 2: Specific query with no results (threshold too high?)
        elif analysis.intent != QueryIntent.OVERVIEW and len(segments) == 0:
            logger.warning(
                "Specific query returned 0 segments, applying lower threshold fallback",
                query_preview=query[:50],
                original_intent=analysis.intent.value,
            )

            # Retry with very low threshold
            fallback_strategy = SemanticSearchStrategy(base_threshold=0.0)
            segments = await fallback_strategy.retrieve(
                query=analysis.expanded_query,
                session_id=session_id,
                documents=documents,
                max_segments=max_segments,
                threshold_override=0.0,  # Override to get ANY results
            )

            logger.info(
                "Fallback applied (low threshold)",
                fallback_segments=len(segments),
                max_score=max((s.score for s in segments), default=0.0),
            )

        return segments
