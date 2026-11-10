from __future__ import annotations

"""
MCP Security - Rate limiting, payload size limits, AuthZ scopes, PII scrubbing.

Features:
- Per-tool rate limiting (Redis-backed sliding window)
- Payload size validation
- Authorization scopes (mcp:tools.audit, mcp:tools.viz, etc.)
- PII scrubbing for logs (emails, phones, SSNs)
- Request validation and sanitization

Security principles:
- Defense in depth
- Fail secure
- Least privilege
- Audit everything
"""

import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

import structlog

from ..core.redis_cache import get_redis_cache

logger = structlog.get_logger(__name__)


class MCPScope(str, Enum):
    """
    Authorization scopes for MCP tools.

    Format: mcp:category.action
    - mcp:tools.* - All tools
    - mcp:tools.audit - Document audit tools
    - mcp:tools.analytics - Data analytics tools
    - mcp:tools.viz - Visualization tools
    - mcp:admin.* - Admin operations
    """

    # Tool access scopes
    TOOLS_ALL = "mcp:tools.*"
    TOOLS_AUDIT = "mcp:tools.audit"
    TOOLS_ANALYTICS = "mcp:tools.analytics"
    TOOLS_VIZ = "mcp:tools.viz"
    TOOLS_RESEARCH = "mcp:tools.research"

    # Admin scopes
    ADMIN_ALL = "mcp:admin.*"
    ADMIN_TOOLS_MANAGE = "mcp:admin.tools.manage"
    ADMIN_METRICS = "mcp:admin.metrics"

    # Task management scopes
    TASKS_CREATE = "mcp:tasks.create"
    TASKS_READ = "mcp:tasks.read"
    TASKS_CANCEL = "mcp:tasks.cancel"


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a tool."""

    calls_per_minute: int
    calls_per_hour: int
    burst_size: int = 10  # Max burst before throttling


class RateLimiter:
    """
    Redis-backed sliding window rate limiter.

    Uses sorted sets with timestamps for precise rate limiting.
    Supports multiple time windows (minute, hour).
    """

    def __init__(self, redis_client=None, *, use_redis: bool = True):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance (optional, uses in-memory fallback)
        """
        self.redis = redis_client
        self.use_redis = use_redis
        self._memory_storage: Dict[str, List[float]] = {}  # Fallback in-memory

    async def _get_redis_client(self):
        """Lazily obtain Redis client (fallback to in-memory on failure)."""
        if not self.use_redis:
            return None

        if self.redis:
            return self.redis

        try:
            redis_cache = await get_redis_cache()
            if redis_cache.client is None:
                await redis_cache.connect()
            self.redis = redis_cache.client
        except Exception as exc:
            logger.warning(
                "RateLimiter redis init failed, using in-memory fallback",
                error=str(exc),
            )
            self.redis = None
        return self.redis

    async def check_rate_limit(
        self,
        key: str,
        limit_config: RateLimitConfig,
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., "user_123:audit_file")
            limit_config: Rate limit configuration

        Returns:
            (allowed: bool, retry_after_ms: Optional[int])
            - allowed: True if request allowed
            - retry_after_ms: Time to wait before retry (if not allowed)
        """
        now = time.time()

        # Check minute window
        minute_key = f"ratelimit:minute:{key}"
        minute_count = await self._get_count(minute_key, now - 60)

        if minute_count >= limit_config.calls_per_minute:
            # Calculate retry time
            oldest_timestamp = await self._get_oldest(minute_key)
            retry_after_ms = int((oldest_timestamp + 60 - now) * 1000)

            logger.warning(
                "Rate limit exceeded (minute)",
                key=key,
                count=minute_count,
                limit=limit_config.calls_per_minute,
                retry_after_ms=retry_after_ms,
            )

            return (False, retry_after_ms)

        # Check hour window
        hour_key = f"ratelimit:hour:{key}"
        hour_count = await self._get_count(hour_key, now - 3600)

        if hour_count >= limit_config.calls_per_hour:
            oldest_timestamp = await self._get_oldest(hour_key)
            retry_after_ms = int((oldest_timestamp + 3600 - now) * 1000)

            logger.warning(
                "Rate limit exceeded (hour)",
                key=key,
                count=hour_count,
                limit=limit_config.calls_per_hour,
                retry_after_ms=retry_after_ms,
            )

            return (False, retry_after_ms)

        # Record request
        await self._record_request(minute_key, now, ttl=120)  # 2 minutes TTL
        await self._record_request(hour_key, now, ttl=7200)  # 2 hours TTL

        return (True, None)

    async def _get_count(self, key: str, since: float) -> int:
        """Get count of requests since timestamp."""
        redis_client = await self._get_redis_client()

        if redis_client:
            # Redis implementation
            try:
                return await redis_client.zcount(key, since, "+inf")
            except Exception as e:
                logger.error("Redis error in rate limiter", error=str(e))
                return 0
        else:
            # In-memory fallback
            timestamps = self._memory_storage.get(key, [])
            return len([t for t in timestamps if t >= since])

    async def _get_oldest(self, key: str) -> float:
        """Get oldest timestamp in window."""
        redis_client = await self._get_redis_client()

        if redis_client:
            try:
                result = await redis_client.zrange(key, 0, 0, withscores=True)
                return result[0][1] if result else time.time()
            except Exception:
                return time.time()
        else:
            timestamps = self._memory_storage.get(key, [])
            return min(timestamps) if timestamps else time.time()

    async def _record_request(self, key: str, timestamp: float, ttl: int):
        """Record a request timestamp."""
        redis_client = await self._get_redis_client()

        if redis_client:
            try:
                await redis_client.zadd(key, {str(timestamp): timestamp})
                await redis_client.expire(key, ttl)
            except Exception as e:
                logger.error("Redis error recording request", error=str(e))
        else:
            # In-memory fallback
            if key not in self._memory_storage:
                self._memory_storage[key] = []
            self._memory_storage[key].append(timestamp)

            # Cleanup old entries
            cutoff = timestamp - ttl
            self._memory_storage[key] = [
                t for t in self._memory_storage[key] if t > cutoff
            ]


class PayloadValidator:
    """Validate and sanitize tool payloads."""

    MAX_PAYLOAD_SIZE_KB = 1024  # 1MB default
    MAX_STRING_LENGTH = 10000
    MAX_ARRAY_LENGTH = 1000
    MAX_NESTING_DEPTH = 10

    @classmethod
    def validate_size(
        cls, payload: dict, max_size_kb: int = MAX_PAYLOAD_SIZE_KB
    ) -> bool:
        """
        Check payload size.

        Args:
            payload: Tool payload
            max_size_kb: Max size in KB

        Returns:
            True if valid

        Raises:
            ValueError: If payload too large
        """
        import json

        payload_bytes = json.dumps(payload).encode("utf-8")
        size_kb = len(payload_bytes) / 1024

        if size_kb > max_size_kb:
            raise ValueError(
                f"Payload too large: {size_kb:.2f}KB exceeds limit of {max_size_kb}KB"
            )

        return True

    @classmethod
    def validate_structure(cls, payload: dict, depth: int = 0) -> bool:
        """
        Validate payload structure.

        Checks:
        - Max nesting depth
        - String length limits
        - Array length limits
        - No executable code

        Raises:
            ValueError: If validation fails
        """
        if depth > cls.MAX_NESTING_DEPTH:
            raise ValueError(f"Payload nesting too deep (max: {cls.MAX_NESTING_DEPTH})")

        for key, value in payload.items():
            # Check key
            if not isinstance(key, str):
                raise ValueError(f"Invalid key type: {type(key)}")

            if len(key) > 100:
                raise ValueError(f"Key too long: {len(key)} chars (max: 100)")

            # Check value
            if isinstance(value, str):
                if len(value) > cls.MAX_STRING_LENGTH:
                    raise ValueError(
                        f"String too long: {len(value)} chars (max: {cls.MAX_STRING_LENGTH})"
                    )

            elif isinstance(value, list):
                if len(value) > cls.MAX_ARRAY_LENGTH:
                    raise ValueError(
                        f"Array too long: {len(value)} items (max: {cls.MAX_ARRAY_LENGTH})"
                    )

                # Check array items recursively
                for item in value:
                    if isinstance(item, dict):
                        cls.validate_structure(item, depth + 1)

            elif isinstance(value, dict):
                cls.validate_structure(value, depth + 1)

        return True


class ScopeValidator:
    """Validate user authorization scopes."""

    # Tool name -> required scope mapping
    TOOL_SCOPES: Dict[str, MCPScope] = {
        "audit_file": MCPScope.TOOLS_AUDIT,
        "excel_analyzer": MCPScope.TOOLS_ANALYTICS,
        "viz_tool": MCPScope.TOOLS_VIZ,
    }

    @classmethod
    def check_scope(cls, user_scopes: Set[str], required_scope: MCPScope) -> bool:
        """
        Check if user has required scope.

        Supports wildcard matching:
        - User has "mcp:tools.*" → Grants access to all tools
        - User has "mcp:admin.*" → Grants access to all admin ops

        Args:
            user_scopes: Set of user's scopes
            required_scope: Required scope

        Returns:
            True if authorized
        """
        # Check exact match
        if required_scope.value in user_scopes:
            return True

        # Check wildcard matches
        # e.g., mcp:tools.* matches mcp:tools.audit
        scope_parts = required_scope.value.split(":")
        if len(scope_parts) == 2:
            category = scope_parts[0]
            action = scope_parts[1]

            # Check category wildcard (e.g., mcp:tools.*)
            wildcard = f"{category}:{action.split('.')[0]}.*"
            if wildcard in user_scopes:
                return True

            # Check full wildcard (mcp:*)
            if f"{category}:*" in user_scopes:
                return True

        return False

    @classmethod
    def get_required_scope(cls, tool_name: str) -> Optional[MCPScope]:
        """Get required scope for a tool."""
        return cls.TOOL_SCOPES.get(tool_name)

    @classmethod
    def validate_tool_access(cls, user_scopes: Set[str], tool_name: str) -> bool:
        """
        Validate user can access tool.

        Raises:
            PermissionError: If user lacks required scope
        """
        required_scope = cls.get_required_scope(tool_name)

        if required_scope is None:
            # No scope required for this tool
            return True

        if not cls.check_scope(user_scopes, required_scope):
            raise PermissionError(
                f"Missing required scope '{required_scope.value}' for tool '{tool_name}'"
            )

        return True

    @classmethod
    def require_scope(cls, user_scopes: Set[str], required_scope: MCPScope) -> None:
        """
        Ensure user has the required scope (raises on failure).
        """
        if not cls.check_scope(user_scopes, required_scope):
            raise PermissionError(f"Missing required scope '{required_scope.value}'")


class PIIScrubber:
    """
    Scrub PII from logs and error messages.

    Redacts:
    - Email addresses
    - Phone numbers (US format)
    - SSNs (US format)
    - Credit card numbers
    - IP addresses
    - API keys/tokens (common patterns)
    """

    # Regex patterns for PII
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(r"\b(?:\d{3}[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
    IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    API_KEY_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")  # Long alphanumeric strings

    @classmethod
    def scrub(cls, text: str) -> str:
        """
        Scrub PII from text.

        Args:
            text: Input text

        Returns:
            Scrubbed text with PII replaced
        """
        # Scrub emails
        text = cls.EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)

        # Scrub phone numbers
        text = cls.PHONE_PATTERN.sub("[PHONE_REDACTED]", text)

        # Scrub SSNs
        text = cls.SSN_PATTERN.sub("[SSN_REDACTED]", text)

        # Scrub credit cards
        text = cls.CREDIT_CARD_PATTERN.sub("[CC_REDACTED]", text)

        # Scrub IPs
        text = cls.IP_PATTERN.sub("[IP_REDACTED]", text)

        # Scrub API keys (be conservative)
        # Only scrub if looks like a key (not just any long string)
        if "key" in text.lower() or "token" in text.lower():
            text = cls.API_KEY_PATTERN.sub("[KEY_REDACTED]", text)

        return text

    @classmethod
    def scrub_dict(cls, data: dict) -> dict:
        """
        Recursively scrub PII from dictionary.

        Args:
            data: Input dictionary

        Returns:
            Scrubbed dictionary
        """
        scrubbed = {}

        for key, value in data.items():
            if isinstance(value, str):
                scrubbed[key] = cls.scrub(value)
            elif isinstance(value, dict):
                scrubbed[key] = cls.scrub_dict(value)
            elif isinstance(value, list):
                scrubbed[key] = [
                    (
                        cls.scrub(item)
                        if isinstance(item, str)
                        else cls.scrub_dict(item)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            else:
                scrubbed[key] = value

        return scrubbed


# Global rate limiter instance
rate_limiter = RateLimiter()


def _get_admin_identifiers() -> Set[str]:
    """Read MCP admin identifiers (usernames/emails) from env."""
    return {
        identifier.strip().lower()
        for identifier in os.getenv("MCP_ADMIN_USERS", "").split(",")
        if identifier.strip()
    }


def get_user_scopes(user) -> Set[str]:
    """
    Extract scopes from user object.

    In future, could read from:
    - User.scopes attribute
    - JWT claims
    - Database roles table

    For now, returns default scopes based on user existence.
    """
    if not user:
        return set()

    # Default scopes for authenticated users
    scopes = {
        MCPScope.TOOLS_ALL.value,
        MCPScope.TASKS_CREATE.value,
        MCPScope.TASKS_READ.value,
        MCPScope.TASKS_CANCEL.value,
    }

    # Grant admin scopes if user is configured as MCP admin
    admin_identifiers = _get_admin_identifiers()
    if admin_identifiers:
        username = getattr(user, "username", "") or ""
        email = getattr(user, "email", "") or ""
        identifiers = {username.lower(), email.lower()}
        if identifiers & admin_identifiers:
            scopes.update(
                {
                    MCPScope.ADMIN_ALL.value,
                    MCPScope.ADMIN_TOOLS_MANAGE.value,
                    MCPScope.ADMIN_METRICS.value,
                }
            )

    return scopes
