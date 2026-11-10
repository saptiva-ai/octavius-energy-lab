#!/usr/bin/env python3
"""
Shared helpers for E2E tests: authentication, SSE parsing, and chat requests.
"""

import json
import os
from typing import Any, Dict, Optional

import requests


# Defaults can be overridden via env when running tests
DEFAULT_BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")
DEFAULT_AUTH_USER = os.environ.get("TEST_AUTH_USER", "demo")
DEFAULT_AUTH_PASS = os.environ.get("TEST_AUTH_PASS", "Demo1234")
# pragma: allowlist secret - test helpers pull creds from env/defaults
DEFAULT_MODEL = os.environ.get("TEST_MODEL", "Saptiva Turbo")


# pragma: allowlist secret
def get_auth_token(
    *,
    backend_url: Optional[str] = None,
    identifier: Optional[str] = None,
    user_secret: Optional[str] = None,
    timeout: int = 10,
) -> Optional[str]:
    """Fetch JWT token for tests; returns None on failure (caller asserts)."""
    url = backend_url or DEFAULT_BACKEND_URL
    payload = {
        "identifier": identifier or DEFAULT_AUTH_USER,
        "password": user_secret or DEFAULT_AUTH_PASS,
    }
    try:
        resp = requests.post(f"{url}/api/auth/login", json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception:
        return None
    return None


def parse_sse_response(response) -> Dict[str, Any]:
    """Parse SSE streaming response into a normalized dict."""
    result: Dict[str, Any] = {
        "events": [],
        "bank_chart": None,
        "bank_clarification": None,
        "clarification": None,
        "meta": None,
        "content": "",
        "error": None,
    }

    current_event = None

    for line in response.iter_lines():
        if not line:
            continue

        decoded = line.decode("utf-8")

        if decoded.startswith("event:"):
            current_event = decoded.split(":", 1)[1].strip()
            result["events"].append(current_event)
            continue

        if decoded.startswith("data:") and current_event:
            payload = decoded.split(":", 1)[1].strip()
            if payload == "[DONE]":
                continue

            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = payload

            if current_event in ("bank_chart", "chart"):
                result["bank_chart"] = parsed
            elif current_event in ("bank_clarification", "clarification"):
                result["clarification"] = parsed
                result["bank_clarification"] = parsed
            elif current_event == "meta":
                result["meta"] = parsed
            elif current_event == "chunk":
                if isinstance(parsed, dict) and "content" in parsed:
                    result["content"] += parsed["content"]
                elif isinstance(parsed, str):
                    result["content"] += parsed
            elif current_event == "error":
                result["error"] = parsed
            else:
                extras = result.setdefault("extra", {})
                extras[current_event] = parsed

    return result


def send_chat_message(
    token: str,
    message: str,
    *,
    backend_url: Optional[str] = None,
    model: Optional[str] = None,
    chat_id: Optional[str] = None,
    stream: bool = True,
    timeout: int = 60,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Send a chat message to backend and return parsed SSE response."""
    url = backend_url or DEFAULT_BACKEND_URL
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    }
    if headers:
        hdrs.update(headers)

    payload: Dict[str, Any] = {
        "message": message,
        "stream": stream,
        "model": model or DEFAULT_MODEL,
    }
    if chat_id:
        payload["chat_id"] = chat_id

    try:
        resp = requests.post(
            f"{url}/api/chat",
            json=payload,
            headers=hdrs,
            stream=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {"error": str(exc)}

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}", "status_code": resp.status_code}

    return parse_sse_response(resp)
