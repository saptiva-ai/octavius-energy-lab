"""Settings endpoints for runtime configuration management."""

from fastapi import APIRouter, HTTPException, Request, status

from ..schemas.settings import (
    SaptivaKeyDeleteResponse,
    SaptivaKeyStatus,
    SaptivaKeyUpdateRequest,
    SaptivaKeyUpdateResponse,
)
from ..services.settings_service import (
    clear_saptiva_api_key,
    get_saptiva_key_status,
    update_saptiva_api_key,
    validate_saptiva_api_key,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/saptiva-key", response_model=SaptivaKeyStatus)
async def get_saptiva_key() -> SaptivaKeyStatus:
    """Return the current SAPTIVA key status without exposing sensitive data."""
    status_payload = await get_saptiva_key_status()
    return SaptivaKeyStatus(**status_payload)


@router.post(
    "/saptiva-key",
    response_model=SaptivaKeyUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def set_saptiva_key(
    payload: SaptivaKeyUpdateRequest, request: Request
) -> SaptivaKeyUpdateResponse:
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La API key no puede estar vacía.",
        )

    validation_message = "Validación omitida"
    if payload.validate_key:
        is_valid, validation_message = await validate_saptiva_api_key(api_key)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=validation_message
            )

    user_id = getattr(request.state, "user_id", None)
    await update_saptiva_api_key(api_key, user_id, validation_message)
    status_payload = await get_saptiva_key_status()
    return SaptivaKeyUpdateResponse(**status_payload)


@router.delete(
    "/saptiva-key",
    response_model=SaptivaKeyDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_saptiva_key(request: Request) -> SaptivaKeyDeleteResponse:
    user_id = getattr(request.state, "user_id", None)
    await clear_saptiva_api_key(user_id)
    status_payload = await get_saptiva_key_status()
    return SaptivaKeyDeleteResponse(**status_payload)
