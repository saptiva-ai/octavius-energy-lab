"""Cliente MCP genérico sobre JSON-RPC 2.0 por HTTP (transporte plano/legacy).

Para plugins que exponen un endpoint JSON-RPC `POST /mcp` (`tools/call`) en vez del
streamable `http_app` (ver `RemoteMcpClient`/fastmcp). Centraliza el envelope JSON-RPC,
el unwrapping del `content` de FastMCP y el manejo de errores — antes DUPLICADOS por
plugin (cf. el viejo `services/audit_mcp_client.py` bespoke). Recomendación A.

Arquitectura: la meta a futuro es UN transporte (streamable) para todos los plugins;
mientras el auditor exponga JSON-RPC plano, este cliente lo consume sin cambiar su wire.
La unificación de transporte es un follow-up (requiere el plugin auditor + verificación).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog

from .errors import RemoteMcpError

logger = structlog.get_logger(__name__)


class JsonRpcMcpClient:
    """Cliente MCP JSON-RPC/HTTP sobre el endpoint de UN plugin (base_url + /mcp)."""

    def __init__(
        self, base_url: str, name: str = "domain-plugin", timeout: float = 120.0
    ) -> None:
        self._base = base_url.rstrip("/")
        self._name = name
        self._timeout = timeout

    @staticmethod
    def _build_call(name: str, arguments: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Envelope JSON-RPC 2.0 para `tools/call`."""
        return {
            "jsonrpc": "2.0",
            "id": f"{name}-call",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }

    @staticmethod
    def _unwrap(rpc_response: dict[str, Any]) -> Any:
        """Desempaqueta el resultado JSON-RPC + `content[0].text` de FastMCP (un solo lugar)."""
        if "error" in rpc_response:
            err = rpc_response["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RemoteMcpError(msg)
        result = rpc_response.get("result", {})
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and "text" in first:
                    return json.loads(first["text"])
        return result

    async def call_tool(
        self, name: str, arguments: Optional[dict[str, Any]] = None
    ) -> Any:
        import httpx  # lazy: el módulo se importa/testea sin httpx

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base}/mcp",
                    json=self._build_call(name, arguments),
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return self._unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            logger.error(
                "jsonrpc_mcp.http_error",
                plugin=self._name,
                status=exc.response.status_code,
            )
            raise RemoteMcpError(
                f"{self._name} HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("jsonrpc_mcp.unreachable", plugin=self._name, error=str(exc))
            raise RemoteMcpError(
                f"{self._name} unreachable at {self._base}: {exc}"
            ) from exc

    async def health(self) -> bool:
        """Readiness best-effort: `GET {base}/health` → 200."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base}/health")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001 — best-effort
            return False
