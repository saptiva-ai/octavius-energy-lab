"""Generated gRPC modules.

Generate with:
    python -m grpc_tools.protoc -I./proto \
        --python_out=./src/grpc/generated \
        --grpc_python_out=./src/grpc/generated \
        ./proto/embedding_service.proto
"""

import importlib.util
import os
from pathlib import Path

embedding_service_pb2 = None
embedding_service_pb2_grpc = None
__all__ = []

# Strategy 1: Try relative imports (works when package is properly loaded)
try:
    from . import embedding_service_pb2 as _pb2
    from . import embedding_service_pb2_grpc as _grpc

    embedding_service_pb2 = _pb2
    embedding_service_pb2_grpc = _grpc
    __all__ = ["embedding_service_pb2", "embedding_service_pb2_grpc"]
except ImportError:
    pass

# Strategy 2: If relative import failed, try absolute path loading
if embedding_service_pb2 is None:
    try:
        _generated_dir = Path(__file__).parent
        _pb2_path = _generated_dir / "embedding_service_pb2.py"
        _grpc_path = _generated_dir / "embedding_service_pb2_grpc.py"

        if _pb2_path.exists() and _grpc_path.exists():
            # Load pb2 first (grpc depends on it)
            _spec_pb2 = importlib.util.spec_from_file_location(
                "embedding_service_pb2", _pb2_path
            )
            _module_pb2 = importlib.util.module_from_spec(_spec_pb2)
            _spec_pb2.loader.exec_module(_module_pb2)
            embedding_service_pb2 = _module_pb2

            # Load pb2_grpc
            _spec_grpc = importlib.util.spec_from_file_location(
                "embedding_service_pb2_grpc", _grpc_path
            )
            _module_grpc = importlib.util.module_from_spec(_spec_grpc)
            # pb2_grpc imports pb2, so make sure it can find it
            import sys
            sys.modules["embedding_service_pb2"] = _module_pb2
            _spec_grpc.loader.exec_module(_module_grpc)
            embedding_service_pb2_grpc = _module_grpc

            __all__ = ["embedding_service_pb2", "embedding_service_pb2_grpc"]
    except Exception:
        # If all strategies fail, leave as None
        pass
