"""
Streaming Services Package.

Extracted services from streaming_handler.py for better testability and maintainability.

Generic, domain-agnostic chat streaming building blocks:

    - AuditorResultFormatterService: Format document audit validation results
    - DocumentContextBuilder: RAG document retrieval and context building
    - MessagePersistenceService: Build metadata and persist assistant messages
    - TokenBudgetManager: Token estimation, dynamic max_tokens, message truncation
    - ResponsePostProcessor: Empty response handling and output sanitization
    - ChunkEmitter: Uniform text chunking for SSE streaming
    - SaptivaStreamer: LLM interaction abstraction with normalized response handling
    - AuditResponseBuilder: Document audit validation response building
    - ChatStreamProducer: LLM streaming producer with backpressure support
    - FileIngestionService: Document ingestion with anti-hallucination wait
    - AuditDocumentResolver: Document resolution and materialization for audit
    - SystemPromptBuilder: System prompt resolution and enhancement
    - StreamResponseFinalizer: Post-streaming finalization and persistence
    - StreamingErrorLogger: Centralized error logging for streaming handlers
"""

from .audit_document_resolver import (
    AuditDocumentResolver,
    ResolutionError,
    ResolvedDocument,
)
from .audit_response_builder import AuditResponseBuilder, AuditResult, AuditSummary
from .auditor_formatter import (
    AUDITOR_DISPLAY_NAMES,
    AUDITOR_HUMANIZE_NAMES,
    AUDITOR_ORDER,
    SEVERITY_DISPLAY,
    AuditorResultFormatterService,
)
from .chat_stream_producer import (
    ChatStreamProducer,
    ProducerConfig,
    ProducerContext,
    ProducerResult,
)
from .chunk_emitter import ChunkEmitter
from .document_context import DocumentContextBuilder
from .error_logger import ErrorContext, StreamingErrorLogger
from .file_ingestion_service import FileIngestionService
from .message_persistence import MessagePersistenceService
from .response_postprocessor import PostProcessResult, ResponsePostProcessor
from .saptiva_streamer import CompletionResult, SaptivaStreamer, StreamerConfig
from .stream_response_finalizer import (
    FinalizerContext,
    FinalizerResult,
    StreamResponseFinalizer,
)
from .system_prompt_builder import PromptBuildResult, SystemPromptBuilder
from .token_budget import TokenBudgetManager, TokenBudgetResult

__all__ = [
    "AuditorResultFormatterService",
    "AUDITOR_ORDER",
    "AUDITOR_DISPLAY_NAMES",
    "AUDITOR_HUMANIZE_NAMES",
    "SEVERITY_DISPLAY",
    "DocumentContextBuilder",
    "MessagePersistenceService",
    "TokenBudgetManager",
    "TokenBudgetResult",
    "ResponsePostProcessor",
    "PostProcessResult",
    "ChunkEmitter",
    "SaptivaStreamer",
    "StreamerConfig",
    "CompletionResult",
    "AuditResponseBuilder",
    "AuditResult",
    "AuditSummary",
    "ChatStreamProducer",
    "ProducerConfig",
    "ProducerContext",
    "ProducerResult",
    "FileIngestionService",
    "AuditDocumentResolver",
    "ResolvedDocument",
    "ResolutionError",
    "SystemPromptBuilder",
    "PromptBuildResult",
    "StreamResponseFinalizer",
    "FinalizerContext",
    "FinalizerResult",
    "StreamingErrorLogger",
    "ErrorContext",
]
