"""
Unit tests for audit_mcp_client.py.

Tests:
- audit_document_via_mcp function
- check_mcp_auditor_health function
- list_policies_via_mcp function
- get_policy_details_via_mcp function
- MCPAuditorUnavailableError exception handling
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from contextlib import asynccontextmanager
import httpx

from src.services.audit_mcp_client import (
    audit_document_via_mcp,
    check_mcp_auditor_health,
    list_policies_via_mcp,
    get_policy_details_via_mcp,
    MCPAuditorUnavailableError,
)


# ============================================================================
# HELPER FOR MOCKING ASYNC HTTP CLIENT
# ============================================================================

def create_mock_async_client(post_response=None, get_response=None, post_side_effect=None, get_side_effect=None):
    """Create a mock async HTTP client context manager.

    This helper creates a properly configured mock for `async with httpx.AsyncClient() as client:`
    pattern, setting up both the context manager protocol and method returns/side_effects.
    """
    mock_client = MagicMock()

    if post_side_effect:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    elif post_response:
        mock_client.post = AsyncMock(return_value=post_response)
    else:
        mock_client.post = AsyncMock()

    if get_side_effect:
        mock_client.get = AsyncMock(side_effect=get_side_effect)
    elif get_response:
        mock_client.get = AsyncMock(return_value=get_response)
    else:
        mock_client.get = AsyncMock()

    @asynccontextmanager
    async def mock_context_manager(*args, **kwargs):
        yield mock_client

    return mock_context_manager, mock_client


# ============================================================================
# AUDIT_DOCUMENT_VIA_MCP TESTS
# ============================================================================

class TestAuditDocumentViaMcp:
    """Tests for audit_document_via_mcp function."""

    @pytest.mark.asyncio
    async def test_raises_when_disabled(self):
        """Should raise MCPAuditorUnavailableError when service is disabled."""
        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', False):
            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await audit_document_via_mcp(file_path="/tmp/test.pdf")

            assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_successful_audit(self):
        """Should return audit result on successful MCP call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "audit-call",
            "result": {
                "job_id": "job-123",
                "total_findings": 5,
                "findings": [
                    {"severity": "warning", "message": "Missing disclaimer"}
                ],
                "summary": "5 findings detected"
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await audit_document_via_mcp(
                file_path="/tmp/test.pdf",
                policy_id="demo-std",
                client_name="BancoMuestra"
            )

            assert result["job_id"] == "job-123"
            assert result["total_findings"] == 5
            assert len(result["findings"]) == 1

    @pytest.mark.asyncio
    async def test_successful_audit_with_nested_content(self):
        """Should unwrap FastMCP nested content structure."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "audit-call",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"job_id": "job-456", "total_findings": 3}'
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await audit_document_via_mcp(file_path="/tmp/test.pdf")

            assert result["job_id"] == "job-456"
            assert result["total_findings"] == 3

    @pytest.mark.asyncio
    async def test_handles_jsonrpc_error(self):
        """Should raise MCPAuditorUnavailableError on JSON-RPC error."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "audit-call",
            "error": {
                "code": -32600,
                "message": "Invalid policy ID"
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await audit_document_via_mcp(file_path="/tmp/test.pdf")

            assert "Invalid policy ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        """Should raise MCPAuditorUnavailableError on HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        http_error = httpx.HTTPStatusError(
            "Server Error",
            request=Mock(),
            response=mock_response
        )

        mock_context, mock_client = create_mock_async_client(post_side_effect=http_error)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await audit_document_via_mcp(file_path="/tmp/test.pdf")

            assert "HTTP 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Should raise MCPAuditorUnavailableError on connection error."""
        mock_context, mock_client = create_mock_async_client(
            post_side_effect=httpx.RequestError("Connection refused")
        )

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await audit_document_via_mcp(file_path="/tmp/test.pdf")

            assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_passes_auditor_flags(self):
        """Should pass all auditor enable flags to MCP call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "audit-call",
            "result": {"job_id": "job-789"}
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            await audit_document_via_mcp(
                file_path="/tmp/test.pdf",
                enable_disclaimer=False,
                enable_logo=False,
                enable_grammar=True,
            )

            # Verify the call arguments
            call_args = mock_client.post.call_args
            json_body = call_args.kwargs.get("json") or call_args[1].get("json")

            arguments = json_body["params"]["arguments"]
            assert arguments["enable_disclaimer"] is False
            assert arguments["enable_logo"] is False
            assert arguments["enable_grammar"] is True


# ============================================================================
# CHECK_MCP_AUDITOR_HEALTH TESTS
# ============================================================================

class TestCheckMcpAuditorHealth:
    """Tests for check_mcp_auditor_health function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_healthy(self):
        """Should return True when health endpoint returns 200."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_context, mock_client = create_mock_async_client(get_response=mock_response)

        with patch('httpx.AsyncClient', mock_context):
            result = await check_mcp_auditor_health()

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_unhealthy(self):
        """Should return False when health endpoint returns non-200."""
        mock_response = Mock()
        mock_response.status_code = 503

        mock_context, mock_client = create_mock_async_client(get_response=mock_response)

        with patch('httpx.AsyncClient', mock_context):
            result = await check_mcp_auditor_health()

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        """Should return False when connection fails."""
        mock_context, mock_client = create_mock_async_client(
            get_side_effect=httpx.RequestError("Connection refused")
        )

        with patch('httpx.AsyncClient', mock_context):
            result = await check_mcp_auditor_health()

            assert result is False


# ============================================================================
# LIST_POLICIES_VIA_MCP TESTS
# ============================================================================

class TestListPoliciesViaMcp:
    """Tests for list_policies_via_mcp function."""

    @pytest.mark.asyncio
    async def test_raises_when_disabled(self):
        """Should raise MCPAuditorUnavailableError when service is disabled."""
        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', False):
            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await list_policies_via_mcp()

            assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_returns_policies_list(self):
        """Should return list of policies on success."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "list-policies",
            "result": [
                {"id": "demo-std", "name": "Standard Demo"},
                {"id": "demo-ext", "name": "Extended Demo"}
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await list_policies_via_mcp()

            assert len(result) == 2
            assert result[0]["id"] == "demo-std"
            assert result[1]["id"] == "demo-ext"

    @pytest.mark.asyncio
    async def test_unwraps_nested_content(self):
        """Should unwrap FastMCP nested content structure."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "list-policies",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '[{"id": "policy-1"}, {"id": "policy-2"}]'
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await list_policies_via_mcp()

            assert len(result) == 2
            assert result[0]["id"] == "policy-1"

    @pytest.mark.asyncio
    async def test_handles_jsonrpc_error(self):
        """Should raise MCPAuditorUnavailableError on JSON-RPC error."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "list-policies",
            "error": {"code": -32600, "message": "Service unavailable"}
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await list_policies_via_mcp()

            assert "Service unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Should raise MCPAuditorUnavailableError on connection error."""
        mock_context, mock_client = create_mock_async_client(
            post_side_effect=httpx.RequestError("Connection refused")
        )

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await list_policies_via_mcp()

            assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_non_list_result(self):
        """Should return empty list when result is not a list."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "list-policies",
            "result": {"unexpected": "format"}
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await list_policies_via_mcp()

            assert result == []


# ============================================================================
# GET_POLICY_DETAILS_VIA_MCP TESTS
# ============================================================================

class TestGetPolicyDetailsViaMcp:
    """Tests for get_policy_details_via_mcp function."""

    @pytest.mark.asyncio
    async def test_raises_when_disabled(self):
        """Should raise MCPAuditorUnavailableError when service is disabled."""
        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', False):
            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await get_policy_details_via_mcp(policy_id="demo-std")

            assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_returns_policy_details(self):
        """Should return policy details on success."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "get-policy",
            "result": {
                "id": "demo-std",
                "name": "Standard Demo",
                "auditors": {
                    "disclaimer": True,
                    "logo": True,
                    "typography": True
                }
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await get_policy_details_via_mcp(policy_id="demo-std")

            assert result["id"] == "demo-std"
            assert result["name"] == "Standard Demo"
            assert result["auditors"]["disclaimer"] is True

    @pytest.mark.asyncio
    async def test_unwraps_nested_content(self):
        """Should unwrap FastMCP nested content structure."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "get-policy",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"id": "demo-ext", "auditors": {"logo": false}}'
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            result = await get_policy_details_via_mcp(policy_id="demo-ext")

            assert result["id"] == "demo-ext"
            assert result["auditors"]["logo"] is False

    @pytest.mark.asyncio
    async def test_handles_jsonrpc_error(self):
        """Should raise MCPAuditorUnavailableError on JSON-RPC error."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "get-policy",
            "error": {"code": -32602, "message": "Policy not found"}
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await get_policy_details_via_mcp(policy_id="invalid")

            assert "Policy not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Should raise MCPAuditorUnavailableError on connection error."""
        mock_context, mock_client = create_mock_async_client(
            post_side_effect=httpx.RequestError("Connection refused")
        )

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            with pytest.raises(MCPAuditorUnavailableError) as exc_info:
                await get_policy_details_via_mcp(policy_id="demo-std")

            assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_passes_policy_id_in_arguments(self):
        """Should pass policy_id in MCP call arguments."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "get-policy",
            "result": {"id": "test-policy"}
        }
        mock_response.raise_for_status = Mock()

        mock_context, mock_client = create_mock_async_client(post_response=mock_response)

        with patch('src.services.audit_mcp_client.USE_MCP_AUDITOR', True), \
             patch('httpx.AsyncClient', mock_context):

            await get_policy_details_via_mcp(policy_id="test-policy-id")

            # Verify the call arguments
            call_args = mock_client.post.call_args
            json_body = call_args.kwargs.get("json") or call_args[1].get("json")

            assert json_body["params"]["arguments"]["policy_id"] == "test-policy-id"


# ============================================================================
# MCP AUDITOR UNAVAILABLE ERROR TESTS
# ============================================================================

class TestMCPAuditorUnavailableError:
    """Tests for MCPAuditorUnavailableError exception."""

    def test_inherits_from_exception(self):
        """Should inherit from Exception."""
        error = MCPAuditorUnavailableError("Test error")
        assert isinstance(error, Exception)

    def test_stores_message(self):
        """Should store error message."""
        error = MCPAuditorUnavailableError("Service is down")
        assert str(error) == "Service is down"

    def test_can_be_caught(self):
        """Should be catchable in try/except."""
        with pytest.raises(MCPAuditorUnavailableError):
            raise MCPAuditorUnavailableError("Test")


# ============================================================================
# CONFIGURATION TESTS
# ============================================================================

class TestConfiguration:
    """Tests for module configuration."""

    def test_default_url(self):
        """Should have default URL configured."""
        with patch.dict('os.environ', {}, clear=True):
            # Re-import to get default
            import importlib
            import src.services.audit_mcp_client as module
            importlib.reload(module)

            # Default should be file-auditor:8002
            assert "file-auditor" in module.MCP_AUDITOR_URL or "8002" in module.MCP_AUDITOR_URL

    def test_custom_url_from_env(self):
        """Should use URL from environment variable."""
        with patch.dict('os.environ', {'AUDITOR_URL': 'http://custom:9000'}):
            import importlib
            import src.services.audit_mcp_client as module
            importlib.reload(module)

            assert module.MCP_AUDITOR_URL == 'http://custom:9000'

    def test_default_timeout(self):
        """Should have default timeout of 120 seconds."""
        with patch.dict('os.environ', {}, clear=True):
            import importlib
            import src.services.audit_mcp_client as module
            importlib.reload(module)

            assert module.MCP_TIMEOUT == 120

    def test_use_mcp_auditor_defaults_true(self):
        """Should default to enabled."""
        with patch.dict('os.environ', {}, clear=True):
            import importlib
            import src.services.audit_mcp_client as module
            importlib.reload(module)

            assert module.USE_MCP_AUDITOR is True
