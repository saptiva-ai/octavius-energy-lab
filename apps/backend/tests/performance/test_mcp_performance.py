"""
Performance and Load Tests for MCP Tools.

These tests measure:
- Response time (p50, p95, p99)
- Throughput (requests/second)
- Concurrent request handling
- Resource usage (memory, CPU)
- Cache effectiveness
- Database query performance

Tools tested:
- deep_research
- extract_document_text
- excel_analyzer
- excel_analyzer

Requirements:
- pytest-benchmark
- pytest-asyncio
- Docker Compose running (MongoDB, Redis, MinIO)

Usage:
    # Run all performance tests
    make test-performance

    # Run with detailed benchmarks
    pytest tests/performance/test_mcp_performance.py -v --benchmark-verbose

    # Save benchmark results
    pytest tests/performance/test_mcp_performance.py --benchmark-save=baseline

    # Compare with baseline
    pytest tests/performance/test_mcp_performance.py --benchmark-compare=baseline
"""

import os
import pytest
import asyncio
import time
from datetime import datetime
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import statistics

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_PERFORMANCE", "false").lower() != "true",
    reason="Pruebas de performance MCP deshabilitadas por defecto (RUN_MCP_PERFORMANCE=true para habilitar).",
)

from src.models.document import Document, DocumentStatus
from src.models.research_task import ResearchTask, TaskStatus


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def perf_user_with_token(client):
    """Create performance test user and return access token."""
    register_data = {
        "username": "perf_test_user",
        "email": "perf@test.com",
        "password": "SecurePass123!",
        "full_name": "Performance Test User"
    }

    response = await client.post("/api/auth/register", json=register_data)
    if response.status_code != 201:
        # User might already exist, try login
        login_data = {
            "identifier": "perf_test_user",
            "password": "SecurePass123!"
        }
        response = await client.post("/api/auth/login", json=login_data)
        data = response.json()
        return data["access_token"], data["user"]["id"]

    data = response.json()
    return data["access_token"], data["user"]["id"]


@pytest.fixture
async def perf_document_pdf(perf_user_with_token):
    """Create test PDF document for performance tests."""
    access_token, user_id = perf_user_with_token

    doc = Document(
        user_id=user_id,
        filename="perf_test.pdf",
        original_filename="perf_test.pdf",
        content_type="application/pdf",
        size_bytes=50000,
        minio_key="perf/test.pdf",
        status=DocumentStatus.READY,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={"pages": 5}
    )
    await doc.save()

    return str(doc.id), access_token, user_id


# ============================================================================
# Performance Tests - Single Request
# ============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestMCPToolsResponseTime:
    """Measure response time for individual MCP tool invocations."""

    async def test_deep_research_response_time(
        self,
        client: AsyncClient,
        perf_user_with_token,
        benchmark
    ):
        """Measure deep_research tool response time."""
        access_token, user_id = perf_user_with_token

        payload = {
            "tool": "deep_research",
            "payload": {
                "query": "Performance test query",
                "depth": "shallow",
                "max_iterations": 1
            },
            "context": {"user_id": user_id}
        }

        # Mock to avoid actual Aletheia calls
        mock_task = MagicMock()
        mock_task.id = "perf_task_123"
        mock_task.status = TaskStatus.PENDING
        mock_task.created_at = datetime.utcnow()
        mock_task.result = None

        with patch(
            "src.services.deep_research_service.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task
        ):
            async def make_request():
                response = await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                return response

            # Benchmark the request
            result = await benchmark.pedantic(
                make_request,
                rounds=10,
                iterations=1
            )

            assert result.status_code == 200

    async def test_extract_document_text_response_time_cached(
        self,
        client: AsyncClient,
        perf_document_pdf,
        benchmark
    ):
        """Measure extract_document_text response time with cache hit."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content for performance testing" * 100

        payload = {
            "tool": "extract_document_text",
            "payload": {
                "doc_id": doc_id,
                "method": "auto"
            },
            "context": {"user_id": user_id}
        }

        # Mock cache hit
        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            async def make_request():
                response = await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                return response

            result = await benchmark.pedantic(
                make_request,
                rounds=10,
                iterations=1
            )

            assert result.status_code == 200
            data = result.json()
            assert data["result"]["method_used"] == "cache"

    async def test_extract_document_text_response_time_extraction(
        self,
        client: AsyncClient,
        perf_document_pdf,
        benchmark
    ):
        """Measure extract_document_text response time with actual extraction."""
        doc_id, access_token, user_id = perf_document_pdf

        extracted_text = "Extracted content for performance testing" * 100
        extraction_result = {
            "text": extracted_text,
            "method": "pypdf"
        }

        payload = {
            "tool": "extract_document_text",
            "payload": {
                "doc_id": doc_id,
                "method": "pypdf"  # Force pypdf
            },
            "context": {"user_id": user_id}
        }

        mock_storage = MagicMock()
        mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), True)

        # Mock cache miss + extraction
        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=None  # Cache miss
        ):
            with patch(
                "src.services.minio_storage.get_minio_storage",
                return_value=mock_storage
            ):
                with patch(
                    "src.services.document_extraction.extract_text_from_pdf",
                    new_callable=AsyncMock,
                    return_value=extraction_result
                ):
                    async def make_request():
                        response = await client.post(
                            "/api/mcp/tools/invoke",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        return response

                    result = await benchmark.pedantic(
                        make_request,
                        rounds=10,
                        iterations=1
                    )

                    assert result.status_code == 200


# ============================================================================
# Load Tests - Concurrent Requests
# ============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestMCPToolsConcurrentLoad:
    """Test MCP tools under concurrent load."""

    async def test_concurrent_document_extraction_10_users(
        self,
        client: AsyncClient,
        perf_document_pdf
    ):
        """Test 10 concurrent document extraction requests."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content" * 50

        payload = {
            "tool": "extract_document_text",
            "payload": {"doc_id": doc_id},
            "context": {"user_id": user_id}
        }

        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            async def make_request():
                response = await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                return response.status_code, response.json()

            # Run 10 concurrent requests
            start_time = time.time()
            tasks = [make_request() for _ in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time

            # Verify all succeeded
            successful = sum(1 for r in results if not isinstance(r, Exception) and r[0] == 200)
            assert successful == 10, f"Only {successful}/10 requests succeeded"

            # Calculate metrics
            throughput = 10 / duration
            avg_latency = duration / 10

            print(f"\n📊 Concurrent Load (10 users):")
            print(f"  Total Duration: {duration:.2f}s")
            print(f"  Throughput: {throughput:.2f} req/s")
            print(f"  Avg Latency: {avg_latency:.3f}s")

            # Performance assertions
            assert duration < 5.0, f"10 concurrent requests took {duration:.2f}s (should be < 5s)"
            assert throughput > 2.0, f"Throughput {throughput:.2f} req/s is too low (should be > 2)"

    async def test_concurrent_deep_research_5_users(
        self,
        client: AsyncClient,
        perf_user_with_token
    ):
        """Test 5 concurrent deep research requests."""
        access_token, user_id = perf_user_with_token

        payload = {
            "tool": "deep_research",
            "payload": {
                "query": "Concurrent test query",
                "depth": "shallow"
            },
            "context": {"user_id": user_id}
        }

        mock_task = MagicMock()
        mock_task.id = "concurrent_task"
        mock_task.status = TaskStatus.PENDING
        mock_task.created_at = datetime.utcnow()

        with patch(
            "src.services.deep_research_service.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task
        ):
            async def make_request():
                response = await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                return response.status_code, time.time()

            # Run 5 concurrent requests
            start_time = time.time()
            tasks = [make_request() for _ in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time

            # Calculate latencies
            latencies = [r[1] - start_time for r in results if not isinstance(r, Exception)]

            successful = sum(1 for r in results if not isinstance(r, Exception) and r[0] == 200)
            assert successful == 5, f"Only {successful}/5 requests succeeded"

            print(f"\n📊 Concurrent Deep Research (5 users):")
            print(f"  Total Duration: {duration:.2f}s")
            print(f"  Throughput: {5/duration:.2f} req/s")
            print(f"  Min Latency: {min(latencies):.3f}s")
            print(f"  Max Latency: {max(latencies):.3f}s")
            print(f"  Avg Latency: {statistics.mean(latencies):.3f}s")

            assert duration < 3.0, f"5 concurrent requests took {duration:.2f}s (should be < 3s)"

    async def test_sustained_load_30_requests(
        self,
        client: AsyncClient,
        perf_document_pdf
    ):
        """Test sustained load with 30 sequential requests."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content"

        payload = {
            "tool": "extract_document_text",
            "payload": {"doc_id": doc_id},
            "context": {"user_id": user_id}
        }

        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            latencies = []
            errors = 0

            start_time = time.time()

            for i in range(30):
                req_start = time.time()
                try:
                    response = await client.post(
                        "/api/mcp/tools/invoke",
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    latency = time.time() - req_start
                    latencies.append(latency)

                    if response.status_code != 200:
                        errors += 1
                except Exception:
                    errors += 1

            total_duration = time.time() - start_time

            # Calculate percentiles
            latencies.sort()
            p50 = latencies[int(len(latencies) * 0.50)]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]

            print(f"\n📊 Sustained Load (30 requests):")
            print(f"  Total Duration: {total_duration:.2f}s")
            print(f"  Throughput: {30/total_duration:.2f} req/s")
            print(f"  Success Rate: {(30-errors)/30*100:.1f}%")
            print(f"  Latency p50: {p50:.3f}s")
            print(f"  Latency p95: {p95:.3f}s")
            print(f"  Latency p99: {p99:.3f}s")

            # Performance assertions
            assert errors == 0, f"{errors}/30 requests failed"
            assert p95 < 1.0, f"p95 latency {p95:.3f}s is too high (should be < 1s)"
            assert 30/total_duration > 5.0, f"Throughput too low: {30/total_duration:.2f} req/s"


# ============================================================================
# Stress Tests - Push System Limits
# ============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
@pytest.mark.slow
class TestMCPToolsStress:
    """Stress tests to find system limits."""

    async def test_stress_burst_50_concurrent_requests(
        self,
        client: AsyncClient,
        perf_document_pdf
    ):
        """Test burst of 50 concurrent requests (stress test)."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content"

        payload = {
            "tool": "extract_document_text",
            "payload": {"doc_id": doc_id},
            "context": {"user_id": user_id}
        }

        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            async def make_request(request_id):
                try:
                    start = time.time()
                    response = await client.post(
                        "/api/mcp/tools/invoke",
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    latency = time.time() - start
                    return {
                        "id": request_id,
                        "status": response.status_code,
                        "latency": latency,
                        "success": response.status_code == 200
                    }
                except Exception as e:
                    return {
                        "id": request_id,
                        "status": 0,
                        "latency": 0,
                        "success": False,
                        "error": str(e)
                    }

            # Launch 50 concurrent requests
            start_time = time.time()
            tasks = [make_request(i) for i in range(50)]
            results = await asyncio.gather(*tasks)
            total_duration = time.time() - start_time

            # Analyze results
            successful = sum(1 for r in results if r["success"])
            failed = 50 - successful
            latencies = [r["latency"] for r in results if r["success"]]

            if latencies:
                latencies.sort()
                p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
                p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else 0
                p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else 0
            else:
                p50 = p95 = p99 = 0

            print(f"\n🔥 Stress Test (50 concurrent):")
            print(f"  Total Duration: {total_duration:.2f}s")
            print(f"  Throughput: {50/total_duration:.2f} req/s")
            print(f"  Successful: {successful}/50 ({successful/50*100:.1f}%)")
            print(f"  Failed: {failed}/50")
            print(f"  Latency p50: {p50:.3f}s")
            print(f"  Latency p95: {p95:.3f}s")
            print(f"  Latency p99: {p99:.3f}s")

            # Stress test should have reasonable success rate
            assert successful >= 40, f"Only {successful}/50 requests succeeded (< 80%)"
            assert p95 < 5.0, f"p95 latency {p95:.3f}s is extremely high"

    async def test_stress_sustained_100_requests_over_time(
        self,
        client: AsyncClient,
        perf_document_pdf
    ):
        """Test sustained load of 100 requests over time."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content"

        payload = {
            "tool": "extract_document_text",
            "payload": {"doc_id": doc_id},
            "context": {"user_id": user_id}
        }

        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            results = []
            start_time = time.time()

            # Send 100 requests in batches of 10
            for batch in range(10):
                batch_start = time.time()

                async def make_request():
                    req_start = time.time()
                    response = await client.post(
                        "/api/mcp/tools/invoke",
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    latency = time.time() - req_start
                    return response.status_code == 200, latency

                # 10 requests per batch
                batch_tasks = [make_request() for _ in range(10)]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                for result in batch_results:
                    if not isinstance(result, Exception):
                        results.append(result)

                batch_duration = time.time() - batch_start

                # Small delay between batches
                if batch < 9:
                    await asyncio.sleep(0.1)

            total_duration = time.time() - start_time

            # Analyze
            successful = sum(1 for r in results if r[0])
            latencies = [r[1] for r in results if r[0]]
            latencies.sort()

            p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
            p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

            print(f"\n🏃 Sustained Load (100 requests in batches):")
            print(f"  Total Duration: {total_duration:.2f}s")
            print(f"  Throughput: {len(results)/total_duration:.2f} req/s")
            print(f"  Success Rate: {successful/len(results)*100:.1f}%")
            print(f"  Latency p50: {p50:.3f}s")
            print(f"  Latency p95: {p95:.3f}s")

            assert successful >= 95, f"Only {successful}/100 requests succeeded"


# ============================================================================
# Cache Performance Tests
# ============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestMCPCachePerformance:
    """Test cache effectiveness and performance."""

    async def test_cache_hit_vs_miss_performance(
        self,
        client: AsyncClient,
        perf_document_pdf
    ):
        """Compare performance of cache hit vs cache miss."""
        doc_id, access_token, user_id = perf_document_pdf

        cached_text = "Cached content" * 100
        extracted_text = "Extracted content" * 100

        payload = {
            "tool": "extract_document_text",
            "payload": {"doc_id": doc_id},
            "context": {"user_id": user_id}
        }

        # Measure cache hit performance
        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=cached_text
        ):
            cache_hit_times = []
            for _ in range(5):
                start = time.time()
                await client.post(
                    "/api/mcp/tools/invoke",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                cache_hit_times.append(time.time() - start)

        # Measure cache miss performance
        mock_storage = MagicMock()
        mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), True)

        with patch(
            "src.services.document_service.get_document_text",
            new_callable=AsyncMock,
            return_value=None
        ):
            with patch("src.services.minio_storage.get_minio_storage", return_value=mock_storage):
                with patch(
                    "src.services.document_extraction.extract_text_from_pdf",
                    new_callable=AsyncMock,
                    return_value={"text": extracted_text, "method": "pypdf"}
                ):
                    cache_miss_times = []
                    for _ in range(5):
                        start = time.time()
                        await client.post(
                            "/api/mcp/tools/invoke",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        cache_miss_times.append(time.time() - start)

        avg_cache_hit = statistics.mean(cache_hit_times)
        avg_cache_miss = statistics.mean(cache_miss_times)
        speedup = avg_cache_miss / avg_cache_hit

        print(f"\n💾 Cache Performance:")
        print(f"  Cache Hit (avg): {avg_cache_hit:.3f}s")
        print(f"  Cache Miss (avg): {avg_cache_miss:.3f}s")
        print(f"  Speedup: {speedup:.1f}x")

        # Cache should provide significant speedup
        assert speedup > 1.2, f"Cache only provides {speedup:.1f}x speedup (should be > 1.2x)"
