"""
Global exception handlers for the FastAPI application.
"""

import traceback
from typing import Any, Union

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings

logger = structlog.get_logger(__name__)


async def validation_exception_handler(
    request: Request, exc: Union[RequestValidationError, ValidationError]
) -> JSONResponse:
    """Handle validation errors."""
    # Convert errors to JSON serializable format
    errors = []
    for error in exc.errors():
        error_dict = {
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        # Add input if it exists and is JSON serializable
        if "input" in error:
            try:
                import json

                json.dumps(error["input"])
                error_dict["input"] = error["input"]
            except (TypeError, ValueError):
                # Skip non-serializable input
                pass
        errors.append(error_dict)

    logger.warning(
        "Validation error",
        path=request.url.path,
        method=request.method,
        errors=errors,
        client_ip=request.client.host if request.client else None,
    )

    # P0-AUTH-ERRMAP: Problem Details format for validation errors
    response_content = {
        "type": "https://api.saptiva.ai/problems/validation_error",
        "title": "Validation Error",
        "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "detail": "Input validation failed",
        "code": "VALIDATION_ERROR",  # P0-AUTH-ERRMAP: Semantic code
        "errors": errors,
        "instance": request.url.path,
    }

    # P0-AUTH-NOSTORE: Add no-cache headers for auth endpoints
    headers = {}
    if request.url.path.startswith("/api/auth"):
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        headers["Pragma"] = "no-cache"
        headers["Expires"] = "0"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response_content,
        headers=headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle HTTP exceptions."""
    logger.warning(
        "HTTP exception",
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        detail=exc.detail,
        client_ip=request.client.host if request.client else None,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "type": "http_error",
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    settings = get_settings()

    # Log the full traceback for debugging
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
        traceback=traceback.format_exc() if settings.debug else None,
        client_ip=request.client.host if request.client else None,
    )

    # Return sanitized error response
    if settings.debug:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "type": "internal_error",
            },
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "type": "internal_error"},
        )


# Custom exception classes with Problem Details support (RFC 7807)
class APIError(Exception):
    """Base API exception with Problem Details support."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "API_ERROR",
        title: str | None = None,
    ):
        self.detail = detail
        self.status_code = status_code
        self.code = code  # P0-AUTH-ERRMAP: Semantic error code
        self.title = title or detail
        super().__init__(detail)


class DatabaseError(APIError):
    """Database operation error."""

    def __init__(
        self, detail: str = "Database operation failed", code: str = "DATABASE_ERROR"
    ):
        super().__init__(detail, status.HTTP_500_INTERNAL_SERVER_ERROR, code)


class BadRequestError(APIError):
    """Input validation / bad request error."""

    def __init__(self, detail: Any = "Bad request", code: str = "BAD_REQUEST"):
        super().__init__(detail, status.HTTP_400_BAD_REQUEST, code)


class AuthenticationError(APIError):
    """Authentication error."""

    def __init__(
        self, detail: str = "Authentication failed", code: str = "AUTHENTICATION_FAILED"
    ):
        super().__init__(detail, status.HTTP_401_UNAUTHORIZED, code)


class AuthorizationError(APIError):
    """Authorization error."""

    def __init__(
        self,
        detail: str = "Insufficient permissions",
        code: str = "INSUFFICIENT_PERMISSIONS",
    ):
        super().__init__(detail, status.HTTP_403_FORBIDDEN, code)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, detail: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(detail, status.HTTP_404_NOT_FOUND, code)


class ConflictError(APIError):
    """Resource conflict error."""

    def __init__(self, detail: str = "Resource conflict", code: str = "CONFLICT"):
        super().__init__(detail, status.HTTP_409_CONFLICT, code)


# Service-specific exceptions (CODE_QUALITY.md recommendation)
class BackendError(Exception):
    """Base exception for all backend service errors."""

    def __init__(self, message: str, cause: Exception | None = None):
        self.message = message
        self.cause = cause
        super().__init__(message)


class ChatServiceError(BackendError):
    """Chat session/message operation failures."""

    pass


class ToolExecutionError(BackendError):
    """Tool invocation failures (MCP, Excel, etc.)."""

    pass


class DocumentProcessingError(BackendError):
    """Document extraction/OCR/parsing failures."""

    pass


class CacheError(BackendError):
    """Cache operation failures (Redis, etc.)."""

    pass


class ExternalServiceError(BackendError):
    """External service communication failures."""

    pass


class LLMError(ExternalServiceError):
    """LLM API communication failures."""

    pass


class HistoryServiceError(BackendError):
    """History service operation failures (timeline, events)."""

    pass


class BankAnalyticsError(ExternalServiceError):
    """Bank analytics HTTP API failures."""

    pass


class RetrievalError(BackendError):
    """Vector search/retrieval operation failures."""

    pass


async def api_exception_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle custom API exceptions with Problem Details format (RFC 7807)."""
    logger.warning(
        "API exception",
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        code=getattr(exc, "code", "API_ERROR"),
        detail=exc.detail,
        error_type=type(exc).__name__,
        client_ip=request.client.host if request.client else None,
    )

    # P0-AUTH-ERRMAP: Problem Details format with semantic code
    response_content = {
        "type": f"https://api.saptiva.ai/problems/{getattr(exc, 'code', 'API_ERROR').lower()}",
        "title": getattr(exc, "title", exc.detail),
        "status": exc.status_code,
        "detail": exc.detail,
        "code": getattr(exc, "code", "API_ERROR"),  # Semantic error code for frontend
        "instance": request.url.path,
    }

    # P0-AUTH-NOSTORE: Add no-cache headers for auth endpoints
    headers = {}
    if request.url.path.startswith("/api/auth"):
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        headers["Pragma"] = "no-cache"
        headers["Expires"] = "0"

    return JSONResponse(
        status_code=exc.status_code, content=response_content, headers=headers
    )
