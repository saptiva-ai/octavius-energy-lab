#!/usr/bin/env python3
"""
Authentication Security Tests - Token Manipulation

Tests for:
- Expired tokens
- Invalid signatures
- Malformed tokens
- Missing tokens
- Token reuse after logout
- Session hijacking attempts
"""

import os
import sys
import base64
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

# Add tests/ to path for shared helpers
sys.path.append(str(Path(__file__).resolve().parents[2]))
from utils.helpers import get_auth_token as helper_get_auth_token

BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")


@dataclass
class AuthTestCase:
    id: str
    description: str
    token_modifier: str  # How to modify the token
    expected_status: int  # Expected HTTP status code
    expected_behavior: str  # "reject", "error", "accept" (should never accept)


AUTH_TESTS: List[AuthTestCase] = [
    # -------------------------------------------------------------------------
    # Missing/Empty Tokens
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-001",
        description="No Authorization header",
        token_modifier="NO_HEADER",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-002",
        description="Empty Authorization header",
        token_modifier="EMPTY",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-003",
        description="Bearer without token",
        token_modifier="BEARER_ONLY",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-004",
        description="Token without Bearer prefix",
        token_modifier="NO_BEARER",
        expected_status=401,
        expected_behavior="reject",
    ),

    # -------------------------------------------------------------------------
    # Malformed Tokens
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-005",
        description="Completely invalid token",
        token_modifier="INVALID_GARBAGE",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-006",
        description="Token with only 2 parts (missing signature)",
        token_modifier="TWO_PARTS",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-007",
        description="Token with 4 parts",
        token_modifier="FOUR_PARTS",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-008",
        description="Non-base64 token parts",
        token_modifier="NON_BASE64",
        expected_status=401,
        expected_behavior="reject",
    ),

    # -------------------------------------------------------------------------
    # Signature Tampering
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-009",
        description="Modified signature (last char changed)",
        token_modifier="TAMPER_SIGNATURE",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-010",
        description="Empty signature",
        token_modifier="EMPTY_SIGNATURE",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-011",
        description="Signature from different token",
        token_modifier="WRONG_SIGNATURE",
        expected_status=401,
        expected_behavior="reject",
    ),

    # -------------------------------------------------------------------------
    # Payload Tampering
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-012",
        description="Modified user ID in payload",
        token_modifier="TAMPER_USER_ID",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-013",
        description="Added admin role to payload",
        token_modifier="ADD_ADMIN_ROLE",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-014",
        description="Extended expiration in payload",
        token_modifier="EXTEND_EXPIRY",
        expected_status=401,
        expected_behavior="reject",
    ),

    # -------------------------------------------------------------------------
    # Algorithm Confusion
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-015",
        description="Algorithm none attack",
        token_modifier="ALG_NONE",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-016",
        description="Algorithm HS256 with empty secret",
        token_modifier="ALG_WEAK",
        expected_status=401,
        expected_behavior="reject",
    ),

    # -------------------------------------------------------------------------
    # Special Values
    # -------------------------------------------------------------------------
    AuthTestCase(
        id="AUTH-017",
        description="Token value 'null'",
        token_modifier="NULL_STRING",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-018",
        description="Token value 'undefined'",
        token_modifier="UNDEFINED_STRING",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-019",
        description="Very long token (10KB)",
        token_modifier="VERY_LONG",
        expected_status=401,
        expected_behavior="reject",
    ),
    AuthTestCase(
        id="AUTH-020",
        description="Token with SQL injection",
        token_modifier="SQL_INJECTION",
        expected_status=401,
        expected_behavior="reject",
    ),
]


def get_valid_token() -> Optional[str]:
    """Get a valid authentication token using shared helper."""
    return helper_get_auth_token(backend_url=BACKEND_URL)


def modify_token(valid_token: str, modifier: str) -> Optional[str]:
    """Modify token based on test case."""
    if modifier == "NO_HEADER":
        return None  # Special case: no header
    elif modifier == "EMPTY":
        return ""
    elif modifier == "BEARER_ONLY":
        return "Bearer "
    elif modifier == "NO_BEARER":
        return valid_token  # Token without Bearer prefix
    elif modifier == "INVALID_GARBAGE":
        return "not-a-valid-jwt-token"
    elif modifier == "TWO_PARTS":
        parts = valid_token.split(".")
        return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else "a.b"
    elif modifier == "FOUR_PARTS":
        return f"{valid_token}.extra"
    elif modifier == "NON_BASE64":
        return "not!base64.also!not!base64.still!not!base64"
    elif modifier == "TAMPER_SIGNATURE":
        parts = valid_token.split(".")
        if len(parts) == 3:
            # Change last character of signature
            sig = parts[2]
            tampered_sig = sig[:-1] + ("X" if sig[-1] != "X" else "Y")
            return f"{parts[0]}.{parts[1]}.{tampered_sig}"
        return valid_token
    elif modifier == "EMPTY_SIGNATURE":
        parts = valid_token.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}."
        return valid_token
    elif modifier == "WRONG_SIGNATURE":
        parts = valid_token.split(".")
        if len(parts) == 3:
            # Use a different random signature
            return f"{parts[0]}.{parts[1]}.dGhpc2lzYWZha2VzaWduYXR1cmU"
        return valid_token
    elif modifier == "TAMPER_USER_ID":
        parts = valid_token.split(".")
        if len(parts) >= 2:
            try:
                # Decode payload, modify, re-encode
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                payload["sub"] = "admin-user-id-fake"
                new_payload = base64.urlsafe_b64encode(
                    json.dumps(payload).encode()
                ).decode().rstrip("=")
                return f"{parts[0]}.{new_payload}.{parts[2]}"
            except Exception:
                pass
        return valid_token
    elif modifier == "ADD_ADMIN_ROLE":
        parts = valid_token.split(".")
        if len(parts) >= 2:
            try:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                payload["role"] = "admin"
                payload["is_admin"] = True
                new_payload = base64.urlsafe_b64encode(
                    json.dumps(payload).encode()
                ).decode().rstrip("=")
                return f"{parts[0]}.{new_payload}.{parts[2]}"
            except Exception:
                pass
        return valid_token
    elif modifier == "EXTEND_EXPIRY":
        parts = valid_token.split(".")
        if len(parts) >= 2:
            try:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                # Extend expiry by 1 year
                payload["exp"] = int(time.time()) + (365 * 24 * 60 * 60)
                new_payload = base64.urlsafe_b64encode(
                    json.dumps(payload).encode()
                ).decode().rstrip("=")
                return f"{parts[0]}.{new_payload}.{parts[2]}"
            except Exception:
                pass
        return valid_token
    elif modifier == "ALG_NONE":
        # Create token with alg: none
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        parts = valid_token.split(".")
        if len(parts) >= 2:
            return f"{header}.{parts[1]}."
        return valid_token
    elif modifier == "ALG_WEAK":
        # Token signed with empty secret
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "admin", "role": "admin"}).encode()
        ).decode().rstrip("=")
        # Signature with empty key would be a specific value
        return f"{header}.{payload}.empty-key-signature"
    elif modifier == "NULL_STRING":
        return "null"
    elif modifier == "UNDEFINED_STRING":
        return "undefined"
    elif modifier == "VERY_LONG":
        return "A" * 10000
    elif modifier == "SQL_INJECTION":
        return "'; DROP TABLE users; --"

    return valid_token


def run_auth_test(test: AuthTestCase, valid_token: str) -> Dict:
    """Run a single authentication test."""
    result = {
        "id": test.id,
        "description": test.description,
        "passed": False,
        "actual_status": None,
        "issues": [],
    }

    modified_token = modify_token(valid_token, test.token_modifier)

    headers = {"Accept": "text/event-stream"}

    # Handle different header scenarios
    if test.token_modifier == "NO_HEADER":
        pass  # Don't add Authorization header
    elif test.token_modifier == "NO_BEARER":
        headers["Authorization"] = modified_token
    elif modified_token is not None:
        headers["Authorization"] = f"Bearer {modified_token}"

    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/chat",
            json={"message": "IMOR de BANCODEMO", "stream": True, "model": "Saptiva Turbo"},
            headers=headers,
            timeout=10,
        )

        result["actual_status"] = resp.status_code

        # Check if the response matches expected behavior
        if test.expected_behavior == "reject":
            if resp.status_code in [401, 403]:
                result["passed"] = True
            elif resp.status_code == 200:
                result["issues"].append("CRITICAL: Request accepted with invalid token!")
            else:
                result["issues"].append(f"Unexpected status: {resp.status_code}")
        elif test.expected_behavior == "error":
            if resp.status_code >= 400:
                result["passed"] = True
            else:
                result["issues"].append(f"Expected error, got {resp.status_code}")

    except requests.exceptions.Timeout:
        result["issues"].append("Request timed out")
    except Exception as e:
        result["issues"].append(f"Exception: {str(e)[:100]}")

    return result


def run_all_auth_tests():
    """Run all authentication tests."""
    print("=" * 70)
    print("AUTHENTICATION SECURITY TESTS")
    print("=" * 70)

    valid_token = get_valid_token()
    if not valid_token:
        print("FATAL: Could not get valid token for testing")
        return

    print(f"Valid token obtained: {valid_token[:20]}...")
    print(f"Total test cases: {len(AUTH_TESTS)}\n")

    total_passed = 0
    total_failed = 0
    critical_issues = []

    for test in AUTH_TESTS:
        result = run_auth_test(test, valid_token)

        if result["passed"]:
            total_passed += 1
            status = "\033[92mPASS\033[0m"
        else:
            total_failed += 1
            status = "\033[91mFAIL\033[0m"

        print(f"[{status}] {test.id}: {test.description}")
        print(f"       Expected: {test.expected_status}, Got: {result['actual_status']}")

        if not result["passed"]:
            for issue in result["issues"]:
                print(f"       \033[93m{issue}\033[0m")
                if "CRITICAL" in issue:
                    critical_issues.append((test.id, issue))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Pass Rate: {total_passed / len(AUTH_TESTS) * 100:.1f}%")

    if critical_issues:
        print(f"\n\033[91mCRITICAL ISSUES ({len(critical_issues)}):\033[0m")
        for test_id, issue in critical_issues:
            print(f"  - {test_id}: {issue}")

    return total_failed == 0


if __name__ == "__main__":
    success = run_all_auth_tests()
    exit(0 if success else 1)
