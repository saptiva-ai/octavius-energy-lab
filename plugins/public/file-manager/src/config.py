"""
Configuration settings for the File Manager plugin.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """File Manager configuration from environment variables."""

    # Service
    service_name: str = "file-manager"
    port: int = 8001
    debug: bool = False
    log_level: str = "INFO"

    # gRPC Server
    grpc_port: int = 50052
    grpc_enabled: bool = True
    grpc_max_workers: int = 10
    grpc_max_message_size: int = 100 * 1024 * 1024  # 100MB

    # MinIO / S3
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_use_ssl: bool = False
    minio_bucket_documents: str = "documents"
    minio_region: str = "us-east-1"

    # Public URL for presigned URLs (optional)
    minio_public_endpoint: Optional[str] = None

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # File Processing
    max_file_size_mb: int = 50
    supported_mime_types: str = "application/pdf,image/png,image/jpeg,image/jpg,image/heic,image/heif,image/gif"

    # OCR Settings
    ocr_max_pages: int = 30
    ocr_raster_dpi: int = 180
    ocr_quality_ratio: float = 0.4

    # Cache
    extraction_cache_ttl_seconds: int = 3600  # 1 hour

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def supported_types_list(self) -> list[str]:
        return [t.strip() for t in self.supported_mime_types.split(",")]

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
