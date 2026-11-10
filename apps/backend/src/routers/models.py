"""
API endpoints for retrieving available models.
"""

from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings

router = APIRouter()


@router.get("/models", tags=["models"])
async def get_models(settings: Settings = Depends(get_settings)):
    """
    Get the list of available models.
    """
    allowed_models_list = [
        model.strip()
        for model in settings.chat_allowed_models.split(",")
        if model.strip()
    ]
    return {
        "default_model": settings.chat_default_model,
        "allowed_models": allowed_models_list,
    }
