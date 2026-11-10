"""Generic MCP client for consuming external domain plugins.

Anti-Corruption Layer: UN cliente para TODOS los plugins de dominio (retail-advisor,
auditor, ...), en vez de módulos httpx/JSON-RPC bespoke por plugin
(cf. `services/audit_mcp_client.py`). Habla el transporte MCP nativo (streamable
HTTP) vía `fastmcp.Client`, así que casa con plugins que exponen `mcp.http_app()`.

Beneficios de diseño:
- Discovery (`list_tools`) → el LLM elige la tool; el backend queda agnóstico (regla #1).
- Unwrapping del resultado FastMCP en UN solo lugar (no repetido por plugin).
- Manejo de errores/timeout uniforme.

Ejemplo:
    client = get_retail_advisor_client()
    tools = await client.list_tools()                 # discovery
    data = await client.call_tool("retail_analytics",  # invocación genérica
                                  {"metric_or_query": "venta por hora"})
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from fastmcp import Client

from .errors import RemoteMcpError  # noqa: F401 — re-export para compatibilidad

logger = structlog.get_logger(__name__)

DEFAULT_RETAIL_ADVISOR_URL = "http://retail-advisor:8002/mcp/mcp"


@dataclass(frozen=True)
class McpToolSpec:
    """Descriptor de una tool descubierta en un plugin (para el LLM / registry)."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        """Formato tool-calling que el LLM puede consumir directamente."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


class RemoteMcpClient:
    """Cliente reutilizable sobre el endpoint MCP de UN plugin de dominio.

    Args:
        url: endpoint MCP completo (incl. path), p.ej.
             ``http://retail-advisor:8002/mcp/mcp``.
        name: nombre lógico del plugin (para logs).
        timeout: timeout por llamada, en segundos.
    """

    def __init__(
        self, url: str, name: str = "domain-plugin", timeout: float = 30.0
    ) -> None:
        self._url = url
        self._name = name
        self._timeout = timeout

    def _client(self) -> Client:
        # Un Client nuevo por operación: sesión corta, sin estado compartido.
        return Client(self._url, timeout=self._timeout)

    async def list_tools(self) -> list[McpToolSpec]:
        """Descubre las tools del plugin (para ofrecerlas al LLM / poblar el registry)."""
        try:
            async with self._client() as client:
                tools = await client.list_tools()
        except Exception as exc:  # noqa: BLE001 — se re-lanza tipado
            logger.warning(
                "mcp.list_tools_failed",
                plugin=self._name,
                url=self._url,
                error=str(exc),
            )
            raise RemoteMcpError(f"list_tools failed for {self._name}: {exc}") from exc

        specs: list[McpToolSpec] = []
        for tool in tools:
            schema = getattr(tool, "inputSchema", None) or getattr(
                tool, "input_schema", None
            )
            specs.append(
                McpToolSpec(
                    name=tool.name,
                    description=getattr(tool, "description", "") or "",
                    input_schema=schema or {},
                )
            )
        return specs

    async def call_tool(
        self, name: str, arguments: Optional[dict[str, Any]] = None
    ) -> Any:
        """Invoca una tool y devuelve su resultado estructurado (unwrap único aquí)."""
        try:
            async with self._client() as client:
                result = await client.call_tool(name, arguments or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mcp.call_tool_failed", plugin=self._name, tool=name, error=str(exc)
            )
            raise RemoteMcpError(
                f"call_tool '{name}' failed for {self._name}: {exc}"
            ) from exc

        # Unwrap del resultado FastMCP en un solo lugar (no por-plugin como el bespoke).
        data = getattr(result, "structured_content", None)
        if data is None:
            data = getattr(result, "data", None)
        return data

    async def health(self) -> bool:
        """Readiness best-effort: ¿podemos descubrir tools?"""
        with contextlib.suppress(Exception):
            await self.list_tools()
            return True
        return False


def _timeout_retail_advisor() -> float:
    """Timeout por llamada al plugin, en segundos (`RETAIL_ADVISOR_TIMEOUT_S`).

    90 s por default y no los 30 genéricos: las tools predictivas del plugin
    consultan Postgres y además narran con un LLM, así que tardan más que una
    tool de lectura. Con 30 s se cortaban a media ejecución y el chat recibía
    un resultado de error (medido en vivo 2026-07-23: la misma consulta
    completó en ~80 s).
    """
    try:
        return float(os.getenv("RETAIL_ADVISOR_TIMEOUT_S", "") or 90.0)
    except ValueError:
        return 90.0


def get_retail_advisor_client(url: Optional[str] = None) -> RemoteMcpClient:
    """Factory del cliente del retail-advisor.

    Resuelve la URL de: arg → env RETAIL_ADVISOR_URL → default. (El app puede pasar
    ``settings.retail_advisor_url`` explícito.)
    """
    resolved = url or os.getenv("RETAIL_ADVISOR_URL", DEFAULT_RETAIL_ADVISOR_URL)
    return RemoteMcpClient(
        url=resolved, name="retail-advisor", timeout=_timeout_retail_advisor()
    )
