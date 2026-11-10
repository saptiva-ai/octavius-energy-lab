"""
gRPC server setup and lifecycle management.

Provides async gRPC server for embedding operations.
Port: 50053
"""

import asyncio
from concurrent import futures
from typing import Optional

import grpc
import structlog
from grpc_reflection.v1alpha import reflection

from ..config import get_settings
from .servicer import EmbeddingServicer

# Import generated protobuf modules
try:
    from .generated import embedding_service_pb2, embedding_service_pb2_grpc

    GRPC_GENERATED = True
except ImportError:
    GRPC_GENERATED = False
    embedding_service_pb2 = None
    embedding_service_pb2_grpc = None

logger = structlog.get_logger(__name__)
settings = get_settings()

# Global server instance
_grpc_server: Optional[grpc.aio.Server] = None


def create_grpc_server(
    max_workers: int = 10,
    max_send_message_length: int = 50 * 1024 * 1024,  # 50MB (embeddings are smaller)
    max_receive_message_length: int = 50 * 1024 * 1024,
) -> grpc.aio.Server:
    """
    Create and configure gRPC server.

    Args:
        max_workers: Maximum thread pool workers
        max_send_message_length: Max message size for sending
        max_receive_message_length: Max message size for receiving

    Returns:
        Configured gRPC server (not started)
    """
    if not GRPC_GENERATED:
        raise RuntimeError(
            "gRPC generated modules not available. "
            "Run: python -m grpc_tools.protoc -I./proto "
            "--python_out=./src/grpc/generated "
            "--grpc_python_out=./src/grpc/generated "
            "./proto/embedding_service.proto"
        )

    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.max_send_message_length", max_send_message_length),
            ("grpc.max_receive_message_length", max_receive_message_length),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.http2.min_time_between_pings_ms", 10000),
        ],
    )

    # Create servicer and register
    servicer = EmbeddingServicer()
    embedding_service_pb2_grpc.add_EmbeddingServiceServicer_to_server(servicer, server)

    # Enable reflection for debugging (grpcurl, grpc_cli)
    service_names = (
        embedding_service_pb2.DESCRIPTOR.services_by_name["EmbeddingService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    logger.info(
        "gRPC server created",
        max_workers=max_workers,
        max_message_size_mb=max_send_message_length // (1024 * 1024),
        reflection_enabled=True,
    )

    return server


async def start_grpc_server(
    server: Optional[grpc.aio.Server] = None,
    port: int = 50053,
) -> grpc.aio.Server:
    """
    Start gRPC server.

    Args:
        server: Optional pre-created server (creates new if None)
        port: Port to listen on (default: 50053)

    Returns:
        Started gRPC server
    """
    global _grpc_server

    if server is None:
        server = create_grpc_server()

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    await server.start()
    _grpc_server = server

    logger.info(
        "gRPC server started",
        address=listen_addr,
        port=port,
    )

    return server


async def stop_grpc_server(
    server: Optional[grpc.aio.Server] = None,
    grace_period: float = 5.0,
) -> None:
    """
    Stop gRPC server gracefully.

    Args:
        server: Server to stop (uses global if None)
        grace_period: Seconds to wait for graceful shutdown
    """
    global _grpc_server

    if server is None:
        server = _grpc_server

    if server is None:
        logger.warning("No gRPC server to stop")
        return

    logger.info("Stopping gRPC server", grace_period=grace_period)

    await server.stop(grace_period)
    _grpc_server = None

    logger.info("gRPC server stopped")


async def serve_forever() -> None:
    """
    Start server and wait for termination.

    This is a blocking call - use for standalone gRPC server.
    """
    server = await start_grpc_server()
    await server.wait_for_termination()


def get_grpc_server() -> Optional[grpc.aio.Server]:
    """Get the current gRPC server instance."""
    return _grpc_server


# CLI entrypoint for standalone gRPC server
if __name__ == "__main__":
    import sys

    structlog.configure(
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    asyncio.run(serve_forever())
