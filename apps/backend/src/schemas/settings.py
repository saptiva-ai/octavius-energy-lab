"""Pydantic schemas for runtime system settings APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SaptivaKeyStatus(BaseModel):
    configured: bool
    mode: Literal["demo", "live"]
    source: Literal["unset", "environment", "database"]
    hint: Optional[str] = None
    status_message: Optional[str] = None
    last_validated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class SaptivaKeyUpdateRequest(BaseModel):
    api_key: str = Field(..., min_length=12, max_length=256, repr=False)
    validate_key: bool = Field(
        default=True, description="Validate the key against SAPTIVA before saving"
    )


class SaptivaKeyUpdateResponse(SaptivaKeyStatus):
    pass


class SaptivaKeyDeleteResponse(SaptivaKeyStatus):
    pass
