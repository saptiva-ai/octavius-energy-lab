"""
Generated gRPC stubs for File Manager.

These files are generated from proto/file_manager.proto.

To regenerate:
    python -m grpc_tools.protoc \
        -I./proto \
        --python_out=./src/grpc/generated \
        --grpc_python_out=./src/grpc/generated \
        --pyi_out=./src/grpc/generated \
        ./proto/file_manager.proto
"""

try:
    from . import file_manager_pb2
    from . import file_manager_pb2_grpc

    __all__ = ["file_manager_pb2", "file_manager_pb2_grpc"]
except ImportError:
    # Proto files not yet generated
    file_manager_pb2 = None
    file_manager_pb2_grpc = None
    __all__ = []
