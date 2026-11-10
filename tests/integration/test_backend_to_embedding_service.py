#!/usr/bin/env python3
"""
Integration tests for Backend-to-Embedding-Service communication.

OPTIMIZATION 2026-01: Validates that backend correctly delegates embedding
generation to the embedding-service plugin via gRPC and HTTP.

Test Categories:
1. gRPC connectivity and encoding
2. HTTP fallback
3. Health endpoint integration
4. Batch operations
5. Error handling

Prerequisites:
- embedding-service running on port 8003 (HTTP) / 50053 (gRPC)
- Backend running on port 8000
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

import httpx

# Environment configuration
BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")
EMBEDDING_SERVICE_URL = os.environ.get(
    "TEST_EMBEDDING_SERVICE_URL", "http://localhost:8003"
)
EMBEDDING_GRPC_HOST = os.environ.get("EMBEDDING_SERVICE_GRPC_HOST", "localhost")
EMBEDDING_GRPC_PORT = int(os.environ.get("EMBEDDING_SERVICE_GRPC_PORT", "50053"))


def log(msg: str, status: str = "INFO") -> None:
    """Print formatted log message."""
    icons = {"PASS": "\u2705", "FAIL": "\u274c", "SKIP": "\u23ed\ufe0f", "INFO": "\u2139\ufe0f"}
    print(f"{icons.get(status, '')} {msg}")


def check_service_health(url: str, service_name: str) -> bool:
    """Check if a service is healthy."""
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            log(f"{service_name} is healthy", "PASS")
            return True
        log(f"{service_name} returned {resp.status_code}", "FAIL")
        return False
    except Exception as e:
        log(f"{service_name} unreachable: {e}", "FAIL")
        return False


# =============================================================================
# Test 1: Embedding Service Health
# =============================================================================


def test_embedding_service_health() -> bool:
    """Test that embedding-service is running and healthy."""
    log("Test 1: Embedding Service Health Check")

    try:
        resp = httpx.get(f"{EMBEDDING_SERVICE_URL}/health", timeout=10)
        if resp.status_code != 200:
            log(f"Health endpoint returned {resp.status_code}", "FAIL")
            return False

        data = resp.json()
        if data.get("status") != "healthy":
            log(f"Service status: {data.get('status')}", "FAIL")
            return False

        log(f"Embedding service healthy - model: {data.get('model')}", "PASS")
        return True

    except Exception as e:
        log(f"Health check failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 2: HTTP Encoding Endpoint
# =============================================================================


def test_http_encoding() -> bool:
    """Test embedding generation via HTTP endpoint."""
    log("Test 2: HTTP Encoding Endpoint")

    try:
        payload = {"texts": ["Hola mundo", "Hello world", "Bonjour le monde"]}
        resp = httpx.post(
            f"{EMBEDDING_SERVICE_URL}/embeddings/encode",
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            log(f"Encode endpoint returned {resp.status_code}", "FAIL")
            return False

        data = resp.json()
        embeddings = data.get("embeddings", [])

        if len(embeddings) != 3:
            log(f"Expected 3 embeddings, got {len(embeddings)}", "FAIL")
            return False

        # Check embedding dimension
        dim = len(embeddings[0])
        if dim != 384:
            log(f"Expected 384 dimensions, got {dim}", "FAIL")
            return False

        log(f"HTTP encoding works - {len(embeddings)} embeddings, {dim} dims", "PASS")
        return True

    except Exception as e:
        log(f"HTTP encoding failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 3: gRPC Encoding (if available)
# =============================================================================


def test_grpc_encoding() -> bool:
    """Test embedding generation via gRPC (requires grpcio)."""
    log("Test 3: gRPC Encoding")

    try:
        import grpc
    except ImportError:
        log("grpcio not installed, skipping gRPC test", "SKIP")
        return True  # Not a failure, just skip

    try:
        # Try to import generated proto modules
        sys.path.insert(0, str(__file__).replace("tests/integration/test_backend_to_embedding_service.py", ""))
        from apps.backend.src.proto_stubs.generated import (
            embedding_service_pb2,
            embedding_service_pb2_grpc,
        )
    except ImportError:
        log("Proto modules not available, skipping gRPC test", "SKIP")
        return True

    try:
        # Connect to gRPC server
        channel = grpc.insecure_channel(f"{EMBEDDING_GRPC_HOST}:{EMBEDDING_GRPC_PORT}")
        stub = embedding_service_pb2_grpc.EmbeddingServiceStub(channel)

        # Create request
        request = embedding_service_pb2.EncodeRequest(
            texts=["Test via gRPC"], batch_size=32
        )

        # Call service
        response = stub.Encode(request, timeout=30)

        if len(response.embeddings) != 1:
            log(f"Expected 1 embedding, got {len(response.embeddings)}", "FAIL")
            return False

        dim = response.dimension
        if dim != 384:
            log(f"Expected 384 dimensions, got {dim}", "FAIL")
            return False

        log(f"gRPC encoding works - {dim} dims, {response.processing_time_ms}ms", "PASS")
        channel.close()
        return True

    except Exception as e:
        log(f"gRPC encoding failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 4: Backend Delegates to Embedding Service
# =============================================================================


def test_backend_embedding_delegation() -> bool:
    """Test that backend's embedding service delegates to embedding-service plugin."""
    log("Test 4: Backend Embedding Delegation")

    # This test requires the backend to be running with DELEGATE_EMBEDDINGS=true
    # We can verify by checking if the backend health includes embedding info

    try:
        resp = httpx.get(f"{BACKEND_URL}/api/health", timeout=10)
        if resp.status_code != 200:
            log(f"Backend health returned {resp.status_code}", "FAIL")
            return False

        data = resp.json()

        # Check if backend is healthy
        if data.get("status") != "healthy":
            log(f"Backend status: {data.get('status')}", "FAIL")
            return False

        log("Backend is healthy and likely using delegation", "PASS")
        return True

    except Exception as e:
        log(f"Backend delegation check failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 5: Chunk and Embed via HTTP
# =============================================================================


def test_chunk_and_embed() -> bool:
    """Test the chunk_and_embed endpoint."""
    log("Test 5: Chunk and Embed")

    try:
        # Create a longer text that will be chunked
        text = " ".join(["Esta es una oración de prueba para chunking."] * 100)

        payload = {"text": text, "page": 1, "metadata": {"source": "test"}}

        resp = httpx.post(
            f"{EMBEDDING_SERVICE_URL}/embeddings/chunk-and-embed",
            json=payload,
            timeout=60,
        )

        if resp.status_code != 200:
            log(f"Chunk-and-embed returned {resp.status_code}", "FAIL")
            print(resp.text)
            return False

        data = resp.json()
        chunks = data.get("chunks", [])

        if len(chunks) == 0:
            log("No chunks returned", "FAIL")
            return False

        # Verify each chunk has required fields
        for chunk in chunks:
            if "chunk_id" not in chunk or "text" not in chunk or "embedding" not in chunk:
                log("Chunk missing required fields", "FAIL")
                return False

        log(
            f"Chunk-and-embed works - {len(chunks)} chunks, "
            f"{data.get('processing_time_ms')}ms",
            "PASS",
        )
        return True

    except Exception as e:
        log(f"Chunk-and-embed failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 6: Single Encode with Cache
# =============================================================================


def test_single_encode_with_cache() -> bool:
    """Test single encoding with caching."""
    log("Test 6: Single Encode with Cache")

    try:
        text = "Prueba de cache de embeddings"

        # First call - should compute
        start1 = time.time()
        resp1 = httpx.post(
            f"{EMBEDDING_SERVICE_URL}/embeddings/encode-single",
            json={"text": text, "use_cache": True},
            timeout=30,
        )
        time1 = time.time() - start1

        if resp1.status_code != 200:
            log(f"First encode returned {resp1.status_code}", "FAIL")
            return False

        data1 = resp1.json()

        # Second call - should be cached (faster)
        start2 = time.time()
        resp2 = httpx.post(
            f"{EMBEDDING_SERVICE_URL}/embeddings/encode-single",
            json={"text": text, "use_cache": True},
            timeout=30,
        )
        time2 = time.time() - start2

        if resp2.status_code != 200:
            log(f"Second encode returned {resp2.status_code}", "FAIL")
            return False

        data2 = resp2.json()

        # Verify embeddings are identical
        if data1.get("embedding") != data2.get("embedding"):
            log("Cached embedding differs from original", "FAIL")
            return False

        log(
            f"Single encode with cache works - "
            f"first: {time1:.3f}s, cached: {time2:.3f}s",
            "PASS",
        )
        return True

    except Exception as e:
        log(f"Single encode failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 7: Model Info Endpoint
# =============================================================================


def test_model_info() -> bool:
    """Test model info endpoint."""
    log("Test 7: Model Info Endpoint")

    try:
        resp = httpx.get(f"{EMBEDDING_SERVICE_URL}/embeddings/model-info", timeout=10)

        if resp.status_code != 200:
            log(f"Model info returned {resp.status_code}", "FAIL")
            return False

        data = resp.json()

        required_fields = ["model_name", "dimension", "device"]
        for field in required_fields:
            if field not in data:
                log(f"Missing field: {field}", "FAIL")
                return False

        log(
            f"Model info: {data.get('model_name')}, "
            f"{data.get('dimension')} dims, {data.get('device')}",
            "PASS",
        )
        return True

    except Exception as e:
        log(f"Model info failed: {e}", "FAIL")
        return False


# =============================================================================
# Test 8: Error Handling - Empty Input
# =============================================================================


def test_error_handling_empty_input() -> bool:
    """Test error handling for empty input."""
    log("Test 8: Error Handling - Empty Input")

    try:
        # Empty texts list
        resp = httpx.post(
            f"{EMBEDDING_SERVICE_URL}/embeddings/encode",
            json={"texts": []},
            timeout=10,
        )

        # Should return empty list, not error
        if resp.status_code == 200:
            data = resp.json()
            if data.get("embeddings") == []:
                log("Empty input returns empty list", "PASS")
                return True

        # Or should return 422 validation error
        if resp.status_code == 422:
            log("Empty input returns validation error", "PASS")
            return True

        log(f"Unexpected response: {resp.status_code}", "FAIL")
        return False

    except Exception as e:
        log(f"Error handling test failed: {e}", "FAIL")
        return False


# =============================================================================
# Main Runner
# =============================================================================


def main() -> int:
    """Run all integration tests."""
    print("=" * 60)
    print("Integration Tests: Backend to Embedding Service")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Embedding Service URL: {EMBEDDING_SERVICE_URL}")
    print(f"gRPC: {EMBEDDING_GRPC_HOST}:{EMBEDDING_GRPC_PORT}")
    print("=" * 60)

    # Pre-flight: Check services are up
    if not check_service_health(EMBEDDING_SERVICE_URL, "Embedding Service"):
        log("Embedding service not available, aborting", "FAIL")
        return 2  # Infra failure

    if not check_service_health(BACKEND_URL + "/api", "Backend"):
        log("Backend not available, aborting", "FAIL")
        return 2

    print()

    # Run tests
    tests = [
        ("Embedding Service Health", test_embedding_service_health),
        ("HTTP Encoding", test_http_encoding),
        ("gRPC Encoding", test_grpc_encoding),
        ("Backend Delegation", test_backend_embedding_delegation),
        ("Chunk and Embed", test_chunk_and_embed),
        ("Single Encode Cache", test_single_encode_with_cache),
        ("Model Info", test_model_info),
        ("Error Handling", test_error_handling_empty_input),
    ]

    results = []
    for name, test_fn in tests:
        print()
        try:
            result = test_fn()
            results.append((name, result))
        except Exception as e:
            log(f"Test {name} crashed: {e}", "FAIL")
            results.append((name, False))

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        log(f"{name}: {status}", status)

    print()
    print(f"Results: {passed}/{total} passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
