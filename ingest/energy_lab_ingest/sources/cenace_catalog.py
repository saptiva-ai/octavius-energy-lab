"""Catálogo de Nodos P de CENACE: nodos, zonas de carga y centros de control.

Fuente: https://www.cenace.gob.mx/Paginas/SIM/NodosP.aspx (xlsx versionado,
se publica casi cada mes). Verificado sobre v2026-10-23: 2,611 nodos
(SIN 2,459, BCA 121, BCS 31) y 108 zonas de carga además de "No Aplica".

Formato: hoja 1, fila 1 con encabezados agrupados, fila 2 con encabezados
reales, datos desde la fila 3. Algunas columnas repiten nombre, así que se
leen por posición.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from ..profiles import spread
from .cenace import zone_key

CATALOG_VERSION = "2026-10-23"
CATALOG_URL = (
    "https://www.cenace.gob.mx/Docs/01_MECP/CatalogoNodosP/2026/"
    "Cat%C3%A1logo%20NodosP%20Sistema%20El%C3%A9ctrico%20Nacional%20(v2026-10-23).xlsx"
)
CATALOG_SHA256 = "6f0273a0d6ce3d8647c86fc86201deb348586198587ff5fb5a5b30e68402216c"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# Posición de las columnas usadas (fila 2 del catálogo).
COL = {"system": 0, "ccr": 1, "zone": 2, "key": 3, "name": 4, "kv": 5, "state": 15, "municipality": 17}
NO_ZONE = "No Aplica"


@dataclass
class Node:
    system: str
    key: str
    name: str
    ccr: str
    zone: str | None
    kv: str | None
    state: str | None
    municipality: str | None


@dataclass
class Zone:
    system: str
    name: str
    key: str
    ccr: str
    states: set[str] = field(default_factory=set)
    nodes: int = 0


@dataclass
class Catalog:
    version: str
    nodes: list[Node]
    zones: list[Zone]

    def zones_by_ccr(self, system: str = "SIN") -> dict[str, list[Zone]]:
        groups: dict[str, list[Zone]] = defaultdict(list)
        for z in sorted(self.zones, key=lambda z: z.key):
            if z.system == system:
                groups[z.ccr].append(z)
        return dict(sorted(groups.items()))

    def stratified_zones(self, per_ccr: int, system: str = "SIN") -> list[Zone]:
        """per_ccr zonas por centro de control, repartidas en cada grupo.

        Evita que la muestra de la demo quede concentrada en una región.
        """
        chosen: list[Zone] = []
        for zones in self.zones_by_ccr(system).values():
            keys = spread([z.key for z in zones], per_ccr)
            chosen.extend(z for z in zones if z.key in keys)
        return chosen


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group()
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_rows(path: Path) -> list[dict[int, str]]:
    """Filas de la primera hoja como {columna: texto}. Solo biblioteca estándar."""
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.find(NS + "sheetData"):
        values: dict[int, str] = {}
        for cell in row:
            kind = cell.get("t")
            if kind == "inlineStr":
                node = cell.find(NS + "is")
                text = "".join(t.text or "" for t in node.iter(NS + "t")) if node is not None else ""
            else:
                v = cell.find(NS + "v")
                if v is None:
                    continue
                text = shared[int(v.text)] if kind == "s" else v.text
            values[_column(cell.get("r"))] = (text or "").strip()
        rows.append(values)
    return rows


def parse_catalog(path: Path, version: str = CATALOG_VERSION) -> Catalog:
    rows = read_rows(path)
    header = rows[1] if len(rows) > 1 else {}
    if (
        header.get(COL["key"], "").upper() != "CLAVE"
        or header.get(COL["zone"], "").upper() != "ZONA DE CARGA"
    ):
        raise ValueError(
            "El catálogo no tiene el formato esperado (fila 2: SISTEMA, ..., ZONA DE CARGA, CLAVE)"
        )
    nodes: list[Node] = []
    zones: dict[tuple[str, str], Zone] = {}
    for values in rows[2:]:
        key = values.get(COL["key"])
        system = values.get(COL["system"])
        if not key or not system:
            continue
        zone_name = values.get(COL["zone"]) or None
        if zone_name == NO_ZONE:
            zone_name = None
        node = Node(
            system=system,
            key=key,
            name=values.get(COL["name"], ""),
            ccr=values.get(COL["ccr"], ""),
            zone=zone_name,
            kv=values.get(COL["kv"]),
            state=values.get(COL["state"]),
            municipality=values.get(COL["municipality"]),
        )
        nodes.append(node)
        if zone_name:
            zone = zones.setdefault(
                (system, zone_name),
                Zone(system=system, name=zone_name, key=zone_key(zone_name), ccr=node.ccr),
            )
            zone.nodes += 1
            if node.state:
                zone.states.add(node.state)
    return Catalog(
        version=version, nodes=nodes, zones=sorted(zones.values(), key=lambda z: (z.system, z.key))
    )


def load_catalog(conn: psycopg.Connection, catalog: Catalog) -> dict[str, int]:
    """Carga zonas y nodos a core.entity con cohortes por sistema y CCR.

    Las llaves coinciden con las que usa CenaceSource (sistema:clave), así que
    las series de precios quedan ligadas a estas entidades.
    """
    counts = {"zones": 0, "nodes": 0}
    with conn.transaction():
        cohort_ids: dict[tuple[str, str], int] = {}

        def cohort(kind: str, name: str) -> int:
            if (kind, name) not in cohort_ids:
                cohort_ids[(kind, name)] = conn.execute(
                    "INSERT INTO core.cohort (kind, name) VALUES (%s, %s) "
                    "ON CONFLICT (kind, name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                    (kind, name),
                ).fetchone()[0]
            return cohort_ids[(kind, name)]

        def entity(source: str, kind: str, key: str, name: str, attrs: dict, cohorts: list[int]) -> None:
            entity_id = conn.execute(
                """
                INSERT INTO core.entity (source, kind, source_key, name, attrs)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source, kind, source_key) DO UPDATE
                    SET name = EXCLUDED.name, attrs = core.entity.attrs || EXCLUDED.attrs
                RETURNING id
                """,
                (source, kind, key, name, Jsonb(attrs)),
            ).fetchone()[0]
            for cohort_id in cohorts:
                conn.execute(
                    "INSERT INTO core.entity_cohort (entity_id, cohort_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (entity_id, cohort_id),
                )

        for z in catalog.zones:
            entity(
                "cenace_pend",
                "load_zone",
                f"{z.system}:{z.key}",
                z.name,
                {
                    "ccr": z.ccr,
                    "states": sorted(z.states),
                    "nodes": z.nodes,
                    "catalog_version": catalog.version,
                },
                [cohort("system", z.system), cohort("ccr", z.ccr)],
            )
            counts["zones"] += 1
        for n in catalog.nodes:
            entity(
                "cenace_pml",
                "node",
                f"{n.system}:{n.key}",
                n.name,
                {
                    "ccr": n.ccr,
                    "zone": n.zone,
                    "kv": n.kv,
                    "state": n.state,
                    "municipality": n.municipality,
                    "catalog_version": catalog.version,
                },
                [cohort("system", n.system), cohort("ccr", n.ccr)],
            )
            counts["nodes"] += 1
    return counts
