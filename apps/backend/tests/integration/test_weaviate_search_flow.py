"""
Integration test: end-to-end Weaviate search flow.

This test exercises:
- Weaviate connection + collection creation
- Chunk upsert with vectors
- Hybrid search with session filtering
"""

import uuid

import pytest

from src.services.weaviate_service import WeaviateService


pytestmark = [pytest.mark.integration]


def _weaviate_ready(service: WeaviateService) -> bool:
    health = service.health_check()
    return health.get("status") == "healthy"


def test_weaviate_search_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    collection_name = f"RAG_Documents_Test_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("RAG_COLLECTION_NAME", collection_name)

    service = WeaviateService()
    if not _weaviate_ready(service):
        pytest.skip("Weaviate not available for integration test")

    service.ensure_collection()

    session_id = f"session-{uuid.uuid4()}"
    document_id = f"doc-{uuid.uuid4()}"
    vector = [0.1, 0.2, 0.3]

    chunks = [
        {
            "chunk_id": 0,
            "text": "La tasa de faltantes mide el inventario no disponible.",
            "embedding": vector,
            "page": 1,
            "metadata": {"filename": "test.pdf"},
        }
    ]

    try:
        service.upsert_chunks(session_id=session_id, document_id=document_id, chunks=chunks)
        results = service.search(
            session_id=session_id,
            query_vector=vector,
            top_k=3,
            score_threshold=0.0,
            query_text="tasa de faltantes",
        )

        assert results, "Expected Weaviate to return at least one result"
        assert results[0]["document_id"] == document_id
        assert "faltantes" in results[0]["text"].lower()
    finally:
        if service.client and service.client.is_connected():
            service.delete_session(session_id)
            try:
                service.client.collections.delete(collection_name)
            except Exception:
                pass
