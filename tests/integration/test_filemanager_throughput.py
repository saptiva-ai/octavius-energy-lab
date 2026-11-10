from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def parse_metric(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def main() -> int:
    print("🧪 Test P-1: File Manager throughput test")

    if not shutil.which("hey"):
        print("⚠️  'hey' tool not found. Skipping performance test.")
        print("Install with: go install github.com/rakyll/hey@latest")
        return 0

    temp_file = Path(tempfile.gettempdir()) / "perf_test_1mb.bin"
    temp_file.write_bytes(os.urandom(1024 * 1024))

    command = [
        "hey",
        "-n",
        "100",
        "-c",
        "10",
        "-m",
        "POST",
        "-T",
        "multipart/form-data; boundary=----WebKitFormBoundary",
        "-D",
        str(temp_file),
        "http://localhost:8001/upload?user_id=perf_test&session_id=perf1",
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    temp_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print("❌ FAIL: hey command failed")
        print(result.stderr)
        return 1

    output = result.stdout
    requests_per_sec = parse_metric(r"Requests/sec:\s+([0-9.]+)", output)
    mean_latency = parse_metric(r"Average:\s+([0-9.]+)", output)

    print(f"Throughput: {requests_per_sec or 'n/a'} req/sec")
    print(f"Mean latency: {mean_latency or 'n/a'}")

    try:
        if requests_per_sec and float(requests_per_sec) > 5:
            print("✅ PASS: Throughput acceptable (>5 req/sec)")
        else:
            print(f"⚠️  WARNING: Throughput low ({requests_per_sec} req/sec)")
    except ValueError:
        print("⚠️  WARNING: Unable to parse throughput")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
