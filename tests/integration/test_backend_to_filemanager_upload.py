from __future__ import annotations

import os
from pathlib import Path

import httpx

from .helpers import (
    DEFAULT_BACKEND_URL,
    copy_fixture_to_temp,
    get_auth_token,
    json_or_raise,
    temp_path,
)


def main() -> int:
    print("🧪 Test 1.1: Backend delegates upload to File Manager")

    token = get_auth_token(token=os.environ.get("TOKEN"))
    temp_file = copy_fixture_to_temp("sample.pdf", "integration_test.pdf")

    with temp_file.open("rb") as handle:
        response = httpx.post(
            f"{DEFAULT_BACKEND_URL}/api/files/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"files": (temp_file.name, handle, "application/pdf")},
            data={"session_id": "integration_test"},
            timeout=60,
        )

    payload = json_or_raise(response)
    files = payload.get("files") or []
    file_id = files[0].get("file_id") if files else None

    if not file_id:
        print("❌ FAIL: No file_id in response")
        return 1

    print(f"File ID: {file_id}")
    temp_path("last_file_id.txt").write_text(file_id)
    print("✅ PASS: Backend → File Manager → MinIO upload works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
