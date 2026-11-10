"""Backend-as-MCP-**client**: generic consumption of external domain plugins.

Separado del backend-as-MCP-**server** (`mcp_integration/` raíz, que expone las tools
propias del backend). Este subpaquete es el Anti-Corruption Layer hacia los plugins de
dominio (retail-advisor, auditor, ...): un solo cliente genérico en vez de módulos
httpx/JSON-RPC bespoke por plugin.
"""

from .errors import RemoteMcpError
from .jsonrpc_client import JsonRpcMcpClient
from .remote_mcp_client import (
    McpToolSpec,
    RemoteMcpClient,
    get_retail_advisor_client,
)

__all__ = [
    "RemoteMcpClient",
    "JsonRpcMcpClient",
    "RemoteMcpError",
    "McpToolSpec",
    "get_retail_advisor_client",
]
