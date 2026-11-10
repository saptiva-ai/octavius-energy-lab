"""
Pytest configuration and fixtures for API tests.

This file is automatically loaded by pytest before running tests.
It configures the Python path to enable proper imports.
"""

import sys
from pathlib import Path

# Add the app directory to Python path (not src/)
# This allows tests to import as: from src.main import app
# This way, src is treated as a package and relative imports work
app_path = Path(__file__).parent.parent
if str(app_path) not in sys.path:
    sys.path.append(str(app_path))

print(f"✓ Added {app_path} to PYTHONPATH for tests (import as: from src.module import ...)")

import pytest
import pytest_asyncio

from src.mcp_integration.versioning import versioned_registry

# Lazy import for motor/beanie - only needed for integration tests
# This prevents import errors in unit tests that don't have motor installed
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from beanie import init_beanie
    from src.core.database import Database
    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialize_database():
    """Initialize database connection for all tests (skip if MONGODB_URL not set)."""
    import os
    mongodb_url = os.getenv("MONGODB_URL")
    if mongodb_url and MOTOR_AVAILABLE:
        try:
            await Database.connect_to_mongo()
            yield
            await Database.close_mongo_connection()
        except Exception:
            # Skip database initialization if connection fails (for unit tests)
            yield
    else:
        # Skip database initialization for unit tests that don't need it
        yield


@pytest.fixture(autouse=True)
def reset_versioned_registry():
    """Ensure versioned tool registry is isolated per test."""
    versioned_registry._tools.clear()
    versioned_registry._latest.clear()
    versioned_registry._deprecated.clear()
    yield
    versioned_registry._tools.clear()
    versioned_registry._latest.clear()
    versioned_registry._deprecated.clear()


# ============================================================================
# Resource Lifecycle Management Test Fixtures
# ============================================================================

from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta
import hashlib
import os

# Set test environment
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "true")


@pytest.fixture
def mock_redis_cache():
    """Mock Redis cache for testing."""
    mock_cache = MagicMock()
    mock_cache.client = MagicMock()
    mock_cache.client.info = AsyncMock(return_value={"used_memory": 50 * 1024 * 1024})
    mock_cache.client.dbsize = AsyncMock(return_value=1000)
    mock_cache.client.scan = AsyncMock(return_value=(0, []))
    mock_cache.client.ttl = AsyncMock(return_value=3600)
    mock_cache.client.delete = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    return mock_cache


@pytest.fixture
def mock_minio_service():
    """Mock MinIO service for testing."""
    mock_service = AsyncMock()
    mock_service.download_to_path = AsyncMock()
    mock_service.delete_file = AsyncMock()
    mock_service.upload_file = AsyncMock()
    return mock_service


@pytest.fixture
def mock_file_storage():
    """Mock file storage for testing."""
    mock_storage = AsyncMock()
    mock_storage.save_upload = AsyncMock(return_value=(
        "uploads", "test_key", "test.pdf", 1000
    ))
    mock_storage.delete_file = AsyncMock()
    return mock_storage


@pytest.fixture
def sample_document():
    """Create sample document for testing."""
    from src.models.document import Document, DocumentStatus

    return Document(
        filename="test_document.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        minio_key="uploads/test.pdf",
        minio_bucket="uploads",
        status=DocumentStatus.READY,
        user_id="user123",
        created_at=datetime.utcnow(),
        metadata={"file_hash": "abc123def456"}
    )


@pytest.fixture
def sample_old_document():
    """Create old document for cleanup testing."""
    from src.models.document import Document, DocumentStatus

    return Document(
        filename="old_document.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        minio_key="uploads/old.pdf",
        minio_bucket="uploads",
        status=DocumentStatus.READY,
        user_id="user123",
        created_at=datetime.utcnow() - timedelta(days=10),
        metadata={"file_hash": "old123def456"}
    )


@pytest.fixture
def sample_pdf_content():
    """Sample PDF content for testing."""
    return b"%PDF-1.4\n%Test PDF\nHello World\nThis is a test PDF content."


@pytest.fixture
def sample_file_hash(sample_pdf_content):
    """Compute hash of sample PDF."""
    return hashlib.sha256(sample_pdf_content).hexdigest()


# Test data fixtures

@pytest.fixture
def test_pdfs_dir():
    """Path to test PDFs directory."""
    return Path(__file__).parent.parent.parent.parent / "packages/tests-e2e/tests/data/sample-docs"


@pytest.fixture
def sample_uso_ia_pdf(test_pdfs_dir):
    """Path to sample_uso_ia.pdf test file."""
    return test_pdfs_dir / "sample_uso_ia.pdf"


# Pytest configuration

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "regression: marks tests as regression tests"
    )
    config.addinivalue_line(
        "markers", "smoke: marks tests as smoke tests (quick connectivity checks)"
    )
    config.addinivalue_line(
        "markers", "grpc: marks tests as gRPC-related tests"
    )
    config.addinivalue_line(
        "markers", "embedding: marks tests as embedding-related tests"
    )


# ============================================================================
# Embedding Service Test Fixtures (OPTIMIZATION 2026-01)
# ============================================================================


@pytest.fixture
def mock_embedding_grpc_client():
    """Mock gRPC client for embedding-service."""
    mock_client = AsyncMock()
    # Default: return 384-dim embeddings
    mock_client.encode = AsyncMock(
        return_value=[[0.1] * 384, [0.2] * 384]
    )
    mock_client.health_check = AsyncMock(
        return_value={"status": "healthy", "model_loaded": True}
    )
    return mock_client


@pytest.fixture
def mock_embedding_http_client():
    """Mock HTTP client for embedding-service."""
    mock_client = AsyncMock()
    mock_client.encode = AsyncMock(
        return_value={"embeddings": [[0.1] * 384, [0.2] * 384]}
    )
    mock_client.health = AsyncMock(
        return_value={"status": "healthy"}
    )
    return mock_client


@pytest.fixture
def sample_texts_for_embedding():
    """Sample texts for embedding tests."""
    return [
        "¿Qué es la disponibilidad?",
        "Explica el índice de faltantes",
        "What is the non-performing loan ratio?",
    ]


@pytest.fixture
def sample_long_text_for_chunking():
    """Long text that will be chunked into multiple pieces."""
    base = "Este es un texto de prueba para verificar el chunking. "
    return base * 200  # ~10000 chars -> multiple chunks


@pytest.fixture
def expected_embedding_dim():
    """Expected embedding dimension for paraphrase-multilingual-MiniLM-L12-v2."""
    return 384
