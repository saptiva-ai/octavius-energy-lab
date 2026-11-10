"""
Generated gRPC stubs for backend clients.

These files are copied from the respective plugins after proto compilation:
- file-manager: plugins/public/file-manager/src/grpc/generated/
- embedding-service: plugins/public/embedding-service/src/grpc/generated/

To regenerate:
    1. Build the plugin container (generates proto files)
    2. Copy the generated files here

Or manually:
    cd plugins/<plugin-path>
    python -m grpc_tools.protoc -I./proto \
        --python_out=./src/grpc/generated \
        --grpc_python_out=./src/grpc/generated \
        ./proto/<plugin>.proto
"""

# File Manager gRPC
try:
    from . import file_manager_pb2, file_manager_pb2_grpc

    FILE_MANAGER_GRPC_AVAILABLE = True
except ImportError:
    file_manager_pb2 = None
    file_manager_pb2_grpc = None
    FILE_MANAGER_GRPC_AVAILABLE = False

# Embedding Service gRPC
try:
    from . import embedding_service_pb2, embedding_service_pb2_grpc

    EMBEDDING_SERVICE_GRPC_AVAILABLE = True
except ImportError:
    embedding_service_pb2 = None
    embedding_service_pb2_grpc = None
    EMBEDDING_SERVICE_GRPC_AVAILABLE = False

__all__ = [
    # File Manager
    "file_manager_pb2",
    "file_manager_pb2_grpc",
    "FILE_MANAGER_GRPC_AVAILABLE",
    # Embedding Service
    "embedding_service_pb2",
    "embedding_service_pb2_grpc",
    "EMBEDDING_SERVICE_GRPC_AVAILABLE",
]
