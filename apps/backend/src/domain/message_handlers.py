"""
Message Handler Chain - Chain of Responsibility Pattern.

Implements Chain of Responsibility for processing chat messages.
Each handler can either process the message or pass it to the next handler.

This pattern allows decoupling specialized message processing (e.g., audit commands)
from standard chat processing, making the system extensible and maintainable.

Architecture:
    - MessageHandler: Abstract base class for all handlers
    - AuditCommandHandler: Handles "Auditar archivo:" commands
    - StandardChatHandler: Handles normal chat messages (fallback)

Usage:
    handler_chain = AuditCommandHandler(next_handler=StandardChatHandler())
    result = await handler_chain.handle(context, ...)
"""

from abc import ABC, abstractmethod
from typing import Optional

import structlog

from .chat_context import ChatContext, ChatProcessingResult

logger = structlog.get_logger(__name__)


class MessageHandler(ABC):
    """
    Abstract base class for message handlers in the chain.

    Each handler can:
    1. Process the message and return a result
    2. Pass the message to the next handler in the chain
    """

    def __init__(self, next_handler: Optional["MessageHandler"] = None):
        """
        Initialize handler with optional next handler in chain.

        Args:
            next_handler: Next handler to call if this one doesn't process the message
        """
        self._next_handler = next_handler

    def set_next(self, handler: "MessageHandler") -> "MessageHandler":
        """
        Set the next handler in the chain (Builder pattern).

        Args:
            handler: Next handler to call

        Returns:
            The handler that was set (for chaining)
        """
        self._next_handler = handler
        return handler

    @abstractmethod
    async def can_handle(self, context: ChatContext) -> bool:
        """
        Check if this handler can process the given context.

        Args:
            context: ChatContext with message and metadata

        Returns:
            True if this handler should process, False otherwise
        """
        pass

    async def handle(
        self, context: ChatContext, chat_service, **kwargs
    ) -> Optional[ChatProcessingResult]:
        """
        Handle the message or pass to next handler.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance for processing
            **kwargs: Additional dependencies (e.g., user_id, settings)

        Returns:
            ChatProcessingResult if handled, None if passed to next handler
        """
        if await self.can_handle(context):
            return await self.process(context, chat_service, **kwargs)
        elif self._next_handler:
            return await self._next_handler.handle(context, chat_service, **kwargs)
        else:
            # No handler could process - should not happen if StandardChatHandler is last
            logger.error(
                "No handler could process message",
                message=context.message[:100],
                session_id=context.session_id,
            )
            return None

    @abstractmethod
    async def process(
        self, context: ChatContext, chat_service, **kwargs
    ) -> ChatProcessingResult:
        """
        Process the message (implemented by concrete handlers).

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance
            **kwargs: Additional dependencies

        Returns:
            ChatProcessingResult with response
        """
        pass


class StandardChatHandler(MessageHandler):
    """
    Standard chat handler - processes normal chat messages.

    This is the fallback handler that always accepts messages.
    It delegates to the existing SimpleChatStrategy.
    """

    def __init__(self, next_handler: Optional[MessageHandler] = None):
        super().__init__(next_handler)
        self._strategy = None  # Will be set when processing

    async def can_handle(self, context: ChatContext) -> bool:
        """Always returns True as this is the fallback handler."""
        return True

    async def process(
        self, context: ChatContext, chat_service, **kwargs
    ) -> ChatProcessingResult:
        """
        Process message using SimpleChatStrategy.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance
            **kwargs: Unused (for interface compatibility)

        Returns:
            ChatProcessingResult from SimpleChatStrategy
        """
        from .chat_strategy import SimpleChatStrategy

        logger.info(
            "Processing message with standard chat handler",
            session_id=context.session_id,
            model=context.model,
            has_documents=bool(context.document_ids),
        )

        strategy = SimpleChatStrategy(chat_service)
        # La sesión (si el endpoint la pasó) aporta el tools_enabled
        # persistido para el function-calling nativo en la ruta no-streaming.
        result = await strategy.process(
            context, chat_session=kwargs.get("chat_session")
        )

        return result


def create_handler_chain() -> MessageHandler:
    """
    Factory function to create the complete handler chain.

    Returns:
        The first handler in the chain

    Note:
        The chain order matters - specialized handlers should come first.
        StandardChatHandler should always be last as it accepts everything.
    """
    # Standard chat is the fallback (always last)
    standard_handler = StandardChatHandler()

    # CLIENT-SPECIFIC: Import and add AuditCommandHandler for Demo
    # This handler is only available in client branches with audit system
    try:
        from .audit_handler import AuditCommandHandler

        audit_handler = AuditCommandHandler(next_handler=standard_handler)
        logger.info("Audit handler registered in chain (client-specific feature)")
        return audit_handler
    except ImportError:
        # audit_handler.py doesn't exist - this is the open-source version
        logger.info("Running open-source version (no audit handler)")
        return standard_handler
