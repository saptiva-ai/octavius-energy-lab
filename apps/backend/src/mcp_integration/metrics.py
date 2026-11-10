"""
MCP Metrics - Product-focused metrics for tool observability.

Integrates with Prometheus for:
- Tool invocation counters (success/failure by tool)
- Tool latency histograms (with outcome labels)
- Tool timeout counters
- Tool validation failure counters
- Task lifecycle metrics

Metrics Design:
- mcp_tool_invocations_total{tool, version, status, user_type}
- mcp_tool_duration_seconds{tool, version, outcome}
- mcp_tool_timeouts_total{tool, version}
- mcp_tool_validation_failures_total{tool, version, error_code}
- mcp_task_created_total{tool, priority}
- mcp_task_completed_total{tool, status}
- mcp_task_duration_seconds{tool, status}
"""

from typing import Optional

import structlog
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


def _get_or_create_counter(name: str, description: str, labelnames: list) -> Counter:
    """Get existing counter or create new one to avoid duplicate registration."""
    # Check if already registered first
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Counter(name, description, labelnames=labelnames)
    except ValueError:
        # Race condition: another thread registered it
        return REGISTRY._names_to_collectors[name]


def _get_or_create_histogram(
    name: str, description: str, labelnames: list, buckets: tuple
) -> Histogram:
    """Get existing histogram or create new one to avoid duplicate registration."""
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Histogram(name, description, labelnames=labelnames, buckets=buckets)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


def _get_or_create_gauge(name: str, description: str, labelnames: list) -> Gauge:
    """Get existing gauge or create new one to avoid duplicate registration."""
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Gauge(name, description, labelnames=labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


# Tool Invocation Metrics

tool_invocations_total = _get_or_create_counter(
    "mcp_tool_invocations_total",
    "Total MCP tool invocations",
    labelnames=["tool", "version", "status", "user_type"],
)

tool_duration_seconds = _get_or_create_histogram(
    "mcp_tool_duration_seconds",
    "MCP tool execution duration in seconds",
    labelnames=["tool", "version", "outcome"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

tool_timeouts_total = _get_or_create_counter(
    "mcp_tool_timeouts_total",
    "Total MCP tool timeouts",
    labelnames=["tool", "version"],
)

tool_validation_failures_total = _get_or_create_counter(
    "mcp_tool_validation_failures_total",
    "Total MCP tool validation failures",
    labelnames=["tool", "version", "error_code"],
)

tool_rate_limit_exceeded_total = _get_or_create_counter(
    "mcp_tool_rate_limit_exceeded_total",
    "Total rate limit exceeded events",
    labelnames=["tool", "user_type"],
)

tool_permission_denied_total = _get_or_create_counter(
    "mcp_tool_permission_denied_total",
    "Total permission denied events",
    labelnames=["tool", "required_scope"],
)

# Task Lifecycle Metrics

task_created_total = _get_or_create_counter(
    "mcp_task_created_total",
    "Total tasks created",
    labelnames=["tool", "priority"],
)

task_completed_total = _get_or_create_counter(
    "mcp_task_completed_total",
    "Total tasks completed",
    labelnames=["tool", "status"],
)

task_duration_seconds = _get_or_create_histogram(
    "mcp_task_duration_seconds",
    "Task execution duration in seconds",
    labelnames=["tool", "status"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0),
)

task_cancelled_total = _get_or_create_counter(
    "mcp_task_cancelled_total",
    "Total tasks cancelled by user",
    labelnames=["tool"],
)

task_queue_size = _get_or_create_gauge(
    "mcp_task_queue_size",
    "Current number of pending tasks",
    labelnames=["priority"],
)

# Version Metrics

tool_version_usage_total = _get_or_create_counter(
    "mcp_tool_version_usage_total",
    "Tool version usage counter",
    labelnames=["tool", "version", "constraint"],
)

tool_deprecated_version_usage_total = _get_or_create_counter(
    "mcp_tool_deprecated_version_usage_total",
    "Deprecated tool version usage counter",
    labelnames=["tool", "version", "replacement"],
)


class MCPMetricsCollector:
    """
    Centralized metrics collector for MCP operations.

    Provides high-level methods to record metrics for:
    - Tool invocations
    - Task lifecycle
    - Version usage
    - Security events
    """

    @staticmethod
    def record_tool_invocation(
        tool: str,
        version: str,
        status: str,  # "success" | "error"
        duration_seconds: float,
        outcome: str,  # "success" | "validation_error" | "permission_denied" | "timeout" | "error"
        user_type: str = "user",  # "user" | "admin" | "service"
    ):
        """
        Record tool invocation metrics.

        Args:
            tool: Tool name
            version: Tool version
            status: "success" or "error"
            duration_seconds: Execution time in seconds
            outcome: Detailed outcome (success, validation_error, etc.)
            user_type: Type of user (for segmentation)
        """
        # Increment invocation counter
        tool_invocations_total.labels(
            tool=tool,
            version=version,
            status=status,
            user_type=user_type,
        ).inc()

        # Record duration histogram
        tool_duration_seconds.labels(
            tool=tool,
            version=version,
            outcome=outcome,
        ).observe(duration_seconds)

        logger.debug(
            "Tool invocation metric recorded",
            tool=tool,
            version=version,
            status=status,
            duration_seconds=duration_seconds,
            outcome=outcome,
        )

    @staticmethod
    def record_tool_timeout(tool: str, version: str):
        """Record tool timeout event."""
        tool_timeouts_total.labels(
            tool=tool,
            version=version,
        ).inc()

        logger.warning("Tool timeout metric recorded", tool=tool, version=version)

    @staticmethod
    def record_validation_failure(tool: str, version: str, error_code: str):
        """Record validation failure (payload size, structure, etc.)."""
        tool_validation_failures_total.labels(
            tool=tool,
            version=version,
            error_code=error_code,
        ).inc()

        logger.debug(
            "Validation failure metric recorded",
            tool=tool,
            version=version,
            error_code=error_code,
        )

    @staticmethod
    def record_rate_limit_exceeded(tool: str, user_type: str = "user"):
        """Record rate limit exceeded event."""
        tool_rate_limit_exceeded_total.labels(
            tool=tool,
            user_type=user_type,
        ).inc()

        logger.warning(
            "Rate limit exceeded metric recorded", tool=tool, user_type=user_type
        )

    @staticmethod
    def record_permission_denied(tool: str, required_scope: str):
        """Record permission denied event."""
        tool_permission_denied_total.labels(
            tool=tool,
            required_scope=required_scope,
        ).inc()

        logger.warning(
            "Permission denied metric recorded",
            tool=tool,
            required_scope=required_scope,
        )

    @staticmethod
    def record_task_created(tool: str, priority: str):
        """Record task creation."""
        task_created_total.labels(
            tool=tool,
            priority=priority,
        ).inc()

        logger.debug("Task created metric recorded", tool=tool, priority=priority)

    @staticmethod
    def record_deprecated_version_usage(
        tool: str, version: str, replacement: Optional[str]
    ):
        """Record when a deprecated tool version is used."""
        tool_deprecated_version_usage_total.labels(
            tool=tool,
            version=version,
            replacement=replacement or "unknown",
        ).inc()

        logger.warning(
            "Deprecated tool version usage recorded",
            tool=tool,
            version=version,
            replacement=replacement,
        )

    @staticmethod
    def record_task_completed(
        tool: str,
        status: str,  # "completed" | "failed" | "cancelled"
        duration_seconds: float,
    ):
        """Record task completion."""
        task_completed_total.labels(
            tool=tool,
            status=status,
        ).inc()

        task_duration_seconds.labels(
            tool=tool,
            status=status,
        ).observe(duration_seconds)

        logger.debug(
            "Task completed metric recorded",
            tool=tool,
            status=status,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    def record_task_cancelled(tool: str):
        """Record task cancellation."""
        task_cancelled_total.labels(tool=tool).inc()

        logger.debug("Task cancelled metric recorded", tool=tool)

    @staticmethod
    def update_task_queue_size(priority: str, size: int):
        """Update task queue size gauge."""
        task_queue_size.labels(priority=priority).set(size)

    @staticmethod
    def record_version_usage(
        tool: str,
        version: str,
        constraint: Optional[str] = None,
        is_deprecated: bool = False,
        replacement: Optional[str] = None,
    ):
        """Record tool version usage."""
        tool_version_usage_total.labels(
            tool=tool,
            version=version,
            constraint=constraint or "exact",
        ).inc()

        if is_deprecated:
            tool_deprecated_version_usage_total.labels(
                tool=tool,
                version=version,
                replacement=replacement or "unknown",
            ).inc()

            logger.warning(
                "Deprecated version usage metric recorded",
                tool=tool,
                version=version,
                replacement=replacement,
            )


# Global collector instance
metrics_collector = MCPMetricsCollector()


def get_metrics_summary() -> dict:
    """
    Get summary of current metrics for health checks.

    Returns:
        Dictionary with metric summaries
    """
    # This is a simplified version - in production, you'd query Prometheus
    return {
        "tool_invocations": "See Prometheus for details",
        "tasks_pending": "See task_queue_size gauge",
        "message": "Use Prometheus /metrics endpoint for detailed metrics",
    }
