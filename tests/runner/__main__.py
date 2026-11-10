from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from .executor import run_suite, summarize
from .suites import all_suites, default_suites, resolve_suites


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run test suites in parallel.")
    parser.add_argument(
        "--suite",
        action="append",
        help="Suite name to run (repeatable). Default runs common suites.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available suites.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Override parallel workers for suites.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suites = all_suites()

    if args.list:
        print("Available suites:")
        for suite in suites.values():
            print(f"- {suite.name}: {suite.description}")
        return 0

    names = args.suite or list(default_suites())
    resolved = resolve_suites(names)

    max_workers = args.max_workers or min(len(resolved), max(os.cpu_count() or 2, 2))

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_suite, suite): suite for suite in resolved}
        for future in as_completed(futures):
            results.append(future.result())

    return summarize(results)


if __name__ == "__main__":
    raise SystemExit(main())
