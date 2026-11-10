"""
Unit tests for QueryUnderstandingService.

Tests:
- Service initialization with default and custom components
- Full query analysis flow
- Query expansion (vague, pronouns, no expansion)
- Entity extraction
- Singleton pattern
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.services.query_understanding.query_understanding_service import (
    QueryUnderstandingService,
    get_query_understanding_service,
    _query_understanding_service,
)
from src.services.query_understanding.types import (
    QueryAnalysis,
    QueryComplexity,
    QueryContext,
    QueryIntent,
)
from src.services.query_understanding.intent_classifier import IntentClassifier
from src.services.query_understanding.complexity_analyzer import ComplexityAnalyzer


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def basic_context():
    """Create a basic query context."""
    return QueryContext(
        conversation_id="conv-123",
        documents_count=1,
        has_recent_entities=False,
        recent_entities=[],
    )


@pytest.fixture
def context_with_entities():
    """Create a context with recent entities."""
    return QueryContext(
        conversation_id="conv-456",
        documents_count=2,
        has_recent_entities=True,
        recent_entities=["Producto ABC", "Cliente XYZ"],
    )


@pytest.fixture
def mock_intent_classifier():
    """Create a mock intent classifier."""
    classifier = Mock(spec=IntentClassifier)
    classifier.classify = Mock(return_value=(
        QueryIntent.OVERVIEW,
        0.85,
        "Question asks for general information"
    ))
    return classifier


@pytest.fixture
def mock_complexity_analyzer():
    """Create a mock complexity analyzer."""
    analyzer = Mock(spec=ComplexityAnalyzer)
    analyzer.analyze = Mock(return_value=(
        QueryComplexity.SIMPLE,
        0.90,
        "Single entity question"
    ))
    return analyzer


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestQueryUnderstandingServiceInit:
    """Tests for service initialization."""

    def test_init_with_defaults(self):
        """Should create default classifiers when none provided."""
        service = QueryUnderstandingService()

        assert service.intent_classifier is not None
        assert service.complexity_analyzer is not None
        assert isinstance(service.intent_classifier, IntentClassifier)
        assert isinstance(service.complexity_analyzer, ComplexityAnalyzer)

    def test_init_with_custom_classifier(self, mock_intent_classifier):
        """Should accept custom intent classifier."""
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier
        )

        assert service.intent_classifier is mock_intent_classifier

    def test_init_with_custom_analyzer(self, mock_complexity_analyzer):
        """Should accept custom complexity analyzer."""
        service = QueryUnderstandingService(
            complexity_analyzer=mock_complexity_analyzer
        )

        assert service.complexity_analyzer is mock_complexity_analyzer

    def test_init_with_both_custom_components(
        self, mock_intent_classifier, mock_complexity_analyzer
    ):
        """Should accept both custom components."""
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier,
            complexity_analyzer=mock_complexity_analyzer,
        )

        assert service.intent_classifier is mock_intent_classifier
        assert service.complexity_analyzer is mock_complexity_analyzer


# ============================================================================
# ANALYZE_QUERY TESTS
# ============================================================================

class TestAnalyzeQuery:
    """Tests for analyze_query method."""

    @pytest.mark.asyncio
    async def test_returns_query_analysis(
        self, mock_intent_classifier, mock_complexity_analyzer, basic_context
    ):
        """Should return complete QueryAnalysis."""
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier,
            complexity_analyzer=mock_complexity_analyzer,
        )

        result = await service.analyze_query("¿Qué contiene el documento?", basic_context)

        assert isinstance(result, QueryAnalysis)
        assert result.original_query == "¿Qué contiene el documento?"
        assert result.intent == QueryIntent.OVERVIEW
        assert result.complexity == QueryComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_calculates_overall_confidence(
        self, mock_intent_classifier, mock_complexity_analyzer, basic_context
    ):
        """Should calculate weighted confidence (70% intent, 30% complexity)."""
        # Intent confidence: 0.85, Complexity confidence: 0.90
        # Expected: 0.85 * 0.7 + 0.90 * 0.3 = 0.595 + 0.27 = 0.865
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier,
            complexity_analyzer=mock_complexity_analyzer,
        )

        result = await service.analyze_query("Test query", basic_context)

        expected_confidence = (0.85 * 0.7) + (0.90 * 0.3)
        assert result.confidence == pytest.approx(expected_confidence, rel=0.01)

    @pytest.mark.asyncio
    async def test_builds_full_reasoning(
        self, mock_intent_classifier, mock_complexity_analyzer, basic_context
    ):
        """Should combine intent and complexity reasoning."""
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier,
            complexity_analyzer=mock_complexity_analyzer,
        )

        result = await service.analyze_query("Test query", basic_context)

        assert "Intent:" in result.reasoning
        assert "Complexity:" in result.reasoning
        assert "Question asks for general information" in result.reasoning
        assert "Single entity question" in result.reasoning

    @pytest.mark.asyncio
    async def test_includes_metadata(
        self, mock_intent_classifier, mock_complexity_analyzer, basic_context
    ):
        """Should include component confidences in metadata."""
        service = QueryUnderstandingService(
            intent_classifier=mock_intent_classifier,
            complexity_analyzer=mock_complexity_analyzer,
        )

        result = await service.analyze_query("Test query", basic_context)

        assert "intent_confidence" in result.metadata
        assert "complexity_confidence" in result.metadata
        assert result.metadata["intent_confidence"] == 0.85
        assert result.metadata["complexity_confidence"] == 0.90

    @pytest.mark.asyncio
    async def test_extracts_entities_from_query(self, basic_context):
        """Should extract capitalized words as entities."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cuál es el precio de Producto ABC en México?",
            basic_context
        )

        # Should extract "Producto", "ABC", "México" (capitalized words)
        assert "Producto" in result.entities or "ABC" in result.entities

    @pytest.mark.asyncio
    async def test_handles_empty_query(self, basic_context):
        """Should handle empty query gracefully."""
        service = QueryUnderstandingService()

        result = await service.analyze_query("", basic_context)

        assert isinstance(result, QueryAnalysis)
        assert result.original_query == ""


# ============================================================================
# QUERY EXPANSION TESTS
# ============================================================================

class TestQueryExpansion:
    """Tests for _expand_query method."""

    @pytest.mark.asyncio
    async def test_expands_vague_overview_query(self, basic_context):
        """Should expand vague overview questions with context."""
        service = QueryUnderstandingService()

        # Mock classifiers to return vague + overview
        with patch.object(service.intent_classifier, 'classify',
                         return_value=(QueryIntent.OVERVIEW, 0.9, "overview")), \
             patch.object(service.complexity_analyzer, 'analyze',
                         return_value=(QueryComplexity.VAGUE, 0.9, "vague")):

            result = await service.analyze_query("¿Qué es esto?", basic_context)

            # Should expand to include summary request
            assert result.expanded_query != "¿Qué es esto?"
            assert "resumen" in result.expanded_query.lower()

    @pytest.mark.asyncio
    async def test_replaces_pronouns_with_entities(self, context_with_entities):
        """Should replace pronouns with recent entities."""
        service = QueryUnderstandingService()

        # Mock classifiers - specific fact but vague
        with patch.object(service.intent_classifier, 'classify',
                         return_value=(QueryIntent.SPECIFIC_FACT, 0.9, "fact")), \
             patch.object(service.complexity_analyzer, 'analyze',
                         return_value=(QueryComplexity.VAGUE, 0.9, "vague")):

            result = await service.analyze_query(
                "¿Cuál es el precio de esto?",
                context_with_entities
            )

            # Should replace "esto" with first recent entity
            assert "Producto ABC" in result.expanded_query

    @pytest.mark.asyncio
    async def test_no_expansion_for_specific_queries(self, basic_context):
        """Should not expand well-formed specific queries."""
        service = QueryUnderstandingService()

        # Mock classifiers - specific fact, simple complexity
        with patch.object(service.intent_classifier, 'classify',
                         return_value=(QueryIntent.SPECIFIC_FACT, 0.9, "fact")), \
             patch.object(service.complexity_analyzer, 'analyze',
                         return_value=(QueryComplexity.SIMPLE, 0.9, "simple")):

            result = await service.analyze_query(
                "¿Cuál es el precio del Producto ABC?",
                basic_context
            )

            # Should keep original query
            assert result.expanded_query == "¿Cuál es el precio del Producto ABC?"

    @pytest.mark.asyncio
    async def test_expansion_handles_multiple_pronouns(self, context_with_entities):
        """Should handle multiple pronouns in query."""
        service = QueryUnderstandingService()

        with patch.object(service.intent_classifier, 'classify',
                         return_value=(QueryIntent.COMPARISON, 0.9, "comparison")), \
             patch.object(service.complexity_analyzer, 'analyze',
                         return_value=(QueryComplexity.VAGUE, 0.9, "vague")):

            # Test direct expansion
            expanded = await service._expand_query(
                "¿Cómo funciona esto y eso?",
                QueryIntent.COMPARISON,
                QueryComplexity.VAGUE,
                context_with_entities
            )

            # Both pronouns should be replaced
            assert "Producto ABC" in expanded


# ============================================================================
# ENTITY EXTRACTION TESTS
# ============================================================================

class TestEntityExtraction:
    """Tests for _extract_entities method."""

    def test_extracts_capitalized_words(self):
        """Should extract capitalized words as entities."""
        service = QueryUnderstandingService()

        entities = service._extract_entities(
            "¿Qué opinas de Microsoft y Google?"
        )

        assert "Microsoft" in entities
        assert "Google" in entities

    def test_skips_first_word(self):
        """Should skip first word (may be capitalized as sentence start)."""
        service = QueryUnderstandingService()

        entities = service._extract_entities(
            "Hola qué tal mundo"  # "Hola" should be skipped
        )

        assert "Hola" not in entities

    def test_removes_punctuation(self):
        """Should remove punctuation from extracted entities."""
        service = QueryUnderstandingService()

        entities = service._extract_entities(
            "¿Qué piensas de Apple, Microsoft?"
        )

        assert "Apple" in entities  # Not "Apple,"
        assert "Microsoft" in entities  # Not "Microsoft?"

    def test_returns_empty_for_no_entities(self):
        """Should return empty list when no entities found."""
        service = QueryUnderstandingService()

        entities = service._extract_entities(
            "¿qué es esto?"  # All lowercase
        )

        assert entities == []

    def test_handles_single_word_query(self):
        """Should handle single word queries."""
        service = QueryUnderstandingService()

        entities = service._extract_entities("Hola")

        # First word skipped, so empty
        assert entities == []

    def test_extracts_spanish_names(self):
        """Should extract Spanish proper names."""
        service = QueryUnderstandingService()

        entities = service._extract_entities(
            "¿Cuál es la dirección de BANCODEMO en México?"
        )

        assert "BANCODEMO" in entities
        assert "México" in entities


# ============================================================================
# SINGLETON PATTERN TESTS
# ============================================================================

class TestGetQueryUnderstandingService:
    """Tests for singleton factory function."""

    def test_returns_service_instance(self):
        """Should return QueryUnderstandingService instance."""
        # Reset singleton
        import src.services.query_understanding.query_understanding_service as module
        module._query_understanding_service = None

        service = get_query_understanding_service()

        assert isinstance(service, QueryUnderstandingService)

    def test_returns_same_instance(self):
        """Should return same instance on multiple calls."""
        import src.services.query_understanding.query_understanding_service as module
        module._query_understanding_service = None

        service1 = get_query_understanding_service()
        service2 = get_query_understanding_service()

        assert service1 is service2

    def test_creates_new_instance_when_none(self):
        """Should create new instance when singleton is None."""
        import src.services.query_understanding.query_understanding_service as module
        module._query_understanding_service = None

        service = get_query_understanding_service()

        assert service is not None
        assert module._query_understanding_service is service


# ============================================================================
# INTEGRATION-LIKE TESTS
# ============================================================================

class TestQueryUnderstandingIntegration:
    """Integration-like tests with real classifiers."""

    @pytest.mark.asyncio
    async def test_overview_query_classification(self, basic_context):
        """Should classify overview queries correctly."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Qué contiene este documento?",
            basic_context
        )

        # Should be classified as OVERVIEW
        assert result.intent == QueryIntent.OVERVIEW

    @pytest.mark.asyncio
    async def test_specific_fact_classification(self, basic_context):
        """Should classify specific fact queries."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cuál es el precio del producto X?",
            basic_context
        )

        # Should be classified as SPECIFIC_FACT or QUANTITATIVE
        assert result.intent in [QueryIntent.SPECIFIC_FACT, QueryIntent.QUANTITATIVE]

    @pytest.mark.asyncio
    async def test_comparison_query_classification(self, basic_context):
        """Should classify comparison queries."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cuál es la diferencia entre X y Y?",
            basic_context
        )

        # Should be classified as COMPARISON
        assert result.intent == QueryIntent.COMPARISON

    @pytest.mark.asyncio
    async def test_procedural_query_classification(self, basic_context):
        """Should classify procedural queries."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cómo funciona el proceso de devolución?",
            basic_context
        )

        # Should be classified as PROCEDURAL
        assert result.intent == QueryIntent.PROCEDURAL

    @pytest.mark.asyncio
    async def test_vague_query_detection(self, basic_context):
        """Should detect vague queries."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Qué es esto?",
            basic_context
        )

        # Should be classified as VAGUE complexity
        assert result.complexity == QueryComplexity.VAGUE

    @pytest.mark.asyncio
    async def test_complex_query_detection(self, basic_context):
        """Should detect complex queries."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cuál es el precio del producto X, el costo de envío y el tiempo de entrega?",
            basic_context
        )

        # Should be classified as COMPLEX
        assert result.complexity == QueryComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_full_analysis_chain(self, context_with_entities):
        """Should run complete analysis chain correctly."""
        service = QueryUnderstandingService()

        result = await service.analyze_query(
            "¿Cuánto cuesta el Producto Premium en México?",
            context_with_entities
        )

        # Verify all components are present
        assert result.original_query == "¿Cuánto cuesta el Producto Premium en México?"
        assert result.intent is not None
        assert result.complexity is not None
        assert result.confidence > 0
        assert result.reasoning != ""
        assert "intent_confidence" in result.metadata
        assert "complexity_confidence" in result.metadata

        # Should extract entities
        assert "Producto" in result.entities or "Premium" in result.entities or "México" in result.entities
