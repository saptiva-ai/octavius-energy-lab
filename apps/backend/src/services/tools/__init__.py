"""
Tool handlers for Copiloto OctaviOS.

Provides executable tool handlers that can be invoked from chat.

Available tools:
- audit_file: Validate document against Copiloto Audit compliance rules

Note: This package shadows the sibling tools.py module. To import utilities
from tools.py, use: `from src.services import tools as tools_module`
"""

# NOTE: audit_file_tool moved to un plugin privado de auditoría (Plugin-First Architecture)
# from .audit_file_tool import execute_audit_file_tool

# Re-export helpers from sibling tools.py module.
# This package shadows tools.py, so we manually load it to expose its utilities.
import importlib.util
from pathlib import Path

_tools_py_path = Path(__file__).parent.parent / "tools.py"
_spec = importlib.util.spec_from_file_location(
    "src.services.tools_module", _tools_py_path
)
if _spec and _spec.loader:
    _tools_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_tools_module)
    normalize_tools_state = _tools_module.normalize_tools_state
    build_tools_context = _tools_module.build_tools_context
    describe_tools_markdown = _tools_module.describe_tools_markdown
    tool_schemas_json = _tools_module.tool_schemas_json
    DEFAULT_AVAILABLE_TOOLS = _tools_module.DEFAULT_AVAILABLE_TOOLS
else:
    raise ImportError("Could not load tools.py module")

__all__ = [
    # "execute_audit_file_tool",  # Moved to un plugin privado de auditoría
    "normalize_tools_state",
    "build_tools_context",
    "describe_tools_markdown",
    "tool_schemas_json",
    "DEFAULT_AVAILABLE_TOOLS",
]
