"""File Manager services."""

from .minio_client import get_minio_client, MinioClient
from .redis_client import get_redis_client
from .extraction import extract_text_from_file

__all__ = [
    "get_minio_client",
    "MinioClient",
    "get_redis_client",
    "extract_text_from_file",
]
