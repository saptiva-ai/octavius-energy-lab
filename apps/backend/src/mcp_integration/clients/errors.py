"""Errores compartidos por los clientes MCP (streamable y JSON-RPC)."""

from __future__ import annotations


class RemoteMcpError(Exception):
    """Raised when a remote MCP plugin call fails (connection or protocol)."""
