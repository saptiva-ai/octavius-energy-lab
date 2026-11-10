from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Embedding(_message.Message):
    __slots__ = ("values", "dimension")
    VALUES_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[float]
    dimension: int
    def __init__(self, values: _Optional[_Iterable[float]] = ..., dimension: _Optional[int] = ...) -> None: ...

class ChunkMetadata(_message.Message):
    __slots__ = ("chunk_id", "start_char", "end_char", "page", "custom")
    class CustomEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CHUNK_ID_FIELD_NUMBER: _ClassVar[int]
    START_CHAR_FIELD_NUMBER: _ClassVar[int]
    END_CHAR_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_FIELD_NUMBER: _ClassVar[int]
    chunk_id: int
    start_char: int
    end_char: int
    page: int
    custom: _containers.ScalarMap[str, str]
    def __init__(self, chunk_id: _Optional[int] = ..., start_char: _Optional[int] = ..., end_char: _Optional[int] = ..., page: _Optional[int] = ..., custom: _Optional[_Mapping[str, str]] = ...) -> None: ...

class EmbeddedChunk(_message.Message):
    __slots__ = ("chunk_id", "text", "embedding", "page", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CHUNK_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    chunk_id: int
    text: str
    embedding: Embedding
    page: int
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, chunk_id: _Optional[int] = ..., text: _Optional[str] = ..., embedding: _Optional[_Union[Embedding, _Mapping]] = ..., page: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class EncodeRequest(_message.Message):
    __slots__ = ("texts", "batch_size")
    TEXTS_FIELD_NUMBER: _ClassVar[int]
    BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    texts: _containers.RepeatedScalarFieldContainer[str]
    batch_size: int
    def __init__(self, texts: _Optional[_Iterable[str]] = ..., batch_size: _Optional[int] = ...) -> None: ...

class EncodeResponse(_message.Message):
    __slots__ = ("embeddings", "dimension", "count", "processing_time_ms")
    EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    embeddings: _containers.RepeatedCompositeFieldContainer[Embedding]
    dimension: int
    count: int
    processing_time_ms: int
    def __init__(self, embeddings: _Optional[_Iterable[_Union[Embedding, _Mapping]]] = ..., dimension: _Optional[int] = ..., count: _Optional[int] = ..., processing_time_ms: _Optional[int] = ...) -> None: ...

class EncodeSingleRequest(_message.Message):
    __slots__ = ("text", "use_cache")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    USE_CACHE_FIELD_NUMBER: _ClassVar[int]
    text: str
    use_cache: bool
    def __init__(self, text: _Optional[str] = ..., use_cache: bool = ...) -> None: ...

class EncodeSingleResponse(_message.Message):
    __slots__ = ("embedding", "cached", "processing_time_ms")
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    embedding: Embedding
    cached: bool
    processing_time_ms: int
    def __init__(self, embedding: _Optional[_Union[Embedding, _Mapping]] = ..., cached: bool = ..., processing_time_ms: _Optional[int] = ...) -> None: ...

class ChunkAndEmbedRequest(_message.Message):
    __slots__ = ("text", "page", "metadata", "batch_size")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEXT_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    text: str
    page: int
    metadata: _containers.ScalarMap[str, str]
    batch_size: int
    def __init__(self, text: _Optional[str] = ..., page: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ..., batch_size: _Optional[int] = ...) -> None: ...

class ChunkAndEmbedResponse(_message.Message):
    __slots__ = ("chunks", "total_chunks", "dimension", "processing_time_ms")
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    chunks: _containers.RepeatedCompositeFieldContainer[EmbeddedChunk]
    total_chunks: int
    dimension: int
    processing_time_ms: int
    def __init__(self, chunks: _Optional[_Iterable[_Union[EmbeddedChunk, _Mapping]]] = ..., total_chunks: _Optional[int] = ..., dimension: _Optional[int] = ..., processing_time_ms: _Optional[int] = ...) -> None: ...

class Document(_message.Message):
    __slots__ = ("id", "text", "page", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    id: str
    text: str
    page: int
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, id: _Optional[str] = ..., text: _Optional[str] = ..., page: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class BatchChunkAndEmbedRequest(_message.Message):
    __slots__ = ("documents", "batch_size")
    DOCUMENTS_FIELD_NUMBER: _ClassVar[int]
    BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    documents: _containers.RepeatedCompositeFieldContainer[Document]
    batch_size: int
    def __init__(self, documents: _Optional[_Iterable[_Union[Document, _Mapping]]] = ..., batch_size: _Optional[int] = ...) -> None: ...

class DocumentResult(_message.Message):
    __slots__ = ("document_id", "chunks", "success", "error")
    DOCUMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    document_id: str
    chunks: _containers.RepeatedCompositeFieldContainer[EmbeddedChunk]
    success: bool
    error: str
    def __init__(self, document_id: _Optional[str] = ..., chunks: _Optional[_Iterable[_Union[EmbeddedChunk, _Mapping]]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class BatchChunkAndEmbedResponse(_message.Message):
    __slots__ = ("results", "total_chunks", "total_processing_time_ms")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[DocumentResult]
    total_chunks: int
    total_processing_time_ms: int
    def __init__(self, results: _Optional[_Iterable[_Union[DocumentResult, _Mapping]]] = ..., total_chunks: _Optional[int] = ..., total_processing_time_ms: _Optional[int] = ...) -> None: ...

class ModelInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ModelInfoResponse(_message.Message):
    __slots__ = ("model_name", "dimension", "device", "chunk_size_tokens", "chunk_overlap_tokens", "cache_size", "cache_used")
    MODEL_NAME_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_TOKENS_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_TOKENS_FIELD_NUMBER: _ClassVar[int]
    CACHE_SIZE_FIELD_NUMBER: _ClassVar[int]
    CACHE_USED_FIELD_NUMBER: _ClassVar[int]
    model_name: str
    dimension: int
    device: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    cache_size: int
    cache_used: int
    def __init__(self, model_name: _Optional[str] = ..., dimension: _Optional[int] = ..., device: _Optional[str] = ..., chunk_size_tokens: _Optional[int] = ..., chunk_overlap_tokens: _Optional[int] = ..., cache_size: _Optional[int] = ..., cache_used: _Optional[int] = ...) -> None: ...

class ClearCacheRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ClearCacheResponse(_message.Message):
    __slots__ = ("entries_removed",)
    ENTRIES_REMOVED_FIELD_NUMBER: _ClassVar[int]
    entries_removed: int
    def __init__(self, entries_removed: _Optional[int] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("status", "model_loaded", "model_name", "dimension", "model_load_time_ms")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MODEL_LOADED_FIELD_NUMBER: _ClassVar[int]
    MODEL_NAME_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_LOAD_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    status: str
    model_loaded: bool
    model_name: str
    dimension: int
    model_load_time_ms: int
    def __init__(self, status: _Optional[str] = ..., model_loaded: bool = ..., model_name: _Optional[str] = ..., dimension: _Optional[int] = ..., model_load_time_ms: _Optional[int] = ...) -> None: ...
