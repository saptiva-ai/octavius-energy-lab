# Workers Directory - Octavius 2.0

## Purpose

This directory contains background job workers and queue consumers for asynchronous processing in Octavius 2.0.

---

## Current Architecture

### Existing Workers

#### 1. `resource_cleanup_worker.py`
- **Purpose**: Periodic cleanup of stale resources (files, sessions, cache)
- **Runtime**: Background task via FastAPI BackgroundTasks
- **Status**: ✅ **PRODUCTION READY**

---

## Planned Architecture (Octavius 2.0 - Phase 3)

### Future Queue-Based System

**Goal**: Migrate long-running operations to asynchronous queue workers powered by **BullMQ** or **Celery** with Redis as the message broker.

### Target Use Cases

#### 1. **Deep Research Processing**
- **Location**: `deep_research_worker.py` (To be created)
- **Trigger**: Chat command or API endpoint
- **Current State**: Synchronous Aletheia orchestrator call
- **Future State**: Producer-Consumer pattern with BullMQ queue
- **Benefits**:
  - Non-blocking chat interface
  - Progress tracking via WebSocket
  - Retry logic for failed research tasks
  - Rate limiting per user

**Implementation Markers**:
```python
# TODO [Octavius-2.0 / Phase 3]:
# Refactor deep_research endpoint to async queue pattern
# 1. Create DeepResearchProducer in services/deep_research_service.py
# 2. Implement DeepResearchConsumer in workers/deep_research_worker.py
# 3. Add BullMQ queue configuration in core/queue_config.py
# 4. Update endpoint to return task_id immediately (202 Accepted)
```

---

#### 2. **Document Audit Processing**
- **Location**: `audit_worker.py` (To be created)
- **Trigger**: `"Auditar archivo: filename.pdf"` chat command
- **Current State**: Synchronous validation (4 parallel auditors)
- **Future State**: Queue-based processing with status updates
- **Benefits**:
  - Handle large PDFs without timeout
  - Parallel processing of multiple documents
  - Real-time progress updates to frontend
  - Resource throttling for logo detection (OpenCV)

**Implementation Markers**:
```python
# TODO [Octavius-2.0 / Phase 3]:
# Migrate ValidationCoordinator to queue worker
# 1. Create AuditProducer in services/validation_coordinator.py
# 2. Implement AuditWorker in workers/audit_worker.py
# 3. Add job progress tracking for each auditor (disclaimer, format, grammar, logo)
# 4. Emit WebSocket events for real-time canvas updates
```

---

#### 3. **RAG Document Ingestion**
- **Location**: `rag_ingestion_worker.py` (To be created)
- **Trigger**: File upload via `/api/documents/upload`
- **Current State**: Synchronous chunking + embedding + Weaviate upsert
- **Future State**: Background ingestion with progress bar
- **Benefits**:
  - Support for large document batches
  - Retry on Weaviate timeout
  - Incremental progress (chunking → embedding → indexing)
  - Background reindexing for semantic search improvements

**Implementation Markers**:
```python
# TODO [Octavius-2.0 / Phase 3]:
# Convert DocumentService.ingest_document() to async queue
# 1. Create RagIngestionProducer in services/document_service.py
# 2. Implement RagIngestionWorker in workers/rag_ingestion_worker.py
# 3. Add chunking progress events (e.g., "Chunked 50/200 pages")
# 4. Support batch embedding with retry logic
```

---

## Technology Stack (Proposed)

### Option A: BullMQ (Recommended for Node.js Ecosystem)
- **Pros**:
  - Native TypeScript support
  - Excellent dashboard (Bull Board)
  - Built on Redis (already in stack)
  - Better integration with Next.js frontend (same runtime)
- **Cons**:
  - Requires Node.js runtime for workers (FastAPI would need bridge)

### Option B: Celery (Recommended for Python-First Projects)
- **Pros**:
  - Native Python support
  - Proven at scale (used by Instagram, Airbnb)
  - Flower dashboard for monitoring
  - Direct integration with FastAPI
- **Cons**:
  - Heavier than BullMQ
  - Requires additional config (broker, result backend)

### Recommendation: **Celery**
**Reason**: Octavius backend is FastAPI (Python). Celery workers can directly import existing services without language boundary.

---

## Implementation Roadmap

### Phase 3.1: Infrastructure Setup (Week 1-2)
- [ ] Install Celery + Redis adapter
- [ ] Create `core/celery_app.py` with task routing config
- [ ] Set up Flower dashboard (Docker service)
- [ ] Add monitoring alerts (Sentry for worker errors)

### Phase 3.2: Deep Research Migration (Week 3-4)
- [ ] Create `workers/deep_research_worker.py`
- [ ] Refactor `routers/deep_research.py` to producer pattern
- [ ] Add task status polling endpoint (`GET /api/tasks/{task_id}`)
- [ ] Implement WebSocket progress updates

### Phase 3.3: Audit & RAG Workers (Week 5-6)
- [ ] Migrate ValidationCoordinator to `audit_worker.py`
- [ ] Convert document ingestion to `rag_ingestion_worker.py`
- [ ] Add retry policies (exponential backoff)
- [ ] Performance testing (100 concurrent tasks)

### Phase 3.4: Production Hardening (Week 7-8)
- [ ] Add dead letter queue (DLQ) for failed tasks
- [ ] Implement rate limiting per user
- [ ] Set up horizontal scaling (multiple worker pods)
- [ ] Load testing + capacity planning

---

## File Structure (Post-Migration)

```
apps/api/src/workers/
├── README.md                          # This file
├── __init__.py                        # Worker registry
├── resource_cleanup_worker.py         # ✅ Existing (Background task)
│
# === Phase 3: Queue Workers ===
├── deep_research_worker.py            # 🚧 Deep research consumer
├── audit_worker.py                    # 🚧 Audit file consumer
├── rag_ingestion_worker.py            # 🚧 RAG embedding consumer
│
# === Shared Infrastructure ===
├── base_worker.py                     # 🚧 Abstract base class for workers
└── worker_utils.py                    # 🚧 Retry logic, metrics, logging
```

---

## Code Patterns

### Example: Deep Research Worker (Celery)

```python
# workers/deep_research_worker.py

from celery import Task
from src.core.celery_app import celery_app
from src.services.deep_research_service import DeepResearchService


@celery_app.task(bind=True, max_retries=3)
def process_deep_research(self: Task, task_id: str, query: str, user_id: str):
    """
    Background worker for deep research processing.

    TODO [Octavius-2.0]: This is a placeholder. Implement in Phase 3.
    """
    try:
        service = DeepResearchService()
        result = await service.execute_research(task_id, query, user_id)

        # Update task status in MongoDB
        # Emit WebSocket event to frontend
        # Return result for Celery result backend

        return {"status": "completed", "result": result}
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries)
```

---

## Monitoring & Observability

### Celery Metrics (via Flower)
- Tasks per minute
- Success/failure rates
- Average task duration
- Active workers count

### Alerts (Sentry)
- Worker crash detection
- Task timeout alerts
- Queue depth warnings (> 1000 pending tasks)

---

## Security Considerations

### Worker Isolation
- Workers run as non-root user (`api_user`)
- Separate Docker service with resource limits
- No direct database write access (only via service layer)

### Input Validation
- All task payloads validated with Pydantic schemas
- User ID verification before processing
- Rate limiting enforced at producer level

---

## Questions for Architecture Review

1. **Should we use BullMQ instead of Celery for better Next.js integration?**
   - Pros: Single runtime (Node.js), simpler deployment
   - Cons: Python-Node bridge complexity, existing FastAPI services

2. **How to handle long-lived WebSocket connections for progress updates?**
   - Option A: Dedicated WebSocket server (Socket.IO)
   - Option B: Server-Sent Events (SSE) via `/api/stream/{task_id}`
   - Option C: Polling every 2s (fallback for unsupported browsers)

3. **What's the max concurrency for workers in production?**
   - Suggested: 4 workers × 10 threads = 40 concurrent tasks
   - Scale horizontally via Kubernetes HPA

---

**Last Updated**: 2025-11-24 (Pre-implementation planning)
**Status**: 📝 Documentation only - No queue infrastructure deployed yet
