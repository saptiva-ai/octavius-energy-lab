from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    commands: Sequence[list[str]]


def discover_scripts(base_dir: Path) -> list[Path]:
    scripts = [path for path in base_dir.rglob("test_*.py")]
    return sorted(path for path in scripts if path.name != "run_all.py")


def python_command(path: Path) -> list[str]:
    return [sys.executable, str(path)]


def build_suite_from_dir(name: str, description: str, base_dir: Path) -> Suite:
    commands = tuple(python_command(path) for path in discover_scripts(base_dir))
    return Suite(name=name, description=description, commands=commands)


def pytest_command(path: str) -> list[str]:
    return [sys.executable, "-m", "pytest", path]


def all_suites() -> dict[str, Suite]:
    # ── Canonical names ─────────────────────────────────────────────
    # Nota (2026-07-07): las suites del producto bancario (regression,
    # conversation, clarification, charts, metrics) se eliminaron con sus
    # directorios; las suites retail equivalentes viven en el eval harness
    # del plugin (plugins/retail-advisor/tests/evals) y en los e2e web.
    suites = {
        "system_security": build_suite_from_dir(
            "system_security",
            "System security coverage (black-box API)",
            PROJECT_ROOT / "tests" / "system" / "security",
        ),
        "system_rag": build_suite_from_dir(
            "system_rag",
            "RAG context/search quality (requires Weaviate)",
            PROJECT_ROOT / "tests" / "system" / "rag",
        ),
        "system_embedding": build_suite_from_dir(
            "system_embedding",
            "Embedding delegation architecture regression",
            PROJECT_ROOT / "tests" / "system" / "embedding",
        ),
        "system_all": build_suite_from_dir(
            "system_all",
            "All system suites (API/SSE black-box, no browser)",
            PROJECT_ROOT / "tests" / "system",
        ),
        "integration": build_suite_from_dir(
            "integration",
            "Integration coverage (service-to-service)",
            PROJECT_ROOT / "tests" / "integration",
        ),
        "smoke": build_suite_from_dir(
            "smoke",
            "Smoke tests for critical paths",
            PROJECT_ROOT / "tests" / "smoke",
        ),
        "unit": Suite(
            name="unit",
            description="Unit tests",
            commands=(pytest_command("tests/unit"),),
        ),
        "backend_unit": Suite(
            name="backend_unit",
            description="Backend unit tests",
            commands=(pytest_command("apps/backend/tests/unit"),),
        ),
    }

    # ── Legacy aliases (backward compat) ────────────────────────────
    suites["e2e_security"] = suites["system_security"]
    suites["e2e_all"] = suites["system_all"]

    return suites


def default_suites() -> tuple[str, ...]:
    return (
        "system_security",
        "system_embedding",
        "integration",
        "unit",
    )


def resolve_suites(names: Iterable[str]) -> list[Suite]:
    suites = all_suites()
    resolved = []
    for name in names:
        if name not in suites:
            raise ValueError(f"Unknown suite '{name}'. Use --list to see options.")
        resolved.append(suites[name])
    return resolved
