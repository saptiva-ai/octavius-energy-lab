"""
Unit tests for mcp_integration/protocol module.

Tests:
- ToolCategory enum
- ToolCapability enum
- ErrorCode enum
- ToolSpec model
- ToolInvokeRequest model
- ToolInvokeResponse model
- ToolError model
- ToolMetrics model
"""

from datetime import datetime

import pytest

from src.mcp_integration.protocol import (
    ErrorCode,
    ToolCapability,
    ToolCategory,
    ToolError,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolMetrics,
    ToolSpec,
)

pytestmark = [pytest.mark.unit]


class TestToolCategory:
    """Test ToolCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories exist."""
        assert ToolCategory.DOCUMENT_ANALYSIS == "document_analysis"
        assert ToolCategory.DATA_ANALYTICS == "data_analytics"
        assert ToolCategory.VISUALIZATION == "visualization"
        assert ToolCategory.RESEARCH == "research"
        assert ToolCategory.COMPLIANCE == "compliance"

    def test_is_string_enum(self):
        """Test categories are string enums."""
        assert isinstance(ToolCategory.DOCUMENT_ANALYSIS, str)


class TestToolCapability:
    """Test ToolCapability enum."""

    def test_all_capabilities_exist(self):
        """Test all expected capabilities exist."""
        assert ToolCapability.SYNC == "sync"
        assert ToolCapability.ASYNC == "async"
        assert ToolCapability.STREAMING == "streaming"
        assert ToolCapability.IDEMPOTENT == "idempotent"
        assert ToolCapability.CACHEABLE == "cacheable"
        assert ToolCapability.STATEFUL == "stateful"

    def test_is_string_enum(self):
        """Test capabilities are string enums."""
        assert isinstance(ToolCapability.SYNC, str)


class TestErrorCode:
    """Test ErrorCode enum."""

    def test_all_error_codes_exist(self):
        """Test all expected error codes exist."""
        expected_codes = [
            "VALIDATION_ERROR",
            "TIMEOUT",
            "TOOL_BUSY",
            "BACKEND_DEP_UNAVAILABLE",
            "RATE_LIMIT",
            "PERMISSION_DENIED",
            "TOOL_NOT_FOUND",
            "EXECUTION_ERROR",
            "CANCELLED",
        ]
        for code in expected_codes:
            assert hasattr(ErrorCode, code)

    def test_is_string_enum(self):
        """Test error codes are string enums."""
        assert isinstance(ErrorCode.VALIDATION_ERROR, str)


class TestToolSpec:
    """Test ToolSpec Pydantic model."""

    def test_create_minimal_spec(self):
        """Test creating spec with required fields."""
        spec = ToolSpec(
            name="test_tool",
            version="1.0.0",
            display_name="Test Tool",
            description="A test tool",
            category=ToolCategory.DOCUMENT_ANALYSIS,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        assert spec.name == "test_tool"
        assert spec.version == "1.0.0"
        assert spec.category == ToolCategory.DOCUMENT_ANALYSIS

    def test_default_values(self):
        """Test default values are set."""
        spec = ToolSpec(
            name="test_tool",
            version="1.0.0",
            display_name="Test Tool",
            description="A test tool",
            category=ToolCategory.DOCUMENT_ANALYSIS,
            input_schema={},
            output_schema={},
        )

        assert spec.capabilities == []
        assert spec.tags == []
        assert spec.author == "OctaviOS"
        assert spec.requires_auth is True
        assert spec.rate_limit is None
        assert spec.timeout_ms == 30000
        assert spec.max_payload_size_kb == 1024

    def test_with_capabilities(self):
        """Test spec with capabilities."""
        spec = ToolSpec(
            name="test_tool",
            version="1.0.0",
            display_name="Test Tool",
            description="A test tool",
            category=ToolCategory.DOCUMENT_ANALYSIS,
            capabilities=[ToolCapability.SYNC, ToolCapability.CACHEABLE],
            input_schema={},
            output_schema={},
        )

        assert ToolCapability.SYNC in spec.capabilities
        assert ToolCapability.CACHEABLE in spec.capabilities

    def test_with_rate_limit(self):
        """Test spec with rate limit."""
        spec = ToolSpec(
            name="test_tool",
            version="1.0.0",
            display_name="Test Tool",
            description="A test tool",
            category=ToolCategory.DATA_ANALYTICS,
            input_schema={},
            output_schema={},
            rate_limit={"calls_per_minute": 10},
        )

        assert spec.rate_limit == {"calls_per_minute": 10}


class TestToolInvokeRequest:
    """Test ToolInvokeRequest Pydantic model."""

    def test_create_minimal_request(self):
        """Test creating request with required fields."""
        request = ToolInvokeRequest(
            tool="test_tool",
            payload={"key": "value"},
        )

        assert request.tool == "test_tool"
        assert request.payload == {"key": "value"}
        assert request.version is None
        assert request.context is None
        assert request.idempotency_key is None

    def test_with_all_fields(self):
        """Test request with all fields."""
        request = ToolInvokeRequest(
            tool="test_tool",
            version="1.0.0",
            payload={"key": "value"},
            context={"user_id": "user_123"},
            idempotency_key="idem_abc123",
        )

        assert request.version == "1.0.0"
        assert request.context == {"user_id": "user_123"}
        assert request.idempotency_key == "idem_abc123"


class TestToolInvokeResponse:
    """Test ToolInvokeResponse Pydantic model."""

    def test_create_success_response(self):
        """Test creating successful response."""
        response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={"data": "value"},
            invocation_id="inv_123",
            duration_ms=50.5,
        )

        assert response.success is True
        assert response.result == {"data": "value"}
        assert response.error is None
        assert response.cached is False

    def test_create_error_response(self):
        """Test creating error response."""
        error = ToolError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid input",
        )

        response = ToolInvokeResponse(
            success=False,
            tool="test_tool",
            version="1.0.0",
            error=error,
            invocation_id="inv_456",
            duration_ms=5.0,
        )

        assert response.success is False
        assert response.error is not None
        assert response.error.code == ErrorCode.VALIDATION_ERROR

    def test_cached_response(self):
        """Test cached response flag."""
        response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={},
            invocation_id="inv_789",
            duration_ms=1.0,
            cached=True,
        )

        assert response.cached is True


class TestToolError:
    """Test ToolError Pydantic model."""

    def test_create_minimal_error(self):
        """Test creating error with required fields."""
        error = ToolError(
            code=ErrorCode.EXECUTION_ERROR,
            message="Something went wrong",
        )

        assert error.code == ErrorCode.EXECUTION_ERROR
        assert error.message == "Something went wrong"
        assert error.user_message is None
        assert error.details is None

    def test_with_all_fields(self):
        """Test error with all fields."""
        error = ToolError(
            code=ErrorCode.RATE_LIMIT,
            message="Rate limit exceeded",
            user_message="Please try again later",
            details={"limit": 10, "current": 15},
            tool_context={"tool": "test_tool"},
            retry_after_ms=60000,
            trace_id="trace_abc",
        )

        assert error.user_message == "Please try again later"
        assert error.details["limit"] == 10
        assert error.retry_after_ms == 60000
        assert error.trace_id == "trace_abc"

    @pytest.mark.parametrize("code", list(ErrorCode))
    def test_all_error_codes_work(self, code):
        """Test all error codes can be used."""
        error = ToolError(code=code, message="Test message")
        assert error.code == code


class TestToolMetrics:
    """Test ToolMetrics Pydantic model."""

    def test_create_minimal_metrics(self):
        """Test creating metrics with required fields."""
        metrics = ToolMetrics(
            tool="test_tool",
            version="1.0.0",
        )

        assert metrics.tool == "test_tool"
        assert metrics.version == "1.0.0"

    def test_default_values(self):
        """Test default metric values."""
        metrics = ToolMetrics(
            tool="test_tool",
            version="1.0.0",
        )

        assert metrics.invocation_count == 0
        assert metrics.success_count == 0
        assert metrics.error_count == 0
        assert metrics.avg_duration_ms == 0.0
        assert metrics.p95_duration_ms == 0.0
        assert metrics.p99_duration_ms == 0.0
        assert metrics.last_invoked_at is None
        assert metrics.cache_hit_rate == 0.0

    def test_with_metrics(self):
        """Test metrics with actual values."""
        metrics = ToolMetrics(
            tool="test_tool",
            version="1.0.0",
            invocation_count=100,
            success_count=95,
            error_count=5,
            avg_duration_ms=25.5,
            p95_duration_ms=50.0,
            p99_duration_ms=100.0,
            last_invoked_at=datetime.now(),
            cache_hit_rate=0.3,
        )

        assert metrics.invocation_count == 100
        assert metrics.success_count == 95
        assert metrics.cache_hit_rate == 0.3


class TestModelSerialization:
    """Test model serialization."""

    def test_tool_spec_to_dict(self):
        """Test ToolSpec serializes to dict."""
        spec = ToolSpec(
            name="test_tool",
            version="1.0.0",
            display_name="Test",
            description="Test",
            category=ToolCategory.RESEARCH,
            input_schema={},
            output_schema={},
        )

        data = spec.model_dump()
        assert data["name"] == "test_tool"
        assert data["category"] == "research"

    def test_tool_error_to_dict(self):
        """Test ToolError serializes to dict."""
        error = ToolError(
            code=ErrorCode.TIMEOUT,
            message="Timeout",
        )

        data = error.model_dump()
        assert data["code"] == "TIMEOUT"
        assert data["message"] == "Timeout"

    def test_tool_invoke_response_to_dict(self):
        """Test ToolInvokeResponse serializes to dict."""
        response = ToolInvokeResponse(
            success=True,
            tool="test",
            version="1.0.0",
            result={"key": "value"},
            invocation_id="inv",
            duration_ms=10.0,
        )

        data = response.model_dump()
        assert data["success"] is True
        assert data["result"] == {"key": "value"}
