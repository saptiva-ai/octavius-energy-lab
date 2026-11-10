"""
Server-driven feature flag endpoints for tool visibility.
"""

from datetime import datetime
from typing import List, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/features", tags=["features"])


@router.get("/tools")
async def get_tool_visibility(settings: Settings = Depends(get_settings)) -> dict:
    """Expose tool visibility flags so the frontend can toggle UI without redeploy."""
    updated_at = (
        settings.tool_flags_updated_at.isoformat()
        if settings.tool_flags_updated_at
        else None
    )

    # Primary flag for the unified files tool. Fallback to legacy flags to ease migration.
    files_enabled = (
        settings.tool_files_enabled
        or settings.tool_add_files_enabled
        or settings.tool_document_review_enabled
    )

    tools: List[dict] = [
        {
            "key": "files",
            "enabled": files_enabled,
            "updated_at": updated_at,
        },
        {
            "key": "retail-advisor",
            "enabled": settings.tool_retail_advisor_enabled,
            "function_calling": settings.retail_advisor_function_calling,
            "updated_at": updated_at,
        },
        # Legacy entries kept for backward compatibility with older clients.
        {
            "key": "add-files",
            "enabled": settings.tool_add_files_enabled
            and not settings.tool_files_enabled,
            "updated_at": updated_at,
        },
        {
            "key": "document-review",
            "enabled": settings.tool_document_review_enabled
            and not settings.tool_files_enabled,
            "updated_at": updated_at,
        },
    ]

    return {
        "rev": int(datetime.utcnow().timestamp()),
        "tools": tools,
    }


@router.get("/suggestions")
async def get_tool_suggestions(settings: Settings = Depends(get_settings)) -> dict:
    """Prompts sugeridos declarados por los plugins de dominio habilitados.

    El backend es agnóstico: solo relaya lo que el plugin declara en su
    catálogo (regla anti-deuda #1). Tolerante: plugin caído → lista vacía,
    el chat no se rompe.
    """
    suggestions: List[dict] = []
    if settings.tool_retail_advisor_enabled:
        # retail_advisor_url apunta al MCP (…/mcp/mcp); las sugerencias viven
        # en el app HTTP del plugin, en la raíz del mismo host.
        base = settings.retail_advisor_url.split("/mcp")[0].rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base}/sugerencias")
                response.raise_for_status()
                suggestions = response.json().get("sugerencias", [])
        except Exception as exc:  # tolerante: sin sugerencias no hay chips, nada más
            logger.warning("features.suggestions_unavailable", error=str(exc))
    return {"suggestions": suggestions}


@router.get("/views")
async def get_tool_views(
    perfil: Optional[str] = None, settings: Settings = Depends(get_settings)
) -> dict:
    """Vistas predefinidas del chat (resúmenes de un clic) declaradas por el
    plugin de dominio, por perfil. Mismo relevo agnóstico que las sugerencias:
    el backend no conoce el dominio y tolera el plugin caído."""
    views: List[dict] = []
    if settings.tool_retail_advisor_enabled:
        base = settings.retail_advisor_url.split("/mcp")[0].rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(
                    f"{base}/vistas", params={"perfil": perfil} if perfil else None
                )
                response.raise_for_status()
                views = response.json().get("vistas", [])
        except Exception as exc:  # tolerante: sin vistas el modal queda vacío
            logger.warning("features.views_unavailable", error=str(exc))
    return {"views": views}


@router.get("/guide")
async def get_tool_guide(settings: Settings = Depends(get_settings)) -> dict:
    """Guía rápida del modal de ayuda (qué puede responder, de qué meses y
    categorías, y qué no tiene) declarada por el plugin de dominio con sus
    datos (QA, P2.2, 2026-10-21). Mismo relevo agnóstico que las
    vistas; plugin caído → guía vacía y la web no la muestra."""
    guide: dict = {"puedes": [], "no_tiene": []}
    if settings.tool_retail_advisor_enabled:
        base = settings.retail_advisor_url.split("/mcp")[0].rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base}/ayuda")
                response.raise_for_status()
                guide = response.json().get("guia") or guide
        except Exception as exc:  # tolerante: sin guía el modal sigue sirviendo
            logger.warning("features.guide_unavailable", error=str(exc))
    return {"guide": guide}
