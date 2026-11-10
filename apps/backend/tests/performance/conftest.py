"""
Pytest configuration for performance tests.

Provides:
- Performance-specific fixtures
- Benchmark configuration
- Resource monitoring
- Custom markers
"""

import pytest
import os
from typing import Dict

# psutil is optional; skip performance tests if not installed
psutil = pytest.importorskip("psutil")

# Register custom markers
def pytest_configure(config):
    """Register custom markers for performance tests."""
    config.addinivalue_line(
        "markers",
        "performance: mark test as performance test (deselect with '-m \"not performance\"')"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (stress tests, deselect with '-m \"not slow\"')"
    )


# Benchmark configuration
@pytest.fixture(scope="session")
def benchmark_config():
    """Configure pytest-benchmark settings."""
    return {
        "min_rounds": 5,
        "min_time": 0.1,
        "max_time": 5.0,
        "warmup": True,
        "warmup_iterations": 2,
    }


# Resource monitoring
@pytest.fixture
def resource_monitor():
    """Monitor system resources during test execution."""
    process = psutil.Process(os.getpid())

    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    initial_cpu = process.cpu_percent(interval=0.1)

    class ResourceMonitor:
        def get_stats(self) -> Dict[str, float]:
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            current_cpu = process.cpu_percent(interval=0.1)

            return {
                "memory_mb": current_memory,
                "memory_delta_mb": current_memory - initial_memory,
                "cpu_percent": current_cpu,
            }

        def print_stats(self):
            stats = self.get_stats()
            print(f"\n📊 Resource Usage:")
            print(f"  Memory: {stats['memory_mb']:.1f} MB (+{stats['memory_delta_mb']:.1f} MB)")
            print(f"  CPU: {stats['cpu_percent']:.1f}%")

    monitor = ResourceMonitor()
    yield monitor
    monitor.print_stats()


# Performance test timeout
@pytest.fixture(autouse=True)
def performance_test_timeout(request):
    """Set timeout for performance tests to prevent hanging."""
    if "performance" in request.keywords:
        # Performance tests have 2 minute timeout
        return pytest.mark.timeout(120)
    return None
