"""
Logging configuration for the FastAPI application.
"""

import logging.config
import sys

import structlog


def pii_scrubbing_processor(logger, method_name, event_dict):
    """
    Structlog processor to scrub PII from logs.

    Scrubs sensitive data before logging to prevent data leaks:
    - Email addresses
    - Phone numbers
    - SSNs
    - Credit cards
    - IP addresses
    - API keys
    """
    # Import here to avoid circular dependency
    from ..mcp_integration.security import PIIScrubber

    # Scrub event message
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = PIIScrubber.scrub(event_dict["event"])

    # Scrub all string values in event_dict
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = PIIScrubber.scrub(value)
        elif isinstance(value, dict):
            event_dict[key] = PIIScrubber.scrub_dict(value)

    return event_dict


def setup_logging(level: str = "INFO", enable_pii_scrubbing: bool = True) -> None:
    """
    Setup structured logging with structlog.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        enable_pii_scrubbing: Enable PII scrubbing processor (default: True)
    """

    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        stream=sys.stdout,
        format="%(message)s",
    )

    # Build processors list
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add PII scrubbing processor before JSON rendering (if enabled)
    if enable_pii_scrubbing:
        processors.append(pii_scrubbing_processor)

    # Add JSON renderer last
    processors.append(structlog.processors.JSONRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
