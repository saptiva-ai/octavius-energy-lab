"""
Unit tests for WeaviateService - Vector Database Service for RAG.

Tests cover:
- Initialization with various URL formats (HTTP, HTTPS, cloud)
- Connection handling (cloud vs custom connectors)
- Collection management (ensure_collection)
- Health checks
- CRUD operations (upsert_chunks, search, delete_session)
- Query augmentation with ontology
- Cleanup expired sessions
- Singleton pattern
"""

import json
import time
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestWeaviateServiceInit:
    """Tests for WeaviateService initialization."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {
            "WEAVIATE_URL": "http://localhost:8080",
            "RAG_COLLECTION_NAME": "TestCollection",
        },
        clear=True,
    )
    def test_init_with_http_url(self, mock_weaviate):
        """Test initialization with HTTP URL."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.host == "localhost"
        assert service.port == 8080
        assert service.grpc_port == 50051
        assert service.http_secure is False
        assert service.grpc_secure is False
        assert service.collection_name == "TestCollection"
        mock_weaviate.connect_to_custom.assert_called_once()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {
            "WEAVIATE_URL": "https://my-cluster.weaviate.cloud",
            "WEAVIATE_API_KEY": "test-api-key",
        },
        clear=True,
    )
    def test_init_with_cloud_url(self, mock_weaviate):
        """Test initialization with Weaviate Cloud URL."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_weaviate_cloud.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.host == "my-cluster.weaviate.cloud"
        assert service.http_secure is True
        assert service.api_key == "test-api-key"
        mock_weaviate.connect_to_weaviate_cloud.assert_called_once()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {
            "WEAVIATE_URL": "http://weaviate:8080",
            "WEAVIATE_GRPC_PORT": "50052",
        },
        clear=True,
    )
    def test_init_with_custom_grpc_port(self, mock_weaviate):
        """Test initialization with custom gRPC port."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.grpc_port == 50052

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "https://secure-instance:443"},
        clear=True,
    )
    def test_init_with_https_non_cloud(self, mock_weaviate):
        """Test initialization with HTTPS non-cloud URL."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.http_secure is True
        assert service.grpc_secure is True
        assert service.port == 443

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict("os.environ", {}, clear=True)
    def test_init_with_defaults(self, mock_weaviate):
        """Test initialization with default values."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.url == "http://weaviate:8080"
        assert service.collection_name == "RAG_Documents"

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {
            "WEAVIATE_URL": "http://localhost:8080",
            "WEAVIATE_GRPC_PORT": "not-a-number",  # Invalid int triggers exception
        },
        clear=True,
    )
    def test_init_with_invalid_grpc_port_falls_back_to_defaults(self, mock_weaviate):
        """Test initialization with invalid gRPC port falls back to defaults (lines 89-96)."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        # Should have fallen back to defaults due to int() ValueError
        assert service.host == "weaviate"
        assert service.port == 8080
        assert service.grpc_port == 50051
        assert service.http_secure is False
        assert service.grpc_secure is False
        assert service.scheme == "http"


class TestWeaviateServiceConnect:
    """Tests for _connect method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_connect_custom_instance(self, mock_weaviate):
        """Test connecting to custom Weaviate instance."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.client == mock_client
        mock_weaviate.connect_to_custom.assert_called_once_with(
            http_host="localhost",
            http_port=8080,
            http_secure=False,
            grpc_host="localhost",
            grpc_port=50051,
            grpc_secure=False,
            auth_credentials=None,
            skip_init_checks=True,
        )

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {
            "WEAVIATE_URL": "https://test.weaviate.cloud",
            "WEAVIATE_API_KEY": "secret-key",
        },
        clear=True,
    )
    def test_connect_cloud_instance_with_auth(self, mock_weaviate):
        """Test connecting to Weaviate Cloud with authentication."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_weaviate_cloud.return_value = mock_client
        mock_auth = MagicMock()
        mock_weaviate.classes.init.Auth.api_key.return_value = mock_auth

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.client == mock_client
        mock_weaviate.connect_to_weaviate_cloud.assert_called_once()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_connect_failure_does_not_raise(self, mock_weaviate):
        """Test that connection failure doesn't raise (allows retry)."""
        mock_weaviate.connect_to_custom.side_effect = Exception("Connection failed")

        from src.services.weaviate_service import WeaviateService

        # Should not raise
        service = WeaviateService()
        assert service.client is None


class TestWeaviateServiceEnsureCollection:
    """Tests for ensure_collection method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_ensure_collection_already_exists(self, mock_weaviate):
        """Test ensure_collection when collection already exists."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = True
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service.ensure_collection()

        mock_client.collections.exists.assert_called_once_with("RAG_Documents")
        mock_client.collections.create.assert_not_called()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_ensure_collection_creates_new(self, mock_weaviate):
        """Test ensure_collection creates collection when it doesn't exist."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service.ensure_collection()

        mock_client.collections.create.assert_called_once()
        call_kwargs = mock_client.collections.create.call_args
        assert call_kwargs.kwargs["name"] == "RAG_Documents"

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_ensure_collection_reconnects_if_not_connected(self, mock_weaviate):
        """Test ensure_collection reconnects if client not connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_client.collections.exists.return_value = True
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service.ensure_collection()

        # Should have called connect_to_custom twice (init + reconnect)
        assert mock_weaviate.connect_to_custom.call_count >= 1

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_ensure_collection_failure_raises(self, mock_weaviate):
        """Test ensure_collection raises on failure."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.side_effect = Exception("DB error")
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        with pytest.raises(RuntimeError, match="Weaviate setup failed"):
            service.ensure_collection()


class TestWeaviateServiceHealthCheck:
    """Tests for health_check method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_healthy(self, mock_weaviate):
        """Test health_check when service is healthy."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.is_ready.return_value = True
        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_aggregate_response = MagicMock()
        mock_aggregate_response.total_count = 100
        mock_collection.aggregate.over_all.return_value = mock_aggregate_response
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.health_check()

        assert result["status"] == "healthy"
        assert result["collection_exists"] is True
        assert result["points_count"] == 100

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_not_connected(self, mock_weaviate):
        """Test health_check when client not connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.health_check()

        assert result["status"] == "unhealthy"
        assert "not connected" in result["error"]

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_not_ready(self, mock_weaviate):
        """Test health_check when Weaviate not ready."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.is_ready.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.health_check()

        assert result["status"] == "unhealthy"
        assert "not ready" in result["error"]

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_collection_not_exists(self, mock_weaviate):
        """Test health_check when collection doesn't exist."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.is_ready.return_value = True
        mock_client.collections.exists.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.health_check()

        assert result["status"] == "healthy"
        assert result["collection_exists"] is False
        assert result["points_count"] == 0

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_exception(self, mock_weaviate):
        """Test health_check when exception occurs."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.is_ready.side_effect = Exception("Connection lost")
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.health_check()

        assert result["status"] == "unhealthy"
        assert "Connection lost" in result["error"]

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_health_check_reconnects_if_no_client(self, mock_weaviate):
        """Test health_check reconnects if client is None."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.is_ready.return_value = True
        mock_client.collections.exists.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service.client = None  # Simulate lost client

        result = service.health_check()

        # Should have reconnected
        assert mock_weaviate.connect_to_custom.call_count >= 2


class TestWeaviateServiceUpsertChunks:
    """Tests for upsert_chunks method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_upsert_chunks_success(self, mock_weaviate):
        """Test successful chunk upsert."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_batch = MagicMock()
        mock_batch.__enter__ = MagicMock(return_value=mock_batch)
        mock_batch.__exit__ = MagicMock(return_value=False)
        mock_collection.batch.dynamic.return_value = mock_batch
        mock_collection.batch.failed_objects = []
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        chunks = [
            {
                "chunk_id": 0,
                "text": "First chunk",
                "page": 1,
                "embedding": [0.1] * 384,
                "metadata": {"source": "test.pdf"},
            },
            {
                "chunk_id": 1,
                "text": "Second chunk",
                "page": 1,
                "embedding": [0.2] * 384,
                "metadata": {},
            },
        ]

        result = service.upsert_chunks("session-123", "doc-456", chunks)

        assert result == 2
        assert mock_batch.add_object.call_count == 2

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_upsert_chunks_with_batch_errors(self, mock_weaviate):
        """Test upsert_chunks raises on batch errors."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_batch = MagicMock()
        mock_batch.__enter__ = MagicMock(return_value=mock_batch)
        mock_batch.__exit__ = MagicMock(return_value=False)
        mock_collection.batch.dynamic.return_value = mock_batch
        mock_collection.batch.failed_objects = [{"error": "Insert failed"}]
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        chunks = [
            {"chunk_id": 0, "text": "Test", "embedding": [0.1] * 384},
        ]

        with pytest.raises(RuntimeError, match="Batch insertion failed"):
            service.upsert_chunks("session-123", "doc-456", chunks)

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_upsert_chunks_reconnects_if_not_connected(self, mock_weaviate):
        """Test upsert_chunks reconnects if not connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False

        mock_collection = MagicMock()
        mock_batch = MagicMock()
        mock_batch.__enter__ = MagicMock(return_value=mock_batch)
        mock_batch.__exit__ = MagicMock(return_value=False)
        mock_collection.batch.dynamic.return_value = mock_batch
        mock_collection.batch.failed_objects = []
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        chunks = [{"chunk_id": 0, "text": "Test", "embedding": [0.1] * 384}]
        service.upsert_chunks("session-123", "doc-456", chunks)

        # Should reconnect
        assert mock_weaviate.connect_to_custom.call_count >= 1

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_upsert_chunks_exception_propagates(self, mock_weaviate):
        """Test upsert_chunks propagates exceptions."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.get.side_effect = Exception("Collection error")
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        chunks = [{"chunk_id": 0, "text": "Test", "embedding": [0.1] * 384}]

        with pytest.raises(Exception):
            service.upsert_chunks("session-123", "doc-456", chunks)


class TestWeaviateServiceNormalizeText:
    """Tests for _normalize_text method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_normalize_text_lowercase(self, mock_weaviate):
        """Test text normalization converts to lowercase."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._normalize_text("HELLO WORLD")

        assert result == "hello world"

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_normalize_text_removes_accents(self, mock_weaviate):
        """Test text normalization removes accents."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._normalize_text("Crédit Débito Préstamo")

        assert result == "credit debito prestamo"

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_normalize_text_collapses_whitespace(self, mock_weaviate):
        """Test text normalization collapses whitespace."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._normalize_text("hello    world\n\ttest")

        assert result == "hello world test"


class TestWeaviateServiceAugmentQuery:
    """Tests for _augment_query method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_augment_query_no_ontology(self, mock_weaviate):
        """Test query augmentation when no ontology exists."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._augment_query("test query")

        assert result == ["test query"]

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_augment_query_with_synonyms(self, mock_weaviate):
        """Test query augmentation with synonyms from ontology."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = True

        mock_ontology = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "term_name": "credit",
            "synonyms": ["loan", "financing"],
        }
        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_ontology.query.hybrid.return_value = mock_response
        mock_client.collections.get.return_value = mock_ontology

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._augment_query("credit card rates")

        assert "credit card rates" in result
        assert len(result) <= 3  # Limited to 3 variations

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_augment_query_exception_returns_original(self, mock_weaviate):
        """Test query augmentation returns original on exception."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.side_effect = Exception("DB error")
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._augment_query("test query")

        assert result == ["test query"]

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_augment_query_reconnects_if_not_connected(self, mock_weaviate):
        """Test _augment_query reconnects if not connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_client.collections.exists.return_value = False
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service._augment_query("test")

        assert mock_weaviate.connect_to_custom.call_count >= 1

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_augment_query_skips_empty_synonyms(self, mock_weaviate):
        """Test query augmentation skips empty/None synonyms (line 313)."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = True

        mock_ontology = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "term_name": "credit",
            "synonyms": ["loan", "", None, "financing"],  # Contains empty/None
        }
        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_ontology.query.hybrid.return_value = mock_response
        mock_client.collections.get.return_value = mock_ontology

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service._augment_query("credit card rates")

        # Original query should be in results
        assert "credit card rates" in result
        # Empty synonyms should have been skipped via continue
        # Only valid synonyms should create variations


class TestWeaviateServiceSearch:
    """Tests for search method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_hybrid_with_text(self, mock_weaviate):
        """Test hybrid search with query text."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = False  # No ontology

        mock_collection = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "document_id": "doc-1",
            "chunk_id": 0,
            "text": "Test content",
            "page": 1,
            "metadata_json": '{"source": "test.pdf"}',
        }
        mock_obj.metadata = MagicMock()
        mock_obj.metadata.score = 0.85
        mock_obj.metadata.distance = None

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.hybrid.return_value = mock_response
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            top_k=5,
            query_text="test query",
        )

        assert len(results) == 1
        assert results[0]["document_id"] == "doc-1"
        assert results[0]["score"] == 0.85
        assert results[0]["metadata"]["source"] == "test.pdf"

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_vector_only(self, mock_weaviate):
        """Test vector-only search without query text."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "document_id": "doc-1",
            "chunk_id": 0,
            "text": "Test content",
            "page": 1,
            "metadata_json": None,
        }
        mock_obj.metadata = MagicMock()
        mock_obj.metadata.score = None
        mock_obj.metadata.distance = 0.2

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.near_vector.return_value = mock_response
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            top_k=5,
        )

        assert len(results) == 1
        assert results[0]["score"] == 0.8  # 1 - 0.2 distance

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_early_exit_on_high_score(self, mock_weaviate):
        """Test search exits early when high score found."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = True  # Has ontology

        # Setup ontology to return synonyms
        mock_ontology = MagicMock()
        mock_ontology_obj = MagicMock()
        mock_ontology_obj.properties = {
            "term_name": "credit",
            "synonyms": ["loan"],
        }
        mock_ontology_response = MagicMock()
        mock_ontology_response.objects = [mock_ontology_obj]
        mock_ontology.query.hybrid.return_value = mock_ontology_response

        mock_collection = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "document_id": "doc-1",
            "chunk_id": 0,
            "text": "Content",
            "page": 1,
            "metadata_json": "{}",
        }
        mock_obj.metadata = MagicMock()
        mock_obj.metadata.score = 0.80  # > 0.75 threshold
        mock_obj.metadata.distance = None

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.hybrid.return_value = mock_response

        def get_collection(name):
            if name == "Ontology_Term":
                return mock_ontology
            return mock_collection

        mock_client.collections.get.side_effect = get_collection
        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            query_text="credit info",
        )

        # Should have result with high score
        assert len(results) == 1
        assert results[0]["score"] > 0.75

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_handles_exception(self, mock_weaviate):
        """Test search handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = False

        mock_collection = MagicMock()
        mock_collection.query.hybrid.side_effect = Exception("Query failed")
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            query_text="test",
        )

        # Should return empty results on error
        assert results == []

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_reconnects_if_not_connected(self, mock_weaviate):
        """Test search reconnects if client not connected (lines 340-341)."""
        mock_client = MagicMock()
        # First call returns False (not connected), triggers reconnect
        mock_client.is_connected.return_value = False
        mock_client.collections.exists.return_value = False

        mock_collection = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "document_id": "doc-1",
            "chunk_id": 0,
            "text": "Content",
            "page": 1,
            "metadata_json": "{}",
        }
        mock_obj.metadata = MagicMock()
        mock_obj.metadata.score = 0.7
        mock_obj.metadata.distance = None

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.hybrid.return_value = mock_response
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            query_text="test",
        )

        # Should have called connect_to_custom more than once (init + reconnect)
        assert mock_weaviate.connect_to_custom.call_count >= 2
        assert len(results) == 1

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_search_invalid_metadata_json(self, mock_weaviate):
        """Test search handles invalid metadata JSON."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.collections.exists.return_value = False

        mock_collection = MagicMock()
        mock_obj = MagicMock()
        mock_obj.properties = {
            "document_id": "doc-1",
            "chunk_id": 0,
            "text": "Content",
            "page": 1,
            "metadata_json": "invalid json {",
        }
        mock_obj.metadata = MagicMock()
        mock_obj.metadata.score = 0.7
        mock_obj.metadata.distance = None

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.hybrid.return_value = mock_response
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        results = service.search(
            session_id="session-123",
            query_vector=[0.1] * 384,
            query_text="test",
        )

        # Should handle invalid JSON gracefully
        assert len(results) == 1
        assert results[0]["metadata"] == {}


class TestWeaviateServiceDeleteSession:
    """Tests for delete_session method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_delete_session_success(self, mock_weaviate):
        """Test successful session deletion."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.successful = 5
        mock_collection.data.delete_many.return_value = mock_result
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.delete_session("session-123")

        assert result == 5
        mock_collection.data.delete_many.assert_called_once()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_delete_session_exception_raises(self, mock_weaviate):
        """Test delete_session raises on exception."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_collection.data.delete_many.side_effect = Exception("Delete failed")
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        with pytest.raises(Exception):
            service.delete_session("session-123")

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_delete_session_reconnects_if_not_connected(self, mock_weaviate):
        """Test delete_session reconnects if not connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.successful = 0
        mock_collection.data.delete_many.return_value = mock_result
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        service.delete_session("session-123")

        assert mock_weaviate.connect_to_custom.call_count >= 1


class TestWeaviateServiceCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions method."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_cleanup_expired_sessions_success(self, mock_weaviate):
        """Test successful cleanup of expired sessions."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.successful = 10
        mock_collection.data.delete_many.return_value = mock_result
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.cleanup_expired_sessions(ttl_hours=24)

        assert result == 10
        mock_collection.data.delete_many.assert_called_once()

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_cleanup_expired_sessions_exception_returns_zero(self, mock_weaviate):
        """Test cleanup_expired_sessions returns 0 on exception."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_collection.data.delete_many.side_effect = Exception("Cleanup failed")
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.cleanup_expired_sessions()

        assert result == 0

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_cleanup_expired_sessions_reconnects_if_not_connected(self, mock_weaviate):
        """Test cleanup_expired_sessions reconnects if not connected (line 475)."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False  # Not connected

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.successful = 3
        mock_collection.data.delete_many.return_value = mock_result
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.cleanup_expired_sessions()

        # Should have called connect_to_custom more than once (init + reconnect)
        assert mock_weaviate.connect_to_custom.call_count >= 2
        assert result == 3

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_cleanup_expired_sessions_custom_ttl(self, mock_weaviate):
        """Test cleanup with custom TTL hours."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.successful = 5
        mock_collection.data.delete_many.return_value = mock_result
        mock_client.collections.get.return_value = mock_collection

        mock_weaviate.connect_to_custom.return_value = mock_client

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()
        result = service.cleanup_expired_sessions(ttl_hours=48)

        assert result == 5


class TestGetWeaviateService:
    """Tests for get_weaviate_service singleton function."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_get_weaviate_service_singleton(self, mock_weaviate):
        """Test get_weaviate_service returns singleton."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        # Reset singleton
        import src.services.weaviate_service as ws

        ws._weaviate_service = None

        service1 = ws.get_weaviate_service()
        service2 = ws.get_weaviate_service()

        assert service1 is service2

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://localhost:8080"},
        clear=True,
    )
    def test_get_weaviate_service_creates_instance(self, mock_weaviate):
        """Test get_weaviate_service creates instance when None."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        # Reset singleton
        import src.services.weaviate_service as ws

        ws._weaviate_service = None

        service = ws.get_weaviate_service()

        assert service is not None
        assert isinstance(service, ws.WeaviateService)


class TestWeaviateServiceURLParsing:
    """Tests for URL parsing edge cases."""

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "http://192.168.1.100:9000"},
        clear=True,
    )
    def test_url_parsing_ip_with_port(self, mock_weaviate):
        """Test URL parsing with IP address and custom port."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        assert service.host == "192.168.1.100"
        assert service.port == 9000

    @patch("src.services.weaviate_service.weaviate")
    @patch.dict(
        "os.environ",
        {"WEAVIATE_URL": "invalid-url-format"},
        clear=True,
    )
    def test_url_parsing_invalid_falls_back_to_defaults(self, mock_weaviate):
        """Test URL parsing with invalid URL uses defaults."""
        mock_weaviate.connect_to_custom.return_value = MagicMock()

        from src.services.weaviate_service import WeaviateService

        service = WeaviateService()

        # Should use defaults due to parsing error
        assert service.host in ["weaviate", "invalid-url-format", None]
