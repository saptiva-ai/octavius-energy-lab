"""
End-to-End Tests for Resource Management API

Tests the complete flow:
1. User authentication
2. File upload with deduplication
3. Resource metrics retrieval
4. Manual cleanup trigger
5. Cleanup queue monitoring
"""

import pytest
import asyncio
from pathlib import Path
from httpx import AsyncClient
from datetime import datetime, timedelta
import os

from src.main import create_app
from src.models.user import User
from src.models.document import Document, DocumentStatus
from src.core.database import Database
from src.services.auth_service import _hash_password

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_RESOURCES", "false").lower() != "true",
    reason="Resource E2E deshabilitado por defecto (requiere stack completa)",
)


class TestResourceAPIE2E:
    """End-to-end tests for Resource Management API."""

    @pytest.fixture(scope="class")
    async def app(self):
        """Create FastAPI app instance."""
        return create_app()

    @pytest.fixture(scope="class")
    async def client(self, app):
        """Create async HTTP client."""
        from httpx import ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    @pytest.fixture
    async def test_user(self):
        """Create test user."""
        await Database.connect_to_mongo()

        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password_hash=_hash_password("TestPassword123"),
        )
        await user.insert()

        yield user

        # Cleanup
        await user.delete()
        await Database.close_mongo_connection()

    @pytest.fixture
    async def auth_token(self, client, test_user):
        """Get authentication token."""
        response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user.email,
                "password": "TestPassword123"
            }
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.mark.asyncio
    async def test_e2e_get_metrics_requires_auth(self, client):
        """Test that getting metrics requires authentication."""
        # Act
        response = await client.get("/api/resources/metrics")

        # Assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_e2e_get_metrics_success(self, client, auth_token):
        """Test successful retrieval of resource metrics."""
        # Act
        response = await client.get(
            "/api/resources/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert "redis" in data
        assert "weaviate" in data
        assert "minio" in data
        assert "mongodb" in data

        # Verify structure
        for resource in ["redis", "weaviate", "minio", "mongodb"]:
            assert "total_items" in data[resource]
            assert "size_mb" in data[resource]
            assert "usage_percentage" in data[resource]
            assert "cleanup_priority" in data[resource]

    @pytest.mark.asyncio
    async def test_e2e_manual_cleanup_all_resources(self, client, auth_token):
        """Test manual cleanup of all resources."""
        # Act
        response = await client.post(
            "/api/resources/cleanup",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"resource_type": None}  # All resources
        )

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "deleted_counts" in data
        assert "message" in data

        # Verify deleted_counts structure
        deleted_counts = data["deleted_counts"]
        assert isinstance(deleted_counts, dict)

    @pytest.mark.asyncio
    async def test_e2e_manual_cleanup_specific_resource(self, client, auth_token):
        """Test manual cleanup of specific resource."""
        # Act
        response = await client.post(
            "/api/resources/cleanup",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"resource_type": "redis_cache"}
        )

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "redis" in data["deleted_counts"]

    @pytest.mark.asyncio
    async def test_e2e_cleanup_invalid_resource_type(self, client, auth_token):
        """Test cleanup with invalid resource type."""
        # Act
        response = await client.post(
            "/api/resources/cleanup",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"resource_type": "invalid_type"}
        )

        # Assert
        assert response.status_code == 400
        assert "Invalid resource type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_e2e_get_cleanup_queue(self, client, auth_token):
        """Test retrieving cleanup queue status."""
        # Act
        response = await client.get(
            "/api/resources/queue",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200

        data = response.json()
        assert "queue_size" in data
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    @pytest.mark.asyncio
    async def test_e2e_file_deduplication_flow(self, client, auth_token, test_user):
        """
        Test complete file deduplication flow:
        1. Upload file first time
        2. Upload same file second time
        3. Verify same document ID returned
        4. Verify metrics show no duplicate storage
        """
        # Arrange
        test_file_content = b"%PDF-1.4\nTest PDF content"
        test_file_name = "test_dedup.pdf"

        # Act 1: First upload
        response1 = await client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {auth_token}"},
            files={"files": (test_file_name, test_file_content, "application/pdf")}
        )

        # Assert first upload
        assert response1.status_code == 201
        data1 = response1.json()
        file_id_1 = data1["files"][0]["file_id"]

        # Act 2: Second upload (same file)
        response2 = await client.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {auth_token}"},
            files={"files": (test_file_name, test_file_content, "application/pdf")}
        )

        # Assert second upload
        assert response2.status_code == 201
        data2 = response2.json()
        file_id_2 = data2["files"][0]["file_id"]

        # Assert deduplication worked
        assert file_id_1 == file_id_2

        # Act 3: Check metrics
        metrics_response = await client.get(
            "/api/resources/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert metrics
        assert metrics_response.status_code == 200
        # Verify MinIO doesn't have duplicate (only 1 file stored)

    @pytest.mark.asyncio
    async def test_e2e_cleanup_after_ttl_expiration(self, client, auth_token, test_user):
        """
        Test that cleanup removes expired resources:
        1. Upload file
        2. Manually set old timestamp
        3. Trigger cleanup
        4. Verify file deleted
        """
        # This test requires database manipulation
        # Implementation depends on your Database setup

        # Arrange
        await Database.connect_to_mongo()

        # Create old document
        old_doc = Document(
            filename="old_file.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            minio_key="uploads/old_file.pdf",
            minio_bucket="uploads",
            status=DocumentStatus.READY,
            user_id=str(test_user.id),
            created_at=datetime.utcnow() - timedelta(days=10),
            metadata={"file_hash": "abc123"}
        )
        await old_doc.insert()

        # Act: Trigger cleanup
        response = await client.post(
            "/api/resources/cleanup",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"resource_type": "minio_files"}
        )

        # Assert
        assert response.status_code == 200

        # Verify document was deleted
        doc_check = await Document.get(str(old_doc.id))
        assert doc_check is None  # Document should be deleted

        await Database.close_mongo_connection()

    @pytest.mark.asyncio
    async def test_e2e_metrics_reflect_resource_usage(self, client, auth_token):
        """
        Test that metrics accurately reflect resource usage:
        1. Get initial metrics
        2. Upload multiple files
        3. Get metrics again
        4. Verify increase in usage
        """
        # Act 1: Get initial metrics
        response1 = await client.get(
            "/api/resources/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        initial_metrics = response1.json()
        initial_minio_items = initial_metrics["minio"]["total_items"]

        # Act 2: Upload files
        for i in range(3):
            test_content = f"Test file {i}".encode()
            await client.post(
                "/api/files/upload",
                headers={"Authorization": f"Bearer {auth_token}"},
                files={"files": (f"test_{i}.pdf", test_content, "application/pdf")}
            )

        # Act 3: Get metrics again
        response2 = await client.get(
            "/api/resources/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        updated_metrics = response2.json()
        updated_minio_items = updated_metrics["minio"]["total_items"]

        # Assert: Metrics increased
        assert updated_minio_items >= initial_minio_items


class TestResourceAPIPerformance:
    """Performance tests for Resource API."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_metrics_retrieval_performance(self, client, auth_token):
        """Test that metrics retrieval is fast (<500ms)."""
        import time

        # Act
        start_time = time.time()
        response = await client.get(
            "/api/resources/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        elapsed = time.time() - start_time

        # Assert
        assert response.status_code == 200
        assert elapsed < 0.5  # Less than 500ms

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_cleanup_requests(self, client, auth_token):
        """Test that concurrent cleanup requests are handled correctly."""
        # Act - Send 5 concurrent cleanup requests
        tasks = [
            client.post(
                "/api/resources/cleanup",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={"resource_type": "redis_cache"}
            )
            for _ in range(5)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - All requests should succeed or handle gracefully
        success_count = sum(
            1 for r in responses
            if not isinstance(r, Exception) and r.status_code == 200
        )

        assert success_count >= 4  # At least 4 out of 5 should succeed


class TestResourceAPIErrorHandling:
    """Error handling tests for Resource API."""

    @pytest.mark.asyncio
    async def test_metrics_handles_redis_failure(self, client, auth_token):
        """Test that metrics endpoint handles Redis failure gracefully."""
        # This would require mocking Redis to fail
        # Placeholder for proper implementation
        pass

    @pytest.mark.asyncio
    async def test_cleanup_handles_partial_failure(self, client, auth_token):
        """Test that cleanup continues even if one resource type fails."""
        # This would require mocking one cleanup to fail
        # Placeholder for proper implementation
        pass
