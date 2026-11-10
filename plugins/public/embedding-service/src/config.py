"""
Embedding Service Configuration.

Uses pydantic-settings for environment-based configuration.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Embedding service settings from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        extra="ignore",
    )

    # Service
    service_name: str = "embedding-service"
    port: int = 8003

    # Model Configuration
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
    device: str = "cpu"  # cpu or cuda

    # Chunking Parameters
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Cache Configuration
    query_cache_size: int = 1000

    # Performance
    batch_size: int = 32


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
