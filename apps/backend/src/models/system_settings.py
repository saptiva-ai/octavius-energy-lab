"""System-wide configuration models."""

from datetime import datetime
from typing import Literal, Optional

from beanie import Document
from pydantic import Field


class SystemSettings(Document):
    """Singleton document holding global configuration flags."""

    id: str = Field(default="global", alias="_id")
    saptiva_api_key_encrypted: Optional[str] = Field(default=None, repr=False)
    saptiva_key_hint: Optional[str] = None
    saptiva_key_last_validated_at: Optional[datetime] = None
    saptiva_key_last_status: Optional[str] = None
    saptiva_key_source: Literal["unset", "environment", "database"] = "unset"
    saptiva_key_updated_at: Optional[datetime] = None
    saptiva_key_updated_by: Optional[str] = None

    class Settings:
        name = "system_settings"
        indexes = ["saptiva_key_source"]
