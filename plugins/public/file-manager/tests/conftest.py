"""
Test fixtures and configuration for file-manager plugin tests.

Provides shared fixtures for unit, integration, regression, and smoke tests.
"""

import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (require services)")
    config.addinivalue_line("markers", "regression: Regression tests (ensure fallback works)")
    config.addinivalue_line("markers", "smoke: Smoke tests (quick health checks)")
    config.addinivalue_line("markers", "rust: Tests that require Rust module")
    config.addinivalue_line("markers", "grpc: Tests that require gRPC")


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """
    Generate minimal valid PDF bytes for testing.

    Uses pypdf to create a structurally valid PDF that works with
    both Python (pypdf) and Rust (lopdf) PDF parsers.
    """
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        # Add metadata so there's some content
        writer.add_metadata({"/Title": "Test PDF", "/Author": "Test"})
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except ImportError:
        # Fallback: hand-crafted minimal PDF (may not pass strict parsers)
        return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
178
%%EOF"""


@pytest.fixture
def sample_image_bytes() -> bytes:
    """
    Generate minimal valid PNG bytes for testing.

    Creates a 10x10 white PNG image.
    """
    # Minimal 10x10 white PNG
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="white")
    # Add some text-like patterns for OCR
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.text((10, 40), "Test Image", fill="black")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def sample_text() -> str:
    """Sample text for quality validation tests."""
    return """
    This is a sample document with sufficient text content.
    It contains multiple paragraphs and sentences that should
    pass the quality validation checks. The text includes
    both English and Spanish words like documento, contenido,
    y párrafos para validar el procesamiento bilingüe.
    """


@pytest.fixture
def low_quality_text() -> str:
    """Low quality text that should fail validation."""
    return "!@#$%^&*()_+-=[]{}|;':\",./<>?"


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_pdf_file(sample_pdf_bytes) -> Generator[Path, None, None]:
    """Create a temporary PDF file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(sample_pdf_bytes)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_image_file(sample_image_bytes) -> Generator[Path, None, None]:
    """Create a temporary image file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(sample_image_bytes)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client for unit tests."""
    client = MagicMock()
    client.bucket_exists.return_value = True
    client.list_buckets.return_value = []
    client.get_object.return_value = MagicMock(
        read=MagicMock(return_value=b"test content"),
        close=MagicMock(),
    )
    client.put_object.return_value = MagicMock()
    client.stat_object.return_value = MagicMock(
        size=1024,
        content_type="application/pdf",
        last_modified=None,
    )
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for unit tests."""
    client = AsyncMock()
    client.get.return_value = None
    client.set.return_value = True
    client.delete.return_value = 1
    client.ping.return_value = True
    return client


@pytest.fixture
def mock_extraction_result():
    """Mock extraction result."""
    return {
        "file_id": "test123",
        "pages": [
            {"page": 0, "text_md": "Page 1 content", "has_table": False},
            {"page": 1, "text_md": "Page 2 content", "has_table": False},
        ],
        "total_pages": 2,
        "ocr_applied": False,
        "source": "rust",
    }


# ============================================================================
# Rust Module Fixtures
# ============================================================================


@pytest.fixture
def rust_module_available() -> bool:
    """Check if Rust module is available."""
    try:
        import document_processing_rs

        return True
    except ImportError:
        return False


@pytest.fixture
def mock_rust_module():
    """Mock Rust module for unit tests when actual module unavailable."""
    mock = MagicMock()

    # Mock PageResult class
    class MockPageResult:
        def __init__(self, page, text, needs_ocr):
            self.page = page
            self.text = text
            self.needs_ocr = needs_ocr
            self.char_count = len(text)
            self.quality_ratio = 0.8

    # Mock ThumbnailResult class
    class MockThumbnailResult:
        def __init__(self):
            self.data = b"\x89PNG\r\n\x1a\n"  # PNG header
            self.width = 200
            self.height = 200
            self.content_type = "image/jpeg"
            self.original_width = 800
            self.original_height = 600

    # Mock QualityMetrics class
    class MockQualityMetrics:
        def __init__(self, text):
            self.char_count = len(text)
            self.word_count = len(text.split())
            self.quality_ratio = 0.8
            self.is_sufficient = True

    mock.extract_text_from_pdf.return_value = [
        MockPageResult(0, "Page 1 text", False),
        MockPageResult(1, "Page 2 text", False),
    ]
    mock.extract_text_parallel.return_value = [
        ("file1.pdf", [MockPageResult(0, "Text", False)]),
    ]
    mock.get_pdf_page_count.return_value = 2

    mock.ocr_image.return_value = "OCR extracted text"
    mock.ocr_image_bytes.return_value = "OCR from bytes"
    mock.ocr_images_parallel.return_value = [("img1.png", "Text 1")]

    mock.generate_thumbnail.return_value = MockThumbnailResult()
    mock.generate_thumbnail_bytes.return_value = MockThumbnailResult()

    mock.is_quality_sufficient.return_value = True
    mock.calculate_char_ratio.return_value = 0.85
    mock.count_words.return_value = 50
    mock.get_quality_metrics.return_value = MockQualityMetrics("test")

    mock.__version__ = "0.1.0"

    return mock


# ============================================================================
# gRPC Fixtures
# ============================================================================


@pytest.fixture
def grpc_available() -> bool:
    """Check if gRPC is available."""
    try:
        import grpc

        return True
    except ImportError:
        return False


@pytest.fixture
def mock_grpc_channel():
    """Mock gRPC channel for unit tests."""
    channel = MagicMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture
def mock_grpc_stub(mock_extraction_result):
    """Mock gRPC stub for unit tests."""
    stub = MagicMock()

    # Mock Health response
    health_response = MagicMock()
    health_response.status = "healthy"
    health_response.dependencies = {"minio": True, "redis": True}
    health_response.rust_available = True
    health_response.rust_module_version = "0.1.0"
    health_response.capabilities = {"pdf_extraction": "rust"}
    stub.Health = AsyncMock(return_value=health_response)

    # Mock Extract response
    extract_response = MagicMock()
    extract_response.result.file_id = "test123"
    extract_response.result.total_pages = 2
    extract_response.result.ocr_applied = False
    extract_response.result.source = "rust"
    extract_response.result.processing_time_ms = 100
    extract_response.result.pages = []
    stub.Extract = AsyncMock(return_value=extract_response)

    # Mock Thumbnail response
    thumb_response = MagicMock()
    thumb_response.thumbnail = b"\x89PNG"
    thumb_response.content_type = "image/jpeg"
    thumb_response.width = 200
    thumb_response.height = 200
    stub.GenerateThumbnail = AsyncMock(return_value=thumb_response)

    return stub


# ============================================================================
# Service Fixtures
# ============================================================================


@pytest.fixture
def file_manager_url() -> str:
    """File manager service URL for integration tests."""
    return os.getenv("FILE_MANAGER_URL", "http://localhost:8001")


@pytest.fixture
def file_manager_grpc_host() -> str:
    """File manager gRPC host for integration tests."""
    return os.getenv("FILE_MANAGER_GRPC_HOST", "localhost")


@pytest.fixture
def file_manager_grpc_port() -> int:
    """File manager gRPC port for integration tests."""
    return int(os.getenv("FILE_MANAGER_GRPC_PORT", "50052"))


# ============================================================================
# Async Fixtures
# ============================================================================


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_http_client():
    """Async HTTP client for integration tests."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client
