"""
gRPC server module for File Manager plugin.

Provides high-performance file operations via gRPC (HTTP/2).
Port: 50052
"""

from .server import create_grpc_server, start_grpc_server, stop_grpc_server

__all__ = [
    "create_grpc_server",
    "start_grpc_server",
    "stop_grpc_server",
]
