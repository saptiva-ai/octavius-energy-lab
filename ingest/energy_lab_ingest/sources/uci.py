"""UCI ElectricityLoadDiagrams20112014.

Fuente: https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014
Licencia: CC BY 4.0.

Formato (verificado con el archivo real):
- LD2011_2014.txt, separador ';', coma decimal, una columna por cliente
  (MT_001 ... MT_370) y una fila cada 15 minutos.
- Los valores son kW promedio del intervalo; la etiqueta marca el final del
  intervalo (la primera es 2011-01-01 00:15).
- Las etiquetas están en hora de Portugal y forman una malla regular: el día
  del cambio de primavera las etiquetas de la hora inexistente valen cero, y
  en otoño la hora repetida aparece una sola vez con la suma de ambas.
- Los clientes dados de alta después de 2011 traen ceros antes de su alta.

Tratamiento:
- Etiquetas convertidas a UTC con Europe/Lisbon.
- Etiquetas de hora inexistente: se descartan (quality.nonexistent_local_time).
- Etiquetas de hora ambigua: se toma la primera ocurrencia y se cuentan
  (quality.ambiguous_local_time). El valor conserva la suma de UCI.
- Ceros iniciales de cada cliente dentro de la selección: no se cargan
  (quality.leading_zeros_skipped).
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..model import DatasetInfo, Record, SeriesSpec, Unit

LISBON = ZoneInfo("Europe/Lisbon")
URL = "https://archive.ics.uci.edu/static/public/321/electricityloaddiagrams20112014.zip"
# sha256 del zip descargado el 2026-11-10 (UCI no publica checksums).
ZIP_SHA256 = "f6c4d0e0df12ecdb9ea008dd6eef3518adb52c559d04a9bac2e1b81dcfc8d4e1"
FILENAME = "LD2011_2014.txt"
ROWS_IN_FULL_FILE = 140_256
CLIENTS_IN_FULL_FILE = 370


def parse_value(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    return float(raw.replace(",", "."))


def classify_local(naive: datetime) -> tuple[datetime | None, str | None]:
    """Convierte una hora local de Lisboa a UTC y dice si era inexistente o ambigua."""
    first = naive.replace(tzinfo=LISBON, fold=0)
    second = naive.replace(tzinfo=LISBON, fold=1)
    as_utc = first.astimezone(UTC)
    # Inexistente: ida y vuelta no regresa a la misma hora local.
    if as_utc.astimezone(LISBON).replace(tzinfo=None) != naive:
        return None, "nonexistent_local_time"
    if first.utcoffset() != second.utcoffset():
        return as_utc, "ambiguous_local_time"
    return as_utc, None


class UciSource:
    name = "uci_eld"

    def __init__(
        self,
        path: Path,
        clients: Sequence[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> None:
        self.path = Path(path)
        self.start = start
        self.end = end
        with self.path.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f, delimiter=";"))
        available = [h for h in header[1:]]
        if clients:
            missing = sorted(set(clients) - set(available))
            if missing:
                raise ValueError(f"Clientes que no existen en el archivo: {', '.join(missing)}")
            self.clients = [c for c in available if c in set(clients)]
        else:
            self.clients = available
        self._columns = [header.index(c) for c in self.clients]

    def dataset_info(self, version: str) -> DatasetInfo:
        return DatasetInfo(
            source=self.name,
            version=version,
            license="CC BY 4.0",
            url=URL,
            sha256=ZIP_SHA256 if self.path.name == FILENAME else None,
            notes="Etiquetas en hora de Portugal convertidas a UTC; kW promedio por 15 min.",
        )

    def series_specs(self) -> list[SeriesSpec]:
        return [
            SeriesSpec(
                source_key=c,
                kind="consumption",
                unit="kW",
                freq="15 minutes",
                entity_kind="client",
                entity_key=c,
                tz="Europe/Lisbon",
                attrs={"ts_label": "interval_end"},
            )
            for c in self.clients
        ]

    def selection(self) -> str:
        desc = (
            f"clients={','.join(self.clients)}|start={self.start.isoformat() if self.start else ''}"
            f"|end={self.end.isoformat() if self.end else ''}|file={self.path.name}"
        )
        return hashlib.sha256(desc.encode()).hexdigest()[:12]

    def iter_units(self) -> Iterator[Unit]:
        """Una pasada por el archivo; agrupa por mes UTC."""
        started = dict.fromkeys(self.clients, False)
        current_key: str | None = None
        buffer: list[Record] = []
        quality: Counter = Counter()

        with self.path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            next(reader)
            for row in reader:
                naive = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                ts, anomaly = classify_local(naive)
                probe = ts or naive.replace(tzinfo=UTC)
                if self.start and probe < self.start:
                    continue
                if self.end and probe >= self.end:
                    break
                key = probe.strftime("%Y-%m")
                if current_key is not None and key != current_key:
                    yield Unit(current_key, buffer, quality)
                    buffer, quality = [], Counter()
                current_key = key

                quality["rows_read"] += len(self._columns)
                if anomaly:
                    quality[anomaly] += len(self._columns)
                if ts is None:
                    continue
                for client, col in zip(self.clients, self._columns, strict=True):
                    value = parse_value(row[col])
                    if value is None:
                        quality["null_values"] += 1
                    elif value == 0:
                        if not started[client]:
                            quality["leading_zeros_skipped"] += 1
                            continue
                        quality["zero_values"] += 1
                    elif value < 0:
                        quality["negative_values"] += 1
                    if value:
                        started[client] = True
                    buffer.append((client, ts, value))
        if current_key is not None:
            yield Unit(current_key, buffer, quality)

    @staticmethod
    def estimate_full_rows() -> int:
        return ROWS_IN_FULL_FILE * CLIENTS_IN_FULL_FILE


def interval() -> timedelta:
    return timedelta(minutes=15)
