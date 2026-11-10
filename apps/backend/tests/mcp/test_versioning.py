"""
Unit tests for MCP tool versioning.

Tests semantic versioning support:
- Version parsing and validation
- Version constraint matching (^, ~, >=, etc.)
- Versioned tool registry
- Version resolution
- Deprecation warnings
"""

import pytest

# Mark all tests in this file with mcp and mcp_versioning markers
pytestmark = [pytest.mark.mcp, pytest.mark.mcp_versioning, pytest.mark.unit]
from src.mcp_integration.versioning import (
    SemanticVersion,
    parse_version,
    parse_version_constraint,
    matches_constraint,
    VersionConstraint,
    VersionedToolRegistry,
)


class TestSemanticVersion:
    """Test SemanticVersion class."""

    def test_version_creation(self):
        """Test creating semantic version."""
        v = SemanticVersion(1, 2, 3)
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert str(v) == "1.2.3"

    def test_version_equality(self):
        """Test version equality."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 3)
        v3 = SemanticVersion(1, 2, 4)

        assert v1 == v2
        assert v1 != v3

    def test_version_comparison(self):
        """Test version comparison."""
        v1_0_0 = SemanticVersion(1, 0, 0)
        v1_1_0 = SemanticVersion(1, 1, 0)
        v1_1_1 = SemanticVersion(1, 1, 1)
        v2_0_0 = SemanticVersion(2, 0, 0)

        assert v1_0_0 < v1_1_0 < v1_1_1 < v2_0_0
        assert v2_0_0 > v1_1_1 > v1_1_0 > v1_0_0

    def test_is_compatible_with(self):
        """Test compatibility check."""
        v1_0_0 = SemanticVersion(1, 0, 0)
        v1_5_0 = SemanticVersion(1, 5, 0)
        v2_0_0 = SemanticVersion(2, 0, 0)

        # Same major, newer minor -> compatible
        assert v1_5_0.is_compatible_with(v1_0_0)

        # Older version -> not compatible
        assert not v1_0_0.is_compatible_with(v1_5_0)

        # Different major -> not compatible
        assert not v2_0_0.is_compatible_with(v1_0_0)
        assert not v1_0_0.is_compatible_with(v2_0_0)

    def test_is_breaking_change(self):
        """Test breaking change detection."""
        v1_0_0 = SemanticVersion(1, 0, 0)
        v1_5_0 = SemanticVersion(1, 5, 0)
        v2_0_0 = SemanticVersion(2, 0, 0)

        # Same major -> not breaking
        assert not v1_5_0.is_breaking_change(v1_0_0)

        # Major bump -> breaking
        assert v2_0_0.is_breaking_change(v1_0_0)
        assert v2_0_0.is_breaking_change(v1_5_0)


class TestParseVersion:
    """Test version parsing."""

    def test_parse_valid_version(self):
        """Test parsing valid version strings."""
        v = parse_version("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_version_with_v_prefix(self):
        """Test parsing version with 'v' prefix."""
        v = parse_version("v1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_invalid_version(self):
        """Test parsing invalid version strings."""
        with pytest.raises(ValueError, match="Invalid semantic version"):
            parse_version("1.2")

        with pytest.raises(ValueError):
            parse_version("1.2.3.4")

        with pytest.raises(ValueError):
            parse_version("abc")


class TestParseVersionConstraint:
    """Test version constraint parsing."""

    def test_parse_exact_constraint(self):
        """Test parsing exact version constraint."""
        constraint, version = parse_version_constraint("1.2.3")
        assert constraint == VersionConstraint.EXACT
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_caret_constraint(self):
        """Test parsing caret constraint (^1.2.3)."""
        constraint, version = parse_version_constraint("^1.2.3")
        assert constraint == VersionConstraint.CARET
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_tilde_constraint(self):
        """Test parsing tilde constraint (~1.2.3)."""
        constraint, version = parse_version_constraint("~1.2.3")
        assert constraint == VersionConstraint.TILDE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_gte_constraint(self):
        """Test parsing >= constraint."""
        constraint, version = parse_version_constraint(">=1.2.3")
        assert constraint == VersionConstraint.GTE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_lte_constraint(self):
        """Test parsing <= constraint."""
        constraint, version = parse_version_constraint("<=1.2.3")
        assert constraint == VersionConstraint.LTE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_gt_constraint(self):
        """Test parsing > constraint."""
        constraint, version = parse_version_constraint(">1.2.3")
        assert constraint == VersionConstraint.GT
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_lt_constraint(self):
        """Test parsing < constraint."""
        constraint, version = parse_version_constraint("<1.2.3")
        assert constraint == VersionConstraint.LT
        assert version == SemanticVersion(1, 2, 3)


class TestMatchesConstraint:
    """Test version constraint matching."""

    def test_exact_match(self):
        """Test exact version matching."""
        v1_2_3 = SemanticVersion(1, 2, 3)
        v1_2_4 = SemanticVersion(1, 2, 4)

        assert matches_constraint(v1_2_3, VersionConstraint.EXACT, v1_2_3)
        assert not matches_constraint(v1_2_4, VersionConstraint.EXACT, v1_2_3)

    def test_caret_match(self):
        """Test caret constraint (^1.2.3)."""
        target = SemanticVersion(1, 2, 3)

        # Compatible versions (same major, >= target)
        assert matches_constraint(SemanticVersion(1, 2, 3), VersionConstraint.CARET, target)
        assert matches_constraint(SemanticVersion(1, 2, 4), VersionConstraint.CARET, target)
        assert matches_constraint(SemanticVersion(1, 5, 0), VersionConstraint.CARET, target)

        # Incompatible versions
        assert not matches_constraint(SemanticVersion(1, 2, 2), VersionConstraint.CARET, target)  # Older
        assert not matches_constraint(SemanticVersion(2, 0, 0), VersionConstraint.CARET, target)  # Breaking
        assert not matches_constraint(SemanticVersion(0, 9, 0), VersionConstraint.CARET, target)  # Different major

    def test_tilde_match(self):
        """Test tilde constraint (~1.2.3)."""
        target = SemanticVersion(1, 2, 3)

        # Compatible versions (same major.minor, >= target)
        assert matches_constraint(SemanticVersion(1, 2, 3), VersionConstraint.TILDE, target)
        assert matches_constraint(SemanticVersion(1, 2, 4), VersionConstraint.TILDE, target)

        # Incompatible versions
        assert not matches_constraint(SemanticVersion(1, 2, 2), VersionConstraint.TILDE, target)  # Older patch
        assert not matches_constraint(SemanticVersion(1, 3, 0), VersionConstraint.TILDE, target)  # Different minor
        assert not matches_constraint(SemanticVersion(2, 2, 3), VersionConstraint.TILDE, target)  # Different major

    def test_gte_match(self):
        """Test >= constraint."""
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(SemanticVersion(1, 2, 3), VersionConstraint.GTE, target)
        assert matches_constraint(SemanticVersion(1, 2, 4), VersionConstraint.GTE, target)
        assert matches_constraint(SemanticVersion(2, 0, 0), VersionConstraint.GTE, target)

        assert not matches_constraint(SemanticVersion(1, 2, 2), VersionConstraint.GTE, target)

    def test_lte_match(self):
        """Test <= constraint."""
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(SemanticVersion(1, 2, 3), VersionConstraint.LTE, target)
        assert matches_constraint(SemanticVersion(1, 2, 2), VersionConstraint.LTE, target)
        assert matches_constraint(SemanticVersion(1, 0, 0), VersionConstraint.LTE, target)

        assert not matches_constraint(SemanticVersion(1, 2, 4), VersionConstraint.LTE, target)


class TestVersionedToolRegistry:
    """Test versioned tool registry."""

    def test_register_single_version(self):
        """Test registering a single version."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        registry.register("test_tool", "1.0.0", tool_v1)

        assert registry.list_versions("test_tool") == ["1.0.0"]
        assert registry.get_latest("test_tool") == "1.0.0"

    def test_register_multiple_versions(self):
        """Test registering multiple versions."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        def tool_v1_1():
            return "v1.1"

        registry.register("test_tool", "1.0.0", tool_v1)
        registry.register("test_tool", "2.0.0", tool_v2)
        registry.register("test_tool", "1.1.0", tool_v1_1)

        versions = registry.list_versions("test_tool")
        assert versions == ["2.0.0", "1.1.0", "1.0.0"]  # Sorted descending
        assert registry.get_latest("test_tool") == "2.0.0"

    def test_resolve_latest(self):
        """Test resolving to latest version."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        registry.register("test_tool", "1.0.0", tool_v1)
        registry.register("test_tool", "2.0.0", tool_v2)

        version, tool_func = registry.resolve("test_tool")
        assert version == "2.0.0"
        assert tool_func() == "v2"

    def test_resolve_exact_version(self):
        """Test resolving exact version."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        registry.register("test_tool", "1.0.0", tool_v1)
        registry.register("test_tool", "2.0.0", tool_v2)

        version, tool_func = registry.resolve("test_tool", "1.0.0")
        assert version == "1.0.0"
        assert tool_func() == "v1"

    def test_resolve_caret_constraint(self):
        """Test resolving caret constraint."""
        registry = VersionedToolRegistry()

        def tool_v1_0():
            return "v1.0"

        def tool_v1_2():
            return "v1.2"

        def tool_v1_5():
            return "v1.5"

        def tool_v2():
            return "v2"

        registry.register("test_tool", "1.0.0", tool_v1_0)
        registry.register("test_tool", "1.2.0", tool_v1_2)
        registry.register("test_tool", "1.5.0", tool_v1_5)
        registry.register("test_tool", "2.0.0", tool_v2)

        # ^1.2.0 should resolve to highest 1.x.x >= 1.2.0
        version, tool_func = registry.resolve("test_tool", "^1.2.0")
        assert version == "1.5.0"
        assert tool_func() == "v1.5"

    def test_resolve_tilde_constraint(self):
        """Test resolving tilde constraint."""
        registry = VersionedToolRegistry()

        def tool_v1_2_0():
            return "v1.2.0"

        def tool_v1_2_3():
            return "v1.2.3"

        def tool_v1_3_0():
            return "v1.3.0"

        registry.register("test_tool", "1.2.0", tool_v1_2_0)
        registry.register("test_tool", "1.2.3", tool_v1_2_3)
        registry.register("test_tool", "1.3.0", tool_v1_3_0)

        # ~1.2.0 should resolve to highest 1.2.x >= 1.2.0
        version, tool_func = registry.resolve("test_tool", "~1.2.0")
        assert version == "1.2.3"
        assert tool_func() == "v1.2.3"

    def test_resolve_nonexistent_tool(self):
        """Test resolving nonexistent tool."""
        registry = VersionedToolRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.resolve("nonexistent_tool")

    def test_resolve_no_matching_version(self):
        """Test resolving when no version matches."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        registry.register("test_tool", "1.0.0", tool_v1)

        with pytest.raises(ValueError, match="No version.*matches constraint"):
            registry.resolve("test_tool", "^2.0.0")

    def test_deprecate_version(self):
        """Test version deprecation."""
        registry = VersionedToolRegistry()

        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        registry.register("test_tool", "1.0.0", tool_v1)
        registry.register("test_tool", "2.0.0", tool_v2)

        registry.deprecate_version("test_tool", "1.0.0", "2.0.0")

        assert registry.is_deprecated("test_tool", "1.0.0")
        assert not registry.is_deprecated("test_tool", "2.0.0")

        # Can still resolve deprecated version (with warning)
        version, tool_func = registry.resolve("test_tool", "1.0.0")
        assert version == "1.0.0"

    def test_list_all_tools(self):
        """Test listing all registered tools."""
        registry = VersionedToolRegistry()

        def tool_a():
            return "a"

        def tool_b():
            return "b"

        registry.register("tool_a", "1.0.0", tool_a)
        registry.register("tool_b", "1.0.0", tool_b)

        tools = registry.list_all_tools()
        assert set(tools) == {"tool_a", "tool_b"}
