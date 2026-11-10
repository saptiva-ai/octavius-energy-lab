"""gRPC server module for Embedding Service."""

try:
    from .server import start_grpc_server, stop_grpc_server, create_grpc_server

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    start_grpc_server = None
    stop_grpc_server = None
    create_grpc_server = None

__all__ = [
    "GRPC_AVAILABLE",
    "start_grpc_server",
    "stop_grpc_server",
    "create_grpc_server",
]
