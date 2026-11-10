#!/bin/bash
# =============================================================================
# Generate gRPC Python stubs from proto files
# =============================================================================
# Usage: ./scripts/generate_proto.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Use venv if available, otherwise system Python
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3.11 &> /dev/null; then
    PYTHON="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

echo "Using Python: $PYTHON"
echo "Generating gRPC stubs from proto/file_manager.proto..."

# Ensure grpcio-tools is installed
$PYTHON -m pip install --quiet grpcio-tools

# Generate Python stubs
$PYTHON -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/grpc/generated \
    --grpc_python_out=./src/grpc/generated \
    --pyi_out=./src/grpc/generated \
    ./proto/file_manager.proto

# Fix imports in generated files (grpc_tools generates absolute imports)
# Convert: import file_manager_pb2 -> from . import file_manager_pb2
sed -i 's/^import file_manager_pb2/from . import file_manager_pb2/' \
    ./src/grpc/generated/file_manager_pb2_grpc.py 2>/dev/null || true

echo "Generated files:"
ls -la ./src/grpc/generated/

echo "Done!"
