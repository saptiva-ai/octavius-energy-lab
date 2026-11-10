"""
Unit tests for MCP security module.

Tests:
- Rate limiting (sliding window)
- Payload validation (size and structure)
- Authorization scopes (wildcard matching)
- PII scrubbing (regex patterns)
"""

import pytest
import os

# Mark all tests in this file with mcp and mcp_security markers
pytestmark = [
    pytest.mark.mcp,
    pytest.mark.mcp_security,
    pytest.mark.unit,
    pytest.mark.skipif(
        os.getenv("RUN_MCP_SECURITY", "false").lower() != "true",
        reason="MCP security tests deshabilitados por defecto (requires full stack).",
    ),
]
import time
from unittest.mock import AsyncMock, Mock

from src.mcp_integration.security import (
    RateLimiter,
    RateLimitConfig,
    PayloadValidator,
    ScopeValidator,
    PIIScrubber,
    MCPScope,
    get_user_scopes,
)


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        """Test requests within limit are allowed."""
        limiter = RateLimiter(use_redis=False)  # In-memory
        config = RateLimitConfig(calls_per_minute=10, calls_per_hour=100)

        # First request should be allowed
        allowed, retry_after = await limiter.check_rate_limit("user_123:test_tool", config)
        assert allowed is True
        assert retry_after is None

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_limit(self):
        """Test requests are blocked after exceeding limit."""
        limiter = RateLimiter(use_redis=False)
        config = RateLimitConfig(calls_per_minute=3, calls_per_hour=100)

        # Make 3 requests (at limit)
        for _ in range(3):
            allowed, _ = await limiter.check_rate_limit("user_123:test_tool", config)
            assert allowed is True

        # 4th request should be blocked
        allowed, retry_after = await limiter.check_rate_limit("user_123:test_tool", config)
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_rate_limit_per_user_per_tool(self):
        """Test rate limits are isolated per user and tool."""
        limiter = RateLimiter(use_redis=False)
        config = RateLimitConfig(calls_per_minute=2, calls_per_hour=100)

        # User 1, Tool A - use up limit
        await limiter.check_rate_limit("user_1:tool_a", config)
        await limiter.check_rate_limit("user_1:tool_a", config)
        allowed, _ = await limiter.check_rate_limit("user_1:tool_a", config)
        assert allowed is False  # Blocked

        # User 1, Tool B - should still work (different tool)
        allowed, _ = await limiter.check_rate_limit("user_1:tool_b", config)
        assert allowed is True

        # User 2, Tool A - should still work (different user)
        allowed, _ = await limiter.check_rate_limit("user_2:tool_a", config)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_hour_window(self):
        """Test hour window rate limiting."""
        limiter = RateLimiter(use_redis=False)
        config = RateLimitConfig(calls_per_minute=1000, calls_per_hour=5)

        # Make 5 requests (at hour limit)
        for _ in range(5):
            allowed, _ = await limiter.check_rate_limit("user_123:test_tool", config)
            assert allowed is True

        # 6th request should be blocked by hour limit
        allowed, retry_after = await limiter.check_rate_limit("user_123:test_tool", config)
        assert allowed is False
        assert retry_after is not None


class TestPayloadValidator:
    """Test payload validation."""

    def test_validate_size_within_limit(self):
        """Test payload within size limit passes."""
        payload = {"data": "x" * 100}  # Small payload
        assert PayloadValidator.validate_size(payload, max_size_kb=1) is True

    def test_validate_size_exceeds_limit(self):
        """Test oversized payload is rejected."""
        payload = {"data": "x" * (2 * 1024 * 1024)}  # 2MB
        with pytest.raises(ValueError, match="Payload too large"):
            PayloadValidator.validate_size(payload, max_size_kb=1024)

    def test_validate_structure_simple(self):
        """Test simple valid structure."""
        payload = {
            "name": "test",
            "count": 123,
            "enabled": True,
        }
        assert PayloadValidator.validate_structure(payload) is True

    def test_validate_structure_nested(self):
        """Test nested structure validation."""
        payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": "nested"
                    }
                }
            }
        }
        assert PayloadValidator.validate_structure(payload) is True

    def test_validate_structure_too_deep(self):
        """Test excessively nested structure is rejected."""
        # Create deeply nested dict (11 levels)
        payload = {"level": "data"}
        for i in range(11):
            payload = {"nested": payload}

        with pytest.raises(ValueError, match="nesting too deep"):
            PayloadValidator.validate_structure(payload)

    def test_validate_structure_string_too_long(self):
        """Test oversized string is rejected."""
        payload = {"data": "x" * (PayloadValidator.MAX_STRING_LENGTH + 1)}

        with pytest.raises(ValueError, match="String too long"):
            PayloadValidator.validate_structure(payload)

    def test_validate_structure_array_too_long(self):
        """Test oversized array is rejected."""
        payload = {"items": list(range(PayloadValidator.MAX_ARRAY_LENGTH + 1))}

        with pytest.raises(ValueError, match="Array too long"):
            PayloadValidator.validate_structure(payload)

    def test_validate_structure_invalid_key(self):
        """Test non-string key is rejected."""
        payload = {123: "value"}  # Integer key

        with pytest.raises(ValueError, match="Invalid key type"):
            PayloadValidator.validate_structure(payload)

    def test_validate_structure_key_too_long(self):
        """Test oversized key is rejected."""
        long_key = "x" * 101
        payload = {long_key: "value"}

        with pytest.raises(ValueError, match="Key too long"):
            PayloadValidator.validate_structure(payload)


class TestScopeValidator:
    """Test authorization scope validation."""

    def test_check_scope_exact_match(self):
        """Test exact scope match."""
        user_scopes = {MCPScope.TOOLS_AUDIT.value}
        required = MCPScope.TOOLS_AUDIT

        assert ScopeValidator.check_scope(user_scopes, required) is True

    def test_check_scope_wildcard_tools(self):
        """Test tools wildcard (mcp:tools.*)."""
        user_scopes = {MCPScope.TOOLS_ALL.value}  # mcp:tools.*
        required = MCPScope.TOOLS_AUDIT  # mcp:tools.audit

        assert ScopeValidator.check_scope(user_scopes, required) is True

    def test_check_scope_wildcard_admin(self):
        """Test admin wildcard (mcp:admin.*)."""
        user_scopes = {MCPScope.ADMIN_ALL.value}  # mcp:admin.*
        required = MCPScope.ADMIN_TOOLS_MANAGE  # mcp:admin.tools.manage

        assert ScopeValidator.check_scope(user_scopes, required) is True

    def test_check_scope_no_match(self):
        """Test scope mismatch."""
        user_scopes = {MCPScope.TOOLS_AUDIT.value}
        required = MCPScope.TOOLS_ANALYTICS

        assert ScopeValidator.check_scope(user_scopes, required) is False

    def test_validate_tool_access_allowed(self):
        """Test tool access validation when allowed."""
        user_scopes = {MCPScope.TOOLS_AUDIT.value}

        # Should not raise
        assert ScopeValidator.validate_tool_access(user_scopes, "excel_analyzer") is True

    def test_validate_tool_access_denied(self):
        """Test tool access validation when denied."""
        user_scopes = {MCPScope.TOOLS_VIZ.value}  # Only viz tools

        with pytest.raises(PermissionError, match="Missing required scope"):
            ScopeValidator.validate_tool_access(user_scopes, "excel_analyzer")

    def test_validate_tool_access_no_scope_required(self):
        """Test tool with no scope requirement."""
        user_scopes = set()  # No scopes

        # Unknown tools have no scope requirement
        assert ScopeValidator.validate_tool_access(user_scopes, "unknown_tool") is True

    def test_get_required_scope(self):
        """Test getting required scope for tools."""
        assert ScopeValidator.get_required_scope("excel_analyzer") == MCPScope.TOOLS_AUDIT
        assert ScopeValidator.get_required_scope("excel_analyzer") == MCPScope.TOOLS_ANALYTICS
        assert ScopeValidator.get_required_scope("viz_tool") == MCPScope.TOOLS_VIZ
        assert ScopeValidator.get_required_scope("unknown_tool") is None


class TestPIIScrubber:
    """Test PII scrubbing functionality."""

    def test_scrub_email(self):
        """Test email address scrubbing."""
        text = "Contact me at john.doe@example.com for details"
        scrubbed = PIIScrubber.scrub(text)

        assert "john.doe@example.com" not in scrubbed
        assert "[EMAIL_REDACTED]" in scrubbed

    def test_scrub_multiple_emails(self):
        """Test multiple email addresses."""
        text = "Email alice@test.com or bob@test.com"
        scrubbed = PIIScrubber.scrub(text)

        assert "alice@test.com" not in scrubbed
        assert "bob@test.com" not in scrubbed
        assert scrubbed.count("[EMAIL_REDACTED]") == 2

    def test_scrub_phone_numbers(self):
        """Test phone number scrubbing."""
        text = "Call 555-123-4567 or 555.987.6543"
        scrubbed = PIIScrubber.scrub(text)

        assert "555-123-4567" not in scrubbed
        assert "555.987.6543" not in scrubbed
        assert "[PHONE_REDACTED]" in scrubbed

    def test_scrub_ssn(self):
        """Test SSN scrubbing."""
        text = "SSN: 123-45-6789"
        scrubbed = PIIScrubber.scrub(text)

        assert "123-45-6789" not in scrubbed
        assert "[SSN_REDACTED]" in scrubbed

    def test_scrub_credit_card(self):
        """Test credit card scrubbing."""
        text = "Card: 4111-1111-1111-1111"
        scrubbed = PIIScrubber.scrub(text)

        assert "4111-1111-1111-1111" not in scrubbed
        assert "[CC_REDACTED]" in scrubbed

    def test_scrub_ip_address(self):
        """Test IP address scrubbing."""
        text = "From IP 192.168.1.100"
        scrubbed = PIIScrubber.scrub(text)

        assert "192.168.1.100" not in scrubbed
        assert "[IP_REDACTED]" in scrubbed

    def test_scrub_api_key(self):
        """Test API key scrubbing."""
        text = "API key: sk_test_EXAMPLE_KEY_FOR_TESTING"
        scrubbed = PIIScrubber.scrub(text)

        assert "sk_test_EXAMPLE_KEY_FOR_TESTING" not in scrubbed
        assert "[KEY_REDACTED]" in scrubbed

    def test_scrub_preserves_structure(self):
        """Test that scrubbing preserves text structure."""
        text = "User alice@test.com called from 555-1234"
        scrubbed = PIIScrubber.scrub(text)

        # Structure should be preserved
        assert scrubbed.startswith("User")
        assert "called from" in scrubbed

    def test_scrub_dict_shallow(self):
        """Test dictionary scrubbing (shallow)."""
        data = {
            "email": "test@example.com",
            "phone": "555-1234",
            "name": "John Doe",
        }

        scrubbed = PIIScrubber.scrub_dict(data)

        assert scrubbed["email"] == "[EMAIL_REDACTED]"
        assert "[PHONE_REDACTED]" in scrubbed["phone"]
        assert scrubbed["name"] == "John Doe"  # No PII

    def test_scrub_dict_nested(self):
        """Test dictionary scrubbing (nested)."""
        data = {
            "user": {
                "email": "test@example.com",
                "contact": {
                    "phone": "555-1234"
                }
            }
        }

        scrubbed = PIIScrubber.scrub_dict(data)

        assert scrubbed["user"]["email"] == "[EMAIL_REDACTED]"
        assert "[PHONE_REDACTED]" in scrubbed["user"]["contact"]["phone"]

    def test_scrub_dict_with_arrays(self):
        """Test dictionary scrubbing with arrays."""
        data = {
            "emails": ["alice@test.com", "bob@test.com"],
            "users": [
                {"email": "charlie@test.com"},
                {"email": "dave@test.com"},
            ]
        }

        scrubbed = PIIScrubber.scrub_dict(data)

        assert scrubbed["emails"][0] == "[EMAIL_REDACTED]"
        assert scrubbed["emails"][1] == "[EMAIL_REDACTED]"
        assert scrubbed["users"][0]["email"] == "[EMAIL_REDACTED]"
        assert scrubbed["users"][1]["email"] == "[EMAIL_REDACTED]"

    def test_scrub_no_pii(self):
        """Test scrubbing text with no PII."""
        text = "This is a normal message with no sensitive data"
        scrubbed = PIIScrubber.scrub(text)

        assert scrubbed == text  # Unchanged


class TestGetUserScopes:
    """Test get_user_scopes helper."""

    def test_get_user_scopes_authenticated(self):
        """Test getting scopes for authenticated user."""
        user = Mock()
        user.id = "user_123"

        scopes = get_user_scopes(user)

        # Should have default scopes
        assert MCPScope.TOOLS_ALL.value in scopes
        assert MCPScope.TASKS_CREATE.value in scopes
        assert MCPScope.TASKS_READ.value in scopes
        assert MCPScope.TASKS_CANCEL.value in scopes

    def test_get_user_scopes_unauthenticated(self):
        """Test getting scopes for unauthenticated user."""
        scopes = get_user_scopes(None)

        assert scopes == set()  # No scopes


class TestSecurityIntegration:
    """Integration tests for security components."""

    @pytest.mark.asyncio
    async def test_full_security_pipeline(self):
        """Test complete security validation pipeline."""
        # 1. Validate payload
        payload = {
            "doc_id": "doc_123",
            "email": "test@example.com",  # Contains PII
        }

        PayloadValidator.validate_size(payload, max_size_kb=1024)
        PayloadValidator.validate_structure(payload)

        # 2. Scrub PII
        scrubbed_payload = PIIScrubber.scrub_dict(payload)
        assert scrubbed_payload["email"] == "[EMAIL_REDACTED]"

        # 3. Check rate limit
        limiter = RateLimiter(use_redis=False)
        config = RateLimitConfig(calls_per_minute=10, calls_per_hour=100)
        allowed, _ = await limiter.check_rate_limit("user_123:excel_analyzer", config)
        assert allowed is True

        # 4. Check authorization
        user_scopes = {MCPScope.TOOLS_AUDIT.value}
        ScopeValidator.validate_tool_access(user_scopes, "excel_analyzer")

    def test_security_defense_in_depth(self):
        """Test multiple security layers catch different issues."""
        # Layer 1: Size validation
        huge_payload = {"data": "x" * (2 * 1024 * 1024)}
        with pytest.raises(ValueError, match="Payload too large"):
            PayloadValidator.validate_size(huge_payload, max_size_kb=1024)

        # Layer 2: Structure validation
        deep_payload = {"nested": {"nested": {"nested": {"nested": {}}}}}
        for _ in range(10):
            deep_payload = {"nested": deep_payload}
        with pytest.raises(ValueError, match="nesting too deep"):
            PayloadValidator.validate_structure(deep_payload)

        # Layer 3: Authorization
        user_scopes = {MCPScope.TOOLS_VIZ.value}
        with pytest.raises(PermissionError):
            ScopeValidator.validate_tool_access(user_scopes, "excel_analyzer")
