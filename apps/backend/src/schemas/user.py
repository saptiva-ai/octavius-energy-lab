"""
User Pydantic schemas
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..core.config import default_chat_model


class UserPreferences(BaseModel):
    """User preferences schema"""

    theme: str = Field(default="auto", description="UI theme preference")
    language: str = Field(default="en", description="Language preference")
    default_model: str = Field(
        default_factory=default_chat_model, description="Default model"
    )
    chat_settings: dict = Field(default_factory=dict, description="Chat settings")


class UserCreate(BaseModel):
    """User creation schema"""

    username: str = Field(
        ...,
        min_length=2,
        max_length=60,
        description="Username - allows Unicode, spaces, periods, hyphens, apostrophes",
        # P0-FIX: Permissive pattern - allows letters (including Unicode), numbers, spaces,
        # periods, hyphens, apostrophes, underscores
        # Supports names like: José O'Connor, María Fernández, jean.dupont
        pattern=r"^[\w\s\.\-']+$",
    )
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=255, description="Password")
    preferences: Optional[UserPreferences] = Field(None, description="User preferences")


class UserUpdate(BaseModel):
    """User update schema"""

    email: Optional[EmailStr] = Field(None, description="Email address")
    preferences: Optional[UserPreferences] = Field(None, description="User preferences")


class AmbitoUsuario(BaseModel):
    """Perfil y ámbito de datos (gerente_tienda | jefe_departamento | compras)."""

    rol: str = Field(..., description="Rol del perfil")
    tienda_id: Optional[str] = Field(None, description="Tienda del gerente o jefe")
    tienda_nombre: Optional[str] = Field(None, description="Nombre corto de la tienda")
    categorias: list[str] = Field(
        default_factory=list, description="Categorías del jefe de departamento"
    )


class User(BaseModel):
    """User schema"""

    id: str = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="Email address")
    is_active: bool = Field(default=True, description="Whether user is active")
    ambito: Optional[AmbitoUsuario] = Field(
        None, description="Perfil y ámbito de datos (None = sin restricción)"
    )
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    preferences: UserPreferences = Field(
        default_factory=UserPreferences, description="User preferences"
    )

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
        }
    )
