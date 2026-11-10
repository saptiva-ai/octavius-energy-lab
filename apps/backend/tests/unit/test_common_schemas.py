"""
Unit tests for common schemas.

Tests Pydantic models used across the application.
"""
import pytest
from datetime import datetime
from uuid import uuid4
from pydantic import ValidationError

from src.schemas.common import (
    ApiError,
    ApiMeta,
    ApiResponse,
    Pagination,
    PaginatedResponse,
    BaseEntity,
    HealthCheck
)


@pytest.mark.unit
class TestCommonSchemas:
    """Test common schema models"""

    def test_api_error_creation(self):
        """Test ApiError model creation"""
        error = ApiError(
            code="AUTH_FAILED",
            message="Authentication failed",
            details={"reason": "Invalid token"},
            trace_id="trace-123"
        )

        assert error.code == "AUTH_FAILED"
        assert error.message == "Authentication failed"
        assert error.details["reason"] == "Invalid token"
        assert error.trace_id == "trace-123"

    def test_api_error_minimal(self):
        """Test ApiError with minimal fields"""
        error = ApiError(code="ERROR", message="Something went wrong")
        assert error.code == "ERROR"
        assert error.message == "Something went wrong"
        assert error.details is None
        assert error.trace_id is None

    def test_api_meta_creation(self):
        """Test ApiMeta model creation"""
        now = datetime.utcnow()
        meta = ApiMeta(
            timestamp=now,
            request_id="req-123",
            version="1.0.0"
        )

        assert meta.timestamp == now
        assert meta.request_id == "req-123"
        assert meta.version == "1.0.0"

    def test_api_response_success(self):
        """Test ApiResponse for successful response"""
        response = ApiResponse(
            success=True,
            message="Operation completed",
            data={"user_id": "123"}
        )

        assert response.success is True
        assert response.message == "Operation completed"
        assert response.data["user_id"] == "123"
        assert response.error is None

    def test_api_response_error(self):
        """Test ApiResponse for error response"""
        error = ApiError(code="ERROR", message="Failed")
        response = ApiResponse(
            success=False,
            error=error
        )

        assert response.success is False
        assert response.error.code == "ERROR"
        assert response.data is None

    def test_pagination_creation(self):
        """Test Pagination model"""
        pagination = Pagination(
            page=2,
            limit=20,
            total=100,
            pages=5
        )

        assert pagination.page == 2
        assert pagination.limit == 20
        assert pagination.total == 100
        assert pagination.pages == 5

    def test_pagination_validation_page(self):
        """Test Pagination validates page >= 1"""
        with pytest.raises(ValidationError):
            Pagination(page=0, limit=20, total=100, pages=5)

    def test_pagination_validation_limit(self):
        """Test Pagination validates limit range"""
        with pytest.raises(ValidationError):
            Pagination(page=1, limit=0, total=100, pages=5)

        with pytest.raises(ValidationError):
            Pagination(page=1, limit=101, total=100, pages=5)

    def test_paginated_response_creation(self):
        """Test PaginatedResponse with data"""
        items = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]
        pagination = Pagination(page=1, limit=20, total=50, pages=3)

        response = PaginatedResponse(
            success=True,
            data=items,
            pagination=pagination
        )

        assert response.success is True
        assert len(response.data) == 2
        assert response.pagination.total == 50

    def test_paginated_response_empty(self):
        """Test PaginatedResponse with no data"""
        pagination = Pagination(page=1, limit=20, total=0, pages=0)

        response = PaginatedResponse(
            success=True,
            data=[],
            pagination=pagination
        )

        assert response.success is True
        assert len(response.data) == 0
        assert response.pagination.total == 0

    def test_base_entity_creation(self):
        """Test BaseEntity model"""
        entity_id = uuid4()
        now = datetime.utcnow()

        entity = BaseEntity(
            id=entity_id,
            created_at=now,
            updated_at=now
        )

        assert entity.id == entity_id
        assert entity.created_at == now
        assert entity.updated_at == now

    def test_health_check_creation(self):
        """Test HealthCheck model"""
        now = datetime.utcnow()
        health = HealthCheck(
            status="healthy",
            timestamp=now,
            uptime_seconds=3600.5
        )

        assert health.status == "healthy"
        assert health.timestamp == now
        assert health.uptime_seconds == 3600.5

    def test_api_response_json_serialization(self):
        """Test ApiResponse can be serialized"""
        response = ApiResponse(success=True, message="OK")
        json_data = response.model_dump()

        assert json_data["success"] is True
        assert json_data["message"] == "OK"
        assert isinstance(json_data, dict)

    def test_pagination_json_schema(self):
        """Test Pagination generates valid JSON schema"""
        schema = Pagination.model_json_schema()
        assert "properties" in schema
        assert "page" in schema["properties"]
        assert "limit" in schema["properties"]
        assert "total" in schema["properties"]
        assert "pages" in schema["properties"]
