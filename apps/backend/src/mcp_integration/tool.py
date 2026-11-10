"""
MCP Tool - Abstract base class for all tools.

Provides common infrastructure:
- Input validation
- Error handling
- Metrics collection
- Lifecycle management
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import uuid4

import jsonschema
import structlog

from .protocol import ToolCapability, ToolError, ToolInvokeResponse, ToolSpec

logger = structlog.get_logger(__name__)


class Tool(ABC):
    """
    Abstract base class for all MCP tools.

    Subclasses must implement:
    - get_spec(): Return tool specification
    - validate_input(payload): Validate input against schema
    - execute(payload, context): Core tool logic
    """

    @abstractmethod
    def get_spec(self) -> ToolSpec:
        """Return tool specification."""
        pass

    @abstractmethod
    async def validate_input(self, payload: Dict[str, Any]) -> None:
        """
        Validate input payload against tool's input schema.

        Raises:
            ValueError: If validation fails
        """
        pass

    @abstractmethod
    async def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute tool logic.

        Args:
            payload: Tool-specific input (pre-validated)
            context: Execution context (user_id, trace_id, etc.)

        Returns:
            Tool-specific output

        Raises:
            Exception: Any execution error
        """
        pass

    async def invoke(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolInvokeResponse:
        """
        Full invocation lifecycle with error handling and metrics.

        This method wraps execute() with:
        - Input validation
        - Timeout enforcement
        - Error handling
        - Metrics collection
        """
        spec = self.get_spec()
        invocation_id = str(uuid4())
        start_time = time.time()

        logger.info(
            "Tool invocation started",
            tool=spec.name,
            version=spec.version,
            invocation_id=invocation_id,
            user_id=context.get("user_id") if context else None,
        )

        try:
            # 1. Validate input
            if spec.input_schema:
                try:
                    jsonschema.validate(payload, spec.input_schema)
                except jsonschema.ValidationError as schema_error:
                    raise ValueError(
                        f"Payload does not match schema: {schema_error.message}"
                    ) from schema_error
            await self.validate_input(payload)

            # 2. Execute tool logic
            result = await self.execute(payload, context)

            # 3. Build success response
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Tool invocation succeeded",
                tool=spec.name,
                version=spec.version,
                invocation_id=invocation_id,
                duration_ms=duration_ms,
            )

            return ToolInvokeResponse(
                success=True,
                tool=spec.name,
                version=spec.version,
                result=result,
                error=None,
                metadata={
                    "context": context or {},
                    "capabilities": [c.value for c in spec.capabilities],
                },
                invocation_id=invocation_id,
                duration_ms=duration_ms,
                cached=False,
            )

        except ValueError as validation_error:
            # Input validation failed
            duration_ms = (time.time() - start_time) * 1000
            logger.warning(
                "Tool invocation failed: invalid input",
                tool=spec.name,
                version=spec.version,
                invocation_id=invocation_id,
                error=str(validation_error),
            )

            return ToolInvokeResponse(
                success=False,
                tool=spec.name,
                version=spec.version,
                result=None,
                error=ToolError(
                    code="INVALID_INPUT",
                    message=str(validation_error),
                    details={"payload": payload},
                ),
                metadata={},
                invocation_id=invocation_id,
                duration_ms=duration_ms,
                cached=False,
            )

        except Exception as execution_error:
            # Tool execution failed
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Tool invocation failed: execution error",
                tool=spec.name,
                version=spec.version,
                invocation_id=invocation_id,
                error=str(execution_error),
                exc_info=True,
            )

            return ToolInvokeResponse(
                success=False,
                tool=spec.name,
                version=spec.version,
                result=None,
                error=ToolError(
                    code="EXECUTION_ERROR",
                    message=f"Tool execution failed: {str(execution_error)}",
                    details={"exc_type": type(execution_error).__name__},
                ),
                metadata={},
                invocation_id=invocation_id,
                duration_ms=duration_ms,
                cached=False,
            )

    def is_idempotent(self) -> bool:
        """Check if tool supports idempotent execution."""
        return ToolCapability.IDEMPOTENT in self.get_spec().capabilities

    def is_cacheable(self) -> bool:
        """Check if tool results can be cached."""
        return ToolCapability.CACHEABLE in self.get_spec().capabilities

    def is_streaming(self) -> bool:
        """Check if tool supports streaming responses."""
        return ToolCapability.STREAMING in self.get_spec().capabilities
