from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileChunk(_message.Message):
    __slots__ = ("data", "offset", "is_last")
    DATA_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    data: bytes
    offset: int
    is_last: bool
    def __init__(self, data: _Optional[bytes] = ..., offset: _Optional[int] = ..., is_last: bool = ...) -> None: ...

class FileMetadata(_message.Message):
    __slots__ = ("file_id", "filename", "size_bytes", "content_type", "minio_key", "minio_bucket", "sha256", "created_at", "last_modified")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    MINIO_KEY_FIELD_NUMBER: _ClassVar[int]
    MINIO_BUCKET_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_MODIFIED_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    filename: str
    size_bytes: int
    content_type: str
    minio_key: str
    minio_bucket: str
    sha256: str
    created_at: str
    last_modified: str
    def __init__(self, file_id: _Optional[str] = ..., filename: _Optional[str] = ..., size_bytes: _Optional[int] = ..., content_type: _Optional[str] = ..., minio_key: _Optional[str] = ..., minio_bucket: _Optional[str] = ..., sha256: _Optional[str] = ..., created_at: _Optional[str] = ..., last_modified: _Optional[str] = ...) -> None: ...

class PageContent(_message.Message):
    __slots__ = ("page", "text_md", "has_table", "table_csv_key", "has_images", "image_keys")
    PAGE_FIELD_NUMBER: _ClassVar[int]
    TEXT_MD_FIELD_NUMBER: _ClassVar[int]
    HAS_TABLE_FIELD_NUMBER: _ClassVar[int]
    TABLE_CSV_KEY_FIELD_NUMBER: _ClassVar[int]
    HAS_IMAGES_FIELD_NUMBER: _ClassVar[int]
    IMAGE_KEYS_FIELD_NUMBER: _ClassVar[int]
    page: int
    text_md: str
    has_table: bool
    table_csv_key: str
    has_images: bool
    image_keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, page: _Optional[int] = ..., text_md: _Optional[str] = ..., has_table: bool = ..., table_csv_key: _Optional[str] = ..., has_images: bool = ..., image_keys: _Optional[_Iterable[str]] = ...) -> None: ...

class ExtractionResult(_message.Message):
    __slots__ = ("file_id", "pages", "total_pages", "ocr_applied", "ocr_language", "extraction_source", "processing_time_ms")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    PAGES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PAGES_FIELD_NUMBER: _ClassVar[int]
    OCR_APPLIED_FIELD_NUMBER: _ClassVar[int]
    OCR_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    EXTRACTION_SOURCE_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    pages: _containers.RepeatedCompositeFieldContainer[PageContent]
    total_pages: int
    ocr_applied: bool
    ocr_language: str
    extraction_source: str
    processing_time_ms: int
    def __init__(self, file_id: _Optional[str] = ..., pages: _Optional[_Iterable[_Union[PageContent, _Mapping]]] = ..., total_pages: _Optional[int] = ..., ocr_applied: bool = ..., ocr_language: _Optional[str] = ..., extraction_source: _Optional[str] = ..., processing_time_ms: _Optional[int] = ...) -> None: ...

class ProgressEvent(_message.Message):
    __slots__ = ("file_id", "phase", "progress", "status", "error")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    phase: str
    progress: float
    status: str
    error: str
    def __init__(self, file_id: _Optional[str] = ..., phase: _Optional[str] = ..., progress: _Optional[float] = ..., status: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class UploadMetadata(_message.Message):
    __slots__ = ("user_id", "filename", "content_type", "session_id", "idempotency_key", "auto_extract")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    AUTO_EXTRACT_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    filename: str
    content_type: str
    session_id: str
    idempotency_key: str
    auto_extract: bool
    def __init__(self, user_id: _Optional[str] = ..., filename: _Optional[str] = ..., content_type: _Optional[str] = ..., session_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., auto_extract: bool = ...) -> None: ...

class UploadSimpleRequest(_message.Message):
    __slots__ = ("metadata", "file_data")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    metadata: UploadMetadata
    file_data: bytes
    def __init__(self, metadata: _Optional[_Union[UploadMetadata, _Mapping]] = ..., file_data: _Optional[bytes] = ...) -> None: ...

class UploadResponse(_message.Message):
    __slots__ = ("file_id", "metadata", "extraction")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    EXTRACTION_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    metadata: FileMetadata
    extraction: ExtractionResult
    def __init__(self, file_id: _Optional[str] = ..., metadata: _Optional[_Union[FileMetadata, _Mapping]] = ..., extraction: _Optional[_Union[ExtractionResult, _Mapping]] = ...) -> None: ...

class UploadStreamRequest(_message.Message):
    __slots__ = ("metadata", "chunk")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    CHUNK_FIELD_NUMBER: _ClassVar[int]
    metadata: UploadMetadata
    chunk: FileChunk
    def __init__(self, metadata: _Optional[_Union[UploadMetadata, _Mapping]] = ..., chunk: _Optional[_Union[FileChunk, _Mapping]] = ...) -> None: ...

class DownloadRequest(_message.Message):
    __slots__ = ("file_path", "bucket")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    BUCKET_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    bucket: str
    def __init__(self, file_path: _Optional[str] = ..., bucket: _Optional[str] = ...) -> None: ...

class DownloadResponse(_message.Message):
    __slots__ = ("metadata", "chunk")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    CHUNK_FIELD_NUMBER: _ClassVar[int]
    metadata: FileMetadata
    chunk: FileChunk
    def __init__(self, metadata: _Optional[_Union[FileMetadata, _Mapping]] = ..., chunk: _Optional[_Union[FileChunk, _Mapping]] = ...) -> None: ...

class ExtractRequest(_message.Message):
    __slots__ = ("file_path", "force", "provider", "ocr_language")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    FORCE_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    OCR_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    force: bool
    provider: str
    ocr_language: str
    def __init__(self, file_path: _Optional[str] = ..., force: bool = ..., provider: _Optional[str] = ..., ocr_language: _Optional[str] = ...) -> None: ...

class ExtractResponse(_message.Message):
    __slots__ = ("result", "from_cache")
    RESULT_FIELD_NUMBER: _ClassVar[int]
    FROM_CACHE_FIELD_NUMBER: _ClassVar[int]
    result: ExtractionResult
    from_cache: bool
    def __init__(self, result: _Optional[_Union[ExtractionResult, _Mapping]] = ..., from_cache: bool = ...) -> None: ...

class ThumbnailRequest(_message.Message):
    __slots__ = ("file_path", "width", "height", "page", "bucket")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    BUCKET_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    width: int
    height: int
    page: int
    bucket: str
    def __init__(self, file_path: _Optional[str] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., page: _Optional[int] = ..., bucket: _Optional[str] = ...) -> None: ...

class ThumbnailResponse(_message.Message):
    __slots__ = ("thumbnail", "content_type", "width", "height", "original_width", "original_height", "processing_time_ms")
    THUMBNAIL_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_WIDTH_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    thumbnail: bytes
    content_type: str
    width: int
    height: int
    original_width: int
    original_height: int
    processing_time_ms: int
    def __init__(self, thumbnail: _Optional[bytes] = ..., content_type: _Optional[str] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., original_width: _Optional[int] = ..., original_height: _Optional[int] = ..., processing_time_ms: _Optional[int] = ...) -> None: ...

class MetadataRequest(_message.Message):
    __slots__ = ("file_path", "include_extraction")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_EXTRACTION_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    include_extraction: bool
    def __init__(self, file_path: _Optional[str] = ..., include_extraction: bool = ...) -> None: ...

class MetadataResponse(_message.Message):
    __slots__ = ("metadata", "extraction")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    EXTRACTION_FIELD_NUMBER: _ClassVar[int]
    metadata: FileMetadata
    extraction: ExtractionResult
    def __init__(self, metadata: _Optional[_Union[FileMetadata, _Mapping]] = ..., extraction: _Optional[_Union[ExtractionResult, _Mapping]] = ...) -> None: ...

class DeleteRequest(_message.Message):
    __slots__ = ("file_path", "bucket")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    BUCKET_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    bucket: str
    def __init__(self, file_path: _Optional[str] = ..., bucket: _Optional[str] = ...) -> None: ...

class DeleteResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class BatchExtractRequest(_message.Message):
    __slots__ = ("file_paths", "force", "provider")
    FILE_PATHS_FIELD_NUMBER: _ClassVar[int]
    FORCE_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    file_paths: _containers.RepeatedScalarFieldContainer[str]
    force: bool
    provider: str
    def __init__(self, file_paths: _Optional[_Iterable[str]] = ..., force: bool = ..., provider: _Optional[str] = ...) -> None: ...

class BatchExtractResult(_message.Message):
    __slots__ = ("file_path", "result", "success", "error")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    result: ExtractionResult
    success: bool
    error: str
    def __init__(self, file_path: _Optional[str] = ..., result: _Optional[_Union[ExtractionResult, _Mapping]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("status", "dependencies", "version")
    class DependenciesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: bool
        def __init__(self, key: _Optional[str] = ..., value: bool = ...) -> None: ...
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    status: str
    dependencies: _containers.ScalarMap[str, bool]
    version: str
    def __init__(self, status: _Optional[str] = ..., dependencies: _Optional[_Mapping[str, bool]] = ..., version: _Optional[str] = ...) -> None: ...
