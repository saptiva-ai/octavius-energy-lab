"""
Unit tests for IntentClassifier.

Tests intent classification using rule-based patterns.
"""

import pytest

from src.services.query_understanding.intent_classifier import IntentClassifier
from src.services.query_understanding.types import QueryContext, QueryIntent

pytestmark = [pytest.mark.unit]


@pytest.fixture
def classifier():
    """Create IntentClassifier instance."""
    return IntentClassifier()


@pytest.fixture
def basic_context():
    """Create basic conversation context."""
    return QueryContext(conversation_id="conv_123")


class TestOverviewIntent:
    """Test classification of overview queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Qué es esto?",
            "¿Qué contiene este documento?",
            "¿De qué trata esto?",
            "Resume el documento",  # Without accent (matches regex)
            "Cuentame qué hay aquí",  # Without accent (matches regex)
            "¿Qué dice este documento?",
        ],
    )
    def test_overview_queries(self, classifier, basic_context, query):
        """Test queries classified as overview."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.OVERVIEW
        assert confidence >= 0.9


class TestQuantitativeIntent:
    """Test classification of quantitative queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Cuánto cuesta?",
            "¿Cuántos empleados hay?",
            "¿Cuál es el porcentaje de crecimiento?",
            "¿Cuál es el monto total?",
            "¿Cuál es la tasa de interés?",
        ],
    )
    def test_quantitative_queries(self, classifier, basic_context, query):
        """Test queries classified as quantitative."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.QUANTITATIVE
        assert confidence >= 0.8


class TestComparisonIntent:
    """Test classification of comparison queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Cuál es la diferencia entre A y B?",
            "Compara los resultados",
            "Tienda Centro versus Tienda Norte",
            "¿Cuál es mejor que el otro?",
        ],
    )
    def test_comparison_queries(self, classifier, basic_context, query):
        """Test queries classified as comparison."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.COMPARISON
        assert confidence >= 0.8


class TestDefinitionalIntent:
    """Test classification of definitional queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Qué significa disponibilidad?",
            "¿Qué es capitalización?",
            "Define faltantes",
            "¿Cuál es el significado de ROE?",
        ],
    )
    def test_definitional_queries(self, classifier, basic_context, query):
        """Test queries classified as definitional."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.DEFINITIONAL
        assert confidence >= 0.8


class TestProceduralIntent:
    """Test classification of procedural queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Cómo funciona esto?",
            "¿Cómo se calcula el disponibilidad?",
            "¿Cuáles son los pasos para aplicar?",
            "Explica el proceso de validación",
        ],
    )
    def test_procedural_queries(self, classifier, basic_context, query):
        """Test queries classified as procedural."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.PROCEDURAL
        assert confidence >= 0.8


class TestAnalyticalIntent:
    """Test classification of analytical queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Por qué aumentó la faltantes?",
            "¿Cuál es la razón del incremento?",
            "¿Cuál es la causa de la caída?",
        ],
    )
    def test_analytical_queries(self, classifier, basic_context, query):
        """Test queries classified as analytical."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.ANALYTICAL
        assert confidence >= 0.8


class TestSpecificFactIntent:
    """Test classification of specific fact queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "¿Cuál es el nombre del producto?",  # Specific fact (not "precio" which triggers quantitative)
            "¿Dónde está ubicado?",
            "¿Cuándo fue publicado?",
            "¿Quién es el responsable?",
        ],
    )
    def test_specific_fact_queries(self, classifier, basic_context, query):
        """Test queries classified as specific fact."""
        intent, confidence, _ = classifier.classify(query, basic_context)

        assert intent == QueryIntent.SPECIFIC_FACT
        assert confidence >= 0.5


class TestDefaultClassification:
    """Test default classification when no patterns match."""

    def test_ambiguous_query_defaults_to_specific_fact(self, classifier, basic_context):
        """Test ambiguous queries default to specific fact."""
        query = "información general"  # Doesn't match specific patterns
        intent, confidence, reasoning = classifier.classify(query, basic_context)

        assert intent == QueryIntent.SPECIFIC_FACT
        assert confidence == 0.5
        assert "default" in reasoning.lower()


class TestClassifierInitialization:
    """Test classifier initialization."""

    def test_patterns_initialized(self, classifier):
        """Test all pattern lists are initialized."""
        assert len(classifier.overview_patterns) > 0
        assert len(classifier.specific_fact_patterns) > 0
        assert len(classifier.procedural_patterns) > 0
        assert len(classifier.analytical_patterns) > 0
        assert len(classifier.definitional_patterns) > 0
        assert len(classifier.quantitative_patterns) > 0
        assert len(classifier.comparison_patterns) > 0


class TestConfidenceValues:
    """Test confidence values are within expected ranges."""

    def test_high_confidence_for_clear_patterns(self, classifier, basic_context):
        """Test high confidence for clear patterns."""
        query = "¿Qué es esto?"
        _, confidence, _ = classifier.classify(query, basic_context)

        assert confidence >= 0.9

    def test_lower_confidence_for_default(self, classifier, basic_context):
        """Test lower confidence for default classification."""
        query = "xyz abc"  # Random text
        _, confidence, _ = classifier.classify(query, basic_context)

        assert confidence == 0.5


class TestReasoningOutput:
    """Test reasoning output in classification."""

    def test_reasoning_includes_pattern_type(self, classifier, basic_context):
        """Test reasoning mentions the matched pattern type."""
        query = "¿Qué es esto?"
        _, _, reasoning = classifier.classify(query, basic_context)

        assert "overview" in reasoning.lower() or "pattern" in reasoning.lower()

    def test_reasoning_for_default(self, classifier, basic_context):
        """Test reasoning for default classification."""
        query = "random text"
        _, _, reasoning = classifier.classify(query, basic_context)

        assert "default" in reasoning.lower() or "no pattern" in reasoning.lower()
