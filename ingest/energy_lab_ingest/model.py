"""Tipos compartidos por fuentes y loader."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# (source_key de la serie, marca en UTC, valor)
Record = tuple[str, datetime, float | None]


@dataclass(frozen=True)
class DatasetInfo:
    source: str
    version: str
    license: str
    url: str | None = None
    sha256: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SeriesSpec:
    source_key: str
    kind: str  # demand, consumption, pml...
    unit: str  # kW, MW, MXN/MWh
    freq: str  # intervalo de PostgreSQL, p. ej. "15 minutes"
    entity_kind: str  # client, household, node, region...
    entity_key: str
    tz: str = "UTC"
    name: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class Unit:
    """Bloque de carga: se confirma o se revierte completo."""

    key: str
    records: Iterator[Record] | Iterable[Record]
    quality: Counter = field(default_factory=Counter)


class Source(Protocol):
    name: str

    def dataset_info(self, version: str) -> DatasetInfo: ...

    def series_specs(self) -> list[SeriesSpec]: ...

    def selection(self) -> str:
        """Huella estable de qué se seleccionó (clientes, fechas)."""
        ...

    def iter_units(self) -> Iterator[Unit]: ...
