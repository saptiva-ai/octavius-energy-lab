"""
Unit tests for MCP versioning module.

Tests:
- SemanticVersion dataclass
- Version parsing
- Version constraint parsing
- Constraint matching
- VersionedToolRegistry
"""

import pytest

from src.mcp_integration.versioning import (
    SemanticVersion,
    VersionConstraint,
    VersionedToolRegistry,
    matches_constraint,
    parse_version,
    parse_version_constraint,
)

pytestmark = [pytest.mark.unit]


class TestVersionConstraintEnum:
    """Test VersionConstraint enum."""

    def test_all_constraints_defined(self):
        """Test all constraint types are defined."""
        assert VersionConstraint.EXACT.value == "exact"
        assert VersionConstraint.CARET.value == "caret"
        assert VersionConstraint.TILDE.value == "tilde"
        assert VersionConstraint.GTE.value == "gte"
        assert VersionConstraint.LTE.value == "lte"
        assert VersionConstraint.GT.value == "gt"
        assert VersionConstraint.LT.value == "lt"


class TestSemanticVersion:
    """Test SemanticVersion dataclass."""

    def test_create_version(self):
        """Test creating a semantic version."""
        v = SemanticVersion(1, 2, 3)

        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_str_representation(self):
        """Test string representation."""
        v = SemanticVersion(1, 2, 3)
        assert str(v) == "1.2.3"

    def test_repr_representation(self):
        """Test repr representation."""
        v = SemanticVersion(1, 2, 3)
        assert repr(v) == "SemanticVersion(1.2.3)"

    def test_equality(self):
        """Test version equality."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 3)
        v3 = SemanticVersion(1, 2, 4)

        assert v1 == v2
        assert v1 != v3

    def test_less_than(self):
        """Test version less than comparison."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 4)
        v3 = SemanticVersion(1, 3, 0)
        v4 = SemanticVersion(2, 0, 0)

        assert v1 < v2
        assert v1 < v3
        assert v1 < v4
        assert not v2 < v1

    def test_less_than_or_equal(self):
        """Test version less than or equal comparison."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 3)
        v3 = SemanticVersion(1, 2, 4)

        assert v1 <= v2
        assert v1 <= v3
        assert not v3 <= v1

    def test_greater_than(self):
        """Test version greater than comparison."""
        v1 = SemanticVersion(2, 0, 0)
        v2 = SemanticVersion(1, 9, 9)

        assert v1 > v2
        assert not v2 > v1

    def test_greater_than_or_equal(self):
        """Test version greater than or equal comparison."""
        v1 = SemanticVersion(2, 0, 0)
        v2 = SemanticVersion(2, 0, 0)
        v3 = SemanticVersion(1, 9, 9)

        assert v1 >= v2
        assert v1 >= v3
        assert not v3 >= v1

    def test_hash(self):
        """Test versions can be hashed (used in sets/dicts)."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 3)

        # Same versions should have same hash
        assert hash(v1) == hash(v2)

        # Can be used in set
        s = {v1, v2}
        assert len(s) == 1

    def test_is_compatible_with_same_major(self):
        """Test compatibility within same major version."""
        v1 = SemanticVersion(1, 5, 0)
        v2 = SemanticVersion(1, 2, 3)

        # 1.5.0 is compatible with 1.2.3
        assert v1.is_compatible_with(v2)

    def test_is_compatible_with_different_major(self):
        """Test incompatibility across major versions."""
        v1 = SemanticVersion(2, 0, 0)
        v2 = SemanticVersion(1, 9, 9)

        # 2.0.0 is not compatible with 1.9.9
        assert not v1.is_compatible_with(v2)

    def test_is_compatible_with_lower_version(self):
        """Test lower version is not compatible with higher."""
        v1 = SemanticVersion(1, 2, 0)
        v2 = SemanticVersion(1, 5, 0)

        # 1.2.0 is not compatible with 1.5.0 (requires features from 1.5.0)
        assert not v1.is_compatible_with(v2)

    def test_is_breaking_change(self):
        """Test breaking change detection."""
        v1 = SemanticVersion(2, 0, 0)
        v2 = SemanticVersion(1, 9, 9)
        v3 = SemanticVersion(1, 0, 0)

        # 2.0.0 is a breaking change from 1.x.x
        assert v1.is_breaking_change(v2)
        assert v1.is_breaking_change(v3)

        # 1.9.9 is not breaking from 1.0.0
        assert not v2.is_breaking_change(v3)


class TestParseVersion:
    """Test parse_version function."""

    def test_parse_simple_version(self):
        """Test parsing simple version string."""
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

    def test_parse_version_zero(self):
        """Test parsing version starting with 0."""
        v = parse_version("0.1.0")

        assert v.major == 0
        assert v.minor == 1
        assert v.patch == 0

    def test_parse_version_large_numbers(self):
        """Test parsing version with large numbers."""
        v = parse_version("100.200.300")

        assert v.major == 100
        assert v.minor == 200
        assert v.patch == 300

    def test_parse_invalid_version_raises(self):
        """Test invalid version string raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_version("1.2")

        assert "Invalid semantic version" in str(exc_info.value)

    def test_parse_version_with_prerelease_fails(self):
        """Test prerelease versions are not supported (raises)."""
        with pytest.raises(ValueError):
            parse_version("1.2.3-alpha")

    def test_parse_version_with_build_fails(self):
        """Test build metadata is not supported (raises)."""
        with pytest.raises(ValueError):
            parse_version("1.2.3+build")

    def test_parse_empty_string_raises(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError):
            parse_version("")

    def test_parse_non_numeric_raises(self):
        """Test non-numeric version raises ValueError."""
        with pytest.raises(ValueError):
            parse_version("a.b.c")


class TestParseVersionConstraint:
    """Test parse_version_constraint function."""

    def test_parse_exact_constraint(self):
        """Test parsing exact version constraint."""
        constraint_type, version = parse_version_constraint("1.2.3")

        assert constraint_type == VersionConstraint.EXACT
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_caret_constraint(self):
        """Test parsing caret (^) constraint."""
        constraint_type, version = parse_version_constraint("^1.2.3")

        assert constraint_type == VersionConstraint.CARET
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_tilde_constraint(self):
        """Test parsing tilde (~) constraint."""
        constraint_type, version = parse_version_constraint("~1.2.3")

        assert constraint_type == VersionConstraint.TILDE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_gte_constraint(self):
        """Test parsing >= constraint."""
        constraint_type, version = parse_version_constraint(">=1.2.3")

        assert constraint_type == VersionConstraint.GTE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_lte_constraint(self):
        """Test parsing <= constraint."""
        constraint_type, version = parse_version_constraint("<=1.2.3")

        assert constraint_type == VersionConstraint.LTE
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_gt_constraint(self):
        """Test parsing > constraint."""
        constraint_type, version = parse_version_constraint(">1.2.3")

        assert constraint_type == VersionConstraint.GT
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_lt_constraint(self):
        """Test parsing < constraint."""
        constraint_type, version = parse_version_constraint("<1.2.3")

        assert constraint_type == VersionConstraint.LT
        assert version == SemanticVersion(1, 2, 3)

    def test_parse_constraint_with_whitespace(self):
        """Test parsing constraint with surrounding whitespace."""
        constraint_type, version = parse_version_constraint("  ^1.2.3  ")

        assert constraint_type == VersionConstraint.CARET
        assert version == SemanticVersion(1, 2, 3)


class TestMatchesConstraint:
    """Test matches_constraint function."""

    def test_exact_match(self):
        """Test exact version matching."""
        v = SemanticVersion(1, 2, 3)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.EXACT, target) is True

    def test_exact_no_match(self):
        """Test exact version not matching."""
        v = SemanticVersion(1, 2, 4)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.EXACT, target) is False

    def test_caret_matches_higher_minor(self):
        """Test caret allows higher minor versions."""
        v = SemanticVersion(1, 5, 0)
        target = SemanticVersion(1, 2, 3)

        # ^1.2.3 allows 1.5.0
        assert matches_constraint(v, VersionConstraint.CARET, target) is True

    def test_caret_matches_higher_patch(self):
        """Test caret allows higher patch versions."""
        v = SemanticVersion(1, 2, 9)
        target = SemanticVersion(1, 2, 3)

        # ^1.2.3 allows 1.2.9
        assert matches_constraint(v, VersionConstraint.CARET, target) is True

    def test_caret_rejects_different_major(self):
        """Test caret rejects different major version."""
        v = SemanticVersion(2, 0, 0)
        target = SemanticVersion(1, 2, 3)

        # ^1.2.3 rejects 2.0.0
        assert matches_constraint(v, VersionConstraint.CARET, target) is False

    def test_caret_rejects_lower_version(self):
        """Test caret rejects lower version."""
        v = SemanticVersion(1, 1, 0)
        target = SemanticVersion(1, 2, 3)

        # ^1.2.3 rejects 1.1.0 (too old)
        assert matches_constraint(v, VersionConstraint.CARET, target) is False

    def test_tilde_matches_higher_patch(self):
        """Test tilde allows higher patch versions."""
        v = SemanticVersion(1, 2, 9)
        target = SemanticVersion(1, 2, 3)

        # ~1.2.3 allows 1.2.9
        assert matches_constraint(v, VersionConstraint.TILDE, target) is True

    def test_tilde_rejects_higher_minor(self):
        """Test tilde rejects higher minor versions."""
        v = SemanticVersion(1, 3, 0)
        target = SemanticVersion(1, 2, 3)

        # ~1.2.3 rejects 1.3.0
        assert matches_constraint(v, VersionConstraint.TILDE, target) is False

    def test_gte_matches_equal(self):
        """Test >= matches equal version."""
        v = SemanticVersion(1, 2, 3)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.GTE, target) is True

    def test_gte_matches_greater(self):
        """Test >= matches greater version."""
        v = SemanticVersion(2, 0, 0)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.GTE, target) is True

    def test_gte_rejects_lesser(self):
        """Test >= rejects lesser version."""
        v = SemanticVersion(1, 0, 0)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.GTE, target) is False

    def test_lte_matches_equal(self):
        """Test <= matches equal version."""
        v = SemanticVersion(1, 2, 3)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.LTE, target) is True

    def test_lte_matches_lesser(self):
        """Test <= matches lesser version."""
        v = SemanticVersion(1, 0, 0)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.LTE, target) is True

    def test_lte_rejects_greater(self):
        """Test <= rejects greater version."""
        v = SemanticVersion(2, 0, 0)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.LTE, target) is False

    def test_gt_matches_greater(self):
        """Test > matches greater version."""
        v = SemanticVersion(1, 2, 4)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.GT, target) is True

    def test_gt_rejects_equal(self):
        """Test > rejects equal version."""
        v = SemanticVersion(1, 2, 3)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.GT, target) is False

    def test_lt_matches_lesser(self):
        """Test < matches lesser version."""
        v = SemanticVersion(1, 2, 2)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.LT, target) is True

    def test_lt_rejects_equal(self):
        """Test < rejects equal version."""
        v = SemanticVersion(1, 2, 3)
        target = SemanticVersion(1, 2, 3)

        assert matches_constraint(v, VersionConstraint.LT, target) is False


class TestVersionedToolRegistry:
    """Test VersionedToolRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry."""
        return VersionedToolRegistry()

    @pytest.fixture
    def populated_registry(self, registry):
        """Create a registry with some tools registered."""
        registry.register("tool_a", "1.0.0", lambda: "v1.0.0")
        registry.register("tool_a", "1.1.0", lambda: "v1.1.0")
        registry.register("tool_a", "1.2.0", lambda: "v1.2.0")
        registry.register("tool_a", "2.0.0", lambda: "v2.0.0")
        registry.register("tool_b", "0.5.0", lambda: "tool_b")
        return registry

    def test_register_tool(self, registry):
        """Test registering a tool."""
        registry.register("my_tool", "1.0.0", lambda: "result")

        assert "my_tool" in registry._tools
        assert "1.0.0" in registry._tools["my_tool"]

    def test_register_updates_latest(self, registry):
        """Test registering updates latest version."""
        registry.register("my_tool", "1.0.0", lambda: "v1")
        assert registry.get_latest("my_tool") == "1.0.0"

        registry.register("my_tool", "1.1.0", lambda: "v2")
        assert registry.get_latest("my_tool") == "1.1.0"

    def test_register_older_version_doesnt_change_latest(self, registry):
        """Test registering older version doesn't change latest."""
        registry.register("my_tool", "2.0.0", lambda: "v2")
        registry.register("my_tool", "1.0.0", lambda: "v1")

        assert registry.get_latest("my_tool") == "2.0.0"

    def test_register_with_metadata(self, registry):
        """Test registering with metadata."""
        metadata = {"author": "test", "changelog": "Initial release"}
        registry.register("my_tool", "1.0.0", lambda: "result", metadata=metadata)

        _, _, stored_metadata = registry._tools["my_tool"]["1.0.0"]
        assert stored_metadata["author"] == "test"

    def test_register_deprecated_version(self, registry):
        """Test registering a deprecated version."""
        registry.register("my_tool", "2.0.0", lambda: "v2")
        registry.register(
            "my_tool",
            "1.0.0",
            lambda: "v1",
            metadata={"deprecated": True, "replacement": "2.0.0"},
        )

        assert registry.is_deprecated("my_tool", "1.0.0")

    def test_resolve_latest_version(self, populated_registry):
        """Test resolving to latest version."""
        version, tool_func = populated_registry.resolve("tool_a")

        assert version == "2.0.0"
        assert tool_func() == "v2.0.0"

    def test_resolve_exact_version(self, populated_registry):
        """Test resolving exact version."""
        version, tool_func = populated_registry.resolve("tool_a", "1.1.0")

        assert version == "1.1.0"
        assert tool_func() == "v1.1.0"

    def test_resolve_caret_constraint(self, populated_registry):
        """Test resolving caret constraint."""
        version, tool_func = populated_registry.resolve("tool_a", "^1.0.0")

        # Should get highest 1.x.x version (1.2.0)
        assert version == "1.2.0"
        assert tool_func() == "v1.2.0"

    def test_resolve_tilde_constraint(self, populated_registry):
        """Test resolving tilde constraint."""
        version, tool_func = populated_registry.resolve("tool_a", "~1.1.0")

        # Should get highest 1.1.x version (only 1.1.0 available)
        assert version == "1.1.0"
        assert tool_func() == "v1.1.0"

    def test_resolve_gte_constraint(self, populated_registry):
        """Test resolving >= constraint."""
        version, tool_func = populated_registry.resolve("tool_a", ">=1.1.0")

        # Should get highest version >= 1.1.0 (2.0.0)
        assert version == "2.0.0"
        assert tool_func() == "v2.0.0"

    def test_resolve_unknown_tool_raises(self, registry):
        """Test resolving unknown tool raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            registry.resolve("nonexistent_tool")

        assert "not found" in str(exc_info.value)

    def test_resolve_no_matching_version_raises(self, populated_registry):
        """Test resolving with no matching version raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            populated_registry.resolve("tool_a", "^5.0.0")

        assert "No version" in str(exc_info.value)
        assert "matches constraint" in str(exc_info.value)

    def test_deprecate_version(self, registry):
        """Test deprecating a version."""
        registry.register("my_tool", "1.0.0", lambda: "v1")
        registry.deprecate_version("my_tool", "1.0.0", "2.0.0")

        assert registry.is_deprecated("my_tool", "1.0.0")

    def test_is_deprecated_false_for_new_version(self, populated_registry):
        """Test non-deprecated version returns False."""
        assert populated_registry.is_deprecated("tool_a", "2.0.0") is False

    def test_list_versions(self, populated_registry):
        """Test listing versions in order."""
        versions = populated_registry.list_versions("tool_a")

        # Should be newest first
        assert versions[0] == "2.0.0"
        assert versions[-1] == "1.0.0"
        assert len(versions) == 4

    def test_list_versions_unknown_tool(self, registry):
        """Test listing versions of unknown tool returns empty."""
        versions = registry.list_versions("nonexistent")
        assert versions == []

    def test_get_latest_unknown_tool(self, registry):
        """Test getting latest of unknown tool returns None."""
        assert registry.get_latest("nonexistent") is None

    def test_list_all_tools(self, populated_registry):
        """Test listing all registered tools."""
        tools = populated_registry.list_all_tools()

        assert "tool_a" in tools
        assert "tool_b" in tools
        assert len(tools) == 2

    def test_list_all_tools_empty_registry(self, registry):
        """Test listing tools in empty registry."""
        tools = registry.list_all_tools()
        assert tools == []
