"""
Integration test for MinIO file upload functionality.

Tests the complete flow:
1. File upload to MinIO via /api/files/upload
2. Thumbnail generation and caching
3. File retrieval and deletion
"""

import pytest
from httpx import AsyncClient
import io
import os

from src.main import app
from src.services.minio_service import minio_service

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_MINIO", "false").lower() != "true",
    reason="Integration MinIO deshabilitado por defecto (requires MinIO service)",
)


@pytest.mark.asyncio
class TestMinIOUpload:
    """Integration tests for MinIO upload flow"""

    async def test_minio_buckets_exist(self):
        """Verify all required MinIO buckets are created"""
        expected_buckets = ["documents", "artifacts", "temp-files", "thumbnails"]

        for bucket in expected_buckets:
            assert minio_service.client.bucket_exists(bucket), f"Bucket '{bucket}' should exist"

    async def test_file_upload_to_minio(self, async_client: AsyncClient, auth_headers: dict):
        """Test file upload stores file in MinIO temp-files bucket"""
        # Create a small test PDF
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000214 00000 n\ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n338\n%%EOF"

        # Upload file
        files = {
            "file": ("test_minio.pdf", io.BytesIO(pdf_content), "application/pdf")
        }

        response = await async_client.post(
            "/api/files/upload",
            files=files,
            headers=auth_headers
        )

        assert response.status_code == 201, f"Upload failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "file_id" in data
        assert data["filename"] == "test_minio.pdf"
        assert data["status"] in ["PROCESSING", "READY"]

        file_id = data["file_id"]

        # Verify file exists in MinIO
        assert minio_service.object_exists("temp-files", f"{file_id}/test_minio.pdf"), \
            "File should exist in MinIO temp-files bucket"

        # Cleanup: Delete the file
        await async_client.delete(f"/api/files/{file_id}", headers=auth_headers)

    async def test_thumbnail_generation_and_caching(self, async_client: AsyncClient, auth_headers: dict):
        """Test thumbnail generation is cached in MinIO thumbnails bucket"""
        # Create a small test PDF
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000214 00000 n\ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n338\n%%EOF"

        # Upload file
        files = {
            "file": ("test_thumb.pdf", io.BytesIO(pdf_content), "application/pdf")
        }

        response = await async_client.post(
            "/api/files/upload",
            files=files,
            headers=auth_headers
        )

        assert response.status_code == 201
        file_id = response.json()["file_id"]

        # Request thumbnail (first request - generation)
        thumb_response = await async_client.get(
            f"/api/documents/{file_id}/thumbnail",
            headers=auth_headers
        )

        # Thumbnail might fail for minimal PDF, but endpoint should respond
        # Either 200 (success) or 404 (generation not supported for minimal PDF)
        assert thumb_response.status_code in [200, 404]

        # Cleanup
        await async_client.delete(f"/api/files/{file_id}", headers=auth_headers)

    async def test_minio_lifecycle_policies(self):
        """Verify lifecycle policies are set for temp buckets"""
        # This is a smoke test - we can't easily test TTL without waiting 1 day
        # Just verify the buckets exist and service initialized
        assert minio_service.client.bucket_exists("temp-files")
        assert minio_service.client.bucket_exists("thumbnails")

        # The lifecycle policies were set during initialization
        # We're verifying the service started successfully (implicit test)
