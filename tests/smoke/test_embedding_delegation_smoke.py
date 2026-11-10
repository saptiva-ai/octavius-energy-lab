#!/usr/bin/env python3
"""
Smoke Tests for Embedding Delegation Architecture.

OPTIMIZATION 2026-01: Quick validation that the new embedding delegation
architecture is working correctly after deployment.

These tests are designed to:
- Run fast (< 30 seconds total)
- Validate critical paths only
- Fail fast on infrastructure issues
- Be suitable for CI/CD pipelines and pre-deploy checks

Exit codes:
- 0: All smoke tests passed
- 1: One or more tests failed
- 2: Infrastructure/preflight failure
"""

from __future__ import annotations

import os
import sys
import time
from typing import Tuple

import httpx

# Configuration
BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")
EMBEDDING_URL = os.environ.get("TEST_EMBEDDING_SERVICE_URL", "http://localhost:8003")
TIMEOUT = 10  # Fast timeout for smoke tests


def smoke_test(name: str):
    """Decorator to mark and time smoke tests."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            print(f"\n{'='*50}")
            print(f"SMOKE: {name}")
            print(f"{'='*50}")
            start = time.time()
            try:
                result, message = func(*args, **kwargs)
                elapsed = time.time() - start
                status = "\u2705 PASS" if result else "\u274c FAIL"
                print(f"{status}: {message} ({elapsed:.2f}s)")
                return result
            except Exception as e:
                elapsed = time.time() - start
                print(f"\u274c CRASH: {e} ({elapsed:.2f}s)")
                return False

        wrapper.__name__ = func.__name__
        wrapper._smoke_test_name = name
        return wrapper

    return decorator


# =============================================================================
# Smoke Test 1: Embedding Service Health
# =============================================================================


@smoke_test("Embedding Service Health")
def test_embedding_service_health() -> Tuple[bool, str]:
    """Verify embedding-service is running and responsive."""
    resp = httpx.get(f"{EMBEDDING_URL}/health", timeout=TIMEOUT)

    if resp.status_code != 200:
        return False, f"Status {resp.status_code}"

    data = resp.json()
    status = data.get("status")
    model = data.get("model", "unknown")

    if status != "healthy":
        return False, f"Status: {status}"

    return True, f"Healthy, model: {model}"


# =============================================================================
# Smoke Test 2: Backend Health
# =============================================================================


@smoke_test("Backend Health")
def test_backend_health() -> Tuple[bool, str]:
    """Verify backend is running and responsive."""
    resp = httpx.get(f"{BACKEND_URL}/api/health", timeout=TIMEOUT)

    if resp.status_code != 200:
        return False, f"Status {resp.status_code}"

    data = resp.json()
    status = data.get("status")

    if status != "healthy":
        return False, f"Status: {status}"

    return True, f"Healthy"


# =============================================================================
# Smoke Test 3: Embedding Generation Works
# =============================================================================


@smoke_test("Embedding Generation")
def test_embedding_generation() -> Tuple[bool, str]:
    """Verify embeddings can be generated via HTTP."""
    payload = {"texts": ["Smoke test embedding"]}
    resp = httpx.post(
        f"{EMBEDDING_URL}/embeddings/encode", json=payload, timeout=TIMEOUT * 3
    )

    if resp.status_code != 200:
        return False, f"Status {resp.status_code}"

    data = resp.json()
    embeddings = data.get("embeddings", [])

    if len(embeddings) != 1:
        return False, f"Expected 1 embedding, got {len(embeddings)}"

    dim = len(embeddings[0])
    if dim != 384:
        return False, f"Expected 384 dims, got {dim}"

    return True, f"Generated 1 embedding, {dim} dims"


# =============================================================================
# Smoke Test 4: gRPC Port Accessible (Connection Only)
# =============================================================================


@smoke_test("gRPC Port Accessible")
def test_grpc_port_accessible() -> Tuple[bool, str]:
    """Verify gRPC port is accessible (connection check only)."""
    import socket

    host = os.environ.get("EMBEDDING_GRPC_HOST", "localhost")
    port = int(os.environ.get("EMBEDDING_GRPC_PORT", "50053"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)

    try:
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            return True, f"Port {host}:{port} open"
        return False, f"Port {host}:{port} closed (error: {result})"
    except Exception as e:
        return False, f"Connection failed: {e}"


# =============================================================================
# Smoke Test 5: Backend-to-Embedding Round Trip
# =============================================================================


@smoke_test("Backend to Embedding Connectivity")
def test_backend_embedding_connectivity() -> Tuple[bool, str]:
    """
    Verify backend can reach embedding service.

    This tests the internal network connectivity when both services
    are running in Docker.
    """
    # We can't directly test internal calls, but we can verify both
    # services are healthy and responding

    # Check embedding service from backend's perspective
    # (if backend is in Docker, it would use internal DNS)
    try:
        # Simple validation: both services healthy
        be_resp = httpx.get(f"{BACKEND_URL}/api/health", timeout=TIMEOUT)
        em_resp = httpx.get(f"{EMBEDDING_URL}/health", timeout=TIMEOUT)

        if be_resp.status_code != 200:
            return False, "Backend unhealthy"
        if em_resp.status_code != 200:
            return False, "Embedding service unhealthy"

        return True, "Both services responsive"

    except Exception as e:
        return False, f"Connectivity check failed: {e}"


# =============================================================================
# Smoke Test 6: Embedding Dimension Consistency
# =============================================================================


@smoke_test("Embedding Dimension Consistency")
def test_embedding_dimension_consistency() -> Tuple[bool, str]:
    """Verify all embeddings have consistent dimensions."""
    texts = ["Test 1", "Test 2 longer", "Test 3 even longer text here"]
    payload = {"texts": texts}

    resp = httpx.post(
        f"{EMBEDDING_URL}/embeddings/encode", json=payload, timeout=TIMEOUT * 3
    )

    if resp.status_code != 200:
        return False, f"Status {resp.status_code}"

    data = resp.json()
    embeddings = data.get("embeddings", [])

    if len(embeddings) != 3:
        return False, f"Expected 3 embeddings, got {len(embeddings)}"

    dims = [len(e) for e in embeddings]
    if len(set(dims)) != 1:
        return False, f"Inconsistent dims: {dims}"

    return True, f"All {len(embeddings)} embeddings have {dims[0]} dims"


# =============================================================================
# Main Runner
# =============================================================================


def main() -> int:
    """Run all smoke tests."""
    print("=" * 60)
    print(" SMOKE TESTS: Embedding Delegation Architecture")
    print("=" * 60)
    print(f"Backend: {BACKEND_URL}")
    print(f"Embedding Service: {EMBEDDING_URL}")
    print(f"Timeout: {TIMEOUT}s per test")

    start_time = time.time()

    # Define test order (critical tests first)
    tests = [
        test_embedding_service_health,
        test_backend_health,
        test_grpc_port_accessible,
        test_embedding_generation,
        test_backend_embedding_connectivity,
        test_embedding_dimension_consistency,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn()
            results.append((test_fn._smoke_test_name, result))
        except Exception as e:
            results.append((test_fn._smoke_test_name, False))
            print(f"\u274c CRASH: {e}")

        # Fail fast on critical tests
        if not results[-1][1] and len(results) <= 2:
            print("\n\u26a0\ufe0f  Critical test failed, aborting smoke suite")
            break

    # Summary
    elapsed = time.time() - start_time
    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("\n" + "=" * 60)
    print(" SMOKE TEST SUMMARY")
    print("=" * 60)

    for name, result in results:
        icon = "\u2705" if result else "\u274c"
        print(f"  {icon} {name}")

    print()
    print(f"Results: {passed}/{total} passed in {elapsed:.2f}s")

    if passed == total:
        print("\n\u2705 ALL SMOKE TESTS PASSED")
        return 0
    elif passed <= 2:
        print("\n\u274c INFRASTRUCTURE FAILURE")
        return 2
    else:
        print("\n\u274c SOME SMOKE TESTS FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
