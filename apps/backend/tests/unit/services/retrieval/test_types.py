"""
Unit tests for retrieval types.

Tests Segment and RetrievalResult dataclasses.
"""

import pytest

from src.services.retrieval.types import RetrievalResult, Segment

pytestmark = [pytest.mark.unit]


class TestSegment:
    """Test Segment dataclass."""

    def test_create_minimal_segment(self):
        """Test creating segment with required fields."""
        segment = Segment(
            doc_id="doc_123",
            doc_name="document.pdf",
            chunk_id=0,
            text="This is content.",
            score=0.85,
        )

        assert segment.doc_id == "doc_123"
        assert segment.doc_name == "document.pdf"
        assert segment.chunk_id == 0
        assert segment.text == "This is content."
        assert segment.score == 0.85
        assert segment.page == 0  # Default
        assert segment.metadata == {}  # Default

    def test_create_full_segment(self):
        """Test creating segment with all fields."""
        segment = Segment(
            doc_id="doc_456",
            doc_name="report.pdf",
            chunk_id=5,
            text="Detailed content here.",
            score=0.95,
            page=10,
            metadata={"section": "introduction"},
        )

        assert segment.page == 10
        assert segment.metadata == {"section": "introduction"}

    def test_to_dict_basic(self):
        """Test to_dict returns correct structure."""
        segment = Segment(
            doc_id="doc_123",
            doc_name="file.pdf",
            chunk_id=2,
            text="Text",
            score=0.75,
        )

        result = segment.to_dict()

        assert result["doc_id"] == "doc_123"
        assert result["doc_name"] == "file.pdf"
        assert result["index"] == 2  # Legacy field name
        assert result["text"] == "Text"
        assert result["score"] == 0.75
        assert result["page"] == 0

    def test_to_dict_includes_metadata(self):
        """Test to_dict includes metadata fields."""
        segment = Segment(
            doc_id="doc_123",
            doc_name="file.pdf",
            chunk_id=0,
            text="Text",
            score=0.9,
            metadata={"custom_key": "custom_value", "count": 42},
        )

        result = segment.to_dict()

        # Metadata should be flattened into the dict
        assert result["custom_key"] == "custom_value"
        assert result["count"] == 42

    def test_metadata_default_factory(self):
        """Test metadata default doesn't share state."""
        seg1 = Segment(doc_id="1", doc_name="a", chunk_id=0, text="t", score=0.5)
        seg2 = Segment(doc_id="2", doc_name="b", chunk_id=0, text="t", score=0.5)

        seg1.metadata["key"] = "value"

        assert "key" not in seg2.metadata


class TestRetrievalResult:
    """Test RetrievalResult dataclass."""

    @pytest.fixture
    def sample_segments(self):
        """Create sample segments for testing."""
        return [
            Segment(doc_id="1", doc_name="a.pdf", chunk_id=0, text="t1", score=0.9),
            Segment(doc_id="2", doc_name="b.pdf", chunk_id=0, text="t2", score=0.7),
            Segment(doc_id="3", doc_name="c.pdf", chunk_id=0, text="t3", score=0.5),
        ]

    def test_create_minimal_result(self, sample_segments):
        """Test creating result with required fields."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="semantic_search",
        )

        assert len(result.segments) == 3
        assert result.strategy_used == "semantic_search"
        assert result.query_analysis is None
        assert result.confidence == 0.0
        assert result.metadata == {}

    def test_create_full_result(self, sample_segments):
        """Test creating result with all fields."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="hybrid",
            query_analysis={"intent": "fact"},
            confidence=0.85,
            metadata={"source": "weaviate"},
        )

        assert result.query_analysis == {"intent": "fact"}
        assert result.confidence == 0.85
        assert result.metadata == {"source": "weaviate"}

    def test_max_score_property(self, sample_segments):
        """Test max_score returns highest score."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="test",
        )

        assert result.max_score == 0.9

    def test_max_score_empty_segments(self):
        """Test max_score returns 0 for empty segments."""
        result = RetrievalResult(segments=[], strategy_used="test")

        assert result.max_score == 0.0

    def test_avg_score_property(self, sample_segments):
        """Test avg_score returns average."""
        result = RetrievalResult(
            segments=sample_segments,
            strategy_used="test",
        )

        expected = (0.9 + 0.7 + 0.5) / 3
        assert abs(result.avg_score - expected) < 0.001

    def test_avg_score_empty_segments(self):
        """Test avg_score returns 0 for empty segments."""
        result = RetrievalResult(segments=[], strategy_used="test")

        assert result.avg_score == 0.0

    def test_avg_score_single_segment(self):
        """Test avg_score with single segment."""
        segment = Segment(
            doc_id="1", doc_name="a.pdf", chunk_id=0, text="t", score=0.8
        )
        result = RetrievalResult(segments=[segment], strategy_used="test")

        assert result.avg_score == 0.8

    def test_metadata_default_factory(self):
        """Test metadata default doesn't share state."""
        r1 = RetrievalResult(segments=[], strategy_used="a")
        r2 = RetrievalResult(segments=[], strategy_used="b")

        r1.metadata["key"] = "value"

        assert "key" not in r2.metadata
