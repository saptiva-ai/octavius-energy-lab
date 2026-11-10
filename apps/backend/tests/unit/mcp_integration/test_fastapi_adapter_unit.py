"""
Unit tests for MCPFastAPIAdapter - No infrastructure required.

Tests adapter methods, schema extraction, and helper functions
without requiring FastMCP server or Redis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import Optional, List
import asyncio
import os


# Skip all tests if MCP stack is disabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_STACK", "true").lower() != "true",
    reason="MCP stack disabled via RUN_MCP_STACK=false",
)


@pytest.fixture(autouse=True)
def mock_client():
    """Mock the fastmcp Client to avoid transport validation."""
    with patch("src.mcp_integration.fastapi_adapter.Client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def adapter():
    """Create adapter with mocked dependencies."""
    from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter

    return MCPFastAPIAdapter(
        mcp_server=MagicMock(),
        auth_dependency=MagicMock(),
    )


class TestMCPFastAPIAdapterInit:
    """Test MCPFastAPIAdapter initialization."""

    def test_init_sets_attributes(self):
        """Test adapter initializes with correct attributes."""
        from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter

        mock_server = MagicMock()
        mock_auth = MagicMock()
        mock_callback = MagicMock()

        adapter = MCPFastAPIAdapter(
            mcp_server=mock_server,
            auth_dependency=mock_auth,
            on_invoke=mock_callback,
            async_threshold_ms=10000,
        )

        assert adapter.mcp_server == mock_server
        assert adapter.auth_dependency == mock_auth
        assert adapter.on_invoke == mock_callback
        assert adapter.async_threshold_ms == 10000

    def test_init_defaults(self):
        """Test adapter initializes with defaults."""
        from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter

        mock_server = MagicMock()
        mock_auth = MagicMock()

        adapter = MCPFastAPIAdapter(
            mcp_server=mock_server,
            auth_dependency=mock_auth,
        )

        assert adapter.on_invoke is None
        assert adapter.async_threshold_ms == 5000


class TestExtractInputSchema:
    """Test _extract_input_schema method."""

    def test_simple_types(self, adapter):
        """Test schema extraction with simple types."""

        async def sample_tool(name: str, count: int, active: bool) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert schema["type"] == "object"
        assert "properties" in schema
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["active"]["type"] == "boolean"
        assert "name" in schema["required"]
        assert "count" in schema["required"]
        assert "active" in schema["required"]

    def test_optional_params(self, adapter):
        """Test that params with defaults are not required."""

        async def sample_tool(name: str, count: int = 10) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert "name" in schema["required"]
        assert "count" not in schema["required"]

    def test_skips_ctx_param(self, adapter):
        """Test that ctx parameter is skipped."""

        async def sample_tool(value: str, ctx=None) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert "value" in schema["properties"]
        assert "ctx" not in schema["properties"]

    def test_skips_self_param(self, adapter):
        """Test that self parameter is skipped."""

        class MyClass:
            async def method(self, value: str) -> dict:
                pass

        schema = adapter._extract_input_schema(MyClass().method)

        assert "value" in schema["properties"]
        assert "self" not in schema["properties"]

    def test_list_type(self, adapter):
        """Test list type handling."""

        async def sample_tool(items: list) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)
        assert schema["properties"]["items"]["type"] == "array"

    def test_dict_type(self, adapter):
        """Test dict type handling."""

        async def sample_tool(data: dict) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)
        assert schema["properties"]["data"]["type"] == "object"


class TestExtractOutputSchema:
    """Test _extract_output_schema method."""

    def test_default_output_schema(self, adapter):
        """Test default output schema for untyped function."""

        async def sample_tool(value: str):
            return {"result": value}

        schema = adapter._extract_output_schema(sample_tool)

        assert schema["type"] == "object"

    def test_output_schema_with_return_hint(self, adapter):
        """Test output schema with return type hint."""

        async def sample_tool(value: str) -> dict:
            return {"result": value}

        schema = adapter._extract_output_schema(sample_tool)

        assert schema["type"] == "object"

    def test_output_schema_with_pydantic_model(self, adapter):
        """Test output schema extraction from Pydantic model."""
        from pydantic import BaseModel

        class OutputModel(BaseModel):
            result: str
            count: int

        async def sample_tool(value: str) -> OutputModel:
            return OutputModel(result=value, count=1)

        schema = adapter._extract_output_schema(sample_tool)

        # Pydantic models generate JSON schema
        assert "properties" in schema
        assert "result" in schema["properties"]
        assert "count" in schema["properties"]


class TestPythonTypeToJsonType:
    """Test _python_type_to_json_type method."""

    def test_basic_types(self, adapter):
        """Test basic type mapping."""
        assert adapter._python_type_to_json_type(str) == "string"
        assert adapter._python_type_to_json_type(int) == "integer"
        assert adapter._python_type_to_json_type(float) == "number"
        assert adapter._python_type_to_json_type(bool) == "boolean"
        assert adapter._python_type_to_json_type(list) == "array"
        assert adapter._python_type_to_json_type(dict) == "object"

    def test_generic_list_type(self, adapter):
        """Test generic List type."""
        assert adapter._python_type_to_json_type(List[str]) == "array"

    def test_unknown_type_defaults_to_string(self, adapter):
        """Test unknown type defaults to string."""

        class CustomClass:
            pass

        assert adapter._python_type_to_json_type(CustomClass) == "string"


class TestGenerateExamplePayload:
    """Test _generate_example_payload method."""

    def test_string_field(self, adapter):
        """Test example generation for string field."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["name"] == "example_name"

    def test_integer_field(self, adapter):
        """Test example generation for integer field."""
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["count"] == 1

    def test_number_field(self, adapter):
        """Test example generation for number field."""
        schema = {
            "type": "object",
            "properties": {"price": {"type": "number"}},
            "required": ["price"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["price"] == 1.0

    def test_boolean_field(self, adapter):
        """Test example generation for boolean field."""
        schema = {
            "type": "object",
            "properties": {"active": {"type": "boolean"}},
            "required": ["active"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["active"] is True

    def test_array_field(self, adapter):
        """Test example generation for array field."""
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array"}},
            "required": ["items"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["items"] == []

    def test_object_field(self, adapter):
        """Test example generation for object field."""
        schema = {
            "type": "object",
            "properties": {"data": {"type": "object"}},
            "required": ["data"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["data"] == {}

    def test_email_format(self, adapter):
        """Test example generation for email format."""
        schema = {
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
            "required": ["email"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["email"] == "user@example.com"

    def test_uri_format(self, adapter):
        """Test example generation for URI format."""
        schema = {
            "type": "object",
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["url"] == "https://example.com"

    def test_date_format(self, adapter):
        """Test example generation for date format."""
        schema = {
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date"}},
            "required": ["date"],
        }

        example = adapter._generate_example_payload(schema)
        assert example["date"] == "2025-01-11"


class TestResolveToolDescription:
    """Test _resolve_tool_description method."""

    def test_description_attribute(self, adapter):
        """Test description from attribute."""
        tool_obj = MagicMock()
        tool_obj.description = "Tool description"

        result = adapter._resolve_tool_description(tool_obj, "test_tool")
        assert result == "Tool description"

    def test_fn_docstring(self, adapter):
        """Test description from fn docstring."""
        tool_obj = MagicMock()
        tool_obj.description = None
        tool_obj.fn = MagicMock()
        tool_obj.fn.__doc__ = "Function docstring"

        result = adapter._resolve_tool_description(tool_obj, "test_tool")
        assert result == "Function docstring"

    def test_object_docstring(self, adapter):
        """Test description from object docstring."""
        tool_obj = MagicMock()
        tool_obj.description = None
        tool_obj.fn = None
        tool_obj.__doc__ = "Object docstring"

        result = adapter._resolve_tool_description(tool_obj, "test_tool")
        assert result == "Object docstring"

    def test_fallback_description(self, adapter):
        """Test fallback description."""
        tool_obj = MagicMock()
        tool_obj.description = None
        tool_obj.fn = None
        tool_obj.__doc__ = None

        result = adapter._resolve_tool_description(tool_obj, "my_tool")
        assert result == "Execute my_tool"


class TestResolveToolDisplayName:
    """Test _resolve_tool_display_name method."""

    def test_simple_name(self, adapter):
        """Test simple tool name."""
        result = adapter._resolve_tool_display_name("audit")
        assert result == "Audit"

    def test_underscored_name(self, adapter):
        """Test underscored tool name."""
        result = adapter._resolve_tool_display_name("audit_file")
        assert result == "Audit File"

    def test_multi_word_name(self, adapter):
        """Test multi-word tool name."""
        result = adapter._resolve_tool_display_name("extract_document_text")
        assert result == "Extract Document Text"


class TestCallableAcceptsParam:
    """Test _callable_accepts_param method."""

    def test_param_exists(self, adapter):
        """Test when param exists."""

        def sample_fn(user_id: str, value: str):
            pass

        assert adapter._callable_accepts_param(sample_fn, "user_id") is True
        assert adapter._callable_accepts_param(sample_fn, "value") is True

    def test_param_not_exists(self, adapter):
        """Test when param doesn't exist."""

        def sample_fn(value: str):
            pass

        assert adapter._callable_accepts_param(sample_fn, "user_id") is False

    def test_invalid_callable(self, adapter):
        """Test with invalid callable."""
        assert adapter._callable_accepts_param(None, "user_id") is False
        assert adapter._callable_accepts_param("not a function", "user_id") is False


class TestGetToolMap:
    """Test _get_tool_map method."""

    @pytest.mark.asyncio
    async def test_get_tools_async_api(self, adapter):
        """Test using async get_tools API."""
        expected_tools = {"tool1": MagicMock(), "tool2": MagicMock()}

        adapter.mcp_server.get_tools = AsyncMock(return_value=expected_tools)

        result = await adapter._get_tool_map()

        assert result == expected_tools

    @pytest.mark.asyncio
    async def test_fallback_to_tools_dict(self, adapter):
        """Test fallback to _tools dict."""
        expected_tools = {"tool1": MagicMock()}

        adapter.mcp_server.get_tools = None
        adapter.mcp_server._tools = expected_tools

        result = await adapter._get_tool_map()

        assert result == expected_tools

    @pytest.mark.asyncio
    async def test_empty_when_no_tools(self, adapter):
        """Test returns empty dict when no tools available."""
        adapter.mcp_server.get_tools = None
        adapter.mcp_server._tools = None

        result = await adapter._get_tool_map()

        assert result == {}


class TestGetToolInputSchema:
    """Test _get_tool_input_schema method."""

    def test_uses_parameters_attr(self, adapter):
        """Test uses parameters attribute if available."""
        tool_obj = MagicMock()
        tool_obj.parameters = {"type": "object", "properties": {"x": {"type": "string"}}}

        result = adapter._get_tool_input_schema(tool_obj, MagicMock())

        assert result == tool_obj.parameters

    def test_falls_back_to_extraction(self, adapter):
        """Test falls back to schema extraction."""
        tool_obj = MagicMock()
        tool_obj.parameters = None

        async def fallback_fn(value: str) -> dict:
            pass

        result = adapter._get_tool_input_schema(tool_obj, fallback_fn)

        assert "properties" in result
        assert "value" in result["properties"]


class TestGetToolOutputSchema:
    """Test _get_tool_output_schema method."""

    def test_uses_output_schema_attr(self, adapter):
        """Test uses output_schema attribute if available."""
        tool_obj = MagicMock()
        tool_obj.output_schema = {"type": "object", "properties": {"result": {"type": "string"}}}

        result = adapter._get_tool_output_schema(tool_obj, MagicMock())

        assert result == tool_obj.output_schema

    def test_falls_back_to_extraction(self, adapter):
        """Test falls back to output schema extraction."""
        tool_obj = MagicMock()
        tool_obj.output_schema = None

        async def fallback_fn(value: str) -> dict:
            return {}

        result = adapter._get_tool_output_schema(tool_obj, fallback_fn)

        assert result["type"] == "object"


class TestNormalizeToolResult:
    """Test _normalize_tool_result method."""

    def test_dict_result(self, adapter):
        """Test normalizing dict result."""
        result = {"key": "value"}

        normalized = adapter._normalize_tool_result(result)

        assert normalized == {"key": "value"}

    def test_structured_content(self, adapter):
        """Test normalizing result with structured_content."""
        result = MagicMock()
        result.structured_content = {"data": "test"}
        result.content = None

        normalized = adapter._normalize_tool_result(result)

        assert normalized == {"data": "test"}

    def test_content_attribute(self, adapter):
        """Test normalizing result with content attribute."""
        result = MagicMock()
        result.structured_content = None
        result.content = "text content"

        normalized = adapter._normalize_tool_result(result)

        assert normalized == {"content": "text content"}

    def test_primitive_result(self, adapter):
        """Test normalizing primitive result."""
        result = "simple string"

        normalized = adapter._normalize_tool_result(result)

        assert normalized == "simple string"


class TestExecuteToolImpl:
    """Test _execute_tool_impl method."""

    @pytest.mark.asyncio
    async def test_tool_with_run_method(self, adapter):
        """Test executing tool with run method."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(return_value={"result": "success"})

        result = await adapter._execute_tool_impl(
            "test_tool", tool_impl, {"value": "test"}, context={}
        )

        assert result == {"result": "success"}
        tool_impl.run.assert_called_once_with({"value": "test"})

    @pytest.mark.asyncio
    async def test_callable_tool(self, adapter):
        """Test executing callable tool."""

        async def tool_fn(payload):
            return {"result": payload["value"]}

        result = await adapter._execute_tool_impl(
            "test_tool", tool_fn, {"value": "test"}, context={}
        )

        assert result == {"result": "test"}

    @pytest.mark.asyncio
    async def test_none_tool_raises_error(self, adapter):
        """Test that None tool raises ValueError."""
        with pytest.raises(ValueError, match="Tool 'test_tool' not found"):
            await adapter._execute_tool_impl("test_tool", None, {}, context={})

    @pytest.mark.asyncio
    async def test_non_executable_raises_error(self, adapter):
        """Test that non-executable raises ValueError."""
        tool_impl = "not a callable"

        with pytest.raises(ValueError, match="not executable"):
            await adapter._execute_tool_impl("test_tool", tool_impl, {}, context={})

    @pytest.mark.asyncio
    async def test_tool_exception_propagates(self, adapter):
        """Test that tool exceptions propagate."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(side_effect=RuntimeError("Tool crashed"))

        with pytest.raises(RuntimeError, match="Tool crashed"):
            await adapter._execute_tool_impl("test_tool", tool_impl, {}, context={})


class TestEstimateDuration:
    """Test _estimate_duration method."""

    def test_audit_file_estimate(self, adapter):
        """Test audit_file duration estimate."""
        result = adapter._estimate_duration("audit_file", {})
        assert result == 5000

    def test_excel_analyzer_estimate(self, adapter):
        """Test excel_analyzer duration estimate."""
        result = adapter._estimate_duration("excel_analyzer", {"operations": ["stats", "aggregate"]})
        assert result == 14000  # 10000 + 2 * 2000

    def test_excel_analyzer_no_operations(self, adapter):
        """Test excel_analyzer without operations."""
        result = adapter._estimate_duration("excel_analyzer", {})
        assert result == 10000  # Base only

    def test_viz_tool_estimate(self, adapter):
        """Test viz_tool duration estimate."""
        result = adapter._estimate_duration("viz_tool", {})
        assert result == 3000

    def test_unknown_tool_default(self, adapter):
        """Test unknown tool defaults to 5s."""
        result = adapter._estimate_duration("unknown_tool", {})
        assert result == 5000


class TestCreateRouter:
    """Test create_router method returns valid router."""

    def test_router_has_expected_routes(self):
        """Test router has expected routes."""
        from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter

        mock_server = MagicMock()
        mock_server.get_tools = AsyncMock(return_value={})

        adapter = MCPFastAPIAdapter(
            mcp_server=mock_server,
            auth_dependency=MagicMock(),
        )

        router = adapter.create_router()

        # Get route paths (may have /mcp/ prefix)
        route_paths = [route.path for route in router.routes]

        # Check for expected route patterns (with or without prefix)
        expected_routes = ["tools", "invoke", "health", "discover", "schema", "tasks"]
        for expected in expected_routes:
            assert any(expected in path for path in route_paths), f"Route containing '{expected}' not found"

    def test_router_custom_prefix(self):
        """Test router with custom prefix."""
        from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter

        mock_server = MagicMock()
        mock_server.get_tools = AsyncMock(return_value={})

        adapter = MCPFastAPIAdapter(
            mcp_server=mock_server,
            auth_dependency=MagicMock(),
        )

        router = adapter.create_router(prefix="/api/mcp", tags=["custom-mcp"])

        assert router.prefix == "/api/mcp"
        assert "custom-mcp" in router.tags


class TestExecuteTask:
    """Test _execute_task method for background task execution."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create mock task manager."""
        with patch("src.mcp_integration.fastapi_adapter.task_manager") as mock:
            mock.get_task.return_value = None
            mock.create_task.return_value = "task-123"
            mock.is_cancellation_requested.return_value = False
            yield mock

    @pytest.fixture
    def mock_metrics(self):
        """Create mock metrics collector."""
        with patch("src.mcp_integration.fastapi_adapter.metrics_collector") as mock:
            yield mock

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = "user_123"
        return user

    @pytest.mark.asyncio
    async def test_successful_task_execution(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test successful task execution."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(return_value={"data": "result"})

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {"param": "value"}, mock_user
            )

        mock_task_manager.mark_running.assert_called_once_with("task-123")
        mock_task_manager.mark_completed.assert_called_once()
        mock_metrics.record_task_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_tool_not_found(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task fails when tool not found."""
        with patch.object(adapter, "_get_tool_map", return_value={}):
            await adapter._execute_task(
                "task-123", "missing_tool", {}, mock_user
            )

        mock_task_manager.mark_failed.assert_called_once()
        call_args = mock_task_manager.mark_failed.call_args
        assert call_args[0][1]["code"] == "TOOL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_task_cancellation(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task cancellation during execution."""
        mock_task_manager.is_cancellation_requested.return_value = True

        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(return_value={"data": "result"})

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {}, mock_user
            )

        mock_task_manager.mark_cancelled.assert_called_once_with("task-123")
        mock_metrics.record_task_completed.assert_called_once()
        assert mock_metrics.record_task_completed.call_args[1]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_task_cancelled_error(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task execution raises CancelledError."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(side_effect=asyncio.CancelledError())

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {}, mock_user
            )

        mock_task_manager.mark_cancelled.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_validation_error(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task execution raises ValueError."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(side_effect=ValueError("Invalid input"))

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {}, mock_user
            )

        mock_task_manager.mark_failed.assert_called_once()
        call_args = mock_task_manager.mark_failed.call_args
        assert call_args[0][1]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_task_permission_error(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task execution raises PermissionError."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(side_effect=PermissionError("Access denied"))

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {}, mock_user
            )

        mock_task_manager.mark_failed.assert_called_once()
        call_args = mock_task_manager.mark_failed.call_args
        assert call_args[0][1]["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_task_generic_error(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test task execution raises generic exception."""
        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(side_effect=RuntimeError("Crash"))

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-123", "test_tool", {}, mock_user
            )

        mock_task_manager.mark_failed.assert_called_once()
        call_args = mock_task_manager.mark_failed.call_args
        assert call_args[0][1]["code"] == "EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_task_injects_user_id_when_function_accepts_it(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test user_id is injected into payload when _callable_accepts_param returns True."""
        captured_payload = {}

        async def tool_impl(payload):
            captured_payload.update(payload)
            return {"result": "ok"}

        # Mock _callable_accepts_param to return True for user_id
        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            with patch.object(adapter, "_callable_accepts_param", return_value=True):
                await adapter._execute_task(
                    "task-123", "test_tool", {"param": "value"}, mock_user
                )

        # user_id should have been added to the payload
        assert captured_payload.get("user_id") == "user_123"

    @pytest.mark.asyncio
    async def test_task_skips_user_id_injection_when_already_present(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test user_id is not overwritten if already in payload."""
        captured_payload = {}

        async def tool_impl(payload):
            captured_payload.update(payload)
            return {"result": "ok"}

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            with patch.object(adapter, "_callable_accepts_param", return_value=True):
                await adapter._execute_task(
                    "task-123", "test_tool", {"param": "value", "user_id": "existing_user"}, mock_user
                )

        # Existing user_id should be preserved
        assert captured_payload.get("user_id") == "existing_user"

    @pytest.mark.asyncio
    async def test_task_creates_fallback_task_entry(
        self, adapter, mock_task_manager, mock_metrics, mock_user
    ):
        """Test creates task entry if not existing."""
        mock_task_manager.get_task.return_value = None

        tool_impl = MagicMock()
        tool_impl.run = AsyncMock(return_value={"data": "ok"})

        with patch.object(adapter, "_get_tool_map", return_value={"test_tool": tool_impl}):
            await adapter._execute_task(
                "task-new", "test_tool", {}, mock_user
            )

        mock_task_manager.create_task.assert_called_once()


class TestGenericListType:
    """Test handling of generic types."""

    def test_optional_type_string(self, adapter):
        """Test Optional type handling."""
        from typing import Optional as Opt

        async def sample_tool(name: Opt[str] = None) -> dict:
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert "name" in schema["properties"]
        assert "name" not in schema["required"]


class TestEmptySchema:
    """Test empty schema scenarios."""

    def test_empty_properties_schema(self, adapter):
        """Test generating example for empty schema."""
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        example = adapter._generate_example_payload(schema)
        assert example == {}

    def test_no_required_in_schema(self, adapter):
        """Test schema without required field."""
        schema = {
            "type": "object",
            "properties": {"opt": {"type": "string"}},
        }

        example = adapter._generate_example_payload(schema)
        # Should still populate optional fields
        assert "opt" in example


class TestToolMapEdgeCases:
    """Test edge cases in _get_tool_map."""

    @pytest.mark.asyncio
    async def test_get_tools_returns_non_dict(self, adapter):
        """Test handling when get_tools returns non-dict."""
        adapter.mcp_server.get_tools = AsyncMock(return_value=[])
        adapter.mcp_server._tools = {"fallback": MagicMock()}

        result = await adapter._get_tool_map()

        # Should fallback to _tools
        assert result == {"fallback": MagicMock().__class__} or result == adapter.mcp_server._tools


class TestNormalizeToolResultEdgeCases:
    """Test edge cases in _normalize_tool_result."""

    def test_both_structured_and_content(self, adapter):
        """Test when both structured_content and content are present."""
        result = MagicMock()
        result.structured_content = {"priority": "data"}
        result.content = "fallback"

        normalized = adapter._normalize_tool_result(result)

        # structured_content takes priority
        assert normalized == {"priority": "data"}

    def test_list_result(self, adapter):
        """Test list result normalization."""
        result = [1, 2, 3]

        normalized = adapter._normalize_tool_result(result)

        assert normalized == [1, 2, 3]

    def test_nested_dict_result(self, adapter):
        """Test nested dict result."""
        result = {"outer": {"inner": "value"}}

        normalized = adapter._normalize_tool_result(result)

        assert normalized == {"outer": {"inner": "value"}}
