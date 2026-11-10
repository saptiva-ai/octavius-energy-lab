"""
Pytest configuration for backend services unit tests.

This conftest.py ensures the backend src is in the Python path
before tests are collected.
"""

import sys
from pathlib import Path

# Add backend src to path for imports
backend_src = Path(__file__).resolve().parent.parent.parent.parent / "apps" / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))
