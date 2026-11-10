"""
Smoke tests for file-manager plugin.

These are quick "sanity check" tests that verify basic functionality
before running the full test suite. They should complete in seconds.

Run with: pytest tests/smoke/ -m smoke
"""

import pytest


# All smoke tests should be fast and basic
pytestmark = [pytest.mark.smoke]


# ============================================================================
# Module Import Smoke Tests
# ============================================================================


class TestImportSmoke:
    """Verify all modules can be imported."""

    def test_import_main(self):
        """Test main module imports."""
        try:
            from src import main

            assert main is not None
        except (ImportError, AttributeError) as e:
            if "generated" in str(e) or "NoneType" in str(e):
                pytest.skip("gRPC proto not generated yet - run scripts/generate_proto.sh")
            raise

    def test_import_config(self):
        """Test config module imports."""
        from src.config import get_settings

        assert get_settings is not None

    def test_import_extraction_service(self):
        """Test extraction service imports."""
        from src.services.extraction import (
            extract_text_from_pdf,
            extract_text_from_image,
            extract_text_from_file,
            generate_thumbnail,
            get_extraction_status,
            RUST_AVAILABLE,
        )

        assert callable(extract_text_from_pdf)
        assert callable(extract_text_from_image)
        assert callable(extract_text_from_file)
        assert callable(generate_thumbnail)
        assert callable(get_extraction_status)
        assert isinstance(RUST_AVAILABLE, bool)

    def test_import_grpc_modules(self):
        """Test gRPC modules import (may skip if not generated)."""
        try:
            from src.grpc.server import create_grpc_server, start_grpc_server

            assert callable(create_grpc_server)
            assert callable(start_grpc_server)
        except (ImportError, AttributeError) as e:
            if "generated" in str(e) or "NoneType" in str(e):
                pytest.skip("gRPC proto not generated yet - run scripts/generate_proto.sh")
            raise

    def test_import_routers(self):
        """Test router modules import."""
        from src.routers import upload, download, metadata

        assert upload is not None
        assert download is not None
        assert metadata is not None


# ============================================================================
# Configuration Smoke Tests
# ============================================================================


class TestConfigSmoke:
    """Verify configuration loads correctly."""

    def test_settings_load(self):
        """Test settings can be loaded."""
        from src.config import get_settings

        settings = get_settings()
        assert settings is not None

    def test_settings_has_required_fields(self):
        """Test settings has required fields."""
        from src.config import get_settings

        settings = get_settings()

        # Core settings
        assert hasattr(settings, "minio_endpoint")
        assert hasattr(settings, "minio_bucket_documents")  # Actual field name
        assert hasattr(settings, "redis_url")

        # gRPC settings (added in migration)
        assert hasattr(settings, "grpc_port")
        assert hasattr(settings, "grpc_enabled")

    def test_settings_defaults(self):
        """Test settings have sensible defaults."""
        from src.config import get_settings

        settings = get_settings()

        # gRPC defaults
        assert settings.grpc_port == 50052
        assert settings.grpc_max_workers >= 1


# ============================================================================
# Service Health Smoke Tests
# ============================================================================


class TestServiceHealthSmoke:
    """Quick service health checks."""

    def test_extraction_status(self):
        """Test extraction status returns valid structure."""
        from src.services.extraction import get_extraction_status

        status = get_extraction_status()

        assert isinstance(status, dict)
        assert "rust_available" in status
        assert "capabilities" in status
        assert "performance" in status

    def test_extraction_capabilities(self):
        """Test extraction capabilities are listed."""
        from src.services.extraction import get_extraction_status

        status = get_extraction_status()
        caps = status["capabilities"]

        # Capabilities can be list or dict depending on implementation
        assert isinstance(caps, (list, dict))
        # Should always have at least Python capabilities
        if isinstance(caps, list):
            assert "pdf_extraction" in caps
        else:
            assert "pdf_extraction" in caps


# ============================================================================
# Basic Functionality Smoke Tests
# ============================================================================


class TestFunctionalitySmoke:
    """Quick functional tests."""

    def test_text_quality_basic(self):
        """Test text quality check works."""
        from src.services.extraction import _is_text_quality_sufficient

        # Text must be >= 150 chars by default, have >= 5 words, and quality ratio >= 0.4
        good = _is_text_quality_sufficient(
            "This is a good quality text with enough words and characters to pass the quality "
            "check validation. The minimum character count is 150, so we need a longer sample "
            "text to ensure the test passes correctly."
        )
        bad = _is_text_quality_sufficient("")

        assert good is True
        assert bad is False

    def test_thumbnail_from_bytes(self, sample_image_bytes):
        """Test thumbnail generation from bytes."""
        from src.services.extraction import generate_thumbnail_bytes

        data, content_type = generate_thumbnail_bytes(sample_image_bytes)

        assert isinstance(data, bytes)
        assert len(data) > 0
        assert content_type.startswith("image/")

    def test_pdf_extraction_basic(self, temp_pdf_file):
        """Test basic PDF extraction works."""
        from src.services.extraction import extract_text_from_pdf

        text, pages = extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)
        assert pages >= 1


# ============================================================================
# gRPC Smoke Tests
# ============================================================================


class TestGrpcSmoke:
    """Quick gRPC-related checks."""

    def test_grpc_servicer_instantiation(self):
        """Test gRPC servicer can be instantiated."""
        try:
            from src.grpc.servicer import FileManagerServicer

            servicer = FileManagerServicer()
            assert servicer is not None
        except (ImportError, AttributeError) as e:
            if "generated" in str(e) or "NoneType" in str(e):
                pytest.skip("gRPC proto not generated yet - run scripts/generate_proto.sh")
            raise

    def test_grpc_server_creation(self):
        """Test gRPC server can be created."""
        try:
            from src.grpc.server import create_grpc_server

            server = create_grpc_server()
            assert server is not None
        except (ImportError, AttributeError) as e:
            if "generated" in str(e) or "NoneType" in str(e):
                pytest.skip("gRPC proto not generated yet - run scripts/generate_proto.sh")
            raise


# ============================================================================
# Rust Module Smoke Tests
# ============================================================================


class TestRustSmoke:
    """Quick Rust module checks (skip if not compiled)."""

    def test_rust_import(self):
        """Test Rust module import."""
        try:
            import document_processing_rs as rs

            assert hasattr(rs, "__version__")
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_rust_basic_function(self):
        """Test basic Rust function works."""
        try:
            import document_processing_rs as rs

            # Simple function that should work
            result = rs.is_quality_sufficient(
                "This is enough text to pass the quality validation check."
            )
            assert isinstance(result, bool)
        except ImportError:
            pytest.skip("Rust module not compiled")


# ============================================================================
# Error Handling Smoke Tests
# ============================================================================


class TestErrorHandlingSmoke:
    """Quick error handling checks."""

    def test_extraction_handles_missing_file(self):
        """Test extraction raises for missing file."""
        from src.services.extraction import extract_text_from_pdf
        from pathlib import Path

        with pytest.raises(Exception):
            extract_text_from_pdf(Path("/nonexistent/file.pdf"))

    def test_thumbnail_handles_invalid_data(self):
        """Test thumbnail raises for invalid data."""
        from src.services.extraction import generate_thumbnail_bytes

        with pytest.raises(Exception):
            generate_thumbnail_bytes(b"not an image")

    def test_quality_handles_none(self):
        """Test quality check handles edge cases."""
        from src.services.extraction import _is_text_quality_sufficient

        # Should not raise, should return False
        result = _is_text_quality_sufficient("")
        assert result is False
