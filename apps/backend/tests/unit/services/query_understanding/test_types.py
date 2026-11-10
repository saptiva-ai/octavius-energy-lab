"""
Unit tests for Query Understanding types.

Tests dataclasses and enums used in query understanding module.
"""

import pytest

from src.services.query_understanding.types import (
    QueryAnalysis,
    QueryComplexity,
    QueryContext,
    QueryIntent,
)

pytestmark = [pytest.mark.unit]


class TestQueryIntent:
    """Test QueryIntent enum."""

    def test_overview_intent(self):
        """Test overview intent value."""
        assert QueryIntent.OVERVIEW.value == "overview"

    def test_specific_fact_intent(self):
        """Test specific_fact intent value."""
        assert QueryIntent.SPECIFIC_FACT.value == "specific_fact"

    def test_comparison_intent(self):
        """Test comparison intent value."""
        assert QueryIntent.COMPARISON.value == "comparison"

    def test_procedural_intent(self):
        """Test procedural intent value."""
        assert QueryIntent.PROCEDURAL.value == "procedural"

    def test_analytical_intent(self):
        """Test analytical intent value."""
        assert QueryIntent.ANALYTICAL.value == "analytical"

    def test_definitional_intent(self):
        """Test definitional intent value."""
        assert QueryIntent.DEFINITIONAL.value == "definitional"

    def test_quantitative_intent(self):
        """Test quantitative intent value."""
        assert QueryIntent.QUANTITATIVE.value == "quantitative"

    def test_all_intents_unique(self):
        """Test all intent values are unique."""
        values = [i.value for i in QueryIntent]
        assert len(values) == len(set(values))


class TestQueryComplexity:
    """Test QueryComplexity enum."""

    def test_vague_complexity(self):
        """Test vague complexity value."""
        assert QueryComplexity.VAGUE.value == "vague"

    def test_simple_complexity(self):
        """Test simple complexity value."""
        assert QueryComplexity.SIMPLE.value == "simple"

    def test_complex_complexity(self):
        """Test complex complexity value."""
        assert QueryComplexity.COMPLEX.value == "complex"

    def test_all_complexities_unique(self):
        """Test all complexity values are unique."""
        values = [c.value for c in QueryComplexity]
        assert len(values) == len(set(values))


class TestQueryContext:
    """Test QueryContext dataclass."""

    def test_create_minimal_context(self):
        """Test creating context with minimal fields."""
        context = QueryContext(conversation_id="conv_123")

        assert context.conversation_id == "conv_123"
        assert context.has_recent_entities is False
        assert context.recent_entities == []
        assert context.documents_count == 0
        assert context.previous_query is None
        assert context.metadata == {}

    def test_create_full_context(self):
        """Test creating context with all fields."""
        context = QueryContext(
            conversation_id="conv_456",
            has_recent_entities=True,
            recent_entities=["Tienda Centro", "Tienda Norte"],
            documents_count=5,
            previous_query="¿Qué es disponibilidad?",
            metadata={"extra": "data"},
        )

        assert context.conversation_id == "conv_456"
        assert context.has_recent_entities is True
        assert context.recent_entities == ["Tienda Centro", "Tienda Norte"]
        assert context.documents_count == 5
        assert context.previous_query == "¿Qué es disponibilidad?"
        assert context.metadata == {"extra": "data"}

    def test_recent_entities_is_mutable_default(self):
        """Test that recent_entities default doesn't share state."""
        context1 = QueryContext(conversation_id="conv_1")
        context2 = QueryContext(conversation_id="conv_2")

        context1.recent_entities.append("entity")

        assert "entity" in context1.recent_entities
        assert "entity" not in context2.recent_entities


class TestQueryAnalysis:
    """Test QueryAnalysis dataclass."""

    def test_create_minimal_analysis(self):
        """Test creating analysis with required fields."""
        analysis = QueryAnalysis(
            original_query="¿Qué es esto?",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            expanded_query="¿Qué es este documento?",
        )

        assert analysis.original_query == "¿Qué es esto?"
        assert analysis.intent == QueryIntent.OVERVIEW
        assert analysis.complexity == QueryComplexity.VAGUE
        assert analysis.expanded_query == "¿Qué es este documento?"
        assert analysis.entities == []
        assert analysis.confidence == 0.0
        assert analysis.reasoning == ""

    def test_create_full_analysis(self):
        """Test creating analysis with all fields."""
        analysis = QueryAnalysis(
            original_query="¿Cuál es el disponibilidad de Tienda Centro?",
            intent=QueryIntent.SPECIFIC_FACT,
            complexity=QueryComplexity.SIMPLE,
            expanded_query="¿Cuál es el disponibilidad de Tienda Centro?",
            entities=["disponibilidad", "Tienda Centro"],
            confidence=0.95,
            reasoning="Contains specific metric and store name",
            metadata={"source": "pattern_match"},
        )

        assert analysis.original_query == "¿Cuál es el disponibilidad de Tienda Centro?"
        assert analysis.intent == QueryIntent.SPECIFIC_FACT
        assert analysis.complexity == QueryComplexity.SIMPLE
        assert analysis.entities == ["disponibilidad", "Tienda Centro"]
        assert analysis.confidence == 0.95
        assert analysis.reasoning == "Contains specific metric and store name"
        assert analysis.metadata == {"source": "pattern_match"}

    def test_analysis_repr(self):
        """Test string representation of analysis."""
        analysis = QueryAnalysis(
            original_query="test",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.SIMPLE,
            expanded_query="test",
            entities=["entity1"],
            confidence=0.85,
        )

        repr_str = repr(analysis)

        assert "intent=overview" in repr_str
        assert "complexity=simple" in repr_str
        assert "confidence=0.85" in repr_str
        assert "entity1" in repr_str

    def test_entities_is_mutable_default(self):
        """Test that entities default doesn't share state."""
        analysis1 = QueryAnalysis(
            original_query="q1",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            expanded_query="q1",
        )
        analysis2 = QueryAnalysis(
            original_query="q2",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            expanded_query="q2",
        )

        analysis1.entities.append("entity")

        assert "entity" in analysis1.entities
        assert "entity" not in analysis2.entities

    def test_confidence_bounds(self):
        """Test confidence can be set to boundary values."""
        # Low confidence
        low = QueryAnalysis(
            original_query="q",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            expanded_query="q",
            confidence=0.0,
        )
        assert low.confidence == 0.0

        # High confidence
        high = QueryAnalysis(
            original_query="q",
            intent=QueryIntent.SPECIFIC_FACT,
            complexity=QueryComplexity.SIMPLE,
            expanded_query="q",
            confidence=1.0,
        )
        assert high.confidence == 1.0
