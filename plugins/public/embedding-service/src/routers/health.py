"""Health check router."""

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..services.embedding import get_embedding_service

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    model: str
    model_loaded: bool
    embedding_dim: int | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns service status and model information.
    """
    service = get_embedding_service()

    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        model=settings.model_name,
        model_loaded=service._model is not None,
        embedding_dim=service._embedding_dim,
    )
