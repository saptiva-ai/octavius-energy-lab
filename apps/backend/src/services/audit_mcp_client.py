"""MCP Client for Demo Capital Auditor Plugin.

Wrapper delgado sobre `JsonRpcMcpClient` (transporte JSON-RPC plano del auditor).
El envelope JSON-RPC + el unwrapping del `content` de FastMCP viven en el cliente
genérico (`mcp_integration/clients/jsonrpc_client.py`), NO aquí (recomendación A:
un solo cliente, sin lógica bespoke duplicada por plugin).

La audit logic vive en `un plugin privado de auditoría`. Este cliente es la ÚNICA forma
de invocar auditorías de documento desde el Core API. API pública y comportamiento
(wire, tool names, excepciones) preservados 1:1 respecto a la versión bespoke.

Usage:
    from services.audit_mcp_client import audit_document_via_mcp

    result = await audit_document_via_mcp(
        file_path="/tmp/document.pdf", policy_id="demo-std", client_name="BancoMuestra",
    )
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog

from ..mcp_integration.clients.errors import RemoteMcpError
from ..mcp_integration.clients.jsonrpc_client import JsonRpcMcpClient

logger = structlog.get_logger(__name__)

# Configuration
MCP_AUDITOR_URL = os.getenv("AUDITOR_URL", "http://file-auditor:8002")
MCP_TIMEOUT = int(os.getenv("AUDITOR_TIMEOUT", "120"))  # 2 minutes
USE_MCP_AUDITOR = os.getenv("USE_MCP_AUDITOR", "true").lower() == "true"


class MCPAuditorUnavailableError(Exception):
    """Raised when the MCP auditor service is unavailable."""


def _client() -> JsonRpcMcpClient:
    return JsonRpcMcpClient(
        base_url=MCP_AUDITOR_URL, name="file-auditor", timeout=MCP_TIMEOUT
    )


async def _call(tool: str, arguments: Dict[str, Any]) -> Any:
    """Invoca una tool del auditor, traduciendo errores al contrato existente."""
    if not USE_MCP_AUDITOR:
        raise MCPAuditorUnavailableError(
            "MCP auditor is disabled. Set USE_MCP_AUDITOR=true in environment."
        )
    try:
        return await _client().call_tool(tool, arguments)
    except RemoteMcpError as exc:
        logger.error("MCP auditor error", tool=tool, error=str(exc))
        raise MCPAuditorUnavailableError(str(exc)) from exc


async def audit_document_via_mcp(
    file_path: str,
    policy_id: str = "auto",
    client_name: Optional[str] = None,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_typography: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    enable_color_palette: bool = True,
    enable_entity_consistency: bool = True,
    enable_semantic_consistency: bool = True,
) -> Dict[str, Any]:
    """Audit a document via MCP protocol to file-auditor service."""
    logger.info(
        "Invoking MCP auditor",
        url=MCP_AUDITOR_URL,
        file_path=file_path,
        policy_id=policy_id,
    )
    result = await _call(
        "audit_document_full",
        {
            "file_path": file_path,
            "policy_id": policy_id,
            "client_name": client_name,
            "enable_disclaimer": enable_disclaimer,
            "enable_format": enable_format,
            "enable_typography": enable_typography,
            "enable_grammar": enable_grammar,
            "enable_logo": enable_logo,
            "enable_color_palette": enable_color_palette,
            "enable_entity_consistency": enable_entity_consistency,
            "enable_semantic_consistency": enable_semantic_consistency,
        },
    )
    if isinstance(result, dict):
        logger.info(
            "MCP audit completed",
            job_id=result.get("job_id"),
            total_findings=result.get("total_findings"),
        )
    return result


async def check_mcp_auditor_health() -> bool:
    """Check if the MCP auditor service is healthy."""
    return await _client().health()


async def list_policies_via_mcp() -> List[Dict[str, Any]]:
    """List available policies from MCP auditor."""
    result = await _call("list_policies", {})
    return result if isinstance(result, list) else []


async def get_policy_details_via_mcp(policy_id: str) -> Dict[str, Any]:
    """Get detailed configuration for a specific policy."""
    return await _call("get_policy_details", {"policy_id": policy_id})
