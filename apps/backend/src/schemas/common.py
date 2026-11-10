"""
Common Pydantic schemas
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiError(BaseModel):
    """API error schema"""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )
    trace_id: Optional[str] = Field(None, description="Trace ID for debugging")


class ApiMeta(BaseModel):
    """API response metadata"""

    timestamp: datetime = Field(..., description="Response timestamp")
    request_id: str = Field(..., description="Request ID")
    version: str = Field(..., description="API version")


class ApiResponse(BaseModel):
    """Generic API response"""

    success: bool = Field(..., description="Whether the request was successful")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[ApiError] = Field(None, description="Error information")
    meta: Optional[ApiMeta] = Field(None, description="Response metadata")


class Pagination(BaseModel):
    """Pagination information"""

    page: int = Field(..., ge=1, description="Current page number")
    limit: int = Field(..., ge=1, le=100, description="Items per page")
    total: int = Field(..., ge=0, description="Total number of items")
    pages: int = Field(..., ge=0, description="Total number of pages")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated API response"""

    success: bool = Field(..., description="Whether the request was successful")
    data: List[T] = Field(..., description="Response data items")
    pagination: Pagination = Field(..., description="Pagination information")
    error: Optional[ApiError] = Field(None, description="Error information")
    meta: Optional[ApiMeta] = Field(None, description="Response metadata")


class BaseEntity(BaseModel):
    """Base entity with common fields"""

    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class HealthCheck(BaseModel):
    """Health check response"""

    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Check timestamp")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
