"""
Secure secrets management for Copilotos Bridge.

This module provides utilities for loading secrets from various sources
in a secure manner, with proper validation and error handling.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    """Raised when a required secret cannot be found."""

    pass


class SecretValidationError(Exception):
    """Raised when a secret fails validation."""

    pass


class SecretsManager:
    """
    Secure secrets manager with multiple backends.

    Supports loading secrets from:
    1. Environment variables
    2. Docker secrets (/run/secrets/)
    3. Files (with proper permissions check)
    4. Future: AWS Secrets Manager, HashiCorp Vault
    """

    def __init__(self, validate_on_init: bool = True):
        self.secrets_cache: Dict[str, Any] = {}
        self.cache_ttl = timedelta(minutes=5)  # Short TTL for security
        self.last_cache_clear = datetime.now()

        if validate_on_init:
            self._validate_critical_secrets()

    def get_secret(
        self,
        secret_name: str,
        required: bool = True,
        min_length: int = 8,
        validate_func: Optional[callable] = None,
    ) -> Optional[str]:
        """
        Get a secret from various sources with validation.

        Args:
            secret_name: Name of the secret
            required: If True, raises exception if secret not found
            min_length: Minimum required length for the secret
            validate_func: Custom validation function

        Returns:
            Secret value or None if not found and not required

        Raises:
            SecretNotFoundError: If required secret is not found
            SecretValidationError: If secret fails validation
        """
        # Check cache first (with TTL)
        if self._is_cache_valid() and secret_name in self.secrets_cache:
            return self.secrets_cache[secret_name]

        secret_value = None
        source = None

        # Try different sources in order of preference
        for source_name, loader in [
            ("docker_secret", self._load_from_docker_secret),
            ("environment", self._load_from_env),
            ("file", self._load_from_file),
        ]:
            try:
                secret_value = loader(secret_name)
                if secret_value:
                    source = source_name
                    break
            except Exception as e:
                logger.debug(
                    f"Failed to load secret '{secret_name}' from {source_name}: {e}"
                )

        if not secret_value:
            if required:
                raise SecretNotFoundError(
                    f"Required secret '{secret_name}' not found in any source"
                )
            return None

        # Validate secret
        try:
            self._validate_secret(secret_name, secret_value, min_length, validate_func)
        except SecretValidationError as e:
            if required:
                raise
            logger.warning(f"Secret validation failed for '{secret_name}': {e}")
            return None

        # Cache the secret (with redacted logging)
        self.secrets_cache[secret_name] = secret_value
        logger.info(
            f"Loaded secret '{secret_name}' from {source} (length: {len(secret_value)})"
        )

        return secret_value

    def get_database_url(self, service: str = "mongodb") -> str:
        """
        Get complete database URL with embedded credentials.

        Priority:
        1. Use {SERVICE}_URL from environment if present (e.g., MONGODB_URL, REDIS_URL)
        2. Otherwise, construct URL from individual components

        This allows flexibility for both:
        - Tests: Can provide complete URLs directly
        - Production: Can use individual components with Docker hostnames
        """
        if service == "mongodb":
            # First check if complete URL is provided (e.g., for tests)
            complete_url = os.getenv("MONGODB_URL")
            if complete_url:
                logger.debug("Using MONGODB_URL from environment")
                return complete_url

            # Otherwise, construct from individual components (production default)
            user = os.getenv("MONGODB_USER", "copilotos_user")
            password = self.get_secret("MONGODB_PASSWORD", required=True)
            host = os.getenv("MONGODB_HOST", "mongodb")
            port = os.getenv("MONGODB_PORT", "27017")
            database = os.getenv("MONGODB_DATABASE", "copilotos")
            auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")

            return f"mongodb://{user}:{password}@{host}:{port}/{database}?authSource={auth_source}"

        elif service == "redis":
            # First check if complete URL is provided (e.g., for tests)
            complete_url = os.getenv("REDIS_URL")
            if complete_url:
                logger.debug("Using REDIS_URL from environment")
                return complete_url

            # Otherwise, construct from individual components (production default)
            password = self.get_secret("REDIS_PASSWORD", required=False)
            host = os.getenv("REDIS_HOST", "redis")
            port = os.getenv("REDIS_PORT", "6379")
            db = os.getenv("REDIS_DB", "0")

            # Build URL with or without password
            if password:
                return f"redis://:{password}@{host}:{port}/{db}"
            else:
                return f"redis://{host}:{port}/{db}"

        else:
            raise ValueError(f"Unsupported database service: {service}")

    def mask_secret(self, secret: str, visible_chars: int = 4) -> str:
        """Mask a secret for safe logging."""
        if len(secret) <= visible_chars * 2:
            return "*" * len(secret)
        return (
            secret[:visible_chars]
            + "*" * (len(secret) - visible_chars * 2)
            + secret[-visible_chars:]
        )

    def _load_from_docker_secret(self, secret_name: str) -> Optional[str]:
        """Load secret from Docker secrets (/run/secrets/)."""
        secret_file = Path(f"/run/secrets/{secret_name}")
        if secret_file.exists():
            return secret_file.read_text().strip()

        # Also try lowercase version
        secret_file_lower = Path(f"/run/secrets/{secret_name.lower()}")
        if secret_file_lower.exists():
            return secret_file_lower.read_text().strip()

        return None

    def _load_from_env(self, secret_name: str) -> Optional[str]:
        """Load secret from environment variables."""
        return os.getenv(secret_name)

    def _load_from_file(self, secret_name: str) -> Optional[str]:
        """Load secret from file (with permission checks)."""
        # Check common secret file locations
        for secret_dir in [
            "/etc/copilotos/secrets",
            "/opt/copilotos/secrets",
            "./secrets",
        ]:
            secret_file = Path(secret_dir) / secret_name.lower()
            if secret_file.exists():
                # Check file permissions (should be 600 or 400)
                stat = secret_file.stat()
                if stat.st_mode & 0o077:  # Check if readable by group or others
                    logger.warning(
                        f"Secret file {secret_file} has unsafe permissions: {oct(stat.st_mode)}"
                    )
                    continue

                return secret_file.read_text().strip()

        return None

    def _validate_secret(
        self,
        name: str,
        value: str,
        min_length: int = 8,
        validate_func: Optional[callable] = None,
    ):
        """Validate a secret value."""
        if not value or not value.strip():
            raise SecretValidationError(f"Secret '{name}' is empty")

        if len(value) < min_length:
            raise SecretValidationError(
                f"Secret '{name}' too short (minimum {min_length} characters)"
            )

        # Check for common weak values
        weak_values = [
            "password",
            "123456",
            "admin",
            "secret",
            "test",
            "demo",
            "change_me",
            "changeme",
            "default",
            "temp",
            "temporary",
        ]
        if value.lower() in weak_values:
            raise SecretValidationError(f"Secret '{name}' uses a weak/default value")

        # Custom validation
        if validate_func and not validate_func(value):
            raise SecretValidationError(f"Secret '{name}' failed custom validation")

        # API key format validation
        if "api_key" in name.lower():
            if not (value.startswith(("va-ai-", "sk-")) or len(value) >= 32):
                raise SecretValidationError(
                    f"Secret '{name}' doesn't match expected API key format"
                )

    def _validate_critical_secrets(self):
        """Validate that all critical secrets are available."""
        critical_secrets = [
            ("MONGODB_PASSWORD", 12),
            # REDIS_PASSWORD is optional (for CI/testing without auth)
            ("JWT_SECRET_KEY", 32),
            ("SECRET_KEY", 32),
        ]

        for secret_name, min_length in critical_secrets:
            try:
                self.get_secret(secret_name, required=True, min_length=min_length)
            except (SecretNotFoundError, SecretValidationError) as e:
                logger.error(f"Critical secret validation failed: {e}")
                # In production, this should fail fast
                if os.getenv("NODE_ENV") == "production":
                    raise
                logger.warning(
                    f"Non-production environment, continuing despite secret error: {e}"
                )

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        return datetime.now() - self.last_cache_clear < self.cache_ttl

    def clear_cache(self):
        """Clear the secrets cache."""
        self.secrets_cache.clear()
        self.last_cache_clear = datetime.now()
        logger.info("Secrets cache cleared")


# Global instance
secrets_manager = SecretsManager()


# Convenience functions
def get_secret(name: str, required: bool = True, min_length: int = 8) -> Optional[str]:
    """Get a secret using the global secrets manager."""
    return secrets_manager.get_secret(name, required=required, min_length=min_length)


def get_database_url(service: str = "mongodb") -> str:
    """Get database URL using the global secrets manager."""
    return secrets_manager.get_database_url(service)


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask a secret for safe logging."""
    return secrets_manager.mask_secret(secret, visible_chars)
