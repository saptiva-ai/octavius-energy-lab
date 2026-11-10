#!/usr/bin/env bash
# =============================================================================
# Python Cache Cleanup Script
# =============================================================================
# Removes __pycache__, .pyc, .pyo files and pytest/mypy caches
# Usage: ./scripts/cleanup-python-cache.sh
# Auto-runs: Called by husky pre-commit hook
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🧹 Cleaning Python caches...${NC}"

# Count files before cleanup (for reporting)
PYCACHE_DIRS=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l || echo 0)
PYC_FILES=$(find . -type f \( -name "*.pyc" -o -name "*.pyo" \) 2>/dev/null | wc -l || echo 0)

# Remove __pycache__ directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove .pyc and .pyo files
find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true

# Remove pytest cache
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

# Remove mypy cache
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

# Remove ruff cache
find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

# Remove pytype cache
find . -type d -name ".pytype" -exec rm -rf {} + 2>/dev/null || true

# Remove coverage files
find . -type f -name ".coverage" -delete 2>/dev/null || true
find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

if [ $PYCACHE_DIRS -gt 0 ] || [ $PYC_FILES -gt 0 ]; then
    echo -e "${GREEN}✅ Cleaned:${NC}"
    echo -e "   - $PYCACHE_DIRS __pycache__ directories"
    echo -e "   - $PYC_FILES bytecode files (.pyc/.pyo)"
    echo -e "   - pytest/mypy/ruff caches"
else
    echo -e "${GREEN}✅ No Python caches found (already clean)${NC}"
fi
