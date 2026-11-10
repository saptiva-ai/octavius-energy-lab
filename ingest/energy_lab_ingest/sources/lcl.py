"""Low Carbon London: consumo eléctrico de 5,567 hogares de Londres.

Fuente: https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d
Licencia: CC BY 4.0 (UK Power Networks).

Formato (verificado el 2026-11-10 sobre "Partitioned LCL Data.zip"):
- 168 CSV de 1,000,000 filas: LCLid, stdorToU, DateTime, "KWH/hh (per half hour) ".
- DateTime con fracción (.0000000) y en GMT: los días de cambio de horario
  de Londres traen 48 lecturas, no 46 ni 50. Se toman como UTC.
- Valores con espacios y "Null"; duplicados exactos (hogar, hora); al final
  de cada hogar, una fila fuera de la malla de media hora (p. ej. 12:37:27)
  con Null.
- Archivos ordenados por tarifa y hogar: los primeros son Std y los últimos
  ToU. Un hogar puede quedar partido entre dos archivos. El demo estratifica
  por tarifa leyendo la primera fila de cada archivo.

Tratamiento:
- Una unidad de carga por archivo.
- Marcas fuera de la malla de 30 minutos: se descartan (quality.off_grid_timestamps).
- "Null": NULL en la base (quality.null_values).
- Duplicados: los elimina el loader (quality.duplicates_dropped).
- Cada hogar entra con la cohorte tariff = Std o ToU.
- No verificado: si DateTime marca el inicio o el fin de la media hora; la
  serie lo declara como attrs.ts_label = "as_published".

Tarifa dinámica 2013 (Tariffs.xlsx): banda por media hora (Normal, Low,
High). Los precios por banda vienen de la página del Datastore:
High 67.20, Normal 11.76 y Low 3.99 p/kWh.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO

from ..model import DatasetInfo, Record, SeriesSpec, Unit
from .cenace_catalog import read_rows

DATASET_URL = (
    "https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d"
)
PARTITIONED_URL = (
    "https://data.london.gov.uk/download/vqm0d/04feba67-f1a3-4563-98d0-f3071e3d56d1/"
    "Partitioned%20LCL%20Data.zip"
)
# sha256 de las descargas del 2026-11-10 (el Datastore no publica checksums).
PARTITIONED_SHA256 = "149a6a9c43c622fd0a14b7d11be055665317d3018d9fb7e1043bd51420bfaea5"
TARIFFS_URL = "https://data.london.gov.uk/download/vqm0d/14855047-44c2-4856-8a48-e5649200e6ce/Tariffs.xlsx"
TARIFFS_SHA256 = "8a2eff6dcb737aee96cfa6c357d2947604d7f812896405c2ab5f98433d2cb150"
TARIFF_PRICES_P_PER_KWH = {"High": 67.20, "Normal": 11.76, "Low": 3.99}
FLAT_TARIFF_P_PER_KWH = 14.228
FILES_IN_FULL = 168
ROWS_PER_FILE = 1_000_000
LICENSE = "CC BY 4.0"

Opener = Callable[[], IO[bytes]]


def parse_ts(raw: str) -> datetime:
    return datetime.strptime(raw.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def first_tariff(zf: zipfile.ZipFile, member: str) -> str:
    """Tarifa (Std o ToU) de la primera fila de datos; solo descomprime el inicio."""
    with zf.open(member) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
        next(reader, None)
        row = next(reader, None)
    return row[1].strip() if row and len(row) > 1 else "unknown"


def pick_files(
    names: Sequence[str], n: int, tariff_of: Callable[[str], str | None] | None = None
) -> list[str]:
    """n archivos para el demo.

    Con tariff_of, estratifica por tarifa: cada grupo recibe archivos en
    proporción a su tamaño y al menos uno. Repartir solo por índice dejó el
    demo sin hogares ToU, porque los archivos ToU están al final.
    """

    def index(name: str) -> int:
        return int(Path(name).stem.rsplit("_", 1)[1])

    def spread_files(items: list[str], k: int) -> list[str]:
        if k >= len(items):
            return items
        step = len(items) / k
        return [items[int(i * step)] for i in range(k)]

    ordered = sorted(names, key=index)
    if n >= len(ordered):
        return ordered
    if tariff_of is None:
        return spread_files(ordered, n)

    groups: dict[str, list[str]] = {}
    for name in ordered:
        groups.setdefault(tariff_of(name) or "unknown", []).append(name)
    quotas = {g: max(1, round(n * len(items) / len(ordered))) for g, items in groups.items()}
    while sum(quotas.values()) > n:
        biggest = max(quotas, key=lambda g: quotas[g])
        quotas[biggest] -= 1
    while sum(quotas.values()) < n:
        quotas[max(groups, key=lambda g: len(groups[g]) - quotas[g])] += 1
    chosen = [f for g, items in groups.items() for f in spread_files(items, quotas[g])]
    return sorted(chosen, key=index)


class LclSource:
    name = "lcl"

    def __init__(
        self, paths: Sequence[Path] | None = None, openers: Sequence[tuple[str, Opener]] = ()
    ) -> None:
        self._openers: list[tuple[str, Opener]] = list(openers)
        for path in paths or []:
            self._openers.append((Path(path).stem, lambda p=Path(path): p.open("rb")))
        self._tariff: dict[str, str] = {}
        self._label = ",".join(name for name, _ in self._openers)

    @classmethod
    def from_zip(cls, archive: Path, members: Sequence[str]) -> LclSource:
        zf = zipfile.ZipFile(archive)
        openers = [(Path(m).stem, lambda m=m: zf.open(m)) for m in members]
        return cls(openers=openers)

    def dataset_info(self, version: str) -> DatasetInfo:
        return DatasetInfo(
            source=self.name,
            version=version,
            license=LICENSE,
            url=DATASET_URL,
            sha256=PARTITIONED_SHA256 if version.startswith("zip-") else None,
            notes="Hogares de Londres, kWh por media hora; DateTime en GMT tomado como UTC.",
        )

    def series_specs(self) -> list[SeriesSpec]:
        return []  # los hogares se descubren al leer

    def spec_for(self, household: str) -> SeriesSpec:
        tariff = self._tariff.get(household, "Std")
        return SeriesSpec(
            source_key=household,
            kind="consumption",
            unit="kWh",
            freq="30 minutes",
            entity_kind="household",
            entity_key=household,
            attrs={"ts_label": "as_published", "tariff": tariff},
            cohorts=(("tariff", tariff),),
        )

    def selection(self) -> str:
        return hashlib.sha256(self._label.encode()).hexdigest()[:12]

    def iter_units(self) -> Iterator[Unit]:
        for name, opener in self._openers:
            quality: Counter = Counter()
            yield Unit(name, self._read(opener, quality), quality)

    def _read(self, opener: Opener, quality: Counter) -> Iterator[Record]:
        with opener() as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            next(reader, None)
            for row in reader:
                if len(row) < 4:
                    quality["malformed_rows"] += 1
                    continue
                household, tariff, stamp, raw_value = row[0], row[1].strip(), row[2], row[3].strip()
                quality["rows_read"] += 1
                self._tariff.setdefault(household, tariff)
                ts = parse_ts(stamp)
                if ts.second or ts.minute not in (0, 30) or stamp.strip()[19:].strip(".0"):
                    quality["off_grid_timestamps"] += 1
                    continue
                if raw_value in ("", "Null"):
                    quality["null_values"] += 1
                    value = None
                else:
                    value = float(raw_value)
                    if value < 0:
                        quality["negative_values"] += 1
                    elif value == 0:
                        quality["zero_values"] += 1
                yield (household, ts, value)


def excel_serial_to_utc(serial: str) -> datetime:
    """Serial de Excel (días desde 1899-12-30) a UTC, redondeado al minuto."""
    moment = datetime(1899, 12, 30, tzinfo=UTC) + timedelta(days=float(serial))
    return (moment + timedelta(seconds=30)).replace(second=0, microsecond=0)


class TariffSource:
    """Tarifa dinámica 2013 como serie de precio por media hora."""

    name = "lcl_tariff"
    KEY = "dToU-2013"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def dataset_info(self, version: str) -> DatasetInfo:
        return DatasetInfo(
            source=self.name,
            version=version,
            license=LICENSE,
            url=DATASET_URL,
            sha256=TARIFFS_SHA256 if version.startswith("xlsx-") else None,
            notes="Banda por media hora de Tariffs.xlsx; precios por banda de la página del Datastore.",
        )

    def series_specs(self) -> list[SeriesSpec]:
        return [
            SeriesSpec(
                source_key=self.KEY,
                kind="tariff_price",
                unit="p/kWh",
                freq="30 minutes",
                entity_kind="system",
                entity_key="LCL-dToU",
                name="Tarifa dinámica LCL 2013",
                attrs={"bands": TARIFF_PRICES_P_PER_KWH, "flat_std_price": FLAT_TARIFF_P_PER_KWH},
                cohorts=(("tariff", "ToU"),),
            )
        ]

    def selection(self) -> str:
        return "tariffs-2013"

    def iter_units(self) -> Iterator[Unit]:
        quality: Counter = Counter()
        yield Unit("2013", self._read(quality), quality)

    def _read(self, quality: Counter) -> Iterator[Record]:
        for values in read_rows(self.path)[1:]:
            serial, band = values.get(0), values.get(1)
            if not serial or band not in TARIFF_PRICES_P_PER_KWH:
                quality["skipped_rows"] += 1
                continue
            quality["rows_read"] += 1
            quality[f"band_{band.lower()}"] += 1
            yield (self.KEY, excel_serial_to_utc(serial), TARIFF_PRICES_P_PER_KWH[band])
