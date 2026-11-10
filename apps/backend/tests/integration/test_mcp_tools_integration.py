"""
Integration tests for MCP tools.

These tests use real MongoDB, Redis, and MinIO connections via Docker Compose
to validate end-to-end behavior of MCP tools:
- deep_research (Aletheia integration)
- extract_document_text (multi-tier extraction)
- excel_analyzer (COPILOTO-AUDIT validation)
- excel_analyzer (Excel data analysis)
- viz_tool (chart generation)

Tests verify:
- Tool registration in FastMCP server
- HTTP endpoint functionality
- Authentication and authorization
- Real service integration
- Caching behavior
- Error handling and logging
"""

import pytest
from datetime import datetime
from fastapi import status
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import io
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_MCP_TOOLS", "false").lower() != "true",
    reason="Integration MCP tools deshabilitado por defecto (requires full stack)",
)

from src.models.document import Document, DocumentStatus
from src.models.research_task import ResearchTask, TaskStatus


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def test_user_with_token(client):
    """Create a test user and return access token."""
    # Register user
    register_data = {
        "username": "mcp_test_user",
        "email": "mcp@test.com",
        "password": "SecurePass123!",
        "full_name": "MCP Test User"
    }

    response = await client.post("/api/auth/register", json=register_data)
    assert response.status_code == status.HTTP_201_CREATED

    # Login to get token
    login_data = {
        "identifier": "mcp_test_user",
        "password": "SecurePass123!"
    }
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    return data["access_token"], data["user"]["id"]


@pytest.fixture
async def test_document_pdf(test_user_with_token):
    """Create a test PDF document in database."""
    access_token, user_id = test_user_with_token

    # Create document directly in database
    doc = Document(
        user_id=user_id,
        filename="test_document.pdf",
        original_filename="test_document.pdf",
        content_type="application/pdf",
        size_bytes=50000,
        minio_key="test/test_document.pdf",
        status=DocumentStatus.READY,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={"pages": 5}
    )
    await doc.save()

    return str(doc.id), access_token, user_id


@pytest.fixture
async def test_document_excel(test_user_with_token):
    """Create a test Excel document in database."""
    access_token, user_id = test_user_with_token

    doc = Document(
        user_id=user_id,
        filename="test_data.xlsx",
        original_filename="test_data.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=25000,
        minio_key="test/test_data.xlsx",
        status=DocumentStatus.READY,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={"sheets": ["Sheet1"]}
    )
    await doc.save()

    return str(doc.id), access_token, user_id


# ============================================================================
# Test MCP Tools Endpoints
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPToolsEndpoints:
    """Test MCP tools HTTP endpoints."""

    async def test_mcp_tools_list_endpoint(self, client: AsyncClient, test_user_with_token):
        """Should list all available MCP tools."""
        access_token, user_id = test_user_with_token

        response = await client.get(
            "/api/mcp/tools",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify response structure (FastMCP adapter returns list directly)
        assert isinstance(data, list)

        # Verify expected tools are present
        tool_names = [tool["name"] for tool in data]
        assert "excel_analyzer" in tool_names
        assert "excel_analyzer" in tool_names
        assert "viz_tool" in tool_names
        assert "deep_research" in tool_names
        assert "extract_document_text" in tool_names

    async def test_mcp_tools_list_unauthorized(self, client: AsyncClient):
        """Should reject request without authentication."""
        response = await client.get("/api/mcp/tools")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Test Deep Research Tool Integration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestDeepResearchToolIntegration:
    """Integration tests for deep_research tool."""

    async def test_deep_research_invoke_creates_task(
        self,
        client: AsyncClient,
        test_user_with_token
    ):
        """Should create research task via MCP endpoint."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "deep_research",
            "payload": {
                "query": "What are the latest trends in AI?",
                "depth": "shallow",
                "max_iterations": 2
            },
            "context": {
                "user_id": user_id
            }
        }

        # Mock create_research_task to avoid actual Aletheia calls
        mock_task = MagicMock()
        mock_task.id = "task_integration_123"
        mock_task.status = TaskStatus.PENDING
        mock_task.created_at = datetime.utcnow()
        mock_task.result = None

        with patch(
            "src.services.deep_research_service.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task
        ):
            response = await client.post(
                "/api/mcp/tools/invoke",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Verify response structure
            assert data["success"] is True
            assert data["tool"] == "deep_research"
            assert data["result"]["task_id"] == "task_integration_123"
            assert data["result"]["status"] == "pending"
            assert data["result"]["query"] == "What are the latest trends in AI?"

    async def test_deep_research_invalid_depth(
        self,
        client: AsyncClient,
        test_user_with_token
    ):
        """Should reject invalid depth parameter."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "deep_research",
            "payload": {
                "query": "Test query",
                "depth": "ultra_deep"  # Invalid
            }
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Tool should return error in response
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_INPUT"
        assert "depth" in data["error"]["message"].lower()

    async def test_deep_research_unauthorized(self, client: AsyncClient):
        """Should reject unauthenticated requests."""
        payload = {
            "tool": "deep_research",
            "payload": {"query": "Test"}
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Test Document Extraction Tool Integration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestDocumentExtractionToolIntegration:
    """Integration tests for extract_document_text tool."""

    async def test_extract_document_text_with_cache(
        self,
        client: AsyncClient,
        test_document_pdf
    ):
        """Should extract text and use cache."""
        doc_id, access_token, user_id = test_document_pdf

        cached_text = "This is cached PDF content for testing."

        # Mock get_document_text to return cached content
        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            payload = {
                "tool": "extract_document_text",
                "payload": {
                    "doc_id": doc_id,
                    "method": "auto",
                    "include_metadata": True
                },
                "context": {
                    "user_id": user_id
                }
            }

            response = await client.post(
                "/api/mcp/tools/invoke",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["success"] is True
            assert data["tool"] == "extract_document_text"
            assert data["result"]["doc_id"] == doc_id
            assert data["result"]["text"] == cached_text
            assert data["result"]["method_used"] == "cache"
            assert data["result"]["metadata"]["cached"] is True
            assert data["result"]["metadata"]["filename"] == "test_document.pdf"

    async def test_extract_document_text_permission_denied(
        self,
        client: AsyncClient,
        test_document_pdf,
        test_user_with_token
    ):
        """Should reject access to other user's documents."""
        doc_id, _, _ = test_document_pdf

        # Create different user
        different_token, different_user_id = test_user_with_token

        payload = {
            "tool": "extract_document_text",
            "payload": {
                "doc_id": doc_id
            },
            "context": {
                "user_id": different_user_id  # Different user
            }
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {different_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return permission error
        assert data["success"] is False
        assert data["error"]["code"] == "EXECUTION_ERROR"
        assert "not authorized" in data["error"]["message"].lower()

    async def test_extract_document_text_not_found(
        self,
        client: AsyncClient,
        test_user_with_token
    ):
        """Should handle document not found."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "extract_document_text",
            "payload": {
                "doc_id": "nonexistent_doc_id"
            },
            "context": {
                "user_id": user_id
            }
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "EXECUTION_ERROR"
        assert "not found" in data["error"]["message"].lower()


# ============================================================================
# Test Audit File Tool Integration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestAuditFileToolIntegration:
    """Integration tests for excel_analyzer tool."""

    async def test_excel_analyzer_invoke(
        self,
        client: AsyncClient,
        test_document_pdf
    ):
        """Should validate PDF document via MCP endpoint."""
        doc_id, access_token, user_id = test_document_pdf

        # Mock validation services
        mock_report = MagicMock()
        mock_report.job_id = "job_123"
        mock_report.status = "done"
        mock_report.findings = []
        mock_report.summary = {
            "total_findings": 0,
            "policy_id": "auto",
            "policy_name": "Auto-detected Policy"
        }
        mock_report.attachments = []

        mock_policy = MagicMock()
        mock_policy.id = "auto"
        mock_policy.name = "Auto Policy"
        mock_policy.client_name = "Test Client"
        mock_policy.to_compliance_config = MagicMock(return_value={})

        with patch(
            "src.services.policy_manager.resolve_policy",
            new_callable=AsyncMock,
            return_value=mock_policy
        ):
            with patch(
                "src.services.validation_coordinator.validate_document",
                new_callable=AsyncMock,
                return_value=mock_report
            ):
                with patch("src.services.minio_storage.get_minio_storage") as mock_storage:
                    mock_storage_instance = MagicMock()
                    mock_storage_instance.materialize_document.return_value = (
                        Path("/tmp/test.pdf"),
                        True
                    )
                    mock_storage.return_value = mock_storage_instance

                    payload = {
                        "tool": "excel_analyzer",
                        "payload": {
                            "doc_id": doc_id,
                            "policy_id": "auto",
                            "enable_disclaimer": True,
                            "enable_format": True,
                            "enable_logo": False
                        },
                        "context": {
                            "user_id": user_id
                        }
                    }

                    response = await client.post(
                        "/api/mcp/tools/invoke",
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )

                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()

                    assert data["success"] is True
                    assert data["tool"] == "excel_analyzer"
                    assert data["result"]["job_id"] == "job_123"
                    assert data["result"]["status"] == "done"
                    assert data["result"]["summary"]["total_findings"] == 0


# ============================================================================
# Test Excel Analyzer Tool Integration
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestExcelAnalyzerToolIntegration:
    """Integration tests for excel_analyzer tool."""

    async def test_excel_analyzer_basic_stats(
        self,
        client: AsyncClient,
        test_document_excel
    ):
        """Should analyze Excel file and return statistics."""
        doc_id, access_token, user_id = test_document_excel

        # Mock pandas DataFrame
        import pandas as pd

        mock_df = pd.DataFrame({
            "Product": ["A", "B", "C"],
            "Revenue": [1000, 2000, 1500],
            "Cost": [500, 800, 600]
        })

        with patch("src.services.minio_storage.get_minio_storage") as mock_storage:
            mock_storage_instance = MagicMock()
            mock_storage_instance.materialize_document.return_value = (
                Path("/tmp/test.xlsx"),
                True
            )
            mock_storage.return_value = mock_storage_instance

            with patch("pandas.read_excel", return_value=mock_df):
                payload = {
                    "tool": "excel_analyzer",
                    "payload": {
                        "doc_id": doc_id,
                        "operations": ["stats", "preview"]
                    },
                    "context": {
                        "user_id": user_id
                    }
                }

                response = await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                assert response.status_code == status.HTTP_200_OK
                data = response.json()

                assert data["success"] is True
                assert data["tool"] == "excel_analyzer"
                assert "stats" in data["result"]
                assert "preview" in data["result"]
                assert data["result"]["stats"]["row_count"] == 3
                assert data["result"]["stats"]["column_count"] == 3

    async def test_excel_analyzer_wrong_file_type(
        self,
        client: AsyncClient,
        test_document_pdf  # PDF instead of Excel
    ):
        """Should reject non-Excel documents."""
        doc_id, access_token, user_id = test_document_pdf

        payload = {
            "tool": "excel_analyzer",
            "payload": {
                "doc_id": doc_id
            },
            "context": {
                "user_id": user_id
            }
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "EXECUTION_ERROR"
        assert "not an Excel file" in data["error"]["message"]


# ============================================================================
# Test MCP Tool Error Handling
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPToolErrorHandling:
    """Test error handling for MCP tools."""

    async def test_tool_not_found(
        self,
        client: AsyncClient,
        test_user_with_token
    ):
        """Should handle tool not found."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "nonexistent_tool",
            "payload": {}
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "TOOL_NOT_FOUND"
        assert "not found" in data["error"]["message"].lower()

    async def test_missing_required_field(
        self,
        client: AsyncClient,
        test_user_with_token
    ):
        """Should handle missing required fields."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "extract_document_text",
            "payload": {}  # Missing doc_id
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_INPUT"
        assert "doc_id" in data["error"]["message"].lower()
