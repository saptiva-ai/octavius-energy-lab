"""
Domain Layer - Business Domain Models and Patterns.

Contains:
- Dataclasses for type-safe DTOs
- Builder Pattern for complex object construction
- Strategy Pattern for pluggable chat handlers
- Command Pattern for encapsulated operations
"""

from .chat_context import (
    ChatContext,
    ChatOperation,
    ChatProcessingResult,
    MessageMetadata,
)
from .chat_response_builder import ChatResponseBuilder, StreamingResponseBuilder
from .chat_strategy import ChatStrategy, SimpleChatStrategy

__all__ = [
    # Context and DTOs
    "ChatContext",
    "MessageMetadata",
    "ChatProcessingResult",
    "ChatOperation",
    # Builders
    "ChatResponseBuilder",
    "StreamingResponseBuilder",
    # Strategies
    "ChatStrategy",
    "SimpleChatStrategy",
]
