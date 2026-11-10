"""
Unit tests for FileIngestionService - Document ingestion with anti-hallucination wait.

Tests cover:
- Checking if documents are already ready
- Dispatching ingestion
- Waiting for documents to become ready
- Timeout handling
- Edge cases (no files, no background tasks)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.streaming.file_ingestion_service import FileIngestionService


@pytest.fixture
def mock_background_tasks():
    """Create mock FastAPI BackgroundTasks."""
    return MagicMock()


@pytest.mark.unit
class TestFileIngestionServiceConstants:
    """Tests for class constants."""

    def test_default_max_wait_seconds(self):
        """Should have default max wait of 30 seconds."""
        assert FileIngestionService.DEFAULT_MAX_WAIT_SECONDS == 30

    def test_default_poll_interval(self):
        """Should have default poll interval of 0.5 seconds."""
        assert FileIngestionService.DEFAULT_POLL_INTERVAL == 0.5

    def test_mongodb_propagation_delay(self):
        """Should have MongoDB propagation delay."""
        assert FileIngestionService.MONGODB_PROPAGATION_DELAY == 0.1


@pytest.mark.unit
class TestIngestFilesIfNeeded:
    """Tests for ingest_files_if_needed method."""

    @pytest.mark.asyncio
    async def test_returns_true_for_empty_file_ids(self, mock_background_tasks):
        """Should return True immediately for empty file list."""
        result = await FileIngestionService.ingest_files_if_needed(
            session_id="session-123",
            file_ids=[],
            background_tasks=mock_background_tasks,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_none_background_tasks(self):
        """Should return True immediately when background_tasks is None."""
        result = await FileIngestionService.ingest_files_if_needed(
            session_id="session-123",
            file_ids=["doc-1"],
            background_tasks=None,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_skips_ingestion_when_all_ready(self, mock_background_tasks):
        """Should skip ingestion when all documents are already READY."""
        with patch.object(
            FileIngestionService, '_check_all_documents_ready', return_value=True
        ) as mock_check:
            result = await FileIngestionService.ingest_files_if_needed(
                session_id="session-123",
                file_ids=["doc-1", "doc-2"],
                background_tasks=mock_background_tasks,
            )

            assert result is True
            mock_check.assert_called_once_with(["doc-1", "doc-2"])

    @pytest.mark.asyncio
    async def test_dispatches_ingestion_when_not_ready(self, mock_background_tasks):
        """Should dispatch ingestion when documents not ready."""
        with patch.object(
            FileIngestionService, '_check_all_documents_ready', return_value=False
        ), patch.object(
            FileIngestionService, '_dispatch_ingestion', new_callable=AsyncMock
        ) as mock_dispatch, patch.object(
            FileIngestionService, '_wait_for_documents_ready', return_value=True
        ):
            result = await FileIngestionService.ingest_files_if_needed(
                session_id="session-123",
                file_ids=["doc-1"],
                background_tasks=mock_background_tasks,
            )

            assert result is True
            mock_dispatch.assert_called_once_with(
                "session-123", ["doc-1"], mock_background_tasks
            )

    @pytest.mark.asyncio
    async def test_returns_false_on_ingestion_error(self, mock_background_tasks):
        """Should return False when ingestion dispatch fails."""
        with patch.object(
            FileIngestionService, '_check_all_documents_ready', return_value=False
        ), patch.object(
            FileIngestionService, '_dispatch_ingestion', side_effect=Exception("Ingestion failed")
        ):
            result = await FileIngestionService.ingest_files_if_needed(
                session_id="session-123",
                file_ids=["doc-1"],
                background_tasks=mock_background_tasks,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_wait_result(self, mock_background_tasks):
        """Should return result of _wait_for_documents_ready."""
        with patch.object(
            FileIngestionService, '_check_all_documents_ready', return_value=False
        ), patch.object(
            FileIngestionService, '_dispatch_ingestion', new_callable=AsyncMock
        ), patch.object(
            FileIngestionService, '_wait_for_documents_ready', return_value=False
        ):
            result = await FileIngestionService.ingest_files_if_needed(
                session_id="session-123",
                file_ids=["doc-1"],
                background_tasks=mock_background_tasks,
            )

            assert result is False


@pytest.mark.unit
class TestCheckAllDocumentsReady:
    """Tests for _check_all_documents_ready method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_all_ready(self):
        """Should return True when all documents have READY status."""
        from src.models.document import DocumentStatus

        mock_doc = MagicMock()
        mock_doc.status = DocumentStatus.READY

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(return_value=mock_doc)

            result = await FileIngestionService._check_all_documents_ready(
                ["doc-1", "doc-2"]
            )

            assert result is True
            assert MockDocument.get.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_false_when_one_not_ready(self):
        """Should return False when any document is not READY."""
        from src.models.document import DocumentStatus

        mock_ready = MagicMock()
        mock_ready.status = DocumentStatus.READY

        mock_processing = MagicMock()
        mock_processing.status = DocumentStatus.PROCESSING

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(side_effect=[mock_ready, mock_processing])

            result = await FileIngestionService._check_all_documents_ready(
                ["doc-ready", "doc-processing"]
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_document_not_found(self):
        """Should return False when document doesn't exist."""
        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(return_value=None)

            result = await FileIngestionService._check_all_documents_ready(["doc-missing"])

            assert result is False


@pytest.mark.unit
class TestDispatchIngestion:
    """Tests for _dispatch_ingestion method."""

    @pytest.mark.asyncio
    async def test_executes_ingest_tool(self):
        """Should execute IngestFilesTool with correct parameters."""
        mock_background_tasks = MagicMock()

        with patch(
            'src.services.streaming.file_ingestion_service.IngestFilesTool'
        ) as MockTool:
            mock_tool_instance = MagicMock()
            mock_tool_instance.execute = AsyncMock(return_value={
                "ingested": 2,
                "status": "ok"
            })
            MockTool.return_value = mock_tool_instance

            with patch('asyncio.sleep', new_callable=AsyncMock):
                await FileIngestionService._dispatch_ingestion(
                    session_id="session-123",
                    file_ids=["doc-1", "doc-2"],
                    background_tasks=mock_background_tasks,
                )

            mock_tool_instance.execute.assert_called_once()
            call_kwargs = mock_tool_instance.execute.call_args.kwargs
            assert call_kwargs["payload"]["conversation_id"] == "session-123"
            assert call_kwargs["payload"]["file_refs"] == ["doc-1", "doc-2"]
            assert call_kwargs["context"]["background_tasks"] == mock_background_tasks

    @pytest.mark.asyncio
    async def test_waits_for_mongodb_propagation(self):
        """Should wait for MongoDB write propagation after dispatch."""
        mock_background_tasks = MagicMock()

        with patch(
            'src.services.streaming.file_ingestion_service.IngestFilesTool'
        ) as MockTool:
            mock_tool_instance = MagicMock()
            mock_tool_instance.execute = AsyncMock(return_value={"ingested": 1})
            MockTool.return_value = mock_tool_instance

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                await FileIngestionService._dispatch_ingestion(
                    session_id="session-123",
                    file_ids=["doc-1"],
                    background_tasks=mock_background_tasks,
                )

                mock_sleep.assert_called_once_with(
                    FileIngestionService.MONGODB_PROPAGATION_DELAY
                )


@pytest.mark.unit
class TestWaitForDocumentsReady:
    """Tests for _wait_for_documents_ready method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_documents_become_ready(self):
        """Should return True when all documents become READY."""
        from src.models.document import DocumentStatus

        call_count = [0]

        async def mock_get(doc_id):
            call_count[0] += 1
            mock_doc = MagicMock()
            # First call: PROCESSING, subsequent: READY
            if call_count[0] <= 1:
                mock_doc.status = DocumentStatus.PROCESSING
            else:
                mock_doc.status = DocumentStatus.READY
            return mock_doc

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = mock_get

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await FileIngestionService._wait_for_documents_ready(
                    session_id="session-123",
                    file_ids=["doc-1"],
                    max_wait_seconds=5,
                    poll_interval=0.1,
                )

                assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        """Should return False when timeout is reached."""
        from src.models.document import DocumentStatus

        mock_doc = MagicMock()
        mock_doc.status = DocumentStatus.PROCESSING

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(return_value=mock_doc)

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await FileIngestionService._wait_for_documents_ready(
                    session_id="session-123",
                    file_ids=["doc-1"],
                    max_wait_seconds=0.1,  # Very short timeout
                    poll_interval=0.05,
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_immediately_if_already_ready(self):
        """Should return True immediately if documents already READY."""
        from src.models.document import DocumentStatus

        mock_doc = MagicMock()
        mock_doc.status = DocumentStatus.READY

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(return_value=mock_doc)

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                result = await FileIngestionService._wait_for_documents_ready(
                    session_id="session-123",
                    file_ids=["doc-1"],
                    max_wait_seconds=30,
                    poll_interval=0.5,
                )

                assert result is True
                # Should not have slept since documents were ready
                mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_checks_all_documents(self):
        """Should check all documents in the list."""
        from src.models.document import DocumentStatus

        mock_doc = MagicMock()
        mock_doc.status = DocumentStatus.READY

        with patch('src.services.streaming.file_ingestion_service.Document') as MockDocument:
            MockDocument.get = AsyncMock(return_value=mock_doc)

            result = await FileIngestionService._wait_for_documents_ready(
                session_id="session-123",
                file_ids=["doc-1", "doc-2", "doc-3"],
                max_wait_seconds=30,
                poll_interval=0.5,
            )

            assert result is True
            assert MockDocument.get.call_count == 3
