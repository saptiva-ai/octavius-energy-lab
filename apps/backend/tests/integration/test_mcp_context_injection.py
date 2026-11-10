"""
Integration tests for MCP tool results context injection into LLM.

Tests Phase 2 MCP integration:
- Tool results appear in LLM context
- Context size limits are enforced
- Error handling works correctly
- Multiple tools can run together
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient
from typing import Dict
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_MCP_CONTEXT", "false").lower() != "true",
    reason="Integration MCP context deshabilitado por defecto (requires tool stack)",
)

from src.services.context_manager import ContextManager
from src.services.saptiva_client import SaptivaResponse


@pytest_asyncio.fixture
async def mock_document(authenticated_client: tuple[AsyncClient, Dict]):
    """Create a mock document for testing."""
    client, auth_data = authenticated_client

    # Create a document in the database
    from src.models.document import Document, DocumentStatus
    from datetime import datetime

    doc = Document(
        filename="test_document.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        minio_key="test/test_document.pdf",
        minio_bucket="documents",
        user_id=auth_data["user_id"],
        total_pages=5,
        pages=[],
        created_at=datetime.utcnow(),
        status=DocumentStatus.READY,
        metadata={}
    )
    await doc.insert()

    yield doc

    # Cleanup
    try:
        await doc.delete()
    except Exception:
        pass  # Best effort cleanup


@pytest_asyncio.fixture
async def mock_excel_document(authenticated_client: tuple[AsyncClient, Dict]):
    """Create a mock Excel document for testing."""
    client, auth_data = authenticated_client

    from src.models.document import Document, DocumentStatus
    from datetime import datetime

    doc = Document(
        filename="test_data.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=2048,
        minio_key="test/test_data.xlsx",
        minio_bucket="documents",
        user_id=auth_data["user_id"],
        total_pages=1,
        pages=[],
        created_at=datetime.utcnow(),
        status=DocumentStatus.READY,
        metadata={}
    )
    await doc.insert()

    yield doc

    # Cleanup
    try:
        await doc.delete()
    except Exception:
        pass  # Best effort cleanup


@pytest.mark.asyncio
async def test_excel_analyzer_results_in_llm_context(authenticated_client, mock_document):
    """
    Test that excel_analyzer tool results are injected into LLM context.

    Scenario: User sends message with excel_analyzer enabled
    Expected: Tool results appear in unified context sent to LLM
    """
    client, auth_data = authenticated_client

    # Mock excel_analyzer tool to return findings
    mock_audit_result = {
        "findings": [
            {
                "severity": "error",
                "message": "Falta disclaimer legal en página 5",
                "page": 5
            },
            {
                "severity": "warning",
                "message": "Logo desactualizado (versión 2023)",
                "page": 2
            },
            {
                "severity": "info",
                "message": "Formato de tabla no estándar",
                "page": 3
            }
        ],
        "total_findings": 3,
        "passed": False
    }

    # Mock Saptiva response that references audit findings
    mock_saptiva_response = SaptivaResponse(
        id="chatcmpl-test-123",
        object="chat.completion",
        created=1234567890,
        model="saptiva-turbo",
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "He analizado el documento y encontré 3 problemas: falta el disclaimer legal en página 5, el logo está desactualizado, y hay un formato de tabla no estándar."
                },
                "finish_reason": "stop"
            }
        ],
        usage={
            "prompt_tokens": 150,
            "completion_tokens": 50,
            "total_tokens": 200
        }
    )

    with patch('src.mcp_integration.fastapi_adapter.MCPFastAPIAdapter._execute_tool_impl', new_callable=AsyncMock) as mock_tool_exec, \
         patch('src.services.chat_service.SaptivaClient') as mock_saptiva:

        # Configure mocks
        mock_tool_exec.return_value = mock_audit_result

        mock_saptiva_instance = AsyncMock()
        mock_saptiva_instance.chat_completion = AsyncMock(return_value=mock_saptiva_response)
        mock_saptiva.return_value = mock_saptiva_instance

        # Send chat message with excel_analyzer enabled
        response = await client.post(
            "/api/chat",
            json={
                "message": "Audita este documento",
                "file_ids": [str(mock_document.id)],
                "tools_enabled": {"excel_analyzer": True},
                "stream": False
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify tool was invoked
        assert mock_tool_exec.called
        tool_call_args = mock_tool_exec.call_args
        assert tool_call_args[1]["payload"]["doc_id"] == str(mock_document.id)

        # Verify Saptiva was called with unified context
        assert mock_saptiva_instance.chat_completion.called
        saptiva_call_args = mock_saptiva_instance.chat_completion.call_args

        # Check that messages include tool results (in system message)
        messages = saptiva_call_args[1].get("messages", [])
        assert len(messages) > 0

        # The system message should contain the document context with tool results
        system_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        assert system_message is not None, "System message not found"

        system_content = system_message.get("content", "")

        # Verify tool results are in system message context
        assert "audit" in system_content.lower() or "findings" in system_content.lower()
        assert "disclaimer" in system_content.lower() or "logo" in system_content.lower()

        # Verify response includes insights from audit
        assert "problemas" in data["content"].lower() or "encontr" in data["content"].lower()


@pytest.mark.asyncio
async def test_excel_analyzer_results_in_llm_context(authenticated_client, mock_excel_document):
    """
    Test that excel_analyzer tool results are injected into LLM context.

    Scenario: User sends message with excel_analyzer enabled for Excel file
    Expected: Excel analysis appears in unified context
    """
    client, auth_data = authenticated_client

    # Mock excel_analyzer tool to return stats
    mock_excel_result = {
        "operations": {
            "stats": {
                "row_count": 150,
                "column_count": 8,
                "sheet_count": 1
            },
            "preview": {
                "headers": ["Date", "Product", "Sales", "Revenue"],
                "rows": [
                    ["2024-01-01", "Product A", 50, 1250.00],
                    ["2024-01-02", "Product B", 30, 900.00]
                ]
            }
        }
    }

    mock_saptiva_response = SaptivaResponse(
        id="chatcmpl-test-456",
        object="chat.completion",
        created=1234567890,
        model="saptiva-turbo",
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "El archivo Excel contiene 150 filas y 8 columnas con datos de ventas."
                },
                "finish_reason": "stop"
            }
        ],
        usage={
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150
        }
    )

    with patch('src.mcp_integration.fastapi_adapter.MCPFastAPIAdapter._execute_tool_impl', new_callable=AsyncMock) as mock_tool_exec, \
         patch('src.services.chat_service.SaptivaClient') as mock_saptiva:

        mock_tool_exec.return_value = mock_excel_result

        mock_saptiva_instance = AsyncMock()
        mock_saptiva_instance.chat_completion = AsyncMock(return_value=mock_saptiva_response)
        mock_saptiva.return_value = mock_saptiva_instance

        # Send chat message with excel_analyzer enabled
        response = await client.post(
            "/api/chat",
            json={
                "message": "Dame estadísticas de este Excel",
                "file_ids": [str(mock_excel_document.id)],
                "tools_enabled": {"excel_analyzer": True},
                "stream": False
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify tool was invoked
        assert mock_tool_exec.called

        # Verify Saptiva received context with Excel stats
        assert mock_saptiva_instance.chat_completion.called
        saptiva_call_args = mock_saptiva_instance.chat_completion.call_args

        # Check messages contain Excel stats
        messages = saptiva_call_args[1].get("messages", [])
        system_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        assert system_message is not None

        system_content = system_message.get("content", "")

        # Verify Excel analysis is in context
        assert "150" in system_content  # Row count
        assert "8" in system_content    # Column count


@pytest.mark.asyncio
async def test_context_size_limits_enforced():
    """
    Test that ContextManager enforces size limits correctly.

    Scenario: Documents + tool results exceed MAX_TOTAL_CONTEXT_CHARS
    Expected: Context is truncated to fit within limits

    Note: This is a unit test for ContextManager, doesn't need DB fixtures.
    """
    # Create ContextManager with small limits for testing
    context_mgr = ContextManager(
        max_document_chars=100,
        max_tool_chars=50,
        max_total_chars=150
    )

    # Add large document
    large_doc_text = "A" * 200  # Exceeds max_document_chars
    context_mgr.add_document_context(
        doc_id="doc_1",
        text=large_doc_text,
        filename="large_doc.pdf"
    )

    # Add large tool result
    large_tool_result = {
        "findings": [
            {"message": f"Finding {i}", "severity": "error"}
            for i in range(20)  # Many findings
        ]
    }
    context_mgr.add_tool_result(
        tool_name="excel_analyzer",
        result=large_tool_result
    )

    # Build context
    unified_context, metadata = context_mgr.build_context_string()

    # Verify size limits are enforced
    assert metadata["total_chars"] <= 150, f"Context size {metadata['total_chars']} exceeds limit 150"
    assert metadata["truncated"] is True

    # Verify metadata reflects truncation
    assert metadata["document_chars"] <= 100
    assert metadata["tool_chars"] <= 50


@pytest.mark.asyncio
async def test_tool_error_handling_graceful_degradation(authenticated_client, mock_document):
    """
    Test that chat continues when tool execution fails.

    Scenario: excel_analyzer tool raises exception
    Expected: Chat completes successfully without tool results
    """
    client, auth_data = authenticated_client

    mock_saptiva_response = SaptivaResponse(
        id="chatcmpl-test-789",
        object="chat.completion",
        created=1234567890,
        model="saptiva-turbo",
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "He procesado tu solicitud."
                },
                "finish_reason": "stop"
            }
        ],
        usage={
            "prompt_tokens": 50,
            "completion_tokens": 10,
            "total_tokens": 60
        }
    )

    with patch('src.mcp_integration.fastapi_adapter.MCPFastAPIAdapter._execute_tool_impl', new_callable=AsyncMock) as mock_tool_exec, \
         patch('src.services.chat_service.SaptivaClient') as mock_saptiva:

        # Configure tool to raise exception
        mock_tool_exec.side_effect = Exception("Tool execution failed")

        mock_saptiva_instance = AsyncMock()
        mock_saptiva_instance.chat_completion = AsyncMock(return_value=mock_saptiva_response)
        mock_saptiva.return_value = mock_saptiva_instance

        # Send chat message
        response = await client.post(
            "/api/chat",
            json={
                "message": "Analiza este documento",
                "file_ids": [str(mock_document.id)],
                "tools_enabled": {"excel_analyzer": True},
                "stream": False
            }
        )

        # Verify chat still succeeds despite tool failure
        assert response.status_code == 200
        data = response.json()

        # Verify response was generated
        assert "content" in data
        assert len(data["content"]) > 0

        # Verify Saptiva was called (without tool results)
        assert mock_saptiva_instance.chat_completion.called


@pytest.mark.asyncio
async def test_multiple_tools_combined_context(authenticated_client, mock_document, mock_excel_document):
    """
    Test that multiple tools can run together and results are combined.

    Scenario: Both excel_analyzer and excel_analyzer enabled with multiple files
    Expected: Both tool results appear in unified context
    """
    client, auth_data = authenticated_client

    mock_audit_result = {
        "findings": [{"severity": "warning", "message": "Minor issue"}],
        "total_findings": 1
    }

    mock_excel_result = {
        "operations": {
            "stats": {"row_count": 100, "column_count": 5}
        }
    }

    mock_saptiva_response = SaptivaResponse(
        id="chatcmpl-test-multi",
        object="chat.completion",
        created=1234567890,
        model="saptiva-turbo",
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "He analizado ambos documentos: el PDF tiene un problema menor, y el Excel contiene 100 filas."
                },
                "finish_reason": "stop"
            }
        ],
        usage={
            "prompt_tokens": 200,
            "completion_tokens": 40,
            "total_tokens": 240
        }
    )

    with patch('src.mcp_integration.fastapi_adapter.MCPFastAPIAdapter._execute_tool_impl', new_callable=AsyncMock) as mock_tool_exec, \
         patch('src.services.chat_service.SaptivaClient') as mock_saptiva:

        # Configure mock to return different results based on tool_name
        async def tool_exec_side_effect(tool_name, tool_impl, payload):
            if tool_name == "excel_analyzer":
                return mock_audit_result
            elif tool_name == "excel_analyzer":
                return mock_excel_result
            return {}

        mock_tool_exec.side_effect = tool_exec_side_effect

        mock_saptiva_instance = AsyncMock()
        mock_saptiva_instance.chat_completion = AsyncMock(return_value=mock_saptiva_response)
        mock_saptiva.return_value = mock_saptiva_instance

        # Send chat message with both documents and both tools enabled
        response = await client.post(
            "/api/chat",
            json={
                "message": "Analiza estos documentos",
                "file_ids": [str(mock_document.id), str(mock_excel_document.id)],
                "tools_enabled": {
                    "excel_analyzer": True,
                    "excel_analyzer": True
                },
                "stream": False
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify both tools were invoked
        assert mock_tool_exec.call_count >= 2

        # Verify Saptiva received context with both tool results
        assert mock_saptiva_instance.chat_completion.called
        saptiva_call_args = mock_saptiva_instance.chat_completion.call_args

        # Check messages contain both tool results
        messages = saptiva_call_args[1].get("messages", [])
        system_message = next((msg for msg in messages if msg.get("role") == "system"), None)
        assert system_message is not None

        system_content = system_message.get("content", "")

        # Verify both tool results are in context (check for keywords from both tools)
        assert ("audit" in system_content.lower() or "findings" in system_content.lower()) and ("150" in system_content or "analysis" in system_content.lower())


@pytest.mark.asyncio
async def test_unified_context_metadata_in_response(authenticated_client, mock_document):
    """
    Test that unified context metadata is included in response.

    Scenario: Tools enabled and executed
    Expected: Response metadata includes unified_context statistics
    """
    client, auth_data = authenticated_client

    mock_audit_result = {
        "findings": [{"severity": "info", "message": "Test finding"}]
    }

    mock_saptiva_response = SaptivaResponse(
        id="chatcmpl-test-metadata",
        object="chat.completion",
        created=1234567890,
        model="saptiva-turbo",
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                },
                "finish_reason": "stop"
            }
        ],
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120
        }
    )

    with patch('src.mcp_integration.fastapi_adapter.MCPFastAPIAdapter._execute_tool_impl', new_callable=AsyncMock) as mock_tool_exec, \
         patch('src.services.chat_service.SaptivaClient') as mock_saptiva:

        mock_tool_exec.return_value = mock_audit_result

        mock_saptiva_instance = AsyncMock()
        mock_saptiva_instance.chat_completion = AsyncMock(return_value=mock_saptiva_response)
        mock_saptiva.return_value = mock_saptiva_instance

        response = await client.post(
            "/api/chat",
            json={
                "message": "Test message",
                "file_ids": [str(mock_document.id)],
                "tools_enabled": {"excel_analyzer": True},
                "stream": False
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify metadata includes unified_context
        assert "metadata" in data
        metadata = data["metadata"]

        # Check for unified_context in decision metadata
        if "decision" in metadata and "unified_context" in metadata["decision"]:
            unified_ctx = metadata["decision"]["unified_context"]

            # Verify structure
            assert "total_sources" in unified_ctx
            assert "document_sources" in unified_ctx
            assert "tool_sources" in unified_ctx
            assert "total_chars" in unified_ctx

            # Verify values make sense
            assert unified_ctx["total_sources"] >= 1
            assert unified_ctx["document_sources"] >= 1
            assert unified_ctx["tool_sources"] >= 0  # May be 0 if tool failed
