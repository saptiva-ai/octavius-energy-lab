"""
Query Understanding Service - Main Orchestrator

Coordinates intent classification, complexity analysis, and query expansion
to produce comprehensive query analysis.

Architecture:
- Service Layer: Orchestrates multiple analyzers
- Dependency Injection: Accepts custom classifiers/analyzers
- Observable: Detailed logging at each step

Usage:
    service = QueryUnderstandingService()
    analysis = await service.analyze_query(
        "¿Qué es esto?",
        context=QueryContext(conversation_id="123", documents_count=1)
    )
    # analysis.intent = QueryIntent.OVERVIEW
    # analysis.complexity = QueryComplexity.VAGUE
"""

from typing import Optional

import structlog

from .complexity_analyzer import ComplexityAnalyzer
from .intent_classifier import IntentClassifier
from .types import (
    QueryAnalysis,
    QueryComplexity,
    QueryContext,
    QueryIntent,
)

logger = structlog.get_logger(__name__)


class QueryUnderstandingService:
    """
    Main service for understanding user queries.

    Responsibilities:
    - Coordinate intent classification
    - Coordinate complexity analysis
    - Perform query expansion (for vague queries)
    - Calculate overall confidence
    - Produce comprehensive QueryAnalysis
    """

    def __init__(
        self,
        intent_classifier: Optional[IntentClassifier] = None,
        complexity_analyzer: Optional[ComplexityAnalyzer] = None,
    ):
        """
        Initialize service with pluggable components.

        Args:
            intent_classifier: Custom classifier (defaults to IntentClassifier)
            complexity_analyzer: Custom analyzer (defaults to ComplexityAnalyzer)
        """
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.complexity_analyzer = complexity_analyzer or ComplexityAnalyzer()

    async def analyze_query(self, query: str, context: QueryContext) -> QueryAnalysis:
        """
        Analyze query to extract intent, complexity, and produce expanded query.

        This is the main entry point for query understanding.

        Args:
            query: User query string
            context: Conversation context

        Returns:
            QueryAnalysis with all information needed for retrieval
        """
        logger.info(
            "Analyzing query",
            query_preview=query[:100],
            conversation_id=context.conversation_id,
            documents_count=context.documents_count,
        )

        # Step 1: Classify intent
        intent, intent_confidence, intent_reasoning = self.intent_classifier.classify(
            query, context
        )

        # Step 2: Analyze complexity
        complexity, complexity_confidence, complexity_reasoning = (
            self.complexity_analyzer.analyze(query, context)
        )

        # Step 3: Query expansion (if vague)
        expanded_query = await self._expand_query(query, intent, complexity, context)

        # Step 4: Entity extraction (simple version - just extract capitalized words)
        entities = self._extract_entities(query)

        # Step 5: Calculate overall confidence
        # Weight intent more heavily (70%) since it drives strategy selection
        overall_confidence = (intent_confidence * 0.7) + (complexity_confidence * 0.3)

        # Step 6: Build reasoning
        full_reasoning = (
            f"Intent: {intent_reasoning}. Complexity: {complexity_reasoning}."
        )

        # Create analysis result
        analysis = QueryAnalysis(
            original_query=query,
            intent=intent,
            complexity=complexity,
            expanded_query=expanded_query,
            entities=entities,
            confidence=overall_confidence,
            reasoning=full_reasoning,
            metadata={
                "intent_confidence": intent_confidence,
                "complexity_confidence": complexity_confidence,
            },
        )

        logger.info(
            "Query analysis complete",
            intent=intent.value,
            complexity=complexity.value,
            confidence=overall_confidence,
            expanded=expanded_query != query,
            entities_count=len(entities),
            query_preview=query[:50],
        )

        return analysis

    async def _expand_query(
        self,
        query: str,
        intent: QueryIntent,
        complexity: QueryComplexity,
        context: QueryContext,
    ) -> str:
        """
        Expand vague queries to improve retrieval.

        Strategy:
        - If query is VAGUE + OVERVIEW: Add document context
        - If query has pronouns: Replace with recent entities
        - Otherwise: Keep original query

        Args:
            query: Original query
            intent: Classified intent
            complexity: Classified complexity
            context: Conversation context

        Returns:
            Expanded query (or original if no expansion needed)
        """

        # Case 1: Vague overview question
        # "¿Qué es esto?" → "¿Qué contiene el documento? Proporciona un resumen general."
        if intent == QueryIntent.OVERVIEW and complexity == QueryComplexity.VAGUE:
            expanded = (
                f"{query} "
                "Proporciona un resumen general del contenido del documento, "
                "incluyendo los temas principales y la información más relevante."
            )

            logger.info(
                "Query expanded (vague overview)", original=query, expanded=expanded
            )

            return expanded

        # Case 2: Specific fact but vague (has pronouns without antecedent)
        # "¿Cuál es el precio de esto?" + context has "Producto X"
        # → "¿Cuál es el precio de Producto X?"
        if complexity == QueryComplexity.VAGUE and context.has_recent_entities:
            # Simple replacement: replace "esto/eso" with most recent entity
            expanded = query
            for pronoun in ["esto", "eso", "este", "ese"]:
                if pronoun in query.lower() and context.recent_entities:
                    entity = context.recent_entities[0]
                    expanded = expanded.replace(pronoun, entity)
                    expanded = expanded.replace(pronoun.capitalize(), entity)

            if expanded != query:
                logger.info(
                    "Query expanded (pronoun resolution)",
                    original=query,
                    expanded=expanded,
                    entities=context.recent_entities,
                )

            return expanded

        # Case 3: No expansion needed
        return query

    def _extract_entities(self, query: str) -> list[str]:
        """
        Extract entities from query (simple heuristic).

        Simple approach: Extract capitalized words (likely proper nouns).
        Future: Use spaCy NER or similar.

        Args:
            query: User query

        Returns:
            List of extracted entities
        """
        # Split and find capitalized words (excluding first word which may be capitalized)
        tokens = query.split()

        entities = []
        for i, token in enumerate(tokens):
            # Skip first word (may be capitalized as sentence start)
            if i == 0:
                continue

            # Check if token starts with uppercase (potential named entity)
            # Also check it's not a question word
            if token and token[0].isupper() and len(token) > 1:
                # Remove punctuation
                clean_token = token.strip(".,;:!?¿¡")
                if clean_token:
                    entities.append(clean_token)

        return entities


# Singleton instance for easy access
_query_understanding_service: Optional[QueryUnderstandingService] = None


def get_query_understanding_service() -> QueryUnderstandingService:
    """
    Get or create singleton query understanding service.

    Returns:
        QueryUnderstandingService instance
    """
    global _query_understanding_service

    if _query_understanding_service is None:
        _query_understanding_service = QueryUnderstandingService()

    return _query_understanding_service
