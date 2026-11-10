import os
import pytest

# Skip MCP tests unless explicitly enabled to avoid loading the MCP stack in environments where it is disabled
if os.getenv("RUN_MCP_TESTS", "false").lower() != "true":
    pytest.skip(
        "Pruebas MCP deshabilitadas (define RUN_MCP_TESTS=true para habilitarlas).",
        allow_module_level=True,
    )
