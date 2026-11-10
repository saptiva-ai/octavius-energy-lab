# Streaming Services

Domain-agnostic building blocks extracted from `streaming_handler.py` for
testability and separation of concerns. The chat host streams LLM responses,
optionally grounded on uploaded documents (RAG), and supports a document-audit
command. Domain analytics (charts, metrics) are provided by MCP plugins, not by
these services.

## Services

### Core Streaming

| Service | Responsibility |
|---------|----------------|
| `ChatStreamProducer` | LLM streaming producer with backpressure |
| `SaptivaStreamer` | LLM interaction abstraction, chunk normalization |
| `ChunkEmitter` | Uniform text chunking for SSE |
| `TokenBudgetManager` | Token estimation, dynamic max_tokens, truncation |
| `SystemPromptBuilder` | System prompt resolution + RAG tools/document context |
| `DocumentContextBuilder` | RAG document retrieval and context building |
| `ResponsePostProcessor` | Empty-response fallback + output sanitization |
| `MessagePersistenceService` | Assistant message metadata and persistence |
| `StreamResponseFinalizer` | Post-streaming finalization and persistence |
| `FileIngestionService` | Document ingestion with anti-hallucination wait |
| `StreamingErrorLogger` | Centralized error logging |

### Audit Services

| Service | Responsibility |
|---------|----------------|
| `AuditDocumentResolver` | Document resolution/materialization for audit |
| `AuditResponseBuilder` | Audit result formatting and SSE events |
| `AuditorResultFormatterService` | Format MCP auditor results |

## Data Flow — Chat Streaming

```python
# StreamingHandler._stream_chat_response()

# Step 1: Build document context (RAG)
doc_context = await DocumentContextBuilder().build(
    document_ids=context.document_ids,
    session_id=context.session_id,
    question=context.message,
)

# Step 2: Resolve system prompt (base prompt + RAG tools + document context)
prompt_result = SystemPromptBuilder.build(
    model=context.model,
    document_context=doc_context,
    document_ids=context.document_ids,
    user_query=context.message,
)

# Step 3: Start producer (puts events on queue)
producer = ChatStreamProducer()
producer_task = create_task(producer.produce(producer_context))

# Step 4: Consumer loop (yields events to client)
while True:
    event = await event_queue.get()
    if event is None:  # End signal
        break
    yield event
```
