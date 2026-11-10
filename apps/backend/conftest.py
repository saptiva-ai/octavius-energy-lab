"""
Pytest configuration and fixtures.

Provides:
- MCP-specific fixtures
- Diff-coverage plugin for incremental testing
- Shared test utilities
"""

import pytest
import os
import subprocess
from typing import Set, List
from pathlib import Path


# ============================================================================
# Diff-Coverage Plugin
# ============================================================================

def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--diff-coverage",
        action="store_true",
        default=False,
        help="Run only tests for files changed in git diff (incremental testing)",
    )
    parser.addoption(
        "--diff-base",
        action="store",
        default="main",
        help="Git base branch for diff comparison (default: main)",
    )
    parser.addoption(
        "--mcp-only",
        action="store_true",
        default=False,
        help="Run only MCP-related tests",
    )


def pytest_configure(config):
    """Configure pytest based on command-line options."""
    if config.option.diff_coverage:
        changed_files = get_changed_files(config.option.diff_base)
        config._changed_files = changed_files

        # Print info
        print(f"\n[Diff Coverage] Found {len(changed_files)} changed files:")
        for file in sorted(changed_files)[:10]:  # Show first 10
            print(f"  - {file}")
        if len(changed_files) > 10:
            print(f"  ... and {len(changed_files) - 10} more")
        print()


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection based on command-line options.

    - If --diff-coverage: Only run tests for changed files
    - If --mcp-only: Only run tests with 'mcp' marker
    """
    # Filter by diff coverage
    if config.option.diff_coverage:
        changed_files = config._changed_files
        selected = []
        deselected = []

        for item in items:
            # Get test file path
            test_file = Path(item.fspath).resolve()

            # Check if test file changed
            if should_run_test(test_file, changed_files):
                selected.append(item)
            else:
                deselected.append(item)

        config.hook.pytest_deselected(items=deselected)
        items[:] = selected

        print(f"[Diff Coverage] Selected {len(selected)}/{len(selected) + len(deselected)} tests\n")

    # Filter by MCP marker
    if config.option.mcp_only:
        selected = []
        deselected = []

        for item in items:
            # Check if test has 'mcp' marker (any mcp_* marker)
            has_mcp_marker = any(
                marker.name.startswith("mcp")
                for marker in item.iter_markers()
            )

            # Also include tests in tests/mcp/ directory
            is_mcp_test_dir = "tests/mcp" in str(item.fspath)

            if has_mcp_marker or is_mcp_test_dir:
                selected.append(item)
            else:
                deselected.append(item)

        config.hook.pytest_deselected(items=deselected)
        items[:] = selected

        print(f"[MCP Tests] Selected {len(selected)}/{len(selected) + len(deselected)} MCP tests\n")


def get_changed_files(base_branch: str) -> Set[str]:
    """
    Get list of changed Python files compared to base branch.

    Args:
        base_branch: Git base branch (e.g., "main", "develop")

    Returns:
        Set of absolute file paths that changed
    """
    try:
        # Get changed files in working directory + staged
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )

        changed_files = set()
        project_root = Path.cwd()

        for line in result.stdout.strip().split("\n"):
            if line and (line.endswith(".py") or "src/" in line or "tests/" in line):
                file_path = project_root / line.strip()
                if file_path.exists():
                    changed_files.add(str(file_path.resolve()))

        return changed_files

    except subprocess.CalledProcessError:
        # If git diff fails (not a git repo, branch doesn't exist), return empty set
        print("[Diff Coverage] Warning: Could not run git diff, running all tests")
        return set()


def should_run_test(test_file: Path, changed_files: Set[str]) -> bool:
    """
    Determine if a test should run based on changed files.

    A test should run if:
    1. The test file itself changed
    2. The corresponding source file changed (tests/test_foo.py -> src/foo.py)
    3. Any file in the same module changed

    Args:
        test_file: Path to test file
        changed_files: Set of changed file paths

    Returns:
        True if test should run
    """
    test_file_str = str(test_file)

    # 1. Test file itself changed
    if test_file_str in changed_files:
        return True

    # 2. Corresponding source file changed
    # tests/test_foo.py -> src/foo.py
    # tests/mcp/test_security.py -> src/mcp/security.py
    if "/tests/" in test_file_str:
        # Extract relative path from tests/
        test_relative = test_file_str.split("/tests/", 1)[1]

        # Remove test_ prefix
        if test_relative.startswith("test_"):
            source_relative = test_relative[5:]  # Remove "test_"
        else:
            source_relative = test_relative

        # Build source path
        project_root = test_file.parents[2]  # Go up to project root
        source_file = project_root / "src" / source_relative

        if str(source_file.resolve()) in changed_files:
            return True

    # 3. Any file in same module changed
    # If tests/mcp/test_security.py exists, check if any src/mcp/*.py changed
    if "/tests/" in test_file_str:
        test_dir = test_file.parent
        module_name = test_dir.name

        project_root = test_file.parents[2]
        source_module_dir = project_root / "src" / module_name

        if source_module_dir.exists():
            for changed_file in changed_files:
                if str(source_module_dir) in changed_file:
                    return True

    return False


# ============================================================================
# MCP Fixtures
# ============================================================================

@pytest.fixture
def mock_user():
    """Mock user for MCP security tests."""
    from unittest.mock import Mock

    user = Mock()
    user.id = "test_user_123"
    user.username = "testuser"
    user.email = "test@example.com"

    return user


@pytest.fixture
def mock_mcp_server():
    """Mock FastMCP server for testing."""
    from unittest.mock import Mock

    server = Mock()
    server._tools = {}

    return server


@pytest.fixture
def sample_tool_payload():
    """Sample tool payload for testing."""
    return {
        "doc_id": "doc_123",
        "policy_id": "auto",
        "enable_disclaimer": True,
    }


# ============================================================================
# Shared Test Utilities
# ============================================================================

def assert_valid_error_response(response: dict, expected_code: str = None):
    """
    Assert that a response is a valid error response.

    Args:
        response: Response dict
        expected_code: Expected error code (optional)
    """
    assert response["success"] is False
    assert "error" in response
    assert "code" in response["error"]
    assert "message" in response["error"]

    if expected_code:
        assert response["error"]["code"] == expected_code


def assert_valid_success_response(response: dict, expected_tool: str = None):
    """
    Assert that a response is a valid success response.

    Args:
        response: Response dict
        expected_tool: Expected tool name (optional)
    """
    assert response["success"] is True
    assert "result" in response
    assert "metadata" in response
    assert "invocation_id" in response
    assert "duration_ms" in response

    if expected_tool:
        assert response["tool"] == expected_tool
