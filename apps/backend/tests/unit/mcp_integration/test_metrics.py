"""
Unit tests for MCP metrics module.

Tests:
- Prometheus metric existence
- MCPMetricsCollector methods
- get_metrics_summary function
"""

import pytest

from src.mcp_integration.metrics import (
    MCPMetricsCollector,
    get_metrics_summary,
    task_cancelled_total,
    task_completed_total,
    task_created_total,
    task_duration_seconds,
    task_queue_size,
    tool_deprecated_version_usage_total,
    tool_duration_seconds,
    tool_invocations_total,
    tool_permission_denied_total,
    tool_rate_limit_exceeded_total,
    tool_timeouts_total,
    tool_validation_failures_total,
    tool_version_usage_total,
)

pytestmark = [pytest.mark.unit]


class TestPrometheusMetrics:
    """Test Prometheus metric definitions."""

    def test_tool_invocations_counter_exists(self):
        """Test tool invocations counter is defined."""
        # Prometheus strips _total suffix from Counter._name internally
        assert tool_invocations_total._name == "mcp_tool_invocations"

    def test_tool_duration_histogram_exists(self):
        """Test tool duration histogram is defined."""
        assert tool_duration_seconds._upper_bounds is not None
        assert len(tool_duration_seconds._upper_bounds) > 0

    def test_tool_timeouts_counter_exists(self):
        """Test tool timeouts counter is defined."""
        # Prometheus strips _total suffix from Counter._name internally
        assert tool_timeouts_total._name == "mcp_tool_timeouts"

    def test_tool_validation_failures_counter_exists(self):
        """Test validation failures counter is defined."""
        assert tool_validation_failures_total._name == "mcp_tool_validation_failures"

    def test_rate_limit_exceeded_counter_exists(self):
        """Test rate limit exceeded counter is defined."""
        assert tool_rate_limit_exceeded_total._name == "mcp_tool_rate_limit_exceeded"

    def test_permission_denied_counter_exists(self):
        """Test permission denied counter is defined."""
        assert tool_permission_denied_total._name == "mcp_tool_permission_denied"

    def test_task_created_counter_exists(self):
        """Test task created counter is defined."""
        assert task_created_total._name == "mcp_task_created"

    def test_task_completed_counter_exists(self):
        """Test task completed counter is defined."""
        assert task_completed_total._name == "mcp_task_completed"

    def test_task_duration_histogram_exists(self):
        """Test task duration histogram is defined."""
        assert task_duration_seconds._upper_bounds is not None
        assert len(task_duration_seconds._upper_bounds) > 0

    def test_task_cancelled_counter_exists(self):
        """Test task cancelled counter is defined."""
        assert task_cancelled_total._name == "mcp_task_cancelled"

    def test_task_queue_gauge_exists(self):
        """Test task queue gauge is defined."""
        assert task_queue_size is not None

    def test_version_usage_counter_exists(self):
        """Test version usage counter is defined."""
        assert tool_version_usage_total._name == "mcp_tool_version_usage"

    def test_deprecated_version_counter_exists(self):
        """Test deprecated version counter is defined."""
        assert tool_deprecated_version_usage_total._name == "mcp_tool_deprecated_version_usage"


class TestMCPMetricsCollector:
    """Test MCPMetricsCollector class."""

    def test_record_tool_invocation_success(self):
        """Test recording successful tool invocation."""
        # Should not raise
        MCPMetricsCollector.record_tool_invocation(
            tool="test_tool",
            version="1.0.0",
            status="success",
            duration_seconds=1.5,
            outcome="success",
            user_type="user",
        )

    def test_record_tool_invocation_error(self):
        """Test recording failed tool invocation."""
        # Should not raise
        MCPMetricsCollector.record_tool_invocation(
            tool="test_tool",
            version="1.0.0",
            status="error",
            duration_seconds=0.5,
            outcome="validation_error",
            user_type="admin",
        )

    def test_record_tool_invocation_default_user_type(self):
        """Test default user_type is 'user'."""
        # Should not raise with default user_type
        MCPMetricsCollector.record_tool_invocation(
            tool="test_tool",
            version="1.0.0",
            status="success",
            duration_seconds=1.0,
            outcome="success",
        )

    def test_record_tool_timeout(self):
        """Test recording tool timeout."""
        MCPMetricsCollector.record_tool_timeout(
            tool="slow_tool",
            version="2.0.0",
        )

    def test_record_validation_failure(self):
        """Test recording validation failure."""
        MCPMetricsCollector.record_validation_failure(
            tool="test_tool",
            version="1.0.0",
            error_code="PAYLOAD_TOO_LARGE",
        )

    def test_record_rate_limit_exceeded(self):
        """Test recording rate limit exceeded."""
        MCPMetricsCollector.record_rate_limit_exceeded(
            tool="busy_tool",
            user_type="user",
        )

    def test_record_rate_limit_exceeded_default_user_type(self):
        """Test default user_type for rate limit."""
        MCPMetricsCollector.record_rate_limit_exceeded(tool="busy_tool")

    def test_record_permission_denied(self):
        """Test recording permission denied."""
        MCPMetricsCollector.record_permission_denied(
            tool="admin_tool",
            required_scope="mcp:admin.tools.manage",
        )

    def test_record_task_created(self):
        """Test recording task creation."""
        MCPMetricsCollector.record_task_created(
            tool="research_tool",
            priority="normal",
        )

    def test_record_task_created_high_priority(self):
        """Test recording high priority task."""
        MCPMetricsCollector.record_task_created(
            tool="urgent_tool",
            priority="high",
        )

    def test_record_deprecated_version_usage(self):
        """Test recording deprecated version usage."""
        MCPMetricsCollector.record_deprecated_version_usage(
            tool="old_tool",
            version="0.5.0",
            replacement="1.0.0",
        )

    def test_record_deprecated_version_usage_no_replacement(self):
        """Test recording deprecated version with no replacement."""
        MCPMetricsCollector.record_deprecated_version_usage(
            tool="old_tool",
            version="0.1.0",
            replacement=None,
        )

    def test_record_task_completed_success(self):
        """Test recording successful task completion."""
        MCPMetricsCollector.record_task_completed(
            tool="research_tool",
            status="completed",
            duration_seconds=45.0,
        )

    def test_record_task_completed_failed(self):
        """Test recording failed task."""
        MCPMetricsCollector.record_task_completed(
            tool="failing_tool",
            status="failed",
            duration_seconds=5.0,
        )

    def test_record_task_completed_cancelled(self):
        """Test recording cancelled task."""
        MCPMetricsCollector.record_task_completed(
            tool="cancelled_tool",
            status="cancelled",
            duration_seconds=10.0,
        )

    def test_record_task_cancelled(self):
        """Test recording task cancellation."""
        MCPMetricsCollector.record_task_cancelled(tool="user_cancelled_tool")

    def test_update_task_queue_size(self):
        """Test updating task queue size gauge."""
        MCPMetricsCollector.update_task_queue_size(
            priority="normal",
            size=10,
        )

    def test_update_task_queue_size_empty(self):
        """Test setting queue size to zero."""
        MCPMetricsCollector.update_task_queue_size(
            priority="high",
            size=0,
        )

    def test_record_version_usage_exact(self):
        """Test recording exact version usage."""
        MCPMetricsCollector.record_version_usage(
            tool="versioned_tool",
            version="2.0.0",
            constraint="exact",
            is_deprecated=False,
        )

    def test_record_version_usage_compatible(self):
        """Test recording compatible version usage."""
        MCPMetricsCollector.record_version_usage(
            tool="versioned_tool",
            version="2.1.0",
            constraint="^2.0.0",
            is_deprecated=False,
        )

    def test_record_version_usage_default_constraint(self):
        """Test default constraint is 'exact'."""
        MCPMetricsCollector.record_version_usage(
            tool="versioned_tool",
            version="1.0.0",
        )

    def test_record_version_usage_deprecated(self):
        """Test recording deprecated version usage."""
        MCPMetricsCollector.record_version_usage(
            tool="legacy_tool",
            version="0.9.0",
            is_deprecated=True,
            replacement="1.0.0",
        )

    def test_record_version_usage_deprecated_no_replacement(self):
        """Test recording deprecated version without replacement."""
        MCPMetricsCollector.record_version_usage(
            tool="abandoned_tool",
            version="0.5.0",
            is_deprecated=True,
            replacement=None,
        )


class TestGetMetricsSummary:
    """Test get_metrics_summary function."""

    def test_returns_dict(self):
        """Test function returns a dictionary."""
        result = get_metrics_summary()
        assert isinstance(result, dict)

    def test_contains_expected_keys(self):
        """Test result contains expected keys."""
        result = get_metrics_summary()

        assert "tool_invocations" in result
        assert "tasks_pending" in result
        assert "message" in result

    def test_message_mentions_prometheus(self):
        """Test message directs to Prometheus."""
        result = get_metrics_summary()

        assert "prometheus" in result["message"].lower()


class TestMetricLabels:
    """Test metric label validation."""

    def test_invocation_with_various_outcomes(self):
        """Test recording invocations with various outcomes."""
        outcomes = [
            "success",
            "validation_error",
            "permission_denied",
            "timeout",
            "error",
        ]

        for outcome in outcomes:
            # Should not raise
            MCPMetricsCollector.record_tool_invocation(
                tool="test_tool",
                version="1.0.0",
                status="error" if outcome != "success" else "success",
                duration_seconds=1.0,
                outcome=outcome,
            )

    def test_invocation_with_various_user_types(self):
        """Test recording invocations with various user types."""
        user_types = ["user", "admin", "service"]

        for user_type in user_types:
            MCPMetricsCollector.record_tool_invocation(
                tool="test_tool",
                version="1.0.0",
                status="success",
                duration_seconds=1.0,
                outcome="success",
                user_type=user_type,
            )

    def test_task_with_various_priorities(self):
        """Test recording tasks with various priorities."""
        priorities = ["low", "normal", "high", "critical"]

        for priority in priorities:
            MCPMetricsCollector.record_task_created(
                tool="priority_tool",
                priority=priority,
            )

    def test_task_with_various_statuses(self):
        """Test recording tasks with various statuses."""
        statuses = ["completed", "failed", "cancelled", "timeout"]

        for status in statuses:
            MCPMetricsCollector.record_task_completed(
                tool="status_tool",
                status=status,
                duration_seconds=1.0,
            )


class TestHistogramBuckets:
    """Test histogram bucket configurations."""

    def test_tool_duration_buckets(self):
        """Test tool duration has appropriate buckets."""
        # prometheus_client uses _upper_bounds instead of _buckets
        buckets = [b for b in tool_duration_seconds._upper_bounds if b != float("inf")]

        # Should have multiple buckets
        assert len(buckets) > 5

        # Should start small (sub-second)
        assert min(buckets) <= 0.5

        # Should go up to long durations (minutes)
        assert max(buckets) >= 60

    def test_task_duration_buckets(self):
        """Test task duration has appropriate buckets."""
        # prometheus_client uses _upper_bounds instead of _buckets
        buckets = [b for b in task_duration_seconds._upper_bounds if b != float("inf")]

        # Should have multiple buckets
        assert len(buckets) > 5

        # Tasks can run longer - should go to minutes
        assert max(buckets) >= 600  # 10+ minutes
