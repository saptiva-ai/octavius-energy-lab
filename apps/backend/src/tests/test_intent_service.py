"""
Tests for intent classification service.

NOTE: These tests are skipped in CI because they depend on ML models
that may not be available or properly configured in the CI environment.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ..schemas.intent import IntentLabel
from ..services.intent_service import IntentClassifier, IntentPrediction

pytestmark = pytest.mark.skip(
    reason="Intent classifier tests require ML models not available in CI"
)


@pytest.fixture
def intent_classifier():
    """Create an IntentClassifier instance for testing."""
    return IntentClassifier()


class TestIntentClassifier:
    """Test cases for IntentClassifier."""

    @pytest.mark.asyncio
    async def test_classify_greeting(self, intent_classifier):
        """Test classification of greeting messages."""
        test_cases = [
            "hola",
            "buenos días",
            "hello",
            "hi there",
            "¿cómo estás?",
        ]

        for text in test_cases:
            result = await intent_classifier.classify(text)
            assert isinstance(result, IntentPrediction)
            assert result.intent == IntentLabel.GREETING
            assert result.confidence >= 0.8
            assert result.model == "heuristic"
            assert len(result.reasons) > 0

    @pytest.mark.asyncio
    async def test_classify_researchable(self, intent_classifier):
        """Test classification of researchable queries."""
        test_cases = [
            "¿Cuál es el impacto de la IA en LATAM 2024?",
            "Analiza las tendencias de fintech en México",
            "¿Qué dice la investigación sobre energías renovables?",
            "Impacto económico del blockchain 2023-2024",
        ]

        for text in test_cases:
            result = await intent_classifier.classify(text)
            assert isinstance(result, IntentPrediction)
            assert result.intent == IntentLabel.RESEARCHABLE
            assert result.confidence >= 0.8
            assert result.model == "heuristic"
            assert len(result.reasons) > 0

    @pytest.mark.asyncio
    async def test_classify_chit_chat(self, intent_classifier):
        """Test classification of casual conversation."""
        test_cases = [
            "me gusta el chocolate",
            "el clima está bonito hoy",
            "no sé qué hacer",
            "tengo hambre",
        ]

        for text in test_cases:
            result = await intent_classifier.classify(text)
            assert isinstance(result, IntentPrediction)
            assert result.intent == IntentLabel.CHIT_CHAT
            assert result.confidence >= 0.7
            assert result.model == "heuristic"

    @pytest.mark.asyncio
    async def test_classify_command(self, intent_classifier):
        """Test classification of commands."""
        test_cases = [
            "resume el documento anterior",
            "traduce esto al inglés",
            "crea una lista de tareas",
            "explica la función anterior",
        ]

        for text in test_cases:
            result = await intent_classifier.classify(text)
            assert isinstance(result, IntentPrediction)
            assert result.intent == IntentLabel.COMMAND
            assert result.confidence >= 0.7
            assert result.model == "heuristic"

    @pytest.mark.asyncio
    async def test_empty_text_handling(self, intent_classifier):
        """Test handling of empty or whitespace-only text."""
        test_cases = ["", "   ", "\n\t", None]

        for text in test_cases:
            with pytest.raises(ValueError, match="Text cannot be empty"):
                await intent_classifier.classify(text)

    @pytest.mark.asyncio
    async def test_very_long_text(self, intent_classifier):
        """Test handling of very long text inputs."""
        long_text = "¿Cuál es el impacto de la IA? " * 100

        result = await intent_classifier.classify(long_text)
        assert isinstance(result, IntentPrediction)
        assert result.intent in [IntentLabel.RESEARCHABLE, IntentLabel.AMBIGUOUS]

    @pytest.mark.asyncio
    async def test_multi_topic_detection(self, intent_classifier):
        """Test detection of multi-topic queries."""
        multi_topic_text = (
            "Hola, ¿podrías investigar el impacto de la IA en LATAM "
            "y también explicarme cómo funciona el blockchain?"
        )

        result = await intent_classifier.classify(multi_topic_text)
        assert isinstance(result, IntentPrediction)
        assert result.intent == IntentLabel.MULTI_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_fallback_classifier(self, mock_post, intent_classifier):
        """Test fallback to API classifier when needed."""
        # Mock API response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "intent": "RESEARCHABLE",
            "confidence": 0.92,
            "reasons": ["API classification"],
            "model": "api_fallback",
        }
        mock_post.return_value.__aenter__.return_value = mock_response

        # Force fallback by using ambiguous text
        ambiguous_text = "esto es algo raro que no se puede clasificar fácilmente"

        result = await intent_classifier.classify(ambiguous_text)
        assert isinstance(result, IntentPrediction)
        # Should use fallback with higher confidence
        assert result.model in ["heuristic", "api_fallback"]
