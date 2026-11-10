"""
User document model
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import BaseModel, EmailStr, Field
from pymongo import ASCENDING, IndexModel

from ..core.config import default_chat_model


class UserPreferences(BaseModel):
    """User preferences subdocument"""

    theme: str = Field(default="auto", description="UI theme preference")
    language: str = Field(default="en", description="Language preference")
    default_model: str = Field(
        default_factory=default_chat_model, description="Default model"
    )
    chat_settings: dict = Field(default_factory=dict, description="Chat settings")


class AmbitoUsuario(BaseModel):
    """Ámbito de datos del perfil.

    Lo lee el chat y lo inyecta en cada llamada a las tools del plugin de
    dominio; el plugin lo aplica antes de agregar. Sin `rol` no hay restricción
    (comportamiento previo). Roles: gerente_tienda (su tienda),
    jefe_departamento (sus categorías en una tienda), compras (total compañía).
    """

    rol: str = Field(..., description="gerente_tienda | jefe_departamento | compras")
    tienda_id: Optional[str] = Field(None, description="Tienda del gerente o jefe")
    tienda_nombre: Optional[str] = Field(None, description="Nombre corto de la tienda")
    categorias: list[str] = Field(
        default_factory=list,
        description="Ids de categoría del catálogo del plugin (jefe de departamento)",
    )


class User(Document):
    """User document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    is_active: bool = Field(default=True, description="Whether user is active")
    ambito: Optional[AmbitoUsuario] = Field(
        None, description="Perfil y ámbito de datos (None = sin restricción)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    preferences: UserPreferences = Field(
        default_factory=UserPreferences, description="User preferences"
    )

    class Settings:
        name = "users"
        indexes = [
            IndexModel(
                [("username", ASCENDING)], unique=True
            ),  # Unique index on username
            IndexModel([("email", ASCENDING)], unique=True),  # Unique index on email
            "created_at",
            "is_active",
        ]

    def __str__(self) -> str:
        return f"User(username={self.username}, email={self.email})"
