from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

from .helpers import DEFAULT_BACKEND_URL


def run_script(label: str, script: Path) -> tuple[str, bool]:
    print(f"\n▶ Running: {label}")
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode == 0:
        print(f"✅ PASSED: {label}")
        return label, True
    print(f"❌ FAILED: {label}")
    return label, False


def main() -> int:
    print("🚀 Running Integration Test Suite for Plugin-First Architecture")
    print("================================================================")

    print("📋 Prerequisites check...")
    try:
        response = httpx.get(f"{DEFAULT_BACKEND_URL}/api/health", timeout=10)
        response.raise_for_status()
    except Exception:
        print("❌ Backend not running. Run 'make dev' first.")
        return 1

    base_dir = Path(__file__).parent
    scripts = [
        (
            "Backend → FileManager Upload",
            base_dir / "test_backend_to_filemanager_upload.py",
        ),
        (
            "Backend → FileManager Download",
            base_dir / "test_backend_to_filemanager_download.py",
        ),
        (
            "Backend → FileManager Extract",
            base_dir / "test_backend_to_filemanager_extract.py",
        ),
        ("Full Audit Flow", base_dir / "test_full_audit_flow.py"),
        ("FileManager Redis Cache", base_dir / "test_filemanager_redis_cache.py"),
        (
            "FileManager Restart Resilience",
            base_dir / "test_filemanager_restart_resilience.py",
        ),
        ("MinIO Outage Handling", base_dir / "test_minio_outage.py"),
        ("FileManager Throughput", base_dir / "test_filemanager_throughput.py"),
    ]

    passed: list[str] = []
    failed: list[str] = []

    for label, script in scripts:
        name, ok = run_script(label, script)
        if ok:
            passed.append(name)
        else:
            failed.append(name)

    print("\n================================================================")
    print("📊 Test Summary")
    print("================================================================")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")

    if failed:
        print("\nFailed tests:")
        for name in failed:
            print(f"  - {name}")
        return 1

    print("\n🎉 All integration tests passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
