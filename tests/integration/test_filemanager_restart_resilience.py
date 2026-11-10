from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import time
import subprocess

import httpx

from .helpers import DEFAULT_BACKEND_URL, compose_command, get_auth_token


def main() -> int:
    print("🧪 Test R-1: File Manager restart resilience")

    token = get_auth_token(token=os.environ.get("TOKEN"))
    temp_file = Path(tempfile.gettempdir()) / "large_file.bin"
    temp_file.write_bytes(os.urandom(10 * 1024 * 1024))

    result: dict[str, str | int | None] = {"status_code": None, "error": None}

    def upload() -> None:
        try:
            with temp_file.open("rb") as handle:
                response = httpx.post(
                    f"{DEFAULT_BACKEND_URL}/api/files/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"files": (temp_file.name, handle)},
                    data={"session_id": "resilience_test"},
                    timeout=120,
                )
            result["status_code"] = response.status_code
            result["response"] = response.text
        except Exception as exc:  # pragma: no cover - network failure
            result["error"] = str(exc)

    thread = threading.Thread(target=upload)
    thread.start()

    time.sleep(1)
    print("Restarting file-manager...")
    subprocess.run(compose_command("restart", "file-manager"), check=False)

    thread.join()

    if result.get("error"):
        print("✅ Upload interrupted/failed as expected during restart.")
    elif result.get("status_code") != 200:
        print("✅ Upload failed with error response as expected.")
    else:
        print("⚠️  Upload finished successfully? Either too fast or restart delayed.")

    print("Waiting for file-manager recovery...")
    for _ in range(30):
        try:
            health = httpx.get("http://localhost:8001/health", timeout=10).json()
            if health.get("status") == "healthy":
                print("✅ PASS: File Manager recovered after restart")
                temp_file.unlink(missing_ok=True)
                return 0
        except Exception:
            pass
        time.sleep(1)

    print("❌ FAIL: File Manager not healthy after 30s")
    temp_file.unlink(missing_ok=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
