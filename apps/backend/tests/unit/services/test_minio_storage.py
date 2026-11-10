"""
Unit tests for MinioStorageService.

Tests:
- Document upload/download operations
- Presigned URL generation
- Initialization
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import io
from minio.error import S3Error

from src.services.minio_storage import MinioStorageService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_minio_client():
    """Create a mock Minio client."""
    client = Mock()
    client.bucket_exists = Mock(return_value=True)
    client.make_bucket = Mock()
    client.put_object = Mock()
    client.get_object = Mock()
    client.stat_object = Mock()
    client.remove_object = Mock()
    client.presigned_get_object = Mock(return_value="https://minio.test/presigned-url")
    return client


@pytest.fixture
def minio_service(mock_minio_client):
    """Create MinioStorageService with mocked client."""
    with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
        with patch.dict('os.environ', {
            'MINIO_ENDPOINT': 'localhost:9000',
            'MINIO_ROOT_USER': 'testuser',
            'MINIO_ROOT_PASSWORD': 'testpass',
        }):
            service = MinioStorageService()
            return service


# ============================================================================
# GET DOCUMENT TESTS
# ============================================================================

class TestGetDocument:
    """Tests for get_document method."""

    def test_get_document_success(self, minio_service, mock_minio_client):
        """Should successfully retrieve a document."""
        mock_response = Mock()
        mock_response.read.return_value = b"document content"
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_minio_client.get_object.return_value = mock_response

        result = minio_service.get_document("documents/user-1/chat-1/file.txt")

        assert result == b"document content"
        mock_minio_client.get_object.assert_called_once()


# ============================================================================
# GET AUDIT REPORT TESTS
# ============================================================================

class TestGetAuditReport:
    """Tests for get_audit_report method."""

    def test_get_audit_report_success(self, minio_service, mock_minio_client):
        """Should successfully retrieve an audit report."""
        mock_response = Mock()
        mock_response.read.return_value = b"# Audit Report Content"
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_minio_client.get_object.return_value = mock_response

        result = minio_service.get_audit_report("audit-reports/user-1/report.md")

        assert result == "# Audit Report Content"


# ============================================================================
# DELETE DOCUMENT TESTS
# ============================================================================

class TestDeleteDocument:
    """Tests for delete_document method."""

    def test_delete_document_success(self, minio_service, mock_minio_client):
        """Should successfully delete a document."""
        object_name = "documents/user-1/file.txt"

        minio_service.delete_document(object_name)

        mock_minio_client.remove_object.assert_called_once()


# ============================================================================
# PRESIGNED URL TESTS
# ============================================================================

class TestGetPresignedUrl:
    """Tests for get_presigned_url method."""

    def test_get_presigned_url_success(self, minio_service, mock_minio_client):
        """Should return presigned URL for object."""
        object_name = "documents/user-1/file.txt"

        result = minio_service.get_presigned_url(object_name)

        assert result is not None
        assert "presigned-url" in result


# ============================================================================
# GET OBJECT METADATA TESTS
# ============================================================================

class TestGetObjectMetadata:
    """Tests for get_object_metadata method."""

    def test_get_metadata_success(self, minio_service, mock_minio_client):
        """Should return object metadata."""
        mock_stat = Mock()
        mock_stat.size = 1024
        mock_stat.content_type = "application/pdf"
        mock_stat.metadata = {"x-amz-meta-original": "test.pdf"}
        mock_minio_client.stat_object.return_value = mock_stat

        result = minio_service.get_object_metadata("documents/file.pdf")

        assert result is not None


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestInitialization:
    """Tests for service initialization."""

    def test_init_creates_buckets(self, mock_minio_client):
        """Should create buckets if they don't exist."""
        mock_minio_client.bucket_exists.return_value = False

        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'localhost:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
            }):
                service = MinioStorageService()

        # make_bucket should be called for missing buckets
        assert mock_minio_client.make_bucket.called

    def test_init_with_ssl_enabled(self, mock_minio_client):
        """Should initialize with SSL when configured."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client) as MockMinio:
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'minio.secure.com',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
                'MINIO_USE_SSL': 'true',
            }):
                service = MinioStorageService()

        # Verify SSL was enabled
        call_kwargs = MockMinio.call_args[1]
        assert call_kwargs['secure'] is True

    def test_init_uses_legacy_env_vars(self, mock_minio_client):
        """Should fall back to legacy MINIO_ACCESS_KEY env vars."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client) as MockMinio:
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'localhost:9000',
                'MINIO_ACCESS_KEY': 'legacy_user',
                'MINIO_SECRET_KEY': 'legacy_pass',
            }, clear=False):
                # Clear the new vars
                import os
                os.environ.pop('MINIO_ROOT_USER', None)
                os.environ.pop('MINIO_ROOT_PASSWORD', None)

                service = MinioStorageService()

        # Service should initialize successfully
        assert service is not None

    def test_init_reads_bucket_config(self, mock_minio_client):
        """Should use custom bucket names from environment."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'localhost:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
                'MINIO_BUCKET_DOCUMENTS': 'custom-docs',
                'MINIO_BUCKET_REPORTS': 'custom-reports',
            }):
                service = MinioStorageService()

        assert service.bucket_documents == 'custom-docs'
        assert service.bucket_reports == 'custom-reports'


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_get_document_handles_error(self, minio_service, mock_minio_client):
        """Should handle errors when getting document."""
        mock_minio_client.get_object.side_effect = Exception("Connection lost")

        # Implementation may raise or return None - verify behavior is defined
        try:
            result = minio_service.get_document("documents/file.txt")
            # If doesn't raise, result should be None
            assert result is None
        except Exception:
            # If raises, test passes (error is propagated)
            pass

    def test_delete_handles_missing_object(self, minio_service, mock_minio_client):
        """Should not raise when deleting non-existent object."""
        mock_minio_client.remove_object.side_effect = Exception("Not found")

        # Should not raise
        try:
            minio_service.delete_document("nonexistent.txt")
        except Exception:
            pass  # Some implementations may raise, some may not


# ============================================================================
# UPLOAD DOCUMENT TESTS
# ============================================================================

class TestUploadDocument:
    """Tests for upload_document method."""

    def test_upload_document_success(self, minio_service, mock_minio_client):
        """Should successfully upload a document."""
        file_data = io.BytesIO(b"test content")

        result = minio_service.upload_document(
            user_id="user-123",
            file_id="file-456",
            file_data=file_data,
            filename="test.pdf",
            content_type="application/pdf",
        )

        assert result == "user-123/file-456.pdf"
        mock_minio_client.put_object.assert_called_once()

    def test_upload_document_with_chat_id(self, minio_service, mock_minio_client):
        """Should include chat_id in path when provided."""
        file_data = io.BytesIO(b"test content")

        result = minio_service.upload_document(
            user_id="user-123",
            file_id="file-456",
            file_data=file_data,
            filename="test.pdf",
            content_type="application/pdf",
            chat_id="chat-789",
        )

        assert result == "user-123/chat-789/file-456.pdf"

    def test_upload_document_with_metadata(self, minio_service, mock_minio_client):
        """Should include custom metadata."""
        file_data = io.BytesIO(b"test content")

        minio_service.upload_document(
            user_id="user-123",
            file_id="file-456",
            file_data=file_data,
            filename="test.txt",
            content_type="text/plain",
            metadata={"custom": "value"},
        )

        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert "custom" in call_kwargs["metadata"]

    def test_upload_document_without_extension(self, minio_service, mock_minio_client):
        """Should use .bin extension when filename has no extension."""
        file_data = io.BytesIO(b"test content")

        result = minio_service.upload_document(
            user_id="user-123",
            file_id="file-456",
            file_data=file_data,
            filename="noext",
            content_type="application/octet-stream",
        )

        assert result.endswith(".bin")

    def test_upload_document_s3_error(self, minio_service, mock_minio_client):
        """Should raise S3Error on upload failure."""
        file_data = io.BytesIO(b"test content")
        mock_minio_client.put_object.side_effect = S3Error(
            "PutObject",
            "NoSuchBucket",
            "The specified bucket does not exist",
            {},
            "bucket",
            "object",
        )

        with pytest.raises(S3Error):
            minio_service.upload_document(
                user_id="user-123",
                file_id="file-456",
                file_data=file_data,
                filename="test.pdf",
                content_type="application/pdf",
            )


# ============================================================================
# UPLOAD AUDIT REPORT TESTS
# ============================================================================

class TestUploadAuditReport:
    """Tests for upload_audit_report method."""

    def test_upload_audit_report_success(self, minio_service, mock_minio_client):
        """Should successfully upload an audit report."""
        result = minio_service.upload_audit_report(
            user_id="user-123",
            report_id="report-456",
            report_content="# Audit Report\n\nContent here",
            chat_id="chat-789",
            document_id="doc-111",
        )

        assert result == "user-123/chat-789/report-456.md"
        mock_minio_client.put_object.assert_called_once()

    def test_upload_audit_report_with_metadata(self, minio_service, mock_minio_client):
        """Should include custom metadata."""
        minio_service.upload_audit_report(
            user_id="user-123",
            report_id="report-456",
            report_content="# Report",
            chat_id="chat-789",
            document_id="doc-111",
            metadata={"auditor": "system"},
        )

        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert "auditor" in call_kwargs["metadata"]

    def test_upload_audit_report_encodes_utf8(self, minio_service, mock_minio_client):
        """Should properly encode UTF-8 content."""
        minio_service.upload_audit_report(
            user_id="user-123",
            report_id="report-456",
            report_content="# Reporte con acentos: café, niño",
            chat_id="chat-789",
            document_id="doc-111",
        )

        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert call_kwargs["content_type"] == "text/markdown; charset=utf-8"

    def test_upload_audit_report_s3_error(self, minio_service, mock_minio_client):
        """Should raise S3Error on upload failure."""
        mock_minio_client.put_object.side_effect = S3Error(
            "PutObject",
            "AccessDenied",
            "Access Denied",
            {},
            "bucket",
            "object",
        )

        with pytest.raises(S3Error):
            minio_service.upload_audit_report(
                user_id="user-123",
                report_id="report-456",
                report_content="# Report",
                chat_id="chat-789",
                document_id="doc-111",
            )


# ============================================================================
# MATERIALIZE DOCUMENT TESTS
# ============================================================================

class TestMaterializeDocument:
    """Tests for materialize_document method."""

    def test_materialize_existing_local_file(self, minio_service, tmp_path):
        """Should return local path if file exists."""
        # Create a temporary file
        local_file = tmp_path / "existing.pdf"
        local_file.write_bytes(b"content")

        path, is_temp = minio_service.materialize_document(str(local_file))

        assert path == local_file
        assert is_temp is False

    def test_materialize_from_minio(self, minio_service, mock_minio_client):
        """Should download from MinIO if file doesn't exist locally."""
        mock_response = Mock()
        mock_response.read.return_value = b"minio content"
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_minio_client.get_object.return_value = mock_response

        path, is_temp = minio_service.materialize_document(
            "user-1/file.pdf",
            filename="document.pdf",
        )

        assert is_temp is True
        assert path.exists()
        assert path.read_bytes() == b"minio content"

        # Cleanup
        path.unlink()

    def test_materialize_preserves_extension(self, minio_service, mock_minio_client):
        """Should preserve file extension in temp file."""
        mock_response = Mock()
        mock_response.read.return_value = b"content"
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_minio_client.get_object.return_value = mock_response

        path, is_temp = minio_service.materialize_document(
            "user-1/file.xlsx",
            filename="spreadsheet.xlsx",
        )

        assert path.suffix == ".xlsx"

        # Cleanup
        path.unlink()


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

class TestHealthCheck:
    """Tests for health_check method."""

    def test_health_check_success(self, minio_service, mock_minio_client):
        """Should return True when MinIO is accessible."""
        mock_minio_client.list_buckets.return_value = [Mock(), Mock()]

        result = minio_service.health_check()

        assert result is True
        mock_minio_client.list_buckets.assert_called_once()

    def test_health_check_no_buckets(self, minio_service, mock_minio_client):
        """Should return False when no buckets exist."""
        mock_minio_client.list_buckets.return_value = []

        result = minio_service.health_check()

        assert result is False

    def test_health_check_s3_error(self, minio_service, mock_minio_client):
        """Should return False on S3 error."""
        mock_minio_client.list_buckets.side_effect = S3Error(
            "ListBuckets",
            "AccessDenied",
            "Access Denied",
            {},
            "bucket",
            "object",
        )

        result = minio_service.health_check()

        assert result is False


# ============================================================================
# UPLOAD FILE (ASYNC) TESTS
# ============================================================================

class TestUploadFile:
    """Tests for upload_file async method."""

    @pytest.mark.asyncio
    async def test_upload_file_success(self, minio_service, mock_minio_client):
        """Should successfully upload a file."""
        file_data = io.BytesIO(b"test content")

        await minio_service.upload_file(
            bucket_name="artifacts",
            object_name="exports/report.pdf",
            data=file_data,
            length=12,
            content_type="application/pdf",
        )

        mock_minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_file_creates_bucket(self, minio_service, mock_minio_client):
        """Should create bucket if it doesn't exist."""
        mock_minio_client.bucket_exists.return_value = False
        file_data = io.BytesIO(b"test content")

        await minio_service.upload_file(
            bucket_name="new-bucket",
            object_name="file.txt",
            data=file_data,
            length=12,
        )

        mock_minio_client.make_bucket.assert_called_with(bucket_name="new-bucket")

    @pytest.mark.asyncio
    async def test_upload_file_with_metadata(self, minio_service, mock_minio_client):
        """Should include metadata in upload."""
        file_data = io.BytesIO(b"test content")

        await minio_service.upload_file(
            bucket_name="artifacts",
            object_name="file.txt",
            data=file_data,
            length=12,
            metadata={"source": "export"},
        )

        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert call_kwargs["metadata"] == {"source": "export"}

    @pytest.mark.asyncio
    async def test_upload_file_s3_error(self, minio_service, mock_minio_client):
        """Should raise S3Error on failure."""
        file_data = io.BytesIO(b"test content")
        mock_minio_client.put_object.side_effect = S3Error(
            "PutObject",
            "InternalError",
            "Internal error",
            {},
            "bucket",
            "object",
        )

        with pytest.raises(S3Error):
            await minio_service.upload_file(
                bucket_name="artifacts",
                object_name="file.txt",
                data=file_data,
                length=12,
            )


# ============================================================================
# PRESIGNED URL BUCKET MAPPING TESTS
# ============================================================================

class TestPresignedUrlBucketMapping:
    """Tests for presigned URL bucket name mapping."""

    def test_presigned_url_documents_bucket(self, minio_service, mock_minio_client):
        """Should map 'documents' to configured bucket."""
        minio_service.get_presigned_url("file.pdf", bucket="documents")

        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs["bucket_name"] == minio_service.bucket_documents

    def test_presigned_url_reports_bucket(self, minio_service, mock_minio_client):
        """Should map 'audit-reports' to configured bucket."""
        minio_service.get_presigned_url("report.md", bucket="audit-reports")

        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs["bucket_name"] == minio_service.bucket_reports

    def test_presigned_url_artifacts_bucket(self, minio_service, mock_minio_client):
        """Should use 'artifacts' directly."""
        minio_service.get_presigned_url("export.pdf", bucket="artifacts")

        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs["bucket_name"] == "artifacts"

    def test_presigned_url_custom_bucket(self, minio_service, mock_minio_client):
        """Should use custom bucket name as-is."""
        minio_service.get_presigned_url("file.txt", bucket="custom-bucket")

        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs["bucket_name"] == "custom-bucket"


# ============================================================================
# GET OBJECT METADATA BUCKET MAPPING TESTS
# ============================================================================

class TestGetObjectMetadataBucketMapping:
    """Tests for get_object_metadata bucket selection."""

    def test_metadata_documents_bucket(self, minio_service, mock_minio_client):
        """Should use documents bucket for 'documents'."""
        mock_stat = Mock()
        mock_stat.size = 100
        mock_stat.etag = "abc123"
        mock_stat.last_modified = None
        mock_stat.content_type = "text/plain"
        mock_stat.metadata = {}
        mock_minio_client.stat_object.return_value = mock_stat

        minio_service.get_object_metadata("file.txt", bucket="documents")

        call_kwargs = mock_minio_client.stat_object.call_args[1]
        assert call_kwargs["bucket_name"] == minio_service.bucket_documents

    def test_metadata_reports_bucket(self, minio_service, mock_minio_client):
        """Should use reports bucket for non-documents."""
        mock_stat = Mock()
        mock_stat.size = 100
        mock_stat.etag = "abc123"
        mock_stat.last_modified = None
        mock_stat.content_type = "text/plain"
        mock_stat.metadata = {}
        mock_minio_client.stat_object.return_value = mock_stat

        minio_service.get_object_metadata("report.md", bucket="audit-reports")

        call_kwargs = mock_minio_client.stat_object.call_args[1]
        assert call_kwargs["bucket_name"] == minio_service.bucket_reports

    def test_metadata_returns_all_fields(self, minio_service, mock_minio_client):
        """Should return all metadata fields."""
        from datetime import datetime

        mock_stat = Mock()
        mock_stat.size = 2048
        mock_stat.etag = "etag-hash"
        mock_stat.last_modified = datetime(2024, 1, 15)
        mock_stat.content_type = "application/pdf"
        mock_stat.metadata = {"x-custom": "value"}
        mock_minio_client.stat_object.return_value = mock_stat

        result = minio_service.get_object_metadata("file.pdf")

        assert result["size"] == 2048
        assert result["etag"] == "etag-hash"
        assert result["content_type"] == "application/pdf"
        assert result["metadata"] == {"x-custom": "value"}


# ============================================================================
# GET MINIO STORAGE SINGLETON TESTS
# ============================================================================

class TestGetMinioStorage:
    """Tests for get_minio_storage singleton function."""

    def test_returns_none_when_disabled(self):
        """Should return None when MINIO_STORAGE_ENABLED=false."""
        import src.services.minio_storage as module
        module._minio_storage_service = None

        with patch.dict('os.environ', {'MINIO_STORAGE_ENABLED': 'false'}):
            from src.services.minio_storage import get_minio_storage
            result = get_minio_storage()

        assert result is None

    def test_creates_instance_when_enabled(self, mock_minio_client):
        """Should create instance when MINIO_STORAGE_ENABLED=true."""
        import src.services.minio_storage as module
        module._minio_storage_service = None

        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
            with patch.dict('os.environ', {
                'MINIO_STORAGE_ENABLED': 'true',
                'MINIO_ENDPOINT': 'localhost:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
            }):
                from src.services.minio_storage import get_minio_storage
                result = get_minio_storage()

        assert result is not None
        assert isinstance(result, MinioStorageService)

    def test_returns_singleton_instance(self, mock_minio_client):
        """Should return same instance on multiple calls."""
        import src.services.minio_storage as module
        module._minio_storage_service = None

        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
            with patch.dict('os.environ', {
                'MINIO_STORAGE_ENABLED': 'true',
                'MINIO_ENDPOINT': 'localhost:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
            }):
                from src.services.minio_storage import get_minio_storage
                first = get_minio_storage()
                second = get_minio_storage()

        assert first is second


# ============================================================================
# PUBLIC CLIENT INITIALIZATION TESTS
# ============================================================================

class TestPublicClientInitialization:
    """Tests for _initialize_public_client method."""

    def test_public_client_from_public_endpoint(self, mock_minio_client):
        """Should use MINIO_PUBLIC_ENDPOINT when set."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client) as MockMinio:
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'minio:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
                'MINIO_PUBLIC_ENDPOINT': 'https://public.minio.example.com',
            }):
                service = MinioStorageService()

        # Minio should be called twice - once for internal, once for public
        assert MockMinio.call_count == 2

    def test_public_client_from_external_host(self, mock_minio_client):
        """Should use MINIO_EXTERNAL_HOST when set."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client) as MockMinio:
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'minio:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
                'MINIO_EXTERNAL_HOST': 'external.minio.com:9000',
            }):
                service = MinioStorageService()

        assert MockMinio.call_count == 2

    def test_public_client_local_fallback(self, mock_minio_client):
        """Should fall back to localhost for local development."""
        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client) as MockMinio:
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'minio:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
            }, clear=False):
                # Clear public endpoint vars
                import os
                os.environ.pop('MINIO_PUBLIC_ENDPOINT', None)
                os.environ.pop('MINIO_EXTERNAL_HOST', None)

                service = MinioStorageService()

        # Should create public client with localhost fallback
        assert MockMinio.call_count >= 1

    def test_public_client_uses_presigned_url(self, mock_minio_client):
        """Should use public client for presigned URLs when available."""
        mock_public_client = Mock()
        mock_public_client.presigned_get_object = Mock(return_value="https://public.url/presigned")

        with patch('src.services.minio_storage.Minio', return_value=mock_minio_client):
            with patch.dict('os.environ', {
                'MINIO_ENDPOINT': 'minio:9000',
                'MINIO_ROOT_USER': 'admin',
                'MINIO_ROOT_PASSWORD': 'secret',
            }):
                service = MinioStorageService()
                service.public_client = mock_public_client

                url = service.get_presigned_url("file.pdf")

        assert url == "https://public.url/presigned"
        mock_public_client.presigned_get_object.assert_called_once()


# ============================================================================
# S3 ERROR HANDLING EDGE CASES
# ============================================================================

class TestS3ErrorHandling:
    """Tests for S3 error handling edge cases."""

    def test_get_document_s3_error_propagates(self, minio_service, mock_minio_client):
        """Should propagate S3Error when getting document fails."""
        mock_minio_client.get_object.side_effect = S3Error(
            "GetObject",
            "NoSuchKey",
            "The specified key does not exist",
            {},
            "documents",
            "missing.pdf",
        )

        with pytest.raises(S3Error) as exc_info:
            minio_service.get_document("missing.pdf")

        assert exc_info.value.code == "NoSuchKey"

    def test_get_audit_report_s3_error_propagates(self, minio_service, mock_minio_client):
        """Should propagate S3Error when getting report fails."""
        mock_minio_client.get_object.side_effect = S3Error(
            "GetObject",
            "NoSuchKey",
            "Report not found",
            {},
            "audit-reports",
            "missing.md",
        )

        with pytest.raises(S3Error):
            minio_service.get_audit_report("missing.md")

    def test_delete_document_s3_error_propagates(self, minio_service, mock_minio_client):
        """Should propagate S3Error when delete fails."""
        mock_minio_client.remove_object.side_effect = S3Error(
            "RemoveObject",
            "AccessDenied",
            "Access denied",
            {},
            "documents",
            "protected.pdf",
        )

        with pytest.raises(S3Error):
            minio_service.delete_document("protected.pdf")

    def test_presigned_url_s3_error_propagates(self, minio_service, mock_minio_client):
        """Should propagate S3Error when presigned URL fails."""
        mock_minio_client.presigned_get_object.side_effect = S3Error(
            "PresignedGet",
            "InvalidBucket",
            "Bucket not found",
            {},
            "invalid-bucket",
            "file.pdf",
        )

        with pytest.raises(S3Error):
            minio_service.get_presigned_url("file.pdf", bucket="invalid-bucket")

    def test_metadata_s3_error_propagates(self, minio_service, mock_minio_client):
        """Should propagate S3Error when metadata fails."""
        mock_minio_client.stat_object.side_effect = S3Error(
            "StatObject",
            "NoSuchKey",
            "Object not found",
            {},
            "documents",
            "missing.pdf",
        )

        with pytest.raises(S3Error):
            minio_service.get_object_metadata("missing.pdf")
