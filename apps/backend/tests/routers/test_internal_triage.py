"""
Unit tests for internal triage API endpoints.

Tests the 3 new endpoints added for triage automation:
- POST /api/internal/feedback/query
- POST /api/internal/feedback/conversations
- GET /api/internal/feedback/stale-charts

Uses mocked MongoDB collections (no real DB required).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set INTERNAL_API_KEY before importing app
os.environ.setdefault("INTERNAL_API_KEY", "test-key-123")


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


class MockCursor:
    """Mock Motor cursor with async iteration and chaining."""

    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self._docs = docs
        self._limit_val = None

    def sort(self, *args: Any, **kwargs: Any) -> "MockCursor":
        return self

    def limit(self, n: int) -> "MockCursor":
        self._limit_val = n
        return self

    async def to_list(self, length: Any = None) -> List[Dict[str, Any]]:
        limit = self._limit_val or length or len(self._docs)
        return self._docs[:limit]

    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        for doc in self._docs:
            yield doc


class MockCollection:
    """Mock MongoDB collection with find/aggregate support."""

    def __init__(self, docs: List[Dict[str, Any]] | None = None) -> None:
        self._docs = docs or []

    def find(self, filter_dict: Dict[str, Any] | None = None) -> MockCursor:
        if not filter_dict:
            return MockCursor(self._docs)

        # Simple filter matching
        result = []
        for doc in self._docs:
            if self._matches(doc, filter_dict):
                result.append(doc)
        return MockCursor(result)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> MockCursor:
        return MockCursor(self._docs)

    async def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        if not filter_dict:
            return len(self._docs)
        return sum(1 for d in self._docs if self._matches(d, filter_dict))

    def _matches(self, doc: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        for key, val in filter_dict.items():
            doc_val = doc.get(key)
            if isinstance(val, dict):
                # Handle operators
                if "$in" in val and doc_val not in val["$in"]:
                    return False
                if "$ne" in val and doc_val == val["$ne"]:
                    return False
                if "$gte" in val and (doc_val is None or doc_val < val["$gte"]):
                    return False
                if "$lte" in val and (doc_val is None or doc_val > val["$lte"]):
                    return False
            else:
                if doc_val != val:
                    return False
        return True


SAMPLE_FEEDBACK = [
    {
        "_id": "fb-001",
        "feedback_id": "FDBK-0109",
        "rating": "down",
        "reason": "datos no coinciden",
        "created_at": datetime(2026, 2, 10, 14, 0),
        "conversation_id": "conv-aaa",
        "message_id": "msg-001",
        "user_id": "user-1",
        "context": {
            "original_query": "muestrame el inventario de Tienda Centro en 2025 vs 2024",
            "response_text": "Aqui los datos...",
        },
        "ticket_id": None,
        "status": "new",
    },
    {
        "_id": "fb-002",
        "feedback_id": "FDBK-0111",
        "rating": "down",
        "reason": "texto confuso",
        "created_at": datetime(2026, 2, 10, 15, 0),
        "conversation_id": "conv-bbb",
        "message_id": "msg-002",
        "user_id": "user-1",
        "context": {
            "original_query": "inventario Tienda Centro 2024",
            "response_text": "Los datos...",
        },
        "ticket_id": "BUG-001",
        "status": "Open",
    },
    {
        "_id": "fb-003",
        "feedback_id": "FDBK-0112",
        "rating": "up",
        "reason": None,
        "created_at": datetime(2026, 2, 10, 16, 0),
        "conversation_id": "conv-aaa",
        "message_id": "msg-003",
        "user_id": "user-2",
        "context": None,
        "ticket_id": None,
        "status": "new",
    },
]

SAMPLE_MESSAGES = [
    {
        "_id": "msg-u1",
        "chat_id": "conv-aaa",
        "role": "user",
        "content": "muestrame el inventario de Tienda Centro en 2025 vs 2024",
        "created_at": datetime(2026, 2, 10, 13, 55),
        "metadata": None,
        "model": None,
    },
    {
        "_id": "msg-001",
        "chat_id": "conv-aaa",
        "role": "assistant",
        "content": "Aqui los datos de inventario...",
        "created_at": datetime(2026, 2, 10, 14, 0),
        "metadata": {"intent": "chart", "handler_name": "evolucion_ventas"},
        "model": "Saptiva Turbo",
    },
]

SAMPLE_ARTIFACTS = [
    {
        "_id": "art-001",
        "chat_session_id": "conv-aaa",
        "type": "chart",
        "title": "Inventario Tienda Centro",
        "content": {
            "chart_status": "success",
            "metric_name": "INVENTARIO_TOTAL",
            "store_names": ["Tienda Centro"],
            "plotly_config": {
                "data": [
                    {
                        "name": "Tienda Centro",
                        "type": "scatter",
                        "x": ["2024-01-01", "2024-06-01", "2025-01-01", "2025-06-01"],
                        "y": [14870, 15000, 15500, 16000],
                    }
                ],
            },
        },
        "created_at": datetime(2026, 2, 10, 14, 0),
        "expires_at": datetime(2026, 3, 12, 14, 0),
    },
]


def _mock_database(
    feedback_docs: List[Dict[str, Any]] | None = None,
    message_docs: List[Dict[str, Any]] | None = None,
    artifact_docs: List[Dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock Database.database with specified collections."""
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "message_feedback": MockCollection(feedback_docs or SAMPLE_FEEDBACK),
            "messages": MockCollection(message_docs or SAMPLE_MESSAGES),
            "artifacts": MockCollection(artifact_docs or SAMPLE_ARTIFACTS),
        }.get(name, MockCollection())
    )
    return mock_db


# ══════════════════════════════════════════════════════════════════════════════
# Tests: POST /api/internal/feedback/query
# ══════════════════════════════════════════════════════════════════════════════


class TestFeedbackQuery:
    """Tests for the feedback query endpoint."""

    @pytest.mark.asyncio
    async def test_query_returns_all_feedback(self) -> None:
        """Query without filters returns all feedback."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import query_feedback, FeedbackQuery

            result = await query_feedback(FeedbackQuery(limit=100))

            assert len(result) == 3
            assert result[0].feedback_id == "FDBK-0109"

    @pytest.mark.asyncio
    async def test_query_filter_by_rating(self) -> None:
        """Query with rating='down' filters correctly."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import query_feedback, FeedbackQuery

            result = await query_feedback(FeedbackQuery(rating="down", limit=100))

            assert len(result) == 2
            assert all(r.rating == "down" for r in result)

    @pytest.mark.asyncio
    async def test_query_filter_by_feedback_ids(self) -> None:
        """Query with specific feedback_ids."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import query_feedback, FeedbackQuery

            result = await query_feedback(
                FeedbackQuery(feedback_ids=["FDBK-0109"], limit=100)
            )

            assert len(result) == 1
            assert result[0].feedback_id == "FDBK-0109"

    @pytest.mark.asyncio
    async def test_query_respects_limit(self) -> None:
        """Query respects the limit parameter."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import query_feedback, FeedbackQuery

            result = await query_feedback(FeedbackQuery(limit=1))

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_query_includes_context(self) -> None:
        """Feedback records include context field."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import query_feedback, FeedbackQuery

            result = await query_feedback(
                FeedbackQuery(feedback_ids=["FDBK-0109"], limit=100)
            )

            assert result[0].context is not None
            assert "original_query" in result[0].context


# ══════════════════════════════════════════════════════════════════════════════
# Tests: POST /api/internal/feedback/conversations
# ══════════════════════════════════════════════════════════════════════════════


class TestConversations:
    """Tests for the conversations endpoint."""

    @pytest.mark.asyncio
    async def test_fetch_conversation_messages(self) -> None:
        """Fetching a conversation returns its messages."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import get_conversations, ConversationQuery

            result = await get_conversations(
                ConversationQuery(conversation_ids=["conv-aaa"])
            )

            assert "conv-aaa" in result
            assert "messages" in result["conv-aaa"]

    @pytest.mark.asyncio
    async def test_fetch_conversation_with_artifacts(self) -> None:
        """Fetching a conversation includes artifacts when requested."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import get_conversations, ConversationQuery

            result = await get_conversations(
                ConversationQuery(
                    conversation_ids=["conv-aaa"],
                    include_artifacts=True,
                )
            )

            assert "artifacts" in result["conv-aaa"]

    @pytest.mark.asyncio
    async def test_fetch_conversation_without_artifacts(self) -> None:
        """Artifacts excluded when include_artifacts=False."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import get_conversations, ConversationQuery

            result = await get_conversations(
                ConversationQuery(
                    conversation_ids=["conv-aaa"],
                    include_artifacts=False,
                )
            )

            assert "artifacts" not in result["conv-aaa"]

    @pytest.mark.asyncio
    async def test_fetch_multiple_conversations(self) -> None:
        """Fetching multiple conversations returns all."""
        with patch("src.routers.internal.Database") as mock_db_cls:
            mock_db_cls.database = _mock_database()

            from src.routers.internal import get_conversations, ConversationQuery

            result = await get_conversations(
                ConversationQuery(conversation_ids=["conv-aaa", "conv-bbb"])
            )

            assert "conv-aaa" in result
            assert "conv-bbb" in result


# NOTE: la detección de charts obsoletos y sus helpers (_classify_chart,
# _extract_years, detect_stale_charts) se retiraron al excindir el dominio vertical.
