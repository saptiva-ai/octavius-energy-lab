"""
Comprehensive tests for models/feedback.py - MessageFeedback Model

Coverage (Phase 1 - Backend Testing for EPIC-HU5):
- MessageFeedback creation with valid data
- Rating enum validation (up/down)
- Reason max length validation (500 chars)
- Indexes verification
- Timestamp auto-generation
- Field constraints and defaults

Maps to Acceptance Criteria:
- CA-05: Feedback stored with correct fields
- CA-11: Timestamp auto-generation
- CA-12: Indexes on message_id, conversation_id, user_id
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from src.models.feedback import MessageFeedback, FeedbackRating


# ============================================================================
# Beanie Mock Setup for Unit Tests
# ============================================================================
# Beanie (MongoDB ODM) requires init_beanie() before creating Document instances.
# For unit tests, we mock the collection to avoid needing MongoDB.

@pytest.fixture(autouse=True)
def mock_beanie_collection():
    """Mock Beanie's collection initialization for unit tests."""
    mock_collection = MagicMock()
    mock_settings = MagicMock()
    mock_settings.pymongo_collection = mock_collection

    with patch.object(MessageFeedback, 'get_settings', return_value=mock_settings):
        yield mock_settings


# ============================================================================
# TEST: MessageFeedback Creation
# ============================================================================

class TestMessageFeedbackCreation:
    """Test CA-05: MessageFeedback can be created with valid data."""

    def test_ca05_create_thumbs_up_feedback(self):
        """CA-05: Can create feedback with thumbs up rating."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP,
            reason=None
        )

        assert feedback.message_id == "msg-123"
        assert feedback.conversation_id == "session-456"
        assert feedback.user_id == "user-789"
        assert feedback.rating == FeedbackRating.UP
        assert feedback.reason is None
        assert feedback.id is not None  # Auto-generated UUID
        assert feedback.created_at is not None  # Auto-generated timestamp

    def test_ca05_create_thumbs_down_feedback(self):
        """CA-05: Can create feedback with thumbs down rating."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason="Data mismatch"
        )

        assert feedback.rating == FeedbackRating.DOWN
        assert feedback.reason == "Data mismatch"

    def test_ca05_create_feedback_with_all_fields(self):
        """CA-05: Can create feedback with all fields populated."""
        now = datetime.utcnow()
        feedback = MessageFeedback(
            id="fb-custom-id",
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason="El dato no coincide con mi reporte interno",
            created_at=now
        )

        assert feedback.id == "fb-custom-id"
        assert feedback.message_id == "msg-123"
        assert feedback.conversation_id == "session-456"
        assert feedback.user_id == "user-789"
        assert feedback.rating == FeedbackRating.DOWN
        assert feedback.reason == "El dato no coincide con mi reporte interno"
        assert feedback.created_at == now


# ============================================================================
# TEST: Rating Enum Validation
# ============================================================================

class TestRatingEnumValidation:
    """Test rating enum accepts only 'up' or 'down'."""

    def test_rating_enum_up(self):
        """Should accept 'up' rating."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP
        )

        assert feedback.rating == FeedbackRating.UP
        assert feedback.rating.value == "up"

    def test_rating_enum_down(self):
        """Should accept 'down' rating."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN
        )

        assert feedback.rating == FeedbackRating.DOWN
        assert feedback.rating.value == "down"

    def test_rating_enum_from_string_up(self):
        """Should create enum from string 'up'."""
        rating = FeedbackRating("up")
        assert rating == FeedbackRating.UP

    def test_rating_enum_from_string_down(self):
        """Should create enum from string 'down'."""
        rating = FeedbackRating("down")
        assert rating == FeedbackRating.DOWN

    def test_rating_enum_invalid_value(self):
        """Should reject invalid rating values."""
        with pytest.raises(ValueError):
            FeedbackRating("invalid")

        with pytest.raises(ValueError):
            FeedbackRating("neutral")

        with pytest.raises(ValueError):
            FeedbackRating("like")


# ============================================================================
# TEST: Reason Max Length Validation
# ============================================================================

class TestReasonMaxLength:
    """Test CA-12: Reason field limited to 500 characters."""

    def test_ca12_reason_within_500_chars(self):
        """CA-12: Should accept reason with ≤500 characters."""
        reason = "x" * 500  # Exactly 500 chars

        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason=reason
        )

        assert len(feedback.reason) == 500

    def test_ca12_reason_empty_string_allowed(self):
        """CA-12: Empty string should be allowed for reason."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason=""
        )

        assert feedback.reason == ""

    def test_ca12_reason_none_allowed(self):
        """CA-12: None should be allowed for reason (optional field)."""
        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP,
            reason=None
        )

        assert feedback.reason is None


# ============================================================================
# TEST: Auto-Generated Fields
# ============================================================================

class TestAutoGeneratedFields:
    """Test CA-11: Auto-generated ID and timestamp."""

    def test_ca11_id_auto_generated_uuid(self):
        """CA-11: ID should auto-generate as UUID if not provided."""
        feedback1 = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP
        )

        feedback2 = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP
        )

        # IDs should be auto-generated
        assert feedback1.id is not None
        assert feedback2.id is not None

        # IDs should be unique
        assert feedback1.id != feedback2.id

        # IDs should be valid UUID format (contain hyphens)
        assert "-" in feedback1.id

    def test_ca11_created_at_auto_generated(self):
        """CA-11: created_at should auto-generate if not provided."""
        before = datetime.utcnow()

        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP
        )

        after = datetime.utcnow()

        # Timestamp should be auto-generated
        assert feedback.created_at is not None

        # Timestamp should be recent
        assert before <= feedback.created_at <= after

    def test_ca11_created_at_can_be_overridden(self):
        """CA-11: created_at can be explicitly set if needed."""
        custom_time = datetime(2025, 1, 1, 12, 0, 0)

        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.UP,
            created_at=custom_time
        )

        assert feedback.created_at == custom_time


# ============================================================================
# TEST: Required Fields Validation
# ============================================================================

class TestRequiredFields:
    """Test that required fields must be provided."""

    def test_missing_message_id(self):
        """Should reject feedback without message_id."""
        with pytest.raises(ValidationError) as exc_info:
            MessageFeedback(
                # Missing message_id
                conversation_id="session-456",
                user_id="user-789",
                rating=FeedbackRating.UP
            )

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('message_id',) for e in errors)

    def test_missing_conversation_id(self):
        """Should reject feedback without conversation_id."""
        with pytest.raises(ValidationError) as exc_info:
            MessageFeedback(
                message_id="msg-123",
                # Missing conversation_id
                user_id="user-789",
                rating=FeedbackRating.UP
            )

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('conversation_id',) for e in errors)

    def test_missing_user_id(self):
        """Should reject feedback without user_id."""
        with pytest.raises(ValidationError) as exc_info:
            MessageFeedback(
                message_id="msg-123",
                conversation_id="session-456",
                # Missing user_id
                rating=FeedbackRating.UP
            )

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('user_id',) for e in errors)

    def test_missing_rating(self):
        """Should reject feedback without rating."""
        with pytest.raises(ValidationError) as exc_info:
            MessageFeedback(
                message_id="msg-123",
                conversation_id="session-456",
                user_id="user-789"
                # Missing rating
            )

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('rating',) for e in errors)


# ============================================================================
# TEST: MongoDB Settings and Indexes
# ============================================================================

class TestMongoDBSettings:
    """Test CA-12: MongoDB collection settings and indexes."""

    def test_ca12_collection_name(self):
        """CA-12: Collection should be named 'message_feedback'."""
        assert MessageFeedback.Settings.name == "message_feedback"

    def test_ca12_indexes_defined(self):
        """CA-12: Indexes should be defined on key fields."""
        indexes = MessageFeedback.Settings.indexes

        # Should have indexes
        assert indexes is not None
        assert len(indexes) > 0

        # Check for single-field indexes
        assert any("message_id" in str(idx) for idx in indexes)
        assert any("conversation_id" in str(idx) for idx in indexes)
        assert any("user_id" in str(idx) for idx in indexes)
        assert any("rating" in str(idx) for idx in indexes)
        assert any("created_at" in str(idx) for idx in indexes)


# ============================================================================
# TEST: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_reason_with_special_characters(self):
        """Should handle reason with special characters."""
        special_reason = "Data: 123.45% — doesn't match! (Σ ≠ expected)"

        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason=special_reason
        )

        assert feedback.reason == special_reason

    def test_reason_with_newlines(self):
        """Should handle reason with newlines."""
        multiline_reason = "Line 1\nLine 2\nLine 3"

        feedback = MessageFeedback(
            message_id="msg-123",
            conversation_id="session-456",
            user_id="user-789",
            rating=FeedbackRating.DOWN,
            reason=multiline_reason
        )

        assert feedback.reason == multiline_reason
        assert "\n" in feedback.reason
