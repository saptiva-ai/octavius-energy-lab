"""
Error response schemas with semantic error codes.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ErrorCode:
    """Standardized error codes for API responses."""

    # Authentication errors
    BAD_CREDENTIALS = "BAD_CREDENTIALS"
    ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
    INVALID_TOKEN = "INVALID_TOKEN"

    # Registration errors
    USER_EXISTS = "USER_EXISTS"
    USERNAME_EXISTS = "USERNAME_EXISTS"
    WEAK_PASSWORD = "WEAK_PASSWORD"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"

    # General errors
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Semantic error code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field that caused the error")
    context: Optional[Dict[str, Any]] = Field(
        None, description="Additional error context"
    )


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: ErrorDetail = Field(..., description="Error details")

    @classmethod
    def create(
        cls,
        code: str,
        message: str,
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        """Create a standardized error response."""
        return cls(
            error=ErrorDetail(code=code, message=message, field=field, context=context)
        )


# Predefined error responses for common scenarios
class AuthErrors:
    """Common authentication error responses."""

    BAD_CREDENTIALS = ErrorResponse.create(
        code=ErrorCode.BAD_CREDENTIALS, message="Correo o contraseña incorrectos."
    )

    ACCOUNT_INACTIVE = ErrorResponse.create(
        code=ErrorCode.ACCOUNT_INACTIVE,
        message="La cuenta está inactiva. Contacta al administrador.",
    )

    INVALID_TOKEN = ErrorResponse.create(
        code=ErrorCode.INVALID_TOKEN, message="El token de sesión ya no es válido."
    )

    USER_NOT_FOUND = ErrorResponse.create(
        code=ErrorCode.USER_NOT_FOUND, message="Usuario no encontrado."
    )


class RegistrationErrors:
    """Common registration error responses."""

    @staticmethod
    def user_exists(field: str = "email") -> ErrorResponse:
        return ErrorResponse.create(
            code=ErrorCode.USER_EXISTS,
            message="Ya existe una cuenta con ese correo.",
            field=field,
        )

    @staticmethod
    def username_exists() -> ErrorResponse:
        return ErrorResponse.create(
            code=ErrorCode.USERNAME_EXISTS,
            message="Ya existe una cuenta con ese usuario.",
            field="username",
        )

    @staticmethod
    def weak_password(details: str) -> ErrorResponse:
        return ErrorResponse.create(
            code=ErrorCode.WEAK_PASSWORD, message=details, field="password"
        )


class ValidationErrors:
    """Common validation error responses."""

    @staticmethod
    def missing_field(field: str) -> ErrorResponse:
        return ErrorResponse.create(
            code=ErrorCode.MISSING_FIELD,
            message=f"El campo {field} es requerido.",
            field=field,
        )

    @staticmethod
    def invalid_format(field: str, expected: str) -> ErrorResponse:
        return ErrorResponse.create(
            code=ErrorCode.INVALID_FORMAT,
            message=f"Formato inválido para {field}. Se esperaba: {expected}",
            field=field,
        )
