"""
Unit Tests for ResourceLifecycleManager

Tests:
- compute_file_hash: SHA256 hash computation
- check_duplicate_file: Duplicate detection logic
- get_resource_metrics: Metrics calculation
- schedule_cleanup_task: Queue management
- cleanup_expired_resources: Cleanup logic
- _get_minio_metrics: MinIO storage metrics
- _get_mongodb_metrics: MongoDB metadata metrics
- get_resource_manager: Singleton access
"""

import pytest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.resource_lifecycle_manager import (
    ResourceLifecycleManager,
    ResourceType,
    CleanupPriority,
    ResourceMetrics,
    CleanupTask,
    get_resource_manager,
)

pytestmark = [pytest.mark.unit]


class TestResourceLifecycleManager:
    """Unit tests for ResourceLifecycleManager."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_compute_file_hash(self, manager):
        """Test SHA256 hash computation."""
        # Arrange
        file_content = b"Hello World"
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash
        assert len(result_hash) == 64  # SHA256 produces 64 hex chars

    @pytest.mark.asyncio
    async def test_compute_file_hash_empty_file(self, manager):
        """Test hash computation for empty file."""
        # Arrange
        file_content = b""
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash

    @pytest.mark.asyncio
    async def test_compute_file_hash_large_file(self, manager):
        """Test hash computation for large file."""
        # Arrange - 10 MB file
        file_content = b"x" * (10 * 1024 * 1024)
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash

    @pytest.mark.asyncio
    async def test_check_duplicate_file_found(self, manager):
        """Test duplicate detection when file exists."""
        # Arrange
        file_hash = "abc123def456"
        user_id = "user123"
        mock_doc = MagicMock()
        mock_doc.id = "doc123"

        with patch("src.models.document.Document") as mock_document:
            mock_document.find_one = AsyncMock(return_value=mock_doc)

            # Act
            result = await manager.check_duplicate_file(file_hash, user_id)

            # Assert
            assert result == "doc123"
            mock_document.find_one.assert_called_once_with({
                "metadata.file_hash": file_hash,
                "user_id": user_id
            })

    @pytest.mark.asyncio
    async def test_check_duplicate_file_not_found(self, manager):
        """Test duplicate detection when file doesn't exist."""
        # Arrange
        file_hash = "abc123def456"
        user_id = "user123"

        with patch("src.models.document.Document") as mock_document:
            mock_document.find_one = AsyncMock(return_value=None)

            # Act
            result = await manager.check_duplicate_file(file_hash, user_id)

            # Assert
            assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_metrics(self, manager):
        """Test Redis metrics calculation."""
        # Arrange
        mock_cache = MagicMock()
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": 128 * 1024 * 1024  # 128 MB
        })
        mock_cache.client.dbsize = AsyncMock(return_value=5000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get_cache:
            mock_get_cache.return_value = mock_cache

            # Act
            metrics = await manager._get_redis_metrics()

            # Assert
            assert isinstance(metrics, ResourceMetrics)
            assert metrics.resource_type == ResourceType.REDIS_CACHE
            assert metrics.total_items == 5000
            assert metrics.total_size_bytes == 128 * 1024 * 1024
            assert 0 <= metrics.usage_percentage <= 1
            assert isinstance(metrics.cleanup_priority, CleanupPriority)

    @pytest.mark.asyncio
    async def test_get_redis_metrics_critical_usage(self, manager):
        """Test Redis metrics when usage is critical."""
        # Arrange - 95% usage
        mock_cache = MagicMock()
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": int(0.95 * manager.max_redis_memory_mb * 1024 * 1024)
        })
        mock_cache.client.dbsize = AsyncMock(return_value=10000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get_cache:
            mock_get_cache.return_value = mock_cache

            # Act
            metrics = await manager._get_redis_metrics()

            # Assert
            assert metrics.cleanup_priority == CleanupPriority.CRITICAL
            assert metrics.usage_percentage >= manager.cleanup_threshold_critical

    @pytest.mark.asyncio
    async def test_get_weaviate_metrics(self, manager):
        """Test Weaviate metrics calculation."""
        # Arrange
        mock_service = MagicMock()
        mock_service.health_check = MagicMock(return_value={"points_count": 1500})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get_service:
            mock_get_service.return_value = mock_service

            # Act
            metrics = await manager._get_weaviate_metrics()

            # Assert
            assert isinstance(metrics, ResourceMetrics)
            assert metrics.resource_type == ResourceType.WEAVIATE_VECTORS
            assert metrics.total_items == 1500
            assert metrics.total_size_bytes == 1500 * 384 * 4  # 384-dim vectors
            assert isinstance(metrics.cleanup_priority, CleanupPriority)

    @pytest.mark.asyncio
    async def test_schedule_cleanup_task(self, manager):
        """Test scheduling cleanup task."""
        # Arrange
        assert len(manager.cleanup_queue) == 0

        # Act
        await manager.schedule_cleanup_task(
            resource_type=ResourceType.REDIS_CACHE,
            target_id="key123",
            priority=CleanupPriority.HIGH,
            reason="High memory usage"
        )

        # Assert
        assert len(manager.cleanup_queue) == 1
        task = manager.cleanup_queue[0]
        assert isinstance(task, CleanupTask)
        assert task.resource_type == ResourceType.REDIS_CACHE
        assert task.priority == CleanupPriority.HIGH
        assert task.reason == "High memory usage"

    @pytest.mark.asyncio
    async def test_schedule_cleanup_task_ordering(self, manager):
        """Test that cleanup queue is ordered by priority."""
        # Arrange & Act - Schedule tasks in reverse priority order
        await manager.schedule_cleanup_task(
            ResourceType.REDIS_CACHE, "1", CleanupPriority.LOW, "Low"
        )
        await manager.schedule_cleanup_task(
            ResourceType.WEAVIATE_VECTORS, "2", CleanupPriority.CRITICAL, "Critical"
        )
        await manager.schedule_cleanup_task(
            ResourceType.MINIO_FILES, "3", CleanupPriority.HIGH, "High"
        )

        # Assert - Queue should be ordered: CRITICAL, HIGH, LOW
        assert len(manager.cleanup_queue) == 3
        assert manager.cleanup_queue[0].priority == CleanupPriority.CRITICAL
        assert manager.cleanup_queue[1].priority == CleanupPriority.HIGH
        assert manager.cleanup_queue[2].priority == CleanupPriority.LOW

    @pytest.mark.asyncio
    async def test_cleanup_redis_cache(self, manager):
        """Test Redis cache cleanup."""
        # Arrange
        mock_cache = MagicMock()

        # Simulate keys without TTL
        mock_cache.client.scan = AsyncMock(side_effect=[
            (0, [b"doc_segments:key1", b"doc_segments:key2"]),  # First scan
        ])
        mock_cache.client.ttl = AsyncMock(side_effect=[-1, -1])  # No TTL
        mock_cache.client.delete = AsyncMock()

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get_cache:
            mock_get_cache.return_value = mock_cache

            # Act
            deleted_count = await manager._cleanup_redis_cache()

            # Assert
            assert deleted_count == 2
            assert mock_cache.client.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_weaviate_vectors(self, manager):
        """Test Weaviate vectors cleanup."""
        # Arrange
        mock_service = MagicMock()
        mock_service.cleanup_expired_sessions = MagicMock(return_value=150)

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get_service:
            mock_get_service.return_value = mock_service

            # Act
            deleted_count = await manager._cleanup_weaviate_vectors()

            # Assert
            assert deleted_count == 150
            mock_service.cleanup_expired_sessions.assert_called_once_with(
                ttl_hours=manager.weaviate_ttl_hours
            )

    @pytest.mark.asyncio
    async def test_cleanup_minio_files(self, manager):
        """Test MinIO files cleanup."""
        # Arrange
        cutoff_time = datetime.utcnow() - timedelta(days=manager.minio_ttl_days)

        # Create mock old document
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = cutoff_time - timedelta(days=1)
        mock_doc.delete = AsyncMock()

        mock_storage = AsyncMock()

        with patch("src.models.document.Document") as mock_document, \
             patch("src.models.chat.ChatSession") as mock_chat_session, \
             patch("src.services.file_storage.get_file_storage") as mock_get_storage:

            mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])
            mock_chat_session.find.return_value.count = AsyncMock(return_value=0)
            mock_get_storage.return_value = mock_storage

            # Act
            deleted_count = await manager._cleanup_minio_files()

            # Assert
            assert deleted_count == 1
            mock_storage.delete_file.assert_called_once_with("uploads/doc123.pdf")
            mock_doc.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cleanup_queue(self, manager):
        """Test processing cleanup queue."""
        # Arrange
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_weaviate_vectors = AsyncMock(return_value=10)

        await manager.schedule_cleanup_task(
            ResourceType.REDIS_CACHE, "all", CleanupPriority.HIGH, "Test"
        )
        await manager.schedule_cleanup_task(
            ResourceType.WEAVIATE_VECTORS, "all", CleanupPriority.CRITICAL, "Test"
        )

        # Act
        await manager.process_cleanup_queue(max_tasks=2)

        # Assert
        assert len(manager.cleanup_queue) == 0
        manager._cleanup_redis_cache.assert_called_once()
        manager._cleanup_weaviate_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cleanup_queue_max_tasks(self, manager):
        """Test that process_cleanup_queue respects max_tasks limit."""
        # Arrange
        manager._cleanup_redis_cache = AsyncMock(return_value=0)

        # Schedule 5 tasks
        for i in range(5):
            await manager.schedule_cleanup_task(
                ResourceType.REDIS_CACHE, f"task{i}", CleanupPriority.LOW, "Test"
            )

        # Act - Process only 3 tasks
        await manager.process_cleanup_queue(max_tasks=3)

        # Assert
        assert len(manager.cleanup_queue) == 2  # 5 - 3 = 2 remaining
        assert manager._cleanup_redis_cache.call_count == 3


class TestResourceMetrics:
    """Unit tests for ResourceMetrics dataclass."""

    def test_resource_metrics_creation(self):
        """Test creating ResourceMetrics instance."""
        # Act
        metrics = ResourceMetrics(
            resource_type=ResourceType.REDIS_CACHE,
            total_items=1000,
            total_size_bytes=50 * 1024 * 1024,
            oldest_item_age_hours=2.5,
            usage_percentage=0.45,
            cleanup_priority=CleanupPriority.MEDIUM
        )

        # Assert
        assert metrics.resource_type == ResourceType.REDIS_CACHE
        assert metrics.total_items == 1000
        assert metrics.total_size_bytes == 50 * 1024 * 1024
        assert metrics.oldest_item_age_hours == 2.5
        assert metrics.usage_percentage == 0.45
        assert metrics.cleanup_priority == CleanupPriority.MEDIUM


class TestCleanupTask:
    """Unit tests for CleanupTask dataclass."""

    def test_cleanup_task_creation(self):
        """Test creating CleanupTask instance."""
        # Arrange
        now = datetime.utcnow()

        # Act
        task = CleanupTask(
            priority=CleanupPriority.HIGH,
            resource_type=ResourceType.WEAVIATE_VECTORS,
            target_id="session123",
            created_at=now,
            reason="High resource usage: 80%"
        )

        # Assert
        assert task.priority == CleanupPriority.HIGH
        assert task.resource_type == ResourceType.WEAVIATE_VECTORS
        assert task.target_id == "session123"
        assert task.created_at == now
        assert task.reason == "High resource usage: 80%"


class TestGetResourceMetrics:
    """Tests for get_resource_metrics method."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_get_redis_metrics_via_router(self, manager):
        """Test getting Redis metrics through router method."""
        mock_cache = MagicMock()
        mock_cache.client.info = AsyncMock(return_value={"used_memory": 50 * 1024 * 1024})
        mock_cache.client.dbsize = AsyncMock(return_value=1000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            metrics = await manager.get_resource_metrics(ResourceType.REDIS_CACHE)

            assert metrics.resource_type == ResourceType.REDIS_CACHE

    @pytest.mark.asyncio
    async def test_get_weaviate_metrics_via_router(self, manager):
        """Test getting Weaviate metrics through router method."""
        mock_service = MagicMock()
        mock_service.health_check = MagicMock(return_value={"points_count": 500})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get:
            mock_get.return_value = mock_service

            metrics = await manager.get_resource_metrics(ResourceType.WEAVIATE_VECTORS)

            assert metrics.resource_type == ResourceType.WEAVIATE_VECTORS

    @pytest.mark.asyncio
    async def test_get_minio_metrics_via_router(self, manager):
        """Test getting MinIO metrics through router method."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=100)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )

            metrics = await manager.get_resource_metrics(ResourceType.MINIO_FILES)

            assert metrics.resource_type == ResourceType.MINIO_FILES

    @pytest.mark.asyncio
    async def test_get_mongodb_metrics_via_router(self, manager):
        """Test getting MongoDB metrics through router method."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=5000)

            metrics = await manager.get_resource_metrics(ResourceType.MONGODB_METADATA)

            assert metrics.resource_type == ResourceType.MONGODB_METADATA

    @pytest.mark.asyncio
    async def test_get_resource_metrics_invalid_type(self, manager):
        """Test that invalid resource type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown resource type"):
            await manager.get_resource_metrics("invalid_type")


class TestGetRedisMetricsPriority:
    """Tests for Redis metrics priority calculation."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_high_priority_usage(self, manager):
        """Test Redis metrics returns HIGH priority at 80% usage."""
        mock_cache = MagicMock()
        # 80% of max_redis_memory_mb (256 MB default)
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": int(0.80 * manager.max_redis_memory_mb * 1024 * 1024)
        })
        mock_cache.client.dbsize = AsyncMock(return_value=8000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            metrics = await manager._get_redis_metrics()

            assert metrics.cleanup_priority == CleanupPriority.HIGH

    @pytest.mark.asyncio
    async def test_medium_priority_usage(self, manager):
        """Test Redis metrics returns MEDIUM priority at 60% usage."""
        mock_cache = MagicMock()
        # 60% of max_redis_memory_mb
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": int(0.60 * manager.max_redis_memory_mb * 1024 * 1024)
        })
        mock_cache.client.dbsize = AsyncMock(return_value=6000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            metrics = await manager._get_redis_metrics()

            assert metrics.cleanup_priority == CleanupPriority.MEDIUM

    @pytest.mark.asyncio
    async def test_low_priority_usage(self, manager):
        """Test Redis metrics returns LOW priority at 30% usage."""
        mock_cache = MagicMock()
        # 30% of max_redis_memory_mb
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": int(0.30 * manager.max_redis_memory_mb * 1024 * 1024)
        })
        mock_cache.client.dbsize = AsyncMock(return_value=3000)

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            metrics = await manager._get_redis_metrics()

            assert metrics.cleanup_priority == CleanupPriority.LOW


class TestGetWeaviateMetricsPriority:
    """Tests for Weaviate metrics priority calculation."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_critical_priority(self, manager):
        """Test Weaviate metrics returns CRITICAL priority at 95% usage."""
        mock_service = MagicMock()
        # 95% of max_weaviate_points (100000 default)
        mock_service.health_check = MagicMock(return_value={"points_count": 95000})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get:
            mock_get.return_value = mock_service

            metrics = await manager._get_weaviate_metrics()

            assert metrics.cleanup_priority == CleanupPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_high_priority(self, manager):
        """Test Weaviate metrics returns HIGH priority at 80% usage."""
        mock_service = MagicMock()
        mock_service.health_check = MagicMock(return_value={"points_count": 80000})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get:
            mock_get.return_value = mock_service

            metrics = await manager._get_weaviate_metrics()

            assert metrics.cleanup_priority == CleanupPriority.HIGH

    @pytest.mark.asyncio
    async def test_medium_priority(self, manager):
        """Test Weaviate metrics returns MEDIUM priority at 60% usage."""
        mock_service = MagicMock()
        mock_service.health_check = MagicMock(return_value={"points_count": 60000})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get:
            mock_get.return_value = mock_service

            metrics = await manager._get_weaviate_metrics()

            assert metrics.cleanup_priority == CleanupPriority.MEDIUM

    @pytest.mark.asyncio
    async def test_low_priority(self, manager):
        """Test Weaviate metrics returns LOW priority at 30% usage."""
        mock_service = MagicMock()
        mock_service.health_check = MagicMock(return_value={"points_count": 30000})

        with patch("src.services.weaviate_service.get_weaviate_service") as mock_get:
            mock_get.return_value = mock_service

            metrics = await manager._get_weaviate_metrics()

            assert metrics.cleanup_priority == CleanupPriority.LOW


class TestGetMinioMetrics:
    """Tests for _get_minio_metrics method."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_returns_metrics_with_documents(self, manager):
        """Test MinIO metrics calculation with existing documents."""
        mock_doc = MagicMock()
        mock_doc.created_at = datetime.utcnow() - timedelta(days=3)

        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=500)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[mock_doc])
            )

            metrics = await manager._get_minio_metrics()

            assert metrics.resource_type == ResourceType.MINIO_FILES
            assert metrics.total_items == 500
            assert metrics.oldest_item_age_hours > 0
            assert isinstance(metrics.cleanup_priority, CleanupPriority)

    @pytest.mark.asyncio
    async def test_returns_metrics_no_documents(self, manager):
        """Test MinIO metrics when no documents exist."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=0)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )

            metrics = await manager._get_minio_metrics()

            assert metrics.total_items == 0
            assert metrics.oldest_item_age_hours == 0
            assert metrics.cleanup_priority == CleanupPriority.LOW

    @pytest.mark.asyncio
    async def test_critical_priority_high_storage(self, manager):
        """Test MinIO metrics returns CRITICAL at high storage usage."""
        # Calculate docs needed for 95% of max_minio_storage_gb (50 GB default)
        # avg 2MB per file, so 50GB / 2MB = 25000 docs at 100%
        # 95% = 23750 docs
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=24000)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )

            metrics = await manager._get_minio_metrics()

            assert metrics.cleanup_priority == CleanupPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_high_priority_storage(self, manager):
        """Test MinIO metrics returns HIGH priority at 80% usage."""
        # 80% of 25000 = 20000 docs
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=20000)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )

            metrics = await manager._get_minio_metrics()

            assert metrics.cleanup_priority == CleanupPriority.HIGH

    @pytest.mark.asyncio
    async def test_medium_priority_storage(self, manager):
        """Test MinIO metrics returns MEDIUM priority at 60% usage."""
        # 60% of 25000 = 15000 docs
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=15000)
            mock_document.find.return_value.sort.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )

            metrics = await manager._get_minio_metrics()

            assert metrics.cleanup_priority == CleanupPriority.MEDIUM


class TestGetMongodbMetrics:
    """Tests for _get_mongodb_metrics method."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_returns_metrics(self, manager):
        """Test MongoDB metrics calculation."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=5000)

            metrics = await manager._get_mongodb_metrics()

            assert metrics.resource_type == ResourceType.MONGODB_METADATA
            assert metrics.total_items == 5000
            # 5KB per doc * 5000 docs
            assert metrics.total_size_bytes == 5000 * 5 * 1024
            assert metrics.oldest_item_age_hours == 0
            assert metrics.cleanup_priority == CleanupPriority.LOW

    @pytest.mark.asyncio
    async def test_usage_percentage_capped(self, manager):
        """Test MongoDB usage percentage is capped at 1.0."""
        with patch("src.models.document.Document") as mock_document:
            # More than 10000 docs
            mock_document.count = AsyncMock(return_value=20000)

            metrics = await manager._get_mongodb_metrics()

            assert metrics.usage_percentage == 1.0

    @pytest.mark.asyncio
    async def test_usage_percentage_calculated(self, manager):
        """Test MongoDB usage percentage calculation."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.count = AsyncMock(return_value=5000)

            metrics = await manager._get_mongodb_metrics()

            assert metrics.usage_percentage == 0.5  # 5000/10000


class TestCleanupExpiredResources:
    """Tests for cleanup_expired_resources method."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_cleanup_all_resources(self, manager):
        """Test cleaning up all resource types."""
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_weaviate_vectors = AsyncMock(return_value=10)
        manager._cleanup_minio_files = AsyncMock(return_value=3)

        results = await manager.cleanup_expired_resources()

        assert results["redis"] == 5
        assert results["weaviate"] == 10
        assert results["minio"] == 3
        manager._cleanup_redis_cache.assert_called_once()
        manager._cleanup_weaviate_vectors.assert_called_once()
        manager._cleanup_minio_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_only_redis(self, manager):
        """Test cleaning up only Redis cache."""
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_weaviate_vectors = AsyncMock(return_value=10)
        manager._cleanup_minio_files = AsyncMock(return_value=3)

        results = await manager.cleanup_expired_resources(
            resource_type=ResourceType.REDIS_CACHE
        )

        assert results["redis"] == 5
        assert "weaviate" not in results
        assert "minio" not in results
        manager._cleanup_redis_cache.assert_called_once()
        manager._cleanup_weaviate_vectors.assert_not_called()
        manager._cleanup_minio_files.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_only_weaviate(self, manager):
        """Test cleaning up only Weaviate vectors."""
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_weaviate_vectors = AsyncMock(return_value=10)
        manager._cleanup_minio_files = AsyncMock(return_value=3)

        results = await manager.cleanup_expired_resources(
            resource_type=ResourceType.WEAVIATE_VECTORS
        )

        assert results["weaviate"] == 10
        assert "redis" not in results
        assert "minio" not in results
        manager._cleanup_weaviate_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_only_minio(self, manager):
        """Test cleaning up only MinIO files."""
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_weaviate_vectors = AsyncMock(return_value=10)
        manager._cleanup_minio_files = AsyncMock(return_value=3)

        results = await manager.cleanup_expired_resources(
            resource_type=ResourceType.MINIO_FILES
        )

        assert results["minio"] == 3
        assert "redis" not in results
        assert "weaviate" not in results
        manager._cleanup_minio_files.assert_called_once()


class TestCleanupRedisCacheEdgeCases:
    """Tests for Redis cache cleanup edge cases."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_cleanup_with_multiple_scans(self, manager):
        """Test Redis cleanup with multiple scan iterations."""
        mock_cache = MagicMock()

        # Simulate multiple scan iterations
        mock_cache.client.scan = AsyncMock(side_effect=[
            (100, [b"doc_segments:key1"]),  # First scan, more to come
            (0, [b"doc_segments:key2"]),    # Final scan
        ])
        mock_cache.client.ttl = AsyncMock(return_value=-1)  # No TTL
        mock_cache.client.delete = AsyncMock()

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            deleted_count = await manager._cleanup_redis_cache()

            assert deleted_count == 2
            assert mock_cache.client.scan.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_skips_keys_with_ttl(self, manager):
        """Test Redis cleanup skips keys that have TTL."""
        mock_cache = MagicMock()

        mock_cache.client.scan = AsyncMock(return_value=(
            0, [b"doc_segments:key1", b"doc_segments:key2"]
        ))
        # First key no TTL, second key has TTL
        mock_cache.client.ttl = AsyncMock(side_effect=[-1, 3600])
        mock_cache.client.delete = AsyncMock()

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            deleted_count = await manager._cleanup_redis_cache()

            assert deleted_count == 1
            mock_cache.client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_keys_found(self, manager):
        """Test Redis cleanup when no keys match pattern."""
        mock_cache = MagicMock()
        mock_cache.client.scan = AsyncMock(return_value=(0, []))

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            deleted_count = await manager._cleanup_redis_cache()

            assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_handles_string_keys(self, manager):
        """Test Redis cleanup handles string keys (not bytes)."""
        mock_cache = MagicMock()

        mock_cache.client.scan = AsyncMock(return_value=(
            0, ["doc_segments:key1"]  # String, not bytes
        ))
        mock_cache.client.ttl = AsyncMock(return_value=-1)
        mock_cache.client.delete = AsyncMock()

        with patch("src.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache

            deleted_count = await manager._cleanup_redis_cache()

            assert deleted_count == 1


class TestCleanupMinioFilesEdgeCases:
    """Tests for MinIO files cleanup edge cases."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_cleanup_skips_active_sessions(self, manager):
        """Test MinIO cleanup skips files with active sessions."""
        cutoff_time = datetime.utcnow() - timedelta(days=manager.minio_ttl_days)

        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.created_at = cutoff_time - timedelta(days=1)
        mock_doc.delete = AsyncMock()

        mock_storage = AsyncMock()

        with patch("src.models.document.Document") as mock_document, \
             patch("src.models.chat.ChatSession") as mock_chat_session, \
             patch("src.services.file_storage.get_file_storage") as mock_get_storage:

            mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])
            # Document has active sessions
            mock_chat_session.find.return_value.count = AsyncMock(return_value=1)
            mock_get_storage.return_value = mock_storage

            deleted_count = await manager._cleanup_minio_files()

            assert deleted_count == 0
            mock_storage.delete_file.assert_not_called()
            mock_doc.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_handles_no_minio_path(self, manager):
        """Test MinIO cleanup handles documents without minio_path."""
        cutoff_time = datetime.utcnow() - timedelta(days=manager.minio_ttl_days)

        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = None  # No MinIO path
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = cutoff_time - timedelta(days=1)
        mock_doc.delete = AsyncMock()

        mock_storage = AsyncMock()

        with patch("src.models.document.Document") as mock_document, \
             patch("src.models.chat.ChatSession") as mock_chat_session, \
             patch("src.services.file_storage.get_file_storage") as mock_get_storage:

            mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])
            mock_chat_session.find.return_value.count = AsyncMock(return_value=0)
            mock_get_storage.return_value = mock_storage

            deleted_count = await manager._cleanup_minio_files()

            assert deleted_count == 1
            mock_storage.delete_file.assert_not_called()
            mock_doc.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_exception(self, manager):
        """Test MinIO cleanup handles exception during deletion."""
        cutoff_time = datetime.utcnow() - timedelta(days=manager.minio_ttl_days)

        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = cutoff_time - timedelta(days=1)

        mock_storage = AsyncMock()
        mock_storage.delete_file = AsyncMock(side_effect=Exception("Storage error"))

        with patch("src.models.document.Document") as mock_document, \
             patch("src.models.chat.ChatSession") as mock_chat_session, \
             patch("src.services.file_storage.get_file_storage") as mock_get_storage:

            mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])
            mock_chat_session.find.return_value.count = AsyncMock(return_value=0)
            mock_get_storage.return_value = mock_storage

            # Should not raise, just log error
            deleted_count = await manager._cleanup_minio_files()

            assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_no_old_documents(self, manager):
        """Test MinIO cleanup when no old documents exist."""
        mock_storage = AsyncMock()

        with patch("src.models.document.Document") as mock_document, \
             patch("src.services.file_storage.get_file_storage") as mock_get_storage:

            mock_document.find.return_value.to_list = AsyncMock(return_value=[])
            mock_get_storage.return_value = mock_storage

            deleted_count = await manager._cleanup_minio_files()

            assert deleted_count == 0


class TestProcessCleanupQueueEdgeCases:
    """Tests for process_cleanup_queue edge cases."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_handles_cleanup_exception(self, manager):
        """Test that process_cleanup_queue handles exceptions gracefully."""
        manager._cleanup_redis_cache = AsyncMock(side_effect=Exception("Cleanup failed"))

        await manager.schedule_cleanup_task(
            ResourceType.REDIS_CACHE, "all", CleanupPriority.HIGH, "Test"
        )

        # Should not raise
        await manager.process_cleanup_queue(max_tasks=1)

        # Queue should be empty (task was popped)
        assert len(manager.cleanup_queue) == 0

    @pytest.mark.asyncio
    async def test_empty_queue(self, manager):
        """Test processing empty cleanup queue."""
        # Should not raise
        await manager.process_cleanup_queue(max_tasks=10)

        assert len(manager.cleanup_queue) == 0

    @pytest.mark.asyncio
    async def test_processes_minio_cleanup(self, manager):
        """Test processing MinIO cleanup task."""
        manager._cleanup_minio_files = AsyncMock(return_value=5)

        await manager.schedule_cleanup_task(
            ResourceType.MINIO_FILES, "all", CleanupPriority.MEDIUM, "Test"
        )

        await manager.process_cleanup_queue(max_tasks=1)

        manager._cleanup_minio_files.assert_called()


class TestGetResourceManagerSingleton:
    """Tests for get_resource_manager singleton function."""

    def test_returns_manager_instance(self):
        """Test that get_resource_manager returns an instance."""
        # Reset singleton for test isolation
        import src.services.resource_lifecycle_manager as module
        original = module._resource_manager
        module._resource_manager = None

        try:
            manager = get_resource_manager()

            assert isinstance(manager, ResourceLifecycleManager)
        finally:
            module._resource_manager = original

    def test_returns_same_instance(self):
        """Test that get_resource_manager returns the same instance."""
        import src.services.resource_lifecycle_manager as module
        original = module._resource_manager
        module._resource_manager = None

        try:
            manager1 = get_resource_manager()
            manager2 = get_resource_manager()

            assert manager1 is manager2
        finally:
            module._resource_manager = original

    def test_uses_existing_instance(self):
        """Test that get_resource_manager uses existing instance."""
        import src.services.resource_lifecycle_manager as module
        original = module._resource_manager

        try:
            existing = ResourceLifecycleManager()
            module._resource_manager = existing

            manager = get_resource_manager()

            assert manager is existing
        finally:
            module._resource_manager = original


class TestResourceTypeEnum:
    """Tests for ResourceType enum."""

    def test_all_types_exist(self):
        """Test all resource types are defined."""
        assert ResourceType.REDIS_CACHE == "redis_cache"
        assert ResourceType.WEAVIATE_VECTORS == "weaviate_vectors"
        assert ResourceType.MINIO_FILES == "minio_files"
        assert ResourceType.MONGODB_METADATA == "mongodb_metadata"

    def test_enum_values_are_strings(self):
        """Test enum values are strings."""
        for rt in ResourceType:
            assert isinstance(rt.value, str)


class TestCleanupPriorityEnum:
    """Tests for CleanupPriority enum."""

    def test_all_priorities_exist(self):
        """Test all cleanup priorities are defined."""
        assert CleanupPriority.CRITICAL == 1
        assert CleanupPriority.HIGH == 2
        assert CleanupPriority.MEDIUM == 3
        assert CleanupPriority.LOW == 4

    def test_enum_ordering(self):
        """Test enum values are ordered by urgency."""
        assert CleanupPriority.CRITICAL < CleanupPriority.HIGH
        assert CleanupPriority.HIGH < CleanupPriority.MEDIUM
        assert CleanupPriority.MEDIUM < CleanupPriority.LOW

    def test_enum_values_are_integers(self):
        """Test enum values are integers."""
        for cp in CleanupPriority:
            assert isinstance(cp.value, int)


class TestCheckDuplicateFileEdgeCases:
    """Tests for check_duplicate_file edge cases."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_returns_document_id(self, manager):
        """Test returns PydanticObjectId when duplicate found."""
        from beanie import PydanticObjectId

        file_hash = "abc123def456"
        user_id = "user123"

        mock_doc = MagicMock()
        mock_doc.id = PydanticObjectId()

        with patch("src.models.document.Document") as mock_document:
            mock_document.find_one = AsyncMock(return_value=mock_doc)

            result = await manager.check_duplicate_file(file_hash, user_id)

            assert result == mock_doc.id
            assert isinstance(result, PydanticObjectId)
