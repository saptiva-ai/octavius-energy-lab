#!/usr/bin/env python3
"""
Master Test Runner for E2E Suite
Runs all test_*.py scripts in subdirectories.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def run_script(path: Path) -> bool:
    print(f"\n{BOLD}>> Running {path}...{RESET}")
    start = time.time()
    try:
        # Run properly capturing output, but streaming it to stdout so user sees progress
        # using subprocess.run with check=False to capture return code
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(path.parents[3]), # run from project root
            env=os.environ.copy()
        )
        duration = time.time() - start
        
        if result.returncode == 0:
            print(f"{GREEN}✓ Passed ({duration:.2f}s){RESET}")
            return True
        else:
            print(f"{RED}✗ Failed (Exit code: {result.returncode}){RESET}")
            return False
    except Exception as e:
        print(f"{RED}✗ Exception: {e}{RESET}")
        return False

def main():
    base_dir = Path(__file__).parent.resolve()
    
    # Discovery
    test_files = sorted(list(base_dir.rglob("test_*.py")))
    # Filter out this script if it was named test_something.py (it's run_all.py)
    test_files = [f for f in test_files if f.name != "run_all.py"]

    print(f"{BOLD}Found {len(test_files)} test scripts in {base_dir}{RESET}")
    
    passed = []
    failed = []
    
    start_total = time.time()
    
    for test_file in test_files:
        # Determine relative path for display
        rel_path = test_file.relative_to(base_dir)
        
        if run_script(test_file):
            passed.append(rel_path)
        else:
            failed.append(rel_path)
            
    total_duration = time.time() - start_total
    
    print("\n" + "="*60)
    print(f"{BOLD}TEST SUITE SUMMARY{RESET}")
    print("="*60)
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Total Tests:    {len(test_files)}")
    print(f"{GREEN}Passed:         {len(passed)}{RESET}")
    print(f"{RED}Failed:         {len(failed)}{RESET}")
    
    if failed:
        print("\nFailed Tests:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All tests passed!{RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
