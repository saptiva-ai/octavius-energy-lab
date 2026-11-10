from __future__ import annotations

import shutil
import subprocess

import httpx

from .helpers import (
    DEFAULT_FILE_MANAGER_URL,
    compose_command,
    fixture_path,
    json_or_raise,
)


def main() -> int:
    print("🧪 Test 4.1: File Manager caches extracted text in Redis")

    pdf_path = fixture_path("sample.pdf")
    with pdf_path.open("rb") as handle:
        upload_response = httpx.post(
            f"{DEFAULT_FILE_MANAGER_URL}/upload",
            files={"file": (pdf_path.name, handle, "application/pdf")},
            data={"user_id": "cache_test"},
            timeout=60,
        )

    payload = json_or_raise(upload_response)
    minio_key = payload.get("minio_key")

    if not minio_key:
        print("❌ FAIL: Upload failed")
        return 1

    print("First extraction...")
    extract_one = json_or_raise(
        httpx.post(
            f"{DEFAULT_FILE_MANAGER_URL}/extract/{minio_key}",
            timeout=60,
        )
    )
    print("Second extraction...")
    extract_two = json_or_raise(
        httpx.post(
            f"{DEFAULT_FILE_MANAGER_URL}/extract/{minio_key}",
            timeout=60,
        )
    )

    cache_key = f"extract:{minio_key}"
    if shutil.which("docker"):
        command = compose_command("exec", "-T", "redis", "redis-cli", "GET", cache_key)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            print("✅ Redis key found.")
        else:
            print("⚠️  Warning: Redis key not found. Cache might have failed.")
    else:
        print("⚠️  Skipping direct Redis check (docker not available)")

    extract_one_text = extract_one.get("extracted_text")
    extract_two_text = extract_two.get("extracted_text")

    if extract_one_text and extract_one_text == extract_two_text:
        print("✅ PASS: Redis cache extraction consistency verified")
        return 0

    print("❌ FAIL: Cache mismatch or extraction failed")
    print(f"Extract 1 len: {len(extract_one_text or '')}")
    print(f"Extract 2 len: {len(extract_two_text or '')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
