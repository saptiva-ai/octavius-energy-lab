"""
MCP Tool Registry - Central tool management and invocation routing.

Provides:
- Tool registration/unregistration
- Discovery (list, search)
- Invocation routing
- Metrics aggregation
"""

from typing import Dict, List, Optional

import structlog

from .protocol import ToolError, ToolInvokeRequest, ToolInvokeResponse, ToolSpec
from .tool import Tool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """
    Central registry for tool discovery and invocation.

    Manages tool lifecycle:
    - Registration
    - Discovery (list, search)
    - Invocation routing
    - Metrics aggregation
    """

    def __init__(self):
        # Key: tool_name, Value: Dict[version, Tool instance]
        self._tools: Dict[str, Dict[str, Tool]] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance

        Raises:
            ValueError: If tool with same name+version already registered
        """
        spec = tool.get_spec()

        if spec.name not in self._tools:
            self._tools[spec.name] = {}

        if spec.version in self._tools[spec.name]:
            raise ValueError(
                f"Tool '{spec.name}' version '{spec.version}' already registered"
            )

        self._tools[spec.name][spec.version] = tool

        logger.info(
            "Tool registered",
            tool=spec.name,
            version=spec.version,
            category=spec.category.value,
            capabilities=[c.value for c in spec.capabilities],
        )

    def unregister(self, tool_name: str, version: Optional[str] = None) -> None:
        """
        Unregister a tool.

        Args:
            tool_name: Tool name
            version: Optional version (if None, unregister all versions)
        """
        if tool_name not in self._tools:
            return

        if version:
            if version in self._tools[tool_name]:
                del self._tools[tool_name][version]
                logger.info("Tool unregistered", tool=tool_name, version=version)

                if not self._tools[tool_name]:
                    del self._tools[tool_name]
        else:
            # Unregister all versions
            del self._tools[tool_name]
            logger.info("Tool unregistered (all versions)", tool=tool_name)

    def get_tool(self, tool_name: str, version: Optional[str] = None) -> Optional[Tool]:
        """
        Get tool instance by name and version.

        Args:
            tool_name: Tool name
            version: Tool version (if None, returns latest)

        Returns:
            Tool instance or None if not found
        """
        if tool_name not in self._tools:
            return None

        versions = self._tools[tool_name]

        if version:
            return versions.get(version)
        else:
            # Return latest version (assumes semantic versioning)
            latest_version = max(versions.keys())
            return versions[latest_version]

    def list_tools(self, category: Optional[str] = None) -> List[ToolSpec]:
        """
        List all registered tools.

        Args:
            category: Optional category filter

        Returns:
            List of tool specifications
        """
        specs = []
        for tool_versions in self._tools.values():
            for tool in tool_versions.values():
                spec = tool.get_spec()
                if category is None or spec.category.value == category:
                    specs.append(spec)

        return specs

    def search_tools(self, query: str) -> List[ToolSpec]:
        """
        Search tools by name, description, or tags.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching tool specifications
        """
        query_lower = query.lower()
        matches = []

        for tool_versions in self._tools.values():
            for tool in tool_versions.values():
                spec = tool.get_spec()
                if (
                    query_lower in spec.name.lower()
                    or query_lower in spec.description.lower()
                    or any(query_lower in tag.lower() for tag in spec.tags)
                ):
                    matches.append(spec)

        return matches

    async def invoke(self, request: ToolInvokeRequest) -> ToolInvokeResponse:
        """
        Invoke a tool by name.

        Args:
            request: Tool invocation request

        Returns:
            Tool invocation response
        """
        tool = self.get_tool(request.tool, request.version)

        if not tool:
            return ToolInvokeResponse(
                success=False,
                tool=request.tool,
                version=request.version or "unknown",
                result=None,
                error=ToolError(
                    code="TOOL_NOT_FOUND",
                    message=f"Tool '{request.tool}' not found",
                    details={"available_tools": list(self._tools.keys())},
                ),
                metadata={},
                invocation_id="error",
                duration_ms=0.0,
                cached=False,
            )

        # Invoke tool with context
        return await tool.invoke(request.payload, request.context)
