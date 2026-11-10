"""
Integration tests for gRPC client/server communication.

These tests require the file-manager service to be running.
Run with: pytest tests/integration/ -m integration
"""

import os
import pytest
import asyncio


# Skip all tests if not in integration mode
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


# ============================================================================
# gRPC Connection Tests
# ============================================================================


class TestGrpcConnection:
    """Test gRPC connection and channel management."""

    @pytest.fixture
    def grpc_target(self, file_manager_grpc_host, file_manager_grpc_port):
        """Get gRPC target address."""
        return f"{file_manager_grpc_host}:{file_manager_grpc_port}"

    async def test_grpc_channel_creation(self, grpc_target):
        """Test gRPC channel can be created."""
        try:
            import grpc
        except ImportError:
            pytest.skip("grpcio not installed")

        channel = grpc.aio.insecure_channel(grpc_target)

        # Channel should be created without error
        assert channel is not None

        await channel.close()

    async def test_grpc_channel_connectivity(self, grpc_target):
        """Test gRPC channel connectivity."""
        try:
            import grpc
        except ImportError:
            pytest.skip("grpcio not installed")

        channel = grpc.aio.insecure_channel(grpc_target)

        try:
            # Try to get channel state
            state = channel.get_state(try_to_connect=True)

            # Wait for connection (with timeout)
            try:
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=5.0,
                )
                connected = True
            except asyncio.TimeoutError:
                connected = False

        finally:
            await channel.close()

        if not connected:
            pytest.skip("gRPC server not reachable")


# ============================================================================
# Health Check Integration Tests
# ============================================================================


class TestGrpcHealthIntegration:
    """Integration tests for gRPC health check."""

    async def test_health_check_via_grpc(
        self, file_manager_grpc_host, file_manager_grpc_port
    ):
        """Test health check via gRPC."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError as e:
            pytest.skip(f"gRPC modules not available: {e}")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            # Wait for connection
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)
            request = file_manager_pb2.HealthRequest()

            response = await stub.Health(request)

            assert response.status in ("healthy", "degraded")
            assert "minio" in response.dependencies
            assert "redis" in response.dependencies
            assert isinstance(response.rust_available, bool)

        finally:
            await channel.close()

    async def test_health_check_rust_info(
        self, file_manager_grpc_host, file_manager_grpc_port
    ):
        """Test health check returns Rust module info."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)
            response = await stub.Health(file_manager_pb2.HealthRequest())

            # Check Rust info is present
            if response.rust_available:
                assert response.rust_module_version != ""
                assert "pdf_extraction" in response.capabilities

        finally:
            await channel.close()


# ============================================================================
# Upload/Download Integration Tests
# ============================================================================


class TestGrpcUploadDownloadIntegration:
    """Integration tests for file upload/download via gRPC."""

    async def test_upload_and_download_cycle(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_pdf_bytes,
    ):
        """Test complete upload and download cycle."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # Upload
            upload_request = file_manager_pb2.UploadSimpleRequest(
                metadata=file_manager_pb2.UploadRequest(
                    user_id="integration_test",
                    filename="test_integration.pdf",
                    content_type="application/pdf",
                    auto_extract=False,
                ),
                file_data=sample_pdf_bytes,
            )

            upload_response = await stub.UploadSimple(upload_request)

            assert upload_response.file_id != ""
            assert upload_response.metadata.size == len(sample_pdf_bytes)

            file_path = upload_response.metadata.minio_key

            # Download
            download_request = file_manager_pb2.DownloadRequest(
                file_path=file_path,
            )

            downloaded_chunks = []
            async for response in stub.Download(download_request):
                if response.HasField("chunk"):
                    downloaded_chunks.append(response.chunk.data)

            downloaded_data = b"".join(downloaded_chunks)
            assert downloaded_data == sample_pdf_bytes

            # Cleanup
            delete_request = file_manager_pb2.DeleteRequest(
                file_path=file_path,
            )
            await stub.Delete(delete_request)

        finally:
            await channel.close()


# ============================================================================
# Extraction Integration Tests
# ============================================================================


class TestGrpcExtractionIntegration:
    """Integration tests for text extraction via gRPC."""

    async def test_extract_pdf_text(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_pdf_bytes,
    ):
        """Test PDF text extraction via gRPC."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # First upload the file
            upload_response = await stub.UploadSimple(
                file_manager_pb2.UploadSimpleRequest(
                    metadata=file_manager_pb2.UploadRequest(
                        user_id="extraction_test",
                        filename="extract_test.pdf",
                        content_type="application/pdf",
                    ),
                    file_data=sample_pdf_bytes,
                )
            )

            file_path = upload_response.metadata.minio_key

            # Extract text
            extract_request = file_manager_pb2.ExtractRequest(
                file_path=file_path,
                force=False,
            )

            extract_response = await stub.Extract(extract_request)

            assert extract_response.result is not None
            assert extract_response.result.total_pages >= 1
            assert extract_response.result.source in ("rust", "python", "cache")
            assert len(extract_response.result.pages) >= 1

            # Cleanup
            await stub.Delete(file_manager_pb2.DeleteRequest(file_path=file_path))

        finally:
            await channel.close()

    async def test_extract_with_auto_extract(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_pdf_bytes,
    ):
        """Test upload with auto-extract enabled."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # Upload with auto_extract=True
            upload_response = await stub.UploadSimple(
                file_manager_pb2.UploadSimpleRequest(
                    metadata=file_manager_pb2.UploadRequest(
                        user_id="auto_extract_test",
                        filename="auto_extract.pdf",
                        content_type="application/pdf",
                        auto_extract=True,
                    ),
                    file_data=sample_pdf_bytes,
                )
            )

            # Extraction should be included in response
            assert upload_response.HasField("extraction")
            assert upload_response.extraction.total_pages >= 1

            # Cleanup
            await stub.Delete(
                file_manager_pb2.DeleteRequest(
                    file_path=upload_response.metadata.minio_key
                )
            )

        finally:
            await channel.close()


# ============================================================================
# Thumbnail Integration Tests
# ============================================================================


class TestGrpcThumbnailIntegration:
    """Integration tests for thumbnail generation via gRPC."""

    async def test_generate_thumbnail(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_image_bytes,
    ):
        """Test thumbnail generation via gRPC."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # Upload image
            upload_response = await stub.UploadSimple(
                file_manager_pb2.UploadSimpleRequest(
                    metadata=file_manager_pb2.UploadRequest(
                        user_id="thumbnail_test",
                        filename="thumb_test.png",
                        content_type="image/png",
                    ),
                    file_data=sample_image_bytes,
                )
            )

            file_path = upload_response.metadata.minio_key

            # Generate thumbnail
            thumb_response = await stub.GenerateThumbnail(
                file_manager_pb2.ThumbnailRequest(
                    file_path=file_path,
                    width=200,
                    height=200,
                    format="jpeg",
                    quality=85,
                )
            )

            assert thumb_response.thumbnail is not None
            assert len(thumb_response.thumbnail) > 0
            assert thumb_response.content_type == "image/jpeg"
            assert thumb_response.width <= 200
            assert thumb_response.height <= 200

            # Cleanup
            await stub.Delete(file_manager_pb2.DeleteRequest(file_path=file_path))

        finally:
            await channel.close()


# ============================================================================
# Batch Operations Integration Tests
# ============================================================================


class TestGrpcBatchIntegration:
    """Integration tests for batch operations via gRPC."""

    async def test_batch_extract(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_pdf_bytes,
    ):
        """Test batch extraction via gRPC."""
        try:
            import grpc
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # Upload multiple files
            file_paths = []
            for i in range(3):
                upload_response = await stub.UploadSimple(
                    file_manager_pb2.UploadSimpleRequest(
                        metadata=file_manager_pb2.UploadRequest(
                            user_id="batch_test",
                            filename=f"batch_{i}.pdf",
                            content_type="application/pdf",
                        ),
                        file_data=sample_pdf_bytes,
                    )
                )
                file_paths.append(upload_response.metadata.minio_key)

            # Batch extract
            batch_response = await stub.BatchExtract(
                file_manager_pb2.BatchExtractRequest(
                    file_paths=file_paths,
                    force=False,
                )
            )

            assert len(batch_response.results) == 3
            assert batch_response.total_processing_time_ms > 0

            # Cleanup
            for path in file_paths:
                await stub.Delete(file_manager_pb2.DeleteRequest(file_path=path))

        finally:
            await channel.close()


# ============================================================================
# Performance Integration Tests
# ============================================================================


@pytest.mark.slow
class TestGrpcPerformanceIntegration:
    """Performance tests for gRPC operations."""

    async def test_extraction_performance(
        self,
        file_manager_grpc_host,
        file_manager_grpc_port,
        sample_pdf_bytes,
    ):
        """Test extraction performance via gRPC."""
        try:
            import grpc
            import time
            from src.grpc.generated import file_manager_pb2, file_manager_pb2_grpc
        except ImportError:
            pytest.skip("gRPC modules not available")

        target = f"{file_manager_grpc_host}:{file_manager_grpc_port}"
        channel = grpc.aio.insecure_channel(target)

        try:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.skip("gRPC server not reachable")

            stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)

            # Upload
            upload_response = await stub.UploadSimple(
                file_manager_pb2.UploadSimpleRequest(
                    metadata=file_manager_pb2.UploadRequest(
                        user_id="perf_test",
                        filename="perf_test.pdf",
                        content_type="application/pdf",
                    ),
                    file_data=sample_pdf_bytes,
                )
            )

            file_path = upload_response.metadata.minio_key

            # Measure extraction time
            start = time.perf_counter()
            extract_response = await stub.Extract(
                file_manager_pb2.ExtractRequest(
                    file_path=file_path,
                    force=True,  # Force to skip cache
                )
            )
            elapsed = time.perf_counter() - start

            print(f"\nExtraction time: {elapsed*1000:.1f}ms")
            print(f"Source: {extract_response.result.source}")
            print(f"Server processing: {extract_response.result.processing_time_ms}ms")

            # Cleanup
            await stub.Delete(file_manager_pb2.DeleteRequest(file_path=file_path))

            # Assert reasonable performance (under 5 seconds)
            assert elapsed < 5.0

        finally:
            await channel.close()
