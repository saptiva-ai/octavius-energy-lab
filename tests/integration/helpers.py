from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")
DEFAULT_FILE_MANAGER_URL = os.environ.get(
    "TEST_FILE_MANAGER_URL", "http://localhost:8001"
)
DEFAULT_AUTH_USER = os.environ.get("TEST_AUTH_USER", "demo@example.com")
DEFAULT_AUTH_PASS = os.environ.get("TEST_AUTH_PASS", "Demo1234")
DEFAULT_TIMEOUT = float(os.environ.get("TEST_TIMEOUT", "30"))


def compose_command(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        "infra/docker-compose.yml",
        "--env-file",
        "envs/.env",
        *args,
    ]


def get_auth_token(
    *,
    token: Optional[str] = None,
    backend_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    if token:
        return token

    url = backend_url or DEFAULT_BACKEND_URL
    payload = {"identifier": DEFAULT_AUTH_USER, "password": DEFAULT_AUTH_PASS}
    response = httpx.post(f"{url}/api/auth/login", json=payload, timeout=timeout)
    response.raise_for_status()
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("Failed to obtain auth token")
    return access_token


def fixture_path(filename: str) -> Path:
    return PROJECT_ROOT / "tests" / "fixtures" / filename


def temp_path(filename: str) -> Path:
    return Path(tempfile.gettempdir()) / filename


def copy_fixture_to_temp(filename: str, dest_name: str) -> Path:
    source = fixture_path(filename)
    destination = temp_path(dest_name)
    shutil.copy(source, destination)
    return destination


def json_or_raise(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Expected JSON object response")
    return data
