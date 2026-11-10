"""
Unit tests for core exception handlers and custom exceptions.

Tests exception classes, handlers, and error response formatting.
Updated to match RFC 7807 Problem Details implementation.
"""

import pytest
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    api_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


class TestCustomExceptions:
    """Test suite for custom exception classes."""

    def test_api_error_base_exception(self):
        """Test APIError base exception."""
        error = APIError(detail="Test error", status_code=500, code="TEST_ERROR")
        assert error.detail == "Test error"
        assert error.status_code == 500
        assert error.code == "TEST_ERROR"
        assert str(error) == "Test error"

    def test_database_error(self):
        """Test DatabaseError exception."""
        error = DatabaseError(detail="Database connection failed")
        assert error.detail == "Database connection failed"
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert error.code == "DATABASE_ERROR"

    def test_bad_request_error(self):
        """Test BadRequestError exception."""
        error = BadRequestError(detail="Invalid input")
        assert error.detail == "Invalid input"
        assert error.status_code == status.HTTP_400_BAD_REQUEST
        assert error.code == "BAD_REQUEST"

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError(detail="Invalid credentials")
        assert error.detail == "Invalid credentials"
        assert error.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.code == "AUTHENTICATION_FAILED"

    def test_authorization_error(self):
        """Test AuthorizationError exception."""
        error = AuthorizationError(detail="Access denied")
        assert error.detail == "Access denied"
        assert error.status_code == status.HTTP_403_FORBIDDEN
        assert error.code == "INSUFFICIENT_PERMISSIONS"

    def test_not_found_error(self):
        """Test NotFoundError exception."""
        error = NotFoundError(detail="Resource not found")
        assert error.detail == "Resource not found"
        assert error.status_code == status.HTTP_404_NOT_FOUND
        assert error.code == "NOT_FOUND"

    def test_conflict_error(self):
        """Test ConflictError exception."""
        error = ConflictError(detail="Resource already exists")
        assert error.detail == "Resource already exists"
        assert error.status_code == status.HTTP_409_CONFLICT
        assert error.code == "CONFLICT"


@pytest.mark.asyncio
class TestExceptionHandlers:
    """Test suite for exception handler functions."""

    async def test_api_exception_handler(self):
        """Test API exception handler response format (RFC 7807)."""
        # Create a mock request
        request = Request(scope={
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": []
        })

        # Create an API error
        error = NotFoundError(detail="User not found", code="USER_NOT_FOUND")

        # Call the handler
        response = await api_exception_handler(request, error)

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "application/json" in response.headers.get("content-type", "")

        # Verify RFC 7807 Problem Details format
        import json
        content = json.loads(response.body.decode())
        assert "type" in content
        assert "title" in content
        assert "status" in content
        assert "detail" in content
        assert "code" in content
        assert content["code"] == "USER_NOT_FOUND"

    async def test_http_exception_handler(self):
        """Test HTTP exception handler response format."""
        request = Request(scope={
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": []
        })

        # Create an HTTP exception
        error = StarletteHTTPException(status_code=404, detail="Not found")

        # Call the handler
        response = await http_exception_handler(request, error)

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify response body contains expected fields
        import json
        content = json.loads(response.body.decode())
        assert "detail" in content
        assert content["detail"] == "Not found"

    async def test_general_exception_handler(self):
        """Test general exception handler for unexpected errors."""
        request = Request(scope={
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": []
        })

        # Create a generic exception
        error = ValueError("Unexpected error")

        # Call the handler
        response = await general_exception_handler(request, error)

        # Verify response returns 500 for unexpected errors
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify response body
        import json
        content = json.loads(response.body.decode())
        assert "detail" in content
        assert "type" in content

    async def test_validation_exception_handler(self):
        """Test validation exception handler for Pydantic validation errors."""
        request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/test",
            "query_string": b"",
            "headers": []
        })

        # Create a validation error
        class TestModel(BaseModel):
            name: str = Field(..., min_length=3)
            age: int = Field(..., ge=0)

        try:
            # This should raise a validation error
            TestModel(name="ab", age=-1)
        except ValidationError as ve:
            # Call the handler
            response = await validation_exception_handler(request, ve)

            # Verify response
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

            # Verify RFC 7807 format
            import json
            content = json.loads(response.body.decode())
            assert "type" in content
            assert "title" in content
            assert "status" in content
            assert "code" in content
            assert content["code"] == "VALIDATION_ERROR"


class TestExceptionInheritance:
    """Test exception inheritance and error code propagation."""

    def test_all_custom_exceptions_inherit_from_api_error(self):
        """Verify all custom exceptions inherit from APIError."""
        exceptions = [
            (DatabaseError, "detail", "DATABASE_ERROR"),
            (BadRequestError, "detail", "BAD_REQUEST"),
            (AuthenticationError, "detail", "AUTHENTICATION_FAILED"),
            (AuthorizationError, "detail", "INSUFFICIENT_PERMISSIONS"),
            (NotFoundError, "detail", "NOT_FOUND"),
            (ConflictError, "detail", "CONFLICT"),
        ]

        for exc_class, param_name, expected_code in exceptions:
            error = exc_class(**{param_name: "Test"})
            assert isinstance(error, APIError)
            assert isinstance(error, Exception)
            assert error.code == expected_code

    def test_exception_with_custom_error_code(self):
        """Test that error codes can be customized."""
        error = NotFoundError(
            detail="User not found",
            code="CUSTOM_USER_NOT_FOUND"
        )
        assert error.code == "CUSTOM_USER_NOT_FOUND"
        assert error.detail == "User not found"

    def test_exception_str_representation(self):
        """Test string representation of exceptions."""
        error = BadRequestError(detail="Invalid email format")
        error_str = str(error)
        assert "Invalid email format" in error_str
