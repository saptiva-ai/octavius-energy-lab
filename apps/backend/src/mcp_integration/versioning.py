"""
MCP Tool Versioning - Semantic versioning support for tools.

Implements:
- Semver parsing and validation (MAJOR.MINOR.PATCH)
- Version range matching (^1.2.0, ~1.2.0, >=1.0.0)
- Tool registry with multiple versions
- Automatic "latest" resolution
- Breaking change detection

Example:
    # Register multiple versions
    registry.register_tool("audit_file", "1.0.0", tool_v1)
    registry.register_tool("audit_file", "1.1.0", tool_v1_1)
    registry.register_tool("audit_file", "2.0.0", tool_v2)

    # Client specifies version
    invoke("audit_file@1.1.0", payload)     # Exact version
    invoke("audit_file@^1.0.0", payload)    # Compatible with 1.x.x
    invoke("audit_file@~1.1.0", payload)    # Compatible with 1.1.x
    invoke("audit_file", payload)           # Latest (2.0.0)
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

from .metrics import metrics_collector

logger = structlog.get_logger(__name__)


class VersionConstraint(str, Enum):
    """Version constraint operators."""

    EXACT = "exact"  # 1.2.3
    CARET = "caret"  # ^1.2.3 (compatible, allows MINOR and PATCH updates)
    TILDE = "tilde"  # ~1.2.3 (allows PATCH updates only)
    GTE = "gte"  # >=1.2.3
    LTE = "lte"  # <=1.2.3
    GT = "gt"  # >1.2.3
    LT = "lt"  # <1.2.3


@dataclass
class SemanticVersion:
    """
    Semantic version: MAJOR.MINOR.PATCH

    - MAJOR: Incompatible API changes
    - MINOR: Backwards-compatible functionality additions
    - PATCH: Backwards-compatible bug fixes
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        return f"SemanticVersion({self.major}.{self.minor}.{self.patch})"

    def __eq__(self, other: "SemanticVersion") -> bool:
        return (self.major, self.minor, self.patch) == (
            other.major,
            other.minor,
            other.patch,
        )

    def __lt__(self, other: "SemanticVersion") -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other: "SemanticVersion") -> bool:
        return self < other or self == other

    def __gt__(self, other: "SemanticVersion") -> bool:
        return not self <= other

    def __ge__(self, other: "SemanticVersion") -> bool:
        return not self < other

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    def is_compatible_with(self, other: "SemanticVersion") -> bool:
        """
        Check if this version is backwards-compatible with other.

        Compatible if:
        - Same MAJOR version
        - This version >= other version
        """
        return self.major == other.major and self >= other

    def is_breaking_change(self, other: "SemanticVersion") -> bool:
        """Check if upgrading from other to this is a breaking change."""
        return self.major > other.major


def parse_version(version_str: str) -> SemanticVersion:
    """
    Parse semantic version string.

    Supports:
    - 1.2.3
    - v1.2.3

    Raises:
        ValueError: If version string is invalid
    """
    # Remove 'v' prefix if present
    version_str = version_str.lstrip("v")

    # Match MAJOR.MINOR.PATCH
    pattern = r"^(\d+)\.(\d+)\.(\d+)$"
    match = re.match(pattern, version_str)

    if not match:
        raise ValueError(
            f"Invalid semantic version: {version_str}. Expected format: MAJOR.MINOR.PATCH"
        )

    major, minor, patch = match.groups()
    return SemanticVersion(int(major), int(minor), int(patch))


def parse_version_constraint(
    constraint_str: str,
) -> Tuple[VersionConstraint, SemanticVersion]:
    """
    Parse version constraint string.

    Supports:
    - 1.2.3           (exact)
    - ^1.2.3          (caret - compatible with 1.x.x)
    - ~1.2.3          (tilde - compatible with 1.2.x)
    - >=1.2.3, >1.2.3 (gte, gt)
    - <=1.2.3, <1.2.3 (lte, lt)

    Returns:
        (constraint_type, version)

    Raises:
        ValueError: If constraint is invalid
    """
    constraint_str = constraint_str.strip()

    # Caret: ^1.2.3
    if constraint_str.startswith("^"):
        version = parse_version(constraint_str[1:])
        return (VersionConstraint.CARET, version)

    # Tilde: ~1.2.3
    if constraint_str.startswith("~"):
        version = parse_version(constraint_str[1:])
        return (VersionConstraint.TILDE, version)

    # Greater than or equal: >=1.2.3
    if constraint_str.startswith(">="):
        version = parse_version(constraint_str[2:])
        return (VersionConstraint.GTE, version)

    # Less than or equal: <=1.2.3
    if constraint_str.startswith("<="):
        version = parse_version(constraint_str[2:])
        return (VersionConstraint.LTE, version)

    # Greater than: >1.2.3
    if constraint_str.startswith(">"):
        version = parse_version(constraint_str[1:])
        return (VersionConstraint.GT, version)

    # Less than: <1.2.3
    if constraint_str.startswith("<"):
        version = parse_version(constraint_str[1:])
        return (VersionConstraint.LT, version)

    # Exact: 1.2.3
    version = parse_version(constraint_str)
    return (VersionConstraint.EXACT, version)


def matches_constraint(
    version: SemanticVersion, constraint: VersionConstraint, target: SemanticVersion
) -> bool:
    """
    Check if version matches constraint against target.

    Examples:
        matches_constraint(v1.5.0, CARET, v1.2.3) -> True   # 1.5.0 is compatible with ^1.2.3
        matches_constraint(v2.0.0, CARET, v1.2.3) -> False  # 2.0.0 breaks with ^1.2.3
        matches_constraint(v1.2.5, TILDE, v1.2.3) -> True   # 1.2.5 is compatible with ~1.2.3
        matches_constraint(v1.3.0, TILDE, v1.2.3) -> False  # 1.3.0 breaks with ~1.2.3
    """
    if constraint == VersionConstraint.EXACT:
        return version == target

    elif constraint == VersionConstraint.CARET:
        # ^1.2.3 matches >=1.2.3 and <2.0.0
        return version.major == target.major and version >= target

    elif constraint == VersionConstraint.TILDE:
        # ~1.2.3 matches >=1.2.3 and <1.3.0
        return (
            version.major == target.major
            and version.minor == target.minor
            and version >= target
        )

    elif constraint == VersionConstraint.GTE:
        return version >= target

    elif constraint == VersionConstraint.LTE:
        return version <= target

    elif constraint == VersionConstraint.GT:
        return version > target

    elif constraint == VersionConstraint.LT:
        return version < target

    return False


class VersionedToolRegistry:
    """
    Registry for managing multiple versions of tools.

    Features:
    - Register tools with semantic versions
    - Resolve version constraints to specific versions
    - Track latest version per tool
    - Deprecation warnings
    """

    def __init__(self):
        # tool_name -> {version_str -> (version, tool_func, metadata)}
        self._tools: Dict[str, Dict[str, Tuple[SemanticVersion, any, Dict]]] = {}

        # tool_name -> latest_version_str
        self._latest: Dict[str, str] = {}

        # tool_name -> {deprecated_version_str -> replacement_version}
        self._deprecated: Dict[str, Dict[str, str]] = {}

    def register(
        self,
        tool_name: str,
        version: str,
        tool_func: any,
        metadata: Optional[Dict] = None,
    ):
        """
        Register a tool version.

        Args:
            tool_name: Tool identifier (e.g., 'audit_file')
            version: Semantic version string (e.g., '1.2.3')
            tool_func: Tool function/callable
            metadata: Optional metadata (deprecated, changelog, etc.)
        """
        parsed_version = parse_version(version)

        if tool_name not in self._tools:
            self._tools[tool_name] = {}

        metadata = metadata or {}
        self._tools[tool_name][version] = (parsed_version, tool_func, metadata)

        # Update latest version
        if tool_name not in self._latest:
            self._latest[tool_name] = version
        else:
            latest = parse_version(self._latest[tool_name])
            if parsed_version > latest:
                self._latest[tool_name] = version

        if metadata.get("deprecated"):
            replacement = metadata.get("replacement") or self._latest.get(
                tool_name, version
            )
            self.deprecate_version(tool_name, version, replacement)

        logger.info(
            "Tool version registered",
            tool=tool_name,
            version=version,
            is_latest=(self._latest[tool_name] == version),
        )

    def deprecate_version(self, tool_name: str, version: str, replacement: str):
        """
        Mark a version as deprecated.

        Args:
            tool_name: Tool identifier
            version: Version to deprecate
            replacement: Recommended replacement version
        """
        if tool_name not in self._deprecated:
            self._deprecated[tool_name] = {}

        self._deprecated[tool_name][version] = replacement

        logger.warning(
            "Tool version deprecated",
            tool=tool_name,
            version=version,
            replacement=replacement,
        )

    def resolve(
        self, tool_name: str, version_constraint: Optional[str] = None
    ) -> Tuple[str, any]:
        """
        Resolve version constraint to specific version and return tool.

        Args:
            tool_name: Tool identifier
            version_constraint: Version constraint (e.g., '^1.2.0', '~1.0.0', '>=1.5.0')
                               If None, returns latest version

        Returns:
            (resolved_version_str, tool_func)

        Raises:
            ValueError: If tool not found or no matching version
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        # No constraint -> return latest
        if version_constraint is None:
            latest_version = self._latest[tool_name]
            _, tool_func, _ = self._tools[tool_name][latest_version]
            return (latest_version, tool_func)

        # Parse constraint
        constraint_type, target_version = parse_version_constraint(version_constraint)

        # Find matching versions
        matching_versions = []
        for version_str, (version, tool_func, metadata) in self._tools[
            tool_name
        ].items():
            if matches_constraint(version, constraint_type, target_version):
                matching_versions.append((version, version_str, tool_func, metadata))

        if not matching_versions:
            available = list(self._tools[tool_name].keys())
            raise ValueError(
                f"No version of '{tool_name}' matches constraint '{version_constraint}'. "
                f"Available versions: {available}"
            )

        # Sort by version (descending) and pick highest
        matching_versions.sort(reverse=True, key=lambda x: x[0])
        _, resolved_version_str, tool_func, metadata = matching_versions[0]

        # Check deprecation
        deprecated_info = None
        if (
            tool_name in self._deprecated
            and resolved_version_str in self._deprecated[tool_name]
        ):
            replacement = self._deprecated[tool_name][resolved_version_str]
            deprecated_info = replacement
            logger.warning(
                "Using deprecated tool version",
                tool=tool_name,
                version=resolved_version_str,
                replacement=replacement,
            )
            metrics_collector.record_deprecated_version_usage(
                tool=tool_name,
                version=resolved_version_str,
                replacement=replacement,
            )

        logger.debug(
            "Tool version resolved",
            tool=tool_name,
            constraint=version_constraint,
            resolved=resolved_version_str,
        )

        if deprecated_info and metadata is not None:
            metadata["deprecated_replacement"] = deprecated_info

        return (resolved_version_str, tool_func)

    def list_versions(self, tool_name: str) -> List[str]:
        """List all available versions of a tool."""
        if tool_name not in self._tools:
            return []

        versions = [(parse_version(v), v) for v in self._tools[tool_name].keys()]
        versions.sort(reverse=True)  # Newest first
        return [v_str for _, v_str in versions]

    def get_latest(self, tool_name: str) -> Optional[str]:
        """Get latest version of a tool."""
        return self._latest.get(tool_name)

    def is_deprecated(self, tool_name: str, version: str) -> bool:
        """Check if a version is deprecated."""
        return tool_name in self._deprecated and version in self._deprecated[tool_name]

    def list_all_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())


# Global versioned tool registry
versioned_registry = VersionedToolRegistry()
