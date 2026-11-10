"""Domain-plugin tool provider for the chat flow (retail-advisor).

Descubre las tools del plugin de dominio vía `RemoteMcpClient` y:
- las describe en markdown para el system prompt (awareness del LLM);
- ejecuta `retail_analytics(metric_or_query=<mensaje>)` de forma GENÉRICA: el plugin
  resuelve el dominio (metric, dimensión); el backend NO parsea (regla anti-deuda #1).

Patrón: tool-augmented generation (pre-fetch + narración), no agentic-loop. El
resultado + grounding se inyectan al system prompt para que el LLM narre con
grounding correcto y sin inventar cifras.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import structlog

from .remote_mcp_client import (
    McpToolSpec,
    RemoteMcpClient,
    RemoteMcpError,
    get_retail_advisor_client,
)

logger = structlog.get_logger(__name__)

# Caches por proceso CON TTL. Sin TTL, un tool nuevo del plugin solo aparecía
# reiniciando el backend — y peor: el LLM veía el tool mencionado en el hilo
# pero ausente de la lista y FABRICABA su resultado (visto en vivo 2026-07-21
# con predecir_demanda: "Resultado obtenido: 1,420 unidades" sin ejecutar nada).
_TOOLS_CACHE_TTL_SEGUNDOS = 300.0
_tools_markdown_cache: Optional[str] = None
_tools_specs_cache: Optional[list["McpToolSpec"]] = None
_tools_cache_ts: float = 0.0


def _cache_vigente() -> bool:
    return (
        _tools_specs_cache is not None
        and (time.monotonic() - _tools_cache_ts) < _TOOLS_CACHE_TTL_SEGUNDOS
    )


def invalidate_tools_cache() -> None:
    """Fuerza el re-descubrimiento de tools en la próxima petición (tests/ops)."""
    global _tools_specs_cache, _tools_markdown_cache, _tools_cache_ts
    _tools_specs_cache = None
    _tools_markdown_cache = None
    _tools_cache_ts = 0.0


class DomainToolProvider:
    """Awareness + descubrimiento + ejecución de las tools del plugin de dominio."""

    ANALYTICS_TOOL = "retail_analytics"

    def __init__(self, client: Optional[RemoteMcpClient] = None) -> None:
        self._client = client or get_retail_advisor_client()

    async def discover(self) -> list["McpToolSpec"]:
        """Descubre (y cachea con TTL) las tools del plugin. [] si no responde."""
        global _tools_specs_cache, _tools_markdown_cache, _tools_cache_ts
        if _cache_vigente():
            return _tools_specs_cache  # type: ignore[return-value]
        try:
            specs = await self._client.list_tools()
        except RemoteMcpError:
            # Falla transitoria: conservar el caché viejo si existía (mejor
            # tools stale que sin tools), sin renovar el TTL.
            return _tools_specs_cache or []
        _tools_specs_cache = specs
        _tools_markdown_cache = None  # el markdown deriva de los specs
        _tools_cache_ts = time.monotonic()
        return specs

    async def tool_schemas(self) -> list[dict[str, Any]]:
        """Schemas en formato OpenAI tool-calling (para pasarlos al LLM)."""
        return [spec.to_openai_tool() for spec in await self.discover()]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Ejecuta una tool arbitraria del plugin (usado por function-calling)."""
        return await self._client.call_tool(name, arguments)

    async def tools_markdown(self) -> Optional[str]:
        """Markdown describiendo las tools del plugin (para el system prompt)."""
        # discover() primero: si el TTL venció y los specs cambiaron, anula el
        # markdown derivado (evita prompt y schemas desincronizados).
        specs = await self.discover()
        global _tools_markdown_cache
        if _tools_markdown_cache is not None:
            return _tools_markdown_cache
        if not specs:
            return None
        lines = ["**Herramientas de datos retail disponibles:**"]
        for spec in specs:
            first_line = (spec.description or "").strip().splitlines()
            desc = first_line[0] if first_line else ""
            lines.append(f"* `{spec.name}` — {desc}")
        _tools_markdown_cache = "\n".join(lines)
        return _tools_markdown_cache

    async def fetch_analytics(
        self, message: str, ambito: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        """Ejecuta la tool de analytics con el mensaje crudo (el plugin resuelve el
        dominio). `ambito` es el perfil del usuario (rol, tienda, categorías)."""
        argumentos: dict[str, Any] = {"metric_or_query": message}
        if ambito:
            argumentos["ambito"] = ambito
        try:
            return await self._client.call_tool(self.ANALYTICS_TOOL, argumentos)
        except RemoteMcpError as exc:
            logger.warning("domain_tools.fetch_failed", error=str(exc))
            return None

    @staticmethod
    def format_analytics_block(data: dict[str, Any]) -> str:
        """Bloque markdown con el dato + grounding para inyectar al system prompt."""
        table = data.get("table_data") or []
        block = [
            "## Datos de retail-advisor",
            "Responde SOLO con estos datos; cita la métrica/fuente y NO inventes cifras.",
            f"- métrica: {data.get('metric_name', '?')}",
            f"- chart_type: {data.get('chart_type')}",
            f"- frescura del dato: {data.get('freshness', 'unknown')} "
            "(day_closed = corte de día cerrado, NO intradía; intraday = por hora). "
            "No implica datos más recientes que su corte.",
            f"- datos al corte: {data.get('data_as_of') or 'sin corte (sin datos cargados)'}",
            f"- resumen del plugin: {data.get('response_text', '')}",
            f"- grounding: {json.dumps(data.get('grounding', {}), ensure_ascii=False)}",
        ]
        if table:
            block.append(
                f"- filas ({len(table)}): {json.dumps(table[:20], ensure_ascii=False)}"
            )
        else:
            block.append(
                "- filas: (sin datos cargados aún — no afirmes cifras concretas)"
            )
        return "\n".join(block)
