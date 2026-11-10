#!/usr/bin/env python3
"""
Regression Tests for Embedding Delegation Architecture.

OPTIMIZATION 2026-01: Ensures that the refactored embedding service
maintains backward compatibility and doesn't break RAG functionality.

Test Categories:
1. RAG query responses still work
2. Document ingestion with embeddings works
3. Semantic search returns relevant results
4. Multi-language support preserved
5. Performance doesn't regress significantly

Prerequisites:
- Full stack running (backend, embedding-service, mongodb, etc.)
- Test user credentials available
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.helpers import (
    DEFAULT_BACKEND_URL,
    get_auth_token,
    parse_sse_response,
    send_chat_message,
)

# Configuration
BACKEND_URL = os.environ.get("TEST_BACKEND_URL", DEFAULT_BACKEND_URL)
VERBOSE = os.environ.get("VERBOSE", "").lower() in ("1", "true", "yes")


@dataclass
class RegressionTestCase:
    """Test case for regression testing."""

    name: str
    query: str
    expected_type: str  # "rag", "chart", "clarification", "general"
    keywords: List[str]  # Keywords that should appear in response
    timeout: int = 60


# =============================================================================
# Test Cases
# =============================================================================

RAG_TEST_CASES = [
    RegressionTestCase(
        name="RAG-001: Basic IMOR Query",
        query="¿Qué es el IMOR?",
        expected_type="rag",
        keywords=["IMOR", "morosidad", "índice", "cartera"],
    ),
    RegressionTestCase(
        name="RAG-002: ICAP Definition",
        query="Explica qué es el ICAP",
        expected_type="rag",
        # EMBEDDING-REG-FIX: Updated keywords to match actual glossary definition
        # Definition uses "proporción" (not "ratio") and "solvencia" (not "adecuado")
        keywords=["ICAP", "capital", "solvencia"],
    ),
    RegressionTestCase(
        name="RAG-003: Regulatory Term",
        query="¿Qué significa CAT en el contexto bancario?",
        expected_type="rag",
        keywords=["CAT", "anual", "total", "costo"],
    ),
    RegressionTestCase(
        name="RAG-004: Multi-concept Query",
        query="Diferencia entre IMOR y cartera vencida",
        expected_type="rag",
        keywords=["IMOR", "cartera", "vencida"],
    ),
    RegressionTestCase(
        name="RAG-005: Spanish Accent Handling",
        query="¿Cuál es la definición de índice de morosidad?",
        expected_type="rag",
        keywords=["morosidad", "índice"],
    ),
]

CHART_TEST_CASES = [
    RegressionTestCase(
        name="CHART-001: IMOR Chart Request",
        query="Muéstrame el IMOR de BANCODEMO",
        expected_type="chart",
        keywords=["IMOR", "BANCODEMO"],
    ),
    RegressionTestCase(
        name="CHART-002: Comparison Chart",
        query="Compara el ICAP de BANCODEMO vs BancoEjemplo",
        expected_type="chart",
        keywords=["ICAP"],
    ),
]


def log(msg: str, status: str = "INFO") -> None:
    """Print formatted log message."""
    icons = {
        "PASS": "\u2705",
        "FAIL": "\u274c",
        "SKIP": "\u23ed\ufe0f",
        "INFO": "\u2139\ufe0f",
        "WARN": "\u26a0\ufe0f",
    }
    print(f"{icons.get(status, '')} {msg}")


def run_test_case(token: str, test_case: RegressionTestCase) -> Dict[str, Any]:
    """Run a single test case and return results."""
    start = time.time()

    result = send_chat_message(
        token=token,
        message=test_case.query,
        backend_url=BACKEND_URL,
        timeout=test_case.timeout,
    )

    elapsed = time.time() - start

    # Analyze result
    passed = True
    reasons = []

    # Check for errors
    if result.get("error"):
        passed = False
        reasons.append(f"Error: {result.get('error')}")
    else:
        content = result.get("content", "").lower()

        # Check expected type
        if test_case.expected_type == "chart":
            if not result.get("bank_chart"):
                # Chart might be in content for some responses
                if "chart" not in content and "gráfico" not in content:
                    passed = False
                    reasons.append("Expected chart response but none received")
        elif test_case.expected_type == "clarification":
            if not result.get("clarification") and not result.get("bank_clarification"):
                passed = False
                reasons.append("Expected clarification but none received")

        # Check keywords (case-insensitive)
        missing_keywords = []
        for keyword in test_case.keywords:
            if keyword.lower() not in content:
                missing_keywords.append(keyword)

        if missing_keywords:
            passed = False
            reasons.append(f"Missing keywords: {missing_keywords}")

    return {
        "name": test_case.name,
        "passed": passed,
        "elapsed_ms": int(elapsed * 1000),
        "reasons": reasons,
        "content_preview": (result.get("content", "")[:200] + "...")
        if result.get("content")
        else None,
    }


# =============================================================================
# Test Suites
# =============================================================================


def run_rag_regression(token: str) -> List[Dict[str, Any]]:
    """Run RAG query regression tests."""
    log("Running RAG Regression Tests", "INFO")
    results = []

    for test_case in RAG_TEST_CASES:
        print(f"\n  Testing: {test_case.name}")
        result = run_test_case(token, test_case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        log(f"{test_case.name}: {status} ({result['elapsed_ms']}ms)", status)

        if not result["passed"] and result["reasons"]:
            for reason in result["reasons"]:
                print(f"    - {reason}")

        if VERBOSE and result.get("content_preview"):
            print(f"    Content: {result['content_preview']}")

    return results


def run_chart_regression(token: str) -> List[Dict[str, Any]]:
    """Run chart query regression tests."""
    log("Running Chart Regression Tests", "INFO")
    results = []

    for test_case in CHART_TEST_CASES:
        print(f"\n  Testing: {test_case.name}")
        result = run_test_case(token, test_case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        log(f"{test_case.name}: {status} ({result['elapsed_ms']}ms)", status)

        if not result["passed"] and result["reasons"]:
            for reason in result["reasons"]:
                print(f"    - {reason}")

    return results


def run_performance_regression(token: str) -> Dict[str, Any]:
    """Run performance regression check."""
    log("Running Performance Regression Check", "INFO")

    # Simple query that should complete quickly
    test_query = "¿Qué es IMOR?"
    times = []

    for i in range(3):
        start = time.time()
        result = send_chat_message(
            token=token, message=test_query, backend_url=BACKEND_URL, timeout=60
        )
        elapsed = time.time() - start
        times.append(elapsed)

        if result.get("error"):
            return {
                "passed": False,
                "reason": f"Query {i+1} failed: {result.get('error')}",
            }

    avg_time = sum(times) / len(times)
    max_time = max(times)

    # Performance thresholds (adjust based on baseline)
    MAX_AVG_TIME = 15.0  # 15 seconds average
    MAX_SINGLE_TIME = 30.0  # 30 seconds max single

    passed = avg_time < MAX_AVG_TIME and max_time < MAX_SINGLE_TIME

    return {
        "passed": passed,
        "avg_time_ms": int(avg_time * 1000),
        "max_time_ms": int(max_time * 1000),
        "threshold_avg_ms": int(MAX_AVG_TIME * 1000),
        "threshold_max_ms": int(MAX_SINGLE_TIME * 1000),
    }


# =============================================================================
# Multi-language Regression
# =============================================================================


def run_multilang_regression(token: str) -> List[Dict[str, Any]]:
    """Test multi-language embedding support."""
    log("Running Multi-language Regression Tests", "INFO")

    test_cases = [
        RegressionTestCase(
            name="LANG-001: Spanish Query",
            query="¿Cuál es la tasa de interés promedio?",
            expected_type="rag",
            keywords=["tasa", "interés"],
        ),
        RegressionTestCase(
            name="LANG-002: Mixed Spanish/English",
            query="¿Qué es el ROE return on equity?",
            expected_type="rag",
            keywords=["ROE", "return", "equity"],
        ),
        RegressionTestCase(
            name="LANG-003: Accented Characters",
            query="Información sobre créditos hipotecários",
            expected_type="rag",
            keywords=["crédito", "hipoteca"],
        ),
    ]

    results = []
    for test_case in test_cases:
        print(f"\n  Testing: {test_case.name}")
        result = run_test_case(token, test_case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        log(f"{test_case.name}: {status}", status)

    return results


# =============================================================================
# Main Runner
# =============================================================================


def main() -> int:
    """Run all regression tests."""
    print("=" * 70)
    print(" REGRESSION TESTS: Embedding Delegation Architecture")
    print("=" * 70)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Verbose: {VERBOSE}")
    print("=" * 70)

    # Get auth token
    log("Authenticating...", "INFO")
    token = get_auth_token(backend_url=BACKEND_URL)

    if not token:
        log("Authentication failed - cannot run regression tests", "FAIL")
        return 2  # Infra failure

    log("Authentication successful", "PASS")

    # Run test suites
    all_results = {
        "rag": [],
        "chart": [],
        "multilang": [],
        "performance": None,
    }

    print("\n" + "=" * 70)
    print(" RAG QUERIES")
    print("=" * 70)
    all_results["rag"] = run_rag_regression(token)

    print("\n" + "=" * 70)
    print(" CHART QUERIES")
    print("=" * 70)
    all_results["chart"] = run_chart_regression(token)

    print("\n" + "=" * 70)
    print(" MULTI-LANGUAGE")
    print("=" * 70)
    all_results["multilang"] = run_multilang_regression(token)

    print("\n" + "=" * 70)
    print(" PERFORMANCE")
    print("=" * 70)
    perf_result = run_performance_regression(token)
    all_results["performance"] = perf_result

    if perf_result["passed"]:
        log(
            f"Performance OK: avg={perf_result['avg_time_ms']}ms, "
            f"max={perf_result['max_time_ms']}ms",
            "PASS",
        )
    else:
        log(
            f"Performance DEGRADED: avg={perf_result['avg_time_ms']}ms "
            f"(threshold: {perf_result['threshold_avg_ms']}ms)",
            "FAIL",
        )

    # Summary
    print("\n" + "=" * 70)
    print(" SUMMARY")
    print("=" * 70)

    total_tests = 0
    passed_tests = 0

    for suite_name, results in all_results.items():
        if suite_name == "performance":
            total_tests += 1
            if results and results.get("passed"):
                passed_tests += 1
            status = "PASS" if results and results.get("passed") else "FAIL"
            print(f"  {suite_name.upper()}: {status}")
        else:
            suite_passed = sum(1 for r in results if r["passed"])
            suite_total = len(results)
            total_tests += suite_total
            passed_tests += suite_passed
            pct = (suite_passed / suite_total * 100) if suite_total > 0 else 0
            status = "PASS" if suite_passed == suite_total else "FAIL"
            print(f"  {suite_name.upper()}: {suite_passed}/{suite_total} ({pct:.0f}%)")

    print()
    overall_pct = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    print(f"TOTAL: {passed_tests}/{total_tests} ({overall_pct:.1f}%)")

    if passed_tests == total_tests:
        print("\n\u2705 ALL REGRESSION TESTS PASSED")
        return 0
    else:
        print(f"\n\u274c {total_tests - passed_tests} REGRESSION TESTS FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
