"""CENACE: precios de nodos distribuidos por zona de carga (SW-PEND) y precios
marginales locales por nodo (SW-PML) del Mercado Eléctrico Mayorista.

Servicios web (verificados el 2026-11-10):
  https://ws01.cenace.gob.mx:8082/SWPEND/SIM/{sistema}/{proceso}/{zonas}/{AAAA/MM/DD}/{AAAA/MM/DD}/JSON
  https://ws01.cenace.gob.mx:8082/SWPML/SIM/{sistema}/{proceso}/{nodos}/{AAAA/MM/DD}/{AAAA/MM/DD}/JSON

- Máximo 7 días y 20 claves por consulta. Fechas inclusivas.
- Además, el segmento de claves de la URL no debe pasar de ~100 caracteres:
  20 zonas de carga con nombres largos dan HTTP 400 (medido: 94-100
  caracteres responden, 139 o más fallan).
- Zonas con espacios se escriben con guiones: CENTRO ORIENTE -> CENTRO-ORIENTE.
- Errores: HTTP 200 con {"Message": "..."}.
- Clave inexistente: status ZERO_RESULTS, o Valores vacío dentro de un OK.
- Valores como texto: fecha, hora (1-24), pz|pml y sus componentes de
  energía (_ene), pérdidas (_per) y congestión (_cng), en MXN/MWh.

Tiempo: `hora` se toma como el índice de la hora desde la medianoche local
del día (hora 1 = primera hora del día). ts es el inicio del intervalo en
UTC, calculado desde la medianoche local más (hora - 1) horas, lo que es
correcto también en días de 23 o 25 horas.

Licencia: CENACE no publica términos de uso explícitos para estos servicios
(ver docs/data/sources.md). Por eso el repositorio no redistribuye datos
crudos: los fixtures de prueba tienen la estructura real con valores
sintéticos.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..model import DatasetInfo, Record, SeriesSpec, Unit

BASE_URL = "https://ws01.cenace.gob.mx:8082"
MAX_DAYS = 7
MAX_KEYS = 20
MAX_KEYS_CHARS = 100
SYSTEMS = ("SIN", "BCA", "BCS")
PROCESSES = ("MDA", "MTR")
# Zona horaria de referencia del mercado. BCA opera en hora del Pacífico.
TIMEZONES = {"SIN": "America/Mexico_City", "BCS": "America/Mazatlan", "BCA": "America/Tijuana"}

SERVICES = {
    "pend": {"path": "SWPEND", "key_field": "zona_carga", "prefix": "pz", "entity": "load_zone"},
    "pml": {"path": "SWPML", "key_field": "clv_nodo", "prefix": "pml", "entity": "node"},
}
COMPONENTS = {
    "total": ("", "price"),
    "energy": ("_ene", "price_energy"),
    "losses": ("_per", "price_losses"),
    "congestion": ("_cng", "price_congestion"),
}

Transport = Callable[[str], dict]


class CenaceApiError(RuntimeError):
    """El servicio respondió con un mensaje de error."""


def http_transport(timeout_s: float = 60) -> Transport:
    def get(url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": "energy-lab-ingest/0.1"})
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    return get


def key_chunks(keys: Sequence[str]) -> list[list[str]]:
    """Bloques de hasta 20 claves cuyo segmento "a,b,c" no pasa de 100 caracteres."""
    chunks: list[list[str]] = []
    current: list[str] = []
    for key in keys:
        if len(key) > MAX_KEYS_CHARS:
            raise ValueError(f"Clave demasiado larga para el servicio: {key}")
        candidate = [*current, key]
        if current and (len(candidate) > MAX_KEYS or len(",".join(candidate)) > MAX_KEYS_CHARS):
            chunks.append(current)
            candidate = [key]
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def windows(keys: Sequence[str], start: date, end: date) -> Iterator[tuple[list[str], date, date]]:
    """Bloques de claves (ver key_chunks) por ventanas de hasta 7 días (inclusivas)."""
    chunks = key_chunks(keys)
    day = start
    while day <= end:
        window_end = min(day + timedelta(days=MAX_DAYS - 1), end)
        for chunk in chunks:
            yield chunk, day, window_end
        day = window_end + timedelta(days=1)


def zone_key(name: str) -> str:
    """Nombre de zona de carga del catálogo a la clave que acepta SW-PEND."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", "-", ascii_name.strip().upper())


def hour_to_utc(day: date, hour: int, tz: str = "America/Mexico_City") -> datetime:
    midnight = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz))
    return midnight.astimezone(UTC) + timedelta(hours=hour - 1)


class CenaceClient:
    def __init__(
        self,
        transport: Transport | None = None,
        delay_s: float = 1.0,
        retries: int = 3,
        backoff_s: float = 5.0,
    ) -> None:
        self.transport = transport or http_transport()
        self.delay_s = delay_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.calls = 0

    def url(
        self, service: str, system: str, process: str, keys: Sequence[str], start: date, end: date
    ) -> str:
        path = SERVICES[service]["path"]
        return (
            f"{BASE_URL}/{path}/SIM/{system}/{process}/{','.join(keys)}/{start:%Y/%m/%d}/{end:%Y/%m/%d}/JSON"
        )

    def get(
        self, service: str, system: str, process: str, keys: Sequence[str], start: date, end: date
    ) -> dict:
        if (end - start).days >= MAX_DAYS or len(keys) > MAX_KEYS or len(",".join(keys)) > MAX_KEYS_CHARS:
            raise ValueError("La consulta excede 7 días, 20 claves o 100 caracteres de claves")
        url = self.url(service, system, process, keys, start, end)
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.calls and self.delay_s:
                time.sleep(self.delay_s)
            self.calls += 1
            try:
                doc = self.transport(url)
            except (OSError, json.JSONDecodeError) as exc:  # red o respuesta truncada
                last_error = exc
                time.sleep(self.backoff_s * (attempt + 1) if self.delay_s else 0)
                continue
            if "Message" in doc and "status" not in doc:
                raise CenaceApiError(doc["Message"])
            return doc
        raise CenaceApiError(f"Sin respuesta tras {self.retries} intentos: {last_error}")


class CenaceSource:
    def __init__(
        self,
        service: str,
        system: str,
        process: str,
        keys: Sequence[str],
        start: date,
        end: date | None = None,
        client: CenaceClient | None = None,
    ) -> None:
        if service not in SERVICES:
            raise ValueError(f"Servicio inválido: {service} (pend o pml)")
        if system not in SYSTEMS:
            raise ValueError(f"Sistema inválido: {system}")
        if process not in PROCESSES:
            raise ValueError(f"Proceso inválido: {process}")
        if not keys:
            raise ValueError("Se necesita al menos una clave")
        self.service = service
        self.system = system
        self.process = process
        self.keys = list(dict.fromkeys(keys))
        self.start = start
        self.end = end or start
        self.client = client or CenaceClient()
        self.tz = TIMEZONES[system]
        self.name = f"cenace_{service}"

    def dataset_info(self, version: str) -> DatasetInfo:
        return DatasetInfo(
            source=self.name,
            version=version,
            license="Sin términos explícitos de CENACE; no se redistribuye",
            url=f"{BASE_URL}/{SERVICES[self.service]['path']}",
            notes=f"{self.system} {self.process}; hora 1-24 local ({self.tz}) a UTC, inicio de intervalo.",
        )

    def _key(self, key: str, component: str) -> str:
        return f"{self.system}:{self.process}:{key}:{component}"

    def series_specs(self) -> list[SeriesSpec]:
        meta = SERVICES[self.service]
        return [
            SeriesSpec(
                source_key=self._key(key, component),
                kind=kind,
                unit="MXN/MWh",
                freq="1 hour",
                entity_kind=meta["entity"],
                entity_key=f"{self.system}:{key}",
                name=key,
                tz=self.tz,
                attrs={"ts_label": "interval_start", "process": self.process, "system": self.system},
            )
            for key in self.keys
            for component, (_, kind) in COMPONENTS.items()
        ]

    def selection(self) -> str:
        import hashlib

        desc = f"{self.service}|{self.system}|{self.process}|{','.join(self.keys)}|{self.start}|{self.end}"
        return hashlib.sha256(desc.encode()).hexdigest()[:12]

    def _months(self) -> Iterator[tuple[str, date, date]]:
        day = self.start
        while day <= self.end:
            next_month = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
            month_end = min(next_month - timedelta(days=1), self.end)
            yield f"{day:%Y-%m}", day, month_end
            day = next_month

    def iter_units(self) -> Iterator[Unit]:
        """Una unidad por mes. Los registros se piden al servicio solo cuando el
        loader los consume: un mes ya cargado se salta sin llamar a CENACE."""
        for unit_key, month_start, month_end in self._months():
            quality: Counter = Counter()
            yield Unit(unit_key, self._fetch_month(month_start, month_end, quality), quality)

    def _fetch_month(self, month_start: date, month_end: date, quality: Counter) -> Iterator[Record]:
        meta = SERVICES[self.service]
        prefix = meta["prefix"]
        requested = set(self.keys)
        seen_with_data: set[str] = set()
        calls_before = self.client.calls
        for keys, start, end in windows(self.keys, month_start, month_end):
            doc = self.client.get(self.service, self.system, self.process, keys, start, end)
            for result in doc.get("Resultados", []):
                raw_key = result.get(meta["key_field"]) or ""
                # SW-PEND responde "CENTRO ORIENTE" aunque se pida CENTRO-ORIENTE.
                key = zone_key(raw_key) if self.service == "pend" else raw_key.strip()
                if key not in requested:
                    quality["unexpected_keys"] += 1
                    continue
                values = result.get("Valores") or []
                if values:
                    seen_with_data.add(key)
                for row in values:
                    quality["hours_read"] += 1
                    ts = hour_to_utc(date.fromisoformat(row["fecha"]), int(row["hora"]), self.tz)
                    for component, (suffix, _) in COMPONENTS.items():
                        raw = row.get(prefix + suffix)
                        value = float(raw) if raw not in (None, "") else None
                        if value is None:
                            quality["null_values"] += 1
                        elif value < 0:
                            quality[f"negative_{component}"] += 1
                        yield (self._key(key, component), ts, value)
        quality["api_calls"] = self.client.calls - calls_before
        quality["keys_without_data"] = len(requested - seen_with_data)
