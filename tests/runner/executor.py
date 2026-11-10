from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Iterable

from .suites import PROJECT_ROOT, Suite


@dataclass(frozen=True)
class CommandResult:
    label: str
    returncode: int
    duration: float


@dataclass(frozen=True)
class SuiteResult:
    name: str
    passed: bool
    duration: float
    failures: tuple[CommandResult, ...]


def run_command(label: str, command: list[str]) -> CommandResult:
    start = time.time()
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    duration = time.time() - start
    return CommandResult(label=label, returncode=result.returncode, duration=duration)


def run_suite(suite: Suite) -> SuiteResult:
    failures: list[CommandResult] = []
    start = time.time()
    for command in suite.commands:
        label = " ".join(command)
        result = run_command(label, command)
        if result.returncode != 0:
            failures.append(result)
    duration = time.time() - start
    return SuiteResult(
        name=suite.name,
        passed=not failures,
        duration=duration,
        failures=tuple(failures),
    )


def summarize(results: Iterable[SuiteResult]) -> int:
    results = list(results)
    failed = [result for result in results if not result.passed]

    print("\n" + "=" * 68)
    print("SUITE SUMMARY")
    print("=" * 68)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status:4} {result.name} ({result.duration:.2f}s)")
        if result.failures:
            for failure in result.failures:
                print(f"  - {failure.label} (exit {failure.returncode})")
    print("=" * 68)
    print(f"Passed suites: {len(results) - len(failed)}")
    print(f"Failed suites: {len(failed)}")

    return 1 if failed else 0
