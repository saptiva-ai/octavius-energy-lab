from __future__ import annotations

import subprocess
import time

import httpx

from .helpers import (
    DEFAULT_FILE_MANAGER_URL,
    compose_command,
    fixture_path,
    json_or_raise,
)


def main() -> int:
    print("🧪 Test R-3: MinIO down - File Manager returns proper error")

    print("Stopping minio...")
    subprocess.run(compose_command("stop", "minio"), check=False)

    print("Attempting upload...")
    pdf_path = fixture_path("sample.pdf")
    with pdf_path.open("rb") as handle:
        response = httpx.post(
            f"{DEFAULT_FILE_MANAGER_URL}/upload",
            files={"file": (pdf_path.name, handle, "application/pdf")},
            data={"user_id": "outage_test"},
            timeout=60,
        )

    http_code = response.status_code
    print(f"HTTP Code: {http_code}")

    if http_code not in (500, 503):
        print(f"❌ FAIL: Unexpected HTTP code: {http_code}")
        subprocess.run(compose_command("start", "minio"), check=False)
        return 1

    print(f"✅ PASS: File Manager handled outage (returned {http_code})")

    print("Restarting minio...")
    subprocess.run(compose_command("start", "minio"), check=False)
    print("Waiting for minio recovery...")
    time.sleep(10)

    with pdf_path.open("rb") as handle:
        recovery_response = httpx.post(
            f"{DEFAULT_FILE_MANAGER_URL}/upload",
            files={"file": (pdf_path.name, handle, "application/pdf")},
            data={"user_id": "outage_test"},
            timeout=60,
        )

    payload = json_or_raise(recovery_response)
    minio_key = payload.get("minio_key")

    if minio_key:
        print("✅ PASS: File Manager recovered after MinIO restart")
        return 0

    print("❌ FAIL: Upload still failing after restart")
    print(payload)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
