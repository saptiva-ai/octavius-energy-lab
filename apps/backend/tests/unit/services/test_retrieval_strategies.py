"""
Unit tests for Retrieval Strategies module.

Tests:
- Segment and RetrievalResult types
- RetrievalStrategy interface compliance
- SemanticSearchStrategy threshold calculation
- OverviewRetrievalStrategy chunk retrieval
- AdaptiveRetrievalOrchestrator strategy selection and fallbacks
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from dataclasses import FrozenInstanceError

from src.services.retrieval.types import Segment, RetrievalResult
from src.services.retrieval.retrieval_strategy import RetrievalStrategy
from src.services.retrieval.semantic_search_strategy import SemanticSearchStrategy
from src.services.retrieval.overview_strategy import OverviewRetrievalStrategy
from src.services.retrieval.adaptive_orchestrator import AdaptiveRetrievalOrchestrator
from src.services.query_understanding.types import (
    QueryIntent,
    QueryComplexity,
    QueryContext,
    QueryAnalysis,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_segment():
    """Create a sample segment for testing."""
    return Segment(
        doc_id="doc-123",
        doc_name="test_document.pdf",
        chunk_id=0,
        text="This is sample text content.",
        score=0.85,
        page=1,
        metadata={"source": "pdf"},
    )


@pytest.fixture
def sample_segments():
    """Create a list of sample segments."""
    return [
        Segment(
            doc_id="doc-1",
            doc_name="doc1.pdf",
            chunk_id=0,
            text="First segment text",
            score=0.9,
            page=1,
        ),
        Segment(
            doc_id="doc-1",
            doc_name="doc1.pdf",
            chunk_id=1,
            text="Second segment text",
            score=0.8,
            page=1,
        ),
        Segment(
            doc_id="doc-2",
            doc_name="doc2.pdf",
            chunk_id=0,
            text="Third segment text",
            score=0.7,
            page=2,
        ),
    ]


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = Mock()
    doc.id = "doc-123"
    doc.filename = "test.pdf"
    return doc


@pytest.fixture
def mock_documents():
    """Create a list of mock documents."""
    docs = []
    for i in range(3):
        doc = Mock()
        doc.id = f"doc-{i}"
        doc.filename = f"doc{i}.pdf"
        docs.append(doc)
    return docs


@pytest.fixture
def basic_query_context():
    """Create basic query context."""
    return QueryContext(
        conversation_id="session-123",
        documents_count=2,
        has_recent_entities=False,
        recent_entities=[],
    )


@pytest.fixture
def mock_query_analysis():
    """Create a mock query analysis."""
    return QueryAnalysis(
        original_query="What is the price?",
        expanded_query="What is the price of the product?",
        intent=QueryIntent.SPECIFIC_FACT,
        complexity=QueryComplexity.SIMPLE,
        confidence=0.9,
        reasoning="Specific fact query",
        entities=["product"],
        metadata={"intent_confidence": 0.9, "complexity_confidence": 0.9},
    )


# ============================================================================
# SEGMENT TESTS
# ============================================================================

class TestSegment:
    """Tests for Segment dataclass."""

    def test_segment_creation(self, sample_segment):
        """Should create segment with all fields."""
        assert sample_segment.doc_id == "doc-123"
        assert sample_segment.doc_name == "test_document.pdf"
        assert sample_segment.chunk_id == 0
        assert sample_segment.text == "This is sample text content."
        assert sample_segment.score == 0.85
        assert sample_segment.page == 1
        assert sample_segment.metadata == {"source": "pdf"}

    def test_segment_default_values(self):
        """Should use default values for optional fields."""
        segment = Segment(
            doc_id="doc-1",
            doc_name="file.pdf",
            chunk_id=0,
            text="Text",
            score=0.5,
        )

        assert segment.page == 0
        assert segment.metadata == {}

    def test_segment_to_dict(self, sample_segment):
        """Should convert to dictionary correctly."""
        result = sample_segment.to_dict()

        assert result["doc_id"] == "doc-123"
        assert result["doc_name"] == "test_document.pdf"
        assert result["index"] == 0  # Legacy field name
        assert result["text"] == "This is sample text content."
        assert result["score"] == 0.85
        assert result["page"] == 1
        assert result["source"] == "pdf"  # From metadata

    def test_segment_to_dict_with_empty_metadata(self):
        """Should handle empty metadata in to_dict."""
        segment = Segment(
            doc_id="doc-1",
            doc_name="file.pdf",
            chunk_id=5,
            text="Sample",
            score=0.6,
        )

        result = segment.to_dict()

        assert "doc_id" in result
        assert "index" in result
        assert result["index"] == 5


# ============================================================================
# RETRIEVAL RESULT TESTS
# ============================================================================

class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_retrieval_result_creation(self, sample_segments, mock_query_analysis):
        """Should create result with all fields."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="SemanticSearchStrategy",
            query_analysis=mock_query_analysis,
            confidence=0.85,
            metadata={"threshold": 0.3},
        )

        assert len(result.segments) == 3
        assert result.strategy_used == "SemanticSearchStrategy"
        assert result.confidence == 0.85
        assert result.metadata["threshold"] == 0.3

    def test_retrieval_result_max_score(self, sample_segments):
        """Should calculate max score correctly."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="test",
        )

        assert result.max_score == 0.9

    def test_retrieval_result_max_score_empty(self):
        """Should return 0 for empty segments."""
        result = RetrievalResult(
            segments=[],
            strategy_used="test",
        )

        assert result.max_score == 0.0

    def test_retrieval_result_avg_score(self, sample_segments):
        """Should calculate average score correctly."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="test",
        )

        expected_avg = (0.9 + 0.8 + 0.7) / 3
        assert result.avg_score == pytest.approx(expected_avg, rel=0.01)

    def test_retrieval_result_avg_score_empty(self):
        """Should return 0 for empty segments."""
        result = RetrievalResult(
            segments=[],
            strategy_used="test",
        )

        assert result.avg_score == 0.0

    def test_retrieval_result_default_values(self, sample_segments):
        """Should use default values."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="test",
        )

        assert result.query_analysis is None
        assert result.confidence == 0.0
        assert result.metadata == {}


# ============================================================================
# SEMANTIC SEARCH STRATEGY TESTS
# ============================================================================

class TestSemanticSearchStrategy:
    """Tests for SemanticSearchStrategy."""

    def test_init_default_threshold(self):
        """Should initialize with default threshold."""
        strategy = SemanticSearchStrategy()
        assert strategy.base_threshold == 0.3

    def test_init_custom_threshold(self):
        """Should accept custom threshold."""
        strategy = SemanticSearchStrategy(base_threshold=0.5)
        assert strategy.base_threshold == 0.5

    def test_implements_retrieval_strategy(self):
        """Should implement RetrievalStrategy interface."""
        strategy = SemanticSearchStrategy()
        assert isinstance(strategy, RetrievalStrategy)
        assert hasattr(strategy, 'retrieve')
        assert callable(strategy.retrieve)

    def test_calculate_adaptive_threshold_override(self, mock_documents):
        """Should use override when provided."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        result = strategy._calculate_adaptive_threshold(
            "test query",
            mock_documents,
            override=0.5,
        )

        assert result == 0.5

    def test_calculate_adaptive_threshold_clamps_override(self, mock_documents):
        """Should clamp override to valid range."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # Test upper bound
        result = strategy._calculate_adaptive_threshold(
            "test", mock_documents, override=1.5
        )
        assert result == 1.0

        # Test lower bound
        result = strategy._calculate_adaptive_threshold(
            "test", mock_documents, override=-0.5
        )
        assert result == 0.0

    def test_calculate_adaptive_threshold_short_query(self, mock_documents):
        """Should lower threshold for short queries."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # Short query (4 words)
        result = strategy._calculate_adaptive_threshold(
            "What is this?",
            mock_documents[:2],  # 2 docs (no corpus adjustment)
        )

        # Base 0.3 - 0.15 (short query) = 0.15
        assert result == pytest.approx(0.15, rel=0.01)

    def test_calculate_adaptive_threshold_long_query(self, mock_documents):
        """Should raise threshold for long queries."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # Long query (>15 words)
        long_query = " ".join(["word"] * 20)
        result = strategy._calculate_adaptive_threshold(
            long_query,
            mock_documents[:2],
        )

        # Base 0.3 + 0.05 (long query) = 0.35
        assert result == pytest.approx(0.35, rel=0.01)

    def test_calculate_adaptive_threshold_large_corpus(self):
        """Should raise threshold for large corpus."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # 6 documents (> 5)
        docs = [Mock() for _ in range(6)]
        result = strategy._calculate_adaptive_threshold(
            "medium length query here today",  # 5 words (normal)
            docs,
        )

        # Base 0.3 + 0.05 (large corpus) = 0.35
        assert result == pytest.approx(0.35, rel=0.01)

    def test_calculate_adaptive_threshold_combined_factors(self):
        """Should combine multiple factors."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # Long query + large corpus
        long_query = " ".join(["word"] * 20)
        docs = [Mock() for _ in range(10)]

        result = strategy._calculate_adaptive_threshold(long_query, docs)

        # Base 0.3 + 0.05 (long) + 0.05 (large) = 0.4
        assert result == pytest.approx(0.4, rel=0.01)

    def test_calculate_adaptive_threshold_max_clamp(self):
        """Should clamp to max threshold of 0.8."""
        strategy = SemanticSearchStrategy(base_threshold=0.9)

        result = strategy._calculate_adaptive_threshold(
            " ".join(["word"] * 20),  # Long query +0.05
            [Mock() for _ in range(10)],  # Large corpus +0.05
        )

        # Would be 1.0 but clamped to 0.8
        assert result == 0.8

    @pytest.mark.asyncio
    async def test_retrieve_with_mocked_services(self, mock_documents):
        """Should perform retrieval with mocked services."""
        strategy = SemanticSearchStrategy(base_threshold=0.3)

        # Mock embedding service
        mock_embedding = Mock()
        mock_embedding.encode_single = Mock(return_value=[0.1] * 384)

        # Mock weaviate service
        mock_weaviate = Mock()
        mock_weaviate.search = Mock(return_value=[
            {
                "document_id": "doc-0",
                "chunk_id": 0,
                "text": "Result text",
                "score": 0.85,
                "page": 1,
                "metadata": {"filename": "doc0.pdf"},
            }
        ])

        with patch(
            "src.services.retrieval.semantic_search_strategy.get_embedding_service",
            return_value=mock_embedding,
        ), patch(
            "src.services.retrieval.semantic_search_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="What is the price?",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        assert len(result) == 1
        assert result[0].score == 0.85
        mock_embedding.encode_single.assert_called_once()
        mock_weaviate.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_handles_exception(self, mock_documents):
        """Should return empty list on error."""
        strategy = SemanticSearchStrategy()

        # Mock embedding service successfully
        mock_embedding = Mock()
        mock_embedding.encode_single = Mock(return_value=[0.1] * 384)

        # Mock weaviate to raise exception
        mock_weaviate = Mock()
        mock_weaviate.search = Mock(side_effect=Exception("Search error"))

        with patch(
            "src.services.retrieval.semantic_search_strategy.get_embedding_service",
            return_value=mock_embedding,
        ), patch(
            "src.services.retrieval.semantic_search_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="test",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        assert result == []


# ============================================================================
# OVERVIEW RETRIEVAL STRATEGY TESTS
# ============================================================================

class TestOverviewRetrievalStrategy:
    """Tests for OverviewRetrievalStrategy."""

    def test_init_default_chunks_per_doc(self):
        """Should initialize with default chunks per doc."""
        strategy = OverviewRetrievalStrategy()
        assert strategy.chunks_per_doc == 3

    def test_init_custom_chunks_per_doc(self):
        """Should accept custom chunks per doc."""
        strategy = OverviewRetrievalStrategy(chunks_per_doc=5)
        assert strategy.chunks_per_doc == 5

    def test_implements_retrieval_strategy(self):
        """Should implement RetrievalStrategy interface."""
        strategy = OverviewRetrievalStrategy()
        assert isinstance(strategy, RetrievalStrategy)
        assert hasattr(strategy, 'retrieve')
        assert callable(strategy.retrieve)

    @pytest.mark.asyncio
    async def test_retrieve_with_mocked_weaviate(self, mock_documents):
        """Should retrieve first chunks from each document."""
        strategy = OverviewRetrievalStrategy(chunks_per_doc=2)

        # Create mock response objects
        mock_obj1 = Mock()
        mock_obj1.properties = {
            "chunk_id": 0,
            "text": "First chunk",
            "page": 1,
            "metadata_json": None,
        }
        mock_obj2 = Mock()
        mock_obj2.properties = {
            "chunk_id": 1,
            "text": "Second chunk",
            "page": 1,
            "metadata_json": None,
        }

        mock_response = Mock()
        mock_response.objects = [mock_obj1, mock_obj2]

        mock_collection = Mock()
        mock_collection.query.fetch_objects = Mock(return_value=mock_response)

        mock_client = Mock()
        mock_client.is_connected = Mock(return_value=True)
        mock_client.collections.get = Mock(return_value=mock_collection)

        mock_weaviate = Mock()
        mock_weaviate.client = mock_client
        mock_weaviate.collection_name = "test_collection"

        with patch(
            "src.services.retrieval.overview_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="What is this document about?",
                session_id="session-123",
                documents=mock_documents[:1],  # 1 document
                max_segments=10,
            )

        assert len(result) == 2
        assert result[0].text == "First chunk"
        assert result[0].score == 1.0  # Overview chunks have fixed score

    @pytest.mark.asyncio
    async def test_retrieve_respects_max_segments(self, mock_documents):
        """Should limit results to max_segments."""
        strategy = OverviewRetrievalStrategy(chunks_per_doc=3)

        # Create multiple mock chunks
        mock_objects = []
        for i in range(6):  # More than max_segments=2
            obj = Mock()
            obj.properties = {
                "chunk_id": i,
                "text": f"Chunk {i}",
                "page": 1,
                "metadata_json": None,
            }
            mock_objects.append(obj)

        mock_response = Mock()
        mock_response.objects = mock_objects[:3]  # chunks_per_doc=3

        mock_collection = Mock()
        mock_collection.query.fetch_objects = Mock(return_value=mock_response)

        mock_client = Mock()
        mock_client.is_connected = Mock(return_value=True)
        mock_client.collections.get = Mock(return_value=mock_collection)

        mock_weaviate = Mock()
        mock_weaviate.client = mock_client
        mock_weaviate.collection_name = "test_collection"

        with patch(
            "src.services.retrieval.overview_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="test",
                session_id="session-123",
                documents=mock_documents[:1],
                max_segments=2,  # Limit to 2
            )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_retrieve_handles_exception(self, mock_documents):
        """Should continue on error for a document."""
        strategy = OverviewRetrievalStrategy()

        mock_weaviate = Mock()
        mock_weaviate.client = Mock()
        mock_weaviate.client.is_connected = Mock(side_effect=Exception("Error"))

        with patch(
            "src.services.retrieval.overview_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="test",
                session_id="session-123",
                documents=mock_documents,
                max_segments=10,
            )

        # Should return empty list, not crash
        assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_parses_metadata_json(self, mock_documents):
        """Should parse metadata_json when present."""
        strategy = OverviewRetrievalStrategy(chunks_per_doc=1)

        mock_obj = Mock()
        mock_obj.properties = {
            "chunk_id": 0,
            "text": "Content",
            "page": 1,
            "metadata_json": '{"source": "pdf", "author": "Test"}',
        }

        mock_response = Mock()
        mock_response.objects = [mock_obj]

        mock_collection = Mock()
        mock_collection.query.fetch_objects = Mock(return_value=mock_response)

        mock_client = Mock()
        mock_client.is_connected = Mock(return_value=True)
        mock_client.collections.get = Mock(return_value=mock_collection)

        mock_weaviate = Mock()
        mock_weaviate.client = mock_client
        mock_weaviate.collection_name = "test_collection"

        with patch(
            "src.services.retrieval.overview_strategy.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            result = await strategy.retrieve(
                query="test",
                session_id="session-123",
                documents=mock_documents[:1],
                max_segments=10,
            )

        assert len(result) == 1
        assert result[0].metadata["source"] == "pdf"
        assert result[0].metadata["author"] == "Test"


# ============================================================================
# ADAPTIVE RETRIEVAL ORCHESTRATOR TESTS
# ============================================================================

class TestAdaptiveRetrievalOrchestrator:
    """Tests for AdaptiveRetrievalOrchestrator."""

    def test_init_with_default_service(self):
        """Should use default query understanding service."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ) as mock_get:
            mock_service = Mock()
            mock_get.return_value = mock_service

            orchestrator = AdaptiveRetrievalOrchestrator()

            assert orchestrator.query_understanding is mock_service
            mock_get.assert_called_once()

    def test_init_with_custom_service(self):
        """Should accept custom query understanding service."""
        mock_service = Mock()
        orchestrator = AdaptiveRetrievalOrchestrator(
            query_understanding_service=mock_service
        )

        assert orchestrator.query_understanding is mock_service

    def test_strategy_registry_populated(self):
        """Should have populated strategy registry."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Should have multiple strategies registered
        assert len(orchestrator.strategy_registry) > 10

        # Check some specific mappings
        assert (QueryIntent.OVERVIEW, QueryComplexity.VAGUE) in orchestrator.strategy_registry
        assert (QueryIntent.SPECIFIC_FACT, QueryComplexity.SIMPLE) in orchestrator.strategy_registry

    def test_fallback_strategy_set(self):
        """Should have fallback strategy."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        assert orchestrator.fallback_strategy is not None
        assert isinstance(orchestrator.fallback_strategy, SemanticSearchStrategy)

    def test_select_strategy_exact_match(self):
        """Should return exact match from registry."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        strategy = orchestrator._select_strategy(
            QueryIntent.OVERVIEW,
            QueryComplexity.VAGUE,
        )

        assert isinstance(strategy, OverviewRetrievalStrategy)
        assert strategy.chunks_per_doc == 3

    def test_select_strategy_intent_match_only(self):
        """Should fall back to intent-only match."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # OVERVIEW + COMPLEX is not in registry, but OVERVIEW + VAGUE is
        strategy = orchestrator._select_strategy(
            QueryIntent.OVERVIEW,
            QueryComplexity.COMPLEX,
        )

        # Should find an OVERVIEW strategy
        assert isinstance(strategy, OverviewRetrievalStrategy)

    def test_select_strategy_fallback(self):
        """Should use fallback when no match."""
        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Clear registry to force fallback
        orchestrator.strategy_registry = {}

        strategy = orchestrator._select_strategy(
            QueryIntent.SPECIFIC_FACT,
            QueryComplexity.SIMPLE,
        )

        assert strategy is orchestrator.fallback_strategy

    @pytest.mark.asyncio
    async def test_retrieve_full_flow(self, mock_documents, mock_query_analysis):
        """Should execute full retrieval flow."""
        mock_query_service = Mock()
        mock_query_service.analyze_query = AsyncMock(return_value=mock_query_analysis)

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Mock strategy retrieve
        mock_segments = [
            Segment(
                doc_id="doc-0",
                doc_name="doc0.pdf",
                chunk_id=0,
                text="Result",
                score=0.8,
            )
        ]

        with patch.object(
            SemanticSearchStrategy, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.return_value = mock_segments

            result = await orchestrator.retrieve(
                query="What is the price?",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        assert isinstance(result, RetrievalResult)
        assert len(result.segments) == 1
        assert result.strategy_used == "SemanticSearchStrategy"
        mock_query_service.analyze_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_creates_default_context(
        self, mock_documents, mock_query_analysis
    ):
        """Should create default context when not provided."""
        mock_query_service = Mock()
        mock_query_service.analyze_query = AsyncMock(return_value=mock_query_analysis)

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        with patch.object(
            SemanticSearchStrategy, "retrieve", new_callable=AsyncMock, return_value=[]
        ):
            await orchestrator.retrieve(
                query="test",
                session_id="session-456",
                documents=mock_documents,
                max_segments=5,
                context=None,  # No context provided
            )

        # Verify analyze_query was called with a QueryContext
        call_args = mock_query_service.analyze_query.call_args
        context_arg = call_args[0][1]
        assert isinstance(context_arg, QueryContext)
        assert context_arg.conversation_id == "session-456"
        assert context_arg.documents_count == 3

    @pytest.mark.asyncio
    async def test_retrieve_handles_strategy_exception(
        self, mock_documents, mock_query_analysis
    ):
        """Should return empty segments on strategy error."""
        mock_query_service = Mock()
        mock_query_service.analyze_query = AsyncMock(return_value=mock_query_analysis)

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # The orchestrator catches exceptions and returns empty segments
        # Then post_process may apply fallback - we just verify it doesn't crash
        call_count = 0

        async def mock_retrieve(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Strategy error")
            # Fallback returns empty
            return []

        with patch.object(
            SemanticSearchStrategy,
            "retrieve",
            new_callable=AsyncMock,
            side_effect=mock_retrieve,
        ):
            result = await orchestrator.retrieve(
                query="test",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        # Should return result (possibly with empty segments due to error handling)
        assert isinstance(result, RetrievalResult)


# ============================================================================
# POST-PROCESSING FALLBACK TESTS
# ============================================================================

class TestPostProcessingFallbacks:
    """Tests for _post_process fallback logic."""

    @pytest.mark.asyncio
    async def test_overview_fallback_on_empty_results(self, mock_documents):
        """Should apply overview fallback when overview query returns empty."""
        mock_query_service = Mock()

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Create overview analysis
        overview_analysis = QueryAnalysis(
            original_query="What is this?",
            expanded_query="What is this document about?",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            confidence=0.8,
            reasoning="Overview query",
            entities=[],
            metadata={},
        )

        # Mock fallback strategy
        fallback_segments = [
            Segment(
                doc_id="doc-0",
                doc_name="doc0.pdf",
                chunk_id=0,
                text="Fallback",
                score=1.0,
            )
        ]

        with patch.object(
            OverviewRetrievalStrategy,
            "retrieve",
            new_callable=AsyncMock,
            return_value=fallback_segments,
        ):
            result = await orchestrator._post_process(
                segments=[],  # Empty results
                analysis=overview_analysis,
                query="What is this?",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        assert len(result) == 1
        assert result[0].text == "Fallback"

    @pytest.mark.asyncio
    async def test_low_threshold_fallback_on_empty_specific_results(
        self, mock_documents
    ):
        """Should apply low threshold fallback for specific queries."""
        mock_query_service = Mock()

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Create specific fact analysis
        specific_analysis = QueryAnalysis(
            original_query="What is the price?",
            expanded_query="What is the price?",
            intent=QueryIntent.SPECIFIC_FACT,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
            reasoning="Specific fact",
            entities=[],
            metadata={},
        )

        # Mock semantic search fallback
        fallback_segments = [
            Segment(
                doc_id="doc-0",
                doc_name="doc0.pdf",
                chunk_id=0,
                text="Low threshold result",
                score=0.1,
            )
        ]

        with patch.object(
            SemanticSearchStrategy,
            "retrieve",
            new_callable=AsyncMock,
            return_value=fallback_segments,
        ):
            result = await orchestrator._post_process(
                segments=[],  # Empty results
                analysis=specific_analysis,
                query="What is the price?",
                session_id="session-123",
                documents=mock_documents,
                max_segments=5,
            )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_no_fallback_when_results_exist(self, mock_documents):
        """Should not apply fallback when results exist."""
        mock_query_service = Mock()

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service",
            return_value=mock_query_service,
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        existing_segments = [
            Segment(
                doc_id="doc-0",
                doc_name="doc0.pdf",
                chunk_id=0,
                text="Existing result",
                score=0.8,
            )
        ]

        overview_analysis = QueryAnalysis(
            original_query="test",
            expanded_query="test",
            intent=QueryIntent.OVERVIEW,
            complexity=QueryComplexity.VAGUE,
            confidence=0.8,
            reasoning="Test",
            entities=[],
            metadata={},
        )

        result = await orchestrator._post_process(
            segments=existing_segments,  # Has results
            analysis=overview_analysis,
            query="test",
            session_id="session-123",
            documents=mock_documents,
            max_segments=5,
        )

        # Should return original segments unchanged
        assert result == existing_segments


# ============================================================================
# STRATEGY PATTERN COMPLIANCE TESTS
# ============================================================================

class TestStrategyPatternCompliance:
    """Tests to verify Strategy Pattern implementation."""

    def test_all_strategies_have_retrieve_method(self):
        """All strategies must implement retrieve method."""
        strategies = [
            SemanticSearchStrategy(),
            OverviewRetrievalStrategy(),
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'retrieve')
            assert callable(strategy.retrieve)

    def test_strategies_inherit_from_base(self):
        """All strategies should inherit from RetrievalStrategy."""
        assert issubclass(SemanticSearchStrategy, RetrievalStrategy)
        assert issubclass(OverviewRetrievalStrategy, RetrievalStrategy)

    def test_strategies_have_log_retrieval_method(self):
        """All strategies should have _log_retrieval from base."""
        strategies = [
            SemanticSearchStrategy(),
            OverviewRetrievalStrategy(),
        ]

        for strategy in strategies:
            assert hasattr(strategy, '_log_retrieval')
            assert callable(strategy._log_retrieval)

    def test_orchestrator_can_use_any_strategy(self):
        """Orchestrator should work with any RetrievalStrategy."""

        class CustomStrategy(RetrievalStrategy):
            async def retrieve(self, query, session_id, documents, max_segments, **kwargs):
                return [Segment(
                    doc_id="custom",
                    doc_name="custom.pdf",
                    chunk_id=0,
                    text="Custom",
                    score=1.0,
                )]

        with patch(
            "src.services.retrieval.adaptive_orchestrator.get_query_understanding_service"
        ):
            orchestrator = AdaptiveRetrievalOrchestrator()

        # Replace a registry entry with custom strategy
        orchestrator.strategy_registry[(QueryIntent.OVERVIEW, QueryComplexity.VAGUE)] = CustomStrategy()

        strategy = orchestrator._select_strategy(QueryIntent.OVERVIEW, QueryComplexity.VAGUE)
        assert isinstance(strategy, CustomStrategy)
