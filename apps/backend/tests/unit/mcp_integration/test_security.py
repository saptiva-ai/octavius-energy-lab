"""
Unit tests for MCP security module.

Tests:
- MCPScope enum values
- PayloadValidator size and structure validation
- ScopeValidator authorization checks
- PIIScrubber data redaction
- RateLimiter in-memory fallback
- get_user_scopes function
"""

import pytest

from src.mcp_integration.security import (
    MCPScope,
    PayloadValidator,
    PIIScrubber,
    RateLimitConfig,
    RateLimiter,
    ScopeValidator,
    get_user_scopes,
)

pytestmark = [pytest.mark.unit]


class TestMCPScope:
    """Test MCPScope enum."""

    def test_tool_scopes_exist(self):
        """Test tool access scopes are defined."""
        assert MCPScope.TOOLS_ALL.value == "mcp:tools.*"
        assert MCPScope.TOOLS_AUDIT.value == "mcp:tools.audit"
        assert MCPScope.TOOLS_ANALYTICS.value == "mcp:tools.analytics"
        assert MCPScope.TOOLS_VIZ.value == "mcp:tools.viz"
        assert MCPScope.TOOLS_RESEARCH.value == "mcp:tools.research"

    def test_admin_scopes_exist(self):
        """Test admin scopes are defined."""
        assert MCPScope.ADMIN_ALL.value == "mcp:admin.*"
        assert MCPScope.ADMIN_TOOLS_MANAGE.value == "mcp:admin.tools.manage"
        assert MCPScope.ADMIN_METRICS.value == "mcp:admin.metrics"

    def test_task_scopes_exist(self):
        """Test task management scopes are defined."""
        assert MCPScope.TASKS_CREATE.value == "mcp:tasks.create"
        assert MCPScope.TASKS_READ.value == "mcp:tasks.read"
        assert MCPScope.TASKS_CANCEL.value == "mcp:tasks.cancel"

    def test_scope_is_string(self):
        """Test scope values are strings."""
        for scope in MCPScope:
            assert isinstance(scope.value, str)
            assert scope.value.startswith("mcp:")


class TestRateLimitConfig:
    """Test RateLimitConfig dataclass."""

    def test_create_config(self):
        """Test creating rate limit config."""
        config = RateLimitConfig(
            calls_per_minute=10,
            calls_per_hour=100,
        )

        assert config.calls_per_minute == 10
        assert config.calls_per_hour == 100
        assert config.burst_size == 10  # Default

    def test_create_config_with_burst(self):
        """Test creating config with custom burst size."""
        config = RateLimitConfig(
            calls_per_minute=5,
            calls_per_hour=50,
            burst_size=20,
        )

        assert config.burst_size == 20


class TestPayloadValidator:
    """Test PayloadValidator class."""

    def test_validate_size_small_payload(self):
        """Test small payload passes size validation."""
        payload = {"key": "value"}
        result = PayloadValidator.validate_size(payload)
        assert result is True

    def test_validate_size_large_payload_rejected(self):
        """Test payload exceeding size limit is rejected."""
        # Create a payload larger than 1KB
        large_string = "x" * (2 * 1024 * 1024)  # 2MB
        payload = {"data": large_string}

        with pytest.raises(ValueError) as exc_info:
            PayloadValidator.validate_size(payload)

        assert "Payload too large" in str(exc_info.value)

    def test_validate_size_custom_limit(self):
        """Test custom size limit."""
        payload = {"data": "x" * 100}  # ~100 bytes

        # With low limit (0.05KB = 51 bytes), should fail
        with pytest.raises(ValueError):
            PayloadValidator.validate_size(payload, max_size_kb=0.05)

    def test_validate_structure_valid(self):
        """Test valid structure passes."""
        payload = {
            "name": "test",
            "items": [1, 2, 3],
            "nested": {"key": "value"},
        }

        result = PayloadValidator.validate_structure(payload)
        assert result is True

    def test_validate_structure_deep_nesting_rejected(self):
        """Test deeply nested structure is rejected."""
        # Create nesting > 10 levels deep
        payload = {"level0": {}}
        current = payload["level0"]
        for i in range(1, 15):
            current[f"level{i}"] = {}
            current = current[f"level{i}"]

        with pytest.raises(ValueError) as exc_info:
            PayloadValidator.validate_structure(payload)

        assert "nesting too deep" in str(exc_info.value)

    def test_validate_structure_long_string_rejected(self):
        """Test overly long string is rejected."""
        payload = {"data": "x" * 15000}  # Exceeds MAX_STRING_LENGTH

        with pytest.raises(ValueError) as exc_info:
            PayloadValidator.validate_structure(payload)

        assert "String too long" in str(exc_info.value)

    def test_validate_structure_long_array_rejected(self):
        """Test overly long array is rejected."""
        payload = {"items": list(range(1500))}  # Exceeds MAX_ARRAY_LENGTH

        with pytest.raises(ValueError) as exc_info:
            PayloadValidator.validate_structure(payload)

        assert "Array too long" in str(exc_info.value)

    def test_validate_structure_long_key_rejected(self):
        """Test overly long key is rejected."""
        long_key = "k" * 150  # Exceeds 100 char limit
        payload = {long_key: "value"}

        with pytest.raises(ValueError) as exc_info:
            PayloadValidator.validate_structure(payload)

        assert "Key too long" in str(exc_info.value)

    def test_validate_structure_nested_dict_in_array(self):
        """Test nested dicts in arrays are validated."""
        payload = {
            "items": [
                {"nested_data": "x" * 15000}  # Too long
            ]
        }

        with pytest.raises(ValueError):
            PayloadValidator.validate_structure(payload)


class TestScopeValidator:
    """Test ScopeValidator class."""

    def test_check_scope_exact_match(self):
        """Test exact scope match."""
        user_scopes = {"mcp:tools.audit"}

        result = ScopeValidator.check_scope(user_scopes, MCPScope.TOOLS_AUDIT)
        assert result is True

    def test_check_scope_no_match(self):
        """Test scope not matching."""
        user_scopes = {"mcp:tools.viz"}

        result = ScopeValidator.check_scope(user_scopes, MCPScope.TOOLS_AUDIT)
        assert result is False

    def test_check_scope_wildcard_tools(self):
        """Test wildcard scope matches tool scopes."""
        user_scopes = {"mcp:tools.*"}

        assert ScopeValidator.check_scope(user_scopes, MCPScope.TOOLS_AUDIT) is True
        assert ScopeValidator.check_scope(user_scopes, MCPScope.TOOLS_VIZ) is True
        assert ScopeValidator.check_scope(user_scopes, MCPScope.TOOLS_ANALYTICS) is True

    def test_check_scope_wildcard_admin(self):
        """Test admin wildcard matches admin scopes."""
        user_scopes = {"mcp:admin.*"}

        assert ScopeValidator.check_scope(user_scopes, MCPScope.ADMIN_METRICS) is True
        assert (
            ScopeValidator.check_scope(user_scopes, MCPScope.ADMIN_TOOLS_MANAGE) is True
        )

    def test_check_scope_wildcard_does_not_cross_categories(self):
        """Test tools wildcard doesn't grant admin access."""
        user_scopes = {"mcp:tools.*"}

        assert ScopeValidator.check_scope(user_scopes, MCPScope.ADMIN_METRICS) is False

    def test_get_required_scope_known_tool(self):
        """Test getting required scope for known tool."""
        scope = ScopeValidator.get_required_scope("audit_file")
        assert scope == MCPScope.TOOLS_AUDIT

        scope = ScopeValidator.get_required_scope("excel_analyzer")
        assert scope == MCPScope.TOOLS_ANALYTICS

    def test_get_required_scope_unknown_tool(self):
        """Test unknown tool returns None."""
        scope = ScopeValidator.get_required_scope("unknown_tool")
        assert scope is None

    def test_validate_tool_access_authorized(self):
        """Test authorized access passes."""
        user_scopes = {"mcp:tools.audit"}

        result = ScopeValidator.validate_tool_access(user_scopes, "audit_file")
        assert result is True

    def test_validate_tool_access_unauthorized(self):
        """Test unauthorized access raises PermissionError."""
        user_scopes = {"mcp:tools.viz"}  # Has viz, not audit

        with pytest.raises(PermissionError) as exc_info:
            ScopeValidator.validate_tool_access(user_scopes, "audit_file")

        assert "mcp:tools.audit" in str(exc_info.value)

    def test_validate_tool_access_no_scope_required(self):
        """Test tool with no required scope passes."""
        user_scopes = set()  # Empty scopes

        # Unknown tool has no required scope
        result = ScopeValidator.validate_tool_access(user_scopes, "unknown_tool")
        assert result is True

    def test_require_scope_passes(self):
        """Test require_scope passes when scope present."""
        user_scopes = {"mcp:tools.audit"}

        # Should not raise
        ScopeValidator.require_scope(user_scopes, MCPScope.TOOLS_AUDIT)

    def test_require_scope_fails(self):
        """Test require_scope raises when scope missing."""
        user_scopes = set()

        with pytest.raises(PermissionError):
            ScopeValidator.require_scope(user_scopes, MCPScope.TOOLS_AUDIT)


class TestPIIScrubber:
    """Test PIIScrubber class."""

    def test_scrub_email(self):
        """Test email addresses are scrubbed."""
        text = "Contact: user@example.com for help"
        result = PIIScrubber.scrub(text)

        assert "user@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_scrub_multiple_emails(self):
        """Test multiple emails are all scrubbed."""
        text = "From: a@x.com To: b@y.org CC: c@z.net"
        result = PIIScrubber.scrub(text)

        assert "a@x.com" not in result
        assert "b@y.org" not in result
        assert "c@z.net" not in result
        assert result.count("[EMAIL_REDACTED]") == 3

    def test_scrub_phone_with_dashes(self):
        """Test phone numbers with dashes are scrubbed."""
        text = "Call 123-456-7890 for support"
        result = PIIScrubber.scrub(text)

        assert "123-456-7890" not in result
        assert "[PHONE_REDACTED]" in result

    def test_scrub_phone_with_dots(self):
        """Test phone numbers with dots are scrubbed."""
        text = "Phone: 123.456.7890"
        result = PIIScrubber.scrub(text)

        assert "123.456.7890" not in result
        assert "[PHONE_REDACTED]" in result

    def test_scrub_phone_without_area_code(self):
        """Test 7-digit phone is scrubbed."""
        text = "Local: 456-7890"
        result = PIIScrubber.scrub(text)

        assert "456-7890" not in result
        assert "[PHONE_REDACTED]" in result

    def test_scrub_ssn(self):
        """Test SSNs are scrubbed."""
        text = "SSN: 123-45-6789"
        result = PIIScrubber.scrub(text)

        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_scrub_credit_card_with_spaces(self):
        """Test credit cards with spaces are scrubbed."""
        text = "CC: 1234 5678 9012 3456"
        result = PIIScrubber.scrub(text)

        assert "1234 5678 9012 3456" not in result
        assert "[CC_REDACTED]" in result

    def test_scrub_credit_card_with_dashes(self):
        """Test credit cards with dashes are scrubbed."""
        text = "CC: 1234-5678-9012-3456"
        result = PIIScrubber.scrub(text)

        assert "1234-5678-9012-3456" not in result
        assert "[CC_REDACTED]" in result

    def test_scrub_ip_address(self):
        """Test IP addresses are scrubbed."""
        text = "Server IP: 192.168.1.100"
        result = PIIScrubber.scrub(text)

        assert "192.168.1.100" not in result
        assert "[IP_REDACTED]" in result

    def test_scrub_api_key_with_keyword(self):
        """Test API keys are scrubbed when 'key' keyword present."""
        # Se arma en tiempo de ejecución para que el escáner de secretos no
        # confunda el fixture con una clave real.
        fake_key = "sk_" + "live_" + "abcdefghijklmnopqrstuvwxyz123456"
        text = f"API key: {fake_key}"
        result = PIIScrubber.scrub(text)

        assert fake_key not in result
        assert "[KEY_REDACTED]" in result

    def test_scrub_token_with_keyword(self):
        """Test tokens are scrubbed when 'token' keyword present."""
        text = "Bearer token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = PIIScrubber.scrub(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "[KEY_REDACTED]" in result

    def test_scrub_long_string_without_keyword_preserved(self):
        """Test long strings without key/token keywords are preserved."""
        text = "Hash: abcdefghijklmnopqrstuvwxyz123456"
        result = PIIScrubber.scrub(text)

        # Without "key" or "token" keyword, should be preserved
        assert "abcdefghijklmnopqrstuvwxyz123456" in result

    def test_scrub_preserves_normal_text(self):
        """Test normal text is preserved."""
        text = "Hello world, this is a test."
        result = PIIScrubber.scrub(text)

        assert result == text

    def test_scrub_dict_basic(self):
        """Test dictionary scrubbing."""
        data = {
            "email": "user@example.com",
            "message": "Contact info",
        }

        result = PIIScrubber.scrub_dict(data)

        assert "[EMAIL_REDACTED]" in result["email"]
        assert result["message"] == "Contact info"

    def test_scrub_dict_nested(self):
        """Test nested dictionary scrubbing."""
        data = {
            "user": {
                "contact": {
                    "email": "nested@example.com"
                }
            }
        }

        result = PIIScrubber.scrub_dict(data)

        assert "[EMAIL_REDACTED]" in result["user"]["contact"]["email"]

    def test_scrub_dict_with_list(self):
        """Test dictionary with list of strings."""
        data = {
            "emails": ["a@x.com", "b@y.com"],
        }

        result = PIIScrubber.scrub_dict(data)

        assert all("[EMAIL_REDACTED]" in email for email in result["emails"])

    def test_scrub_dict_with_list_of_dicts(self):
        """Test dictionary with list of nested dicts."""
        data = {
            "users": [
                {"email": "user1@example.com"},
                {"email": "user2@example.com"},
            ]
        }

        result = PIIScrubber.scrub_dict(data)

        for user in result["users"]:
            assert "[EMAIL_REDACTED]" in user["email"]

    def test_scrub_dict_preserves_non_string_values(self):
        """Test non-string values are preserved."""
        data = {
            "count": 42,
            "active": True,
            "ratio": 3.14,
        }

        result = PIIScrubber.scrub_dict(data)

        assert result["count"] == 42
        assert result["active"] is True
        assert result["ratio"] == 3.14


class TestRateLimiter:
    """Test RateLimiter class (in-memory mode)."""

    @pytest.fixture
    def limiter(self):
        """Create rate limiter in in-memory mode."""
        return RateLimiter(redis_client=None, use_redis=False)

    @pytest.fixture
    def strict_config(self):
        """Create strict rate limit config."""
        return RateLimitConfig(
            calls_per_minute=3,
            calls_per_hour=10,
            burst_size=2,
        )

    @pytest.mark.asyncio
    async def test_allows_first_request(self, limiter, strict_config):
        """Test first request is allowed."""
        allowed, retry_after = await limiter.check_rate_limit(
            "test_key", strict_config
        )

        assert allowed is True
        assert retry_after is None

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self, limiter, strict_config):
        """Test requests within limit are allowed."""
        for i in range(3):
            allowed, _ = await limiter.check_rate_limit("test_key", strict_config)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_request_exceeding_minute_limit(self, limiter, strict_config):
        """Test request exceeding minute limit is blocked."""
        # Make 3 requests (the limit)
        for _ in range(3):
            await limiter.check_rate_limit("test_key", strict_config)

        # 4th request should be blocked
        allowed, retry_after = await limiter.check_rate_limit(
            "test_key", strict_config
        )

        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, limiter, strict_config):
        """Test different keys have independent limits."""
        # Exhaust limit for key1
        for _ in range(3):
            await limiter.check_rate_limit("key1", strict_config)

        # key2 should still be allowed
        allowed, _ = await limiter.check_rate_limit("key2", strict_config)
        assert allowed is True


class TestGetUserScopes:
    """Test get_user_scopes function."""

    def test_no_user_returns_empty(self):
        """Test None user returns empty scopes."""
        scopes = get_user_scopes(None)
        assert scopes == set()

    def test_authenticated_user_gets_default_scopes(self):
        """Test authenticated user gets default scopes."""

        class FakeUser:
            pass

        user = FakeUser()
        scopes = get_user_scopes(user)

        assert MCPScope.TOOLS_ALL.value in scopes
        assert MCPScope.TASKS_CREATE.value in scopes
        assert MCPScope.TASKS_READ.value in scopes
        assert MCPScope.TASKS_CANCEL.value in scopes

    def test_admin_scopes_not_granted_by_default(self):
        """Test admin scopes not granted to regular users."""

        class FakeUser:
            username = "regular_user"
            email = "user@example.com"

        user = FakeUser()
        scopes = get_user_scopes(user)

        # Should NOT have admin scopes (no MCP_ADMIN_USERS env var set)
        assert MCPScope.ADMIN_ALL.value not in scopes
        assert MCPScope.ADMIN_METRICS.value not in scopes
