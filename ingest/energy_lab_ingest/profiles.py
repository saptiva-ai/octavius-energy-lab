"""Perfiles smoke, demo y full, y estimación previa de recursos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Costo por fila de core.observation con índices, medido con el perfil demo de
# UCI (2026-11-10: 1,266,530 filas en 115 MB). El benchmark E1 lo refina.
BYTES_PER_ROW_ON_DISK = 95
# Tuplas en memoria por unidad antes del COPY (tupla Python + datetime + float).
BYTES_PER_ROW_IN_MEMORY = 160


@dataclass(frozen=True)
class Estimate:
    rows: int
    disk_gb: float
    peak_memory_mb: float
    units: int

    def describe(self) -> str:
        return (
            f"filas estimadas: {self.rows:,}\n"
            f"disco estimado en PostgreSQL: {self.disk_gb:.1f} GB\n"
            f"memoria pico por unidad: {self.peak_memory_mb:.0f} MB\n"
            f"unidades (meses): {self.units}"
        )


def estimate(rows: int, units: int) -> Estimate:
    per_unit = rows / max(units, 1)
    return Estimate(
        rows=rows,
        disk_gb=rows * BYTES_PER_ROW_ON_DISK / 1e9,
        peak_memory_mb=per_unit * BYTES_PER_ROW_IN_MEMORY / 1e6,
        units=units,
    )


def spread(items: list[str], n: int) -> list[str]:
    """n elementos repartidos uniformemente, no los primeros n.

    Tomar los primeros clientes sesgaría la muestra hacia los de numeración
    baja; repartirlos es una selección determinista y reproducible.
    """
    if n >= len(items):
        return list(items)
    if n <= 0:
        raise ValueError("n debe ser positivo")
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]
