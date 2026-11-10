"""
HTTP and gRPC clients for external services and plugins.

This module provides clients to communicate with:
- file-manager: Public plugin for file operations (HTTP + gRPC)
- embedding-service: Public plugin for text embeddings (HTTP + gRPC)
- file-auditor: Private plugin for document auditing

Pattern: Each plugin has both HTTP (REST) and gRPC clients.
- HTTP: For debugging and simple operations
- gRPC: For high-performance operations (embeddings, extraction)
"""

from .embedding_service import EmbeddingServiceClient, get_embedding_client
from .embedding_service_grpc import (
    EmbeddingServiceGrpcClient,
    get_embedding_grpc_client,
)
from .embedding_service_grpc import (
    is_grpc_available as is_embedding_grpc_available,
)
from .file_manager import FileManagerClient, get_file_manager_client

__all__ = [
    # File Manager
    "FileManagerClient",
    "get_file_manager_client",
    # Embedding Service (HTTP)
    "EmbeddingServiceClient",
    "get_embedding_client",
    # Embedding Service (gRPC)
    "EmbeddingServiceGrpcClient",
    "get_embedding_grpc_client",
    "is_embedding_grpc_available",
]
