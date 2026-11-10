"""Etiquetas en español para tipos de serie, entidades y calidad."""

from __future__ import annotations

import ast
from pathlib import Path

import psycopg

from conftest import dsn_for
from energy_lab_ingest.etiquetas import CALIDAD, TIPOS_DE_SERIE, describir_calidad, etiqueta
from energy_lab_ingest.loader import Loader
from energy_lab_ingest.profiles import FIXTURES
from energy_lab_ingest.sources.lcl import LclSource

SOURCES = Path(__file__).resolve().parents[1] / "energy_lab_ingest" / "sources"


def _quality_keys_in_sources() -> set[str]:
    """Llaves literales que las fuentes escriben en quality[...]."""
    keys = set()
    for path in SOURCES.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "quality"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
    return keys


def test_toda_llave_de_calidad_tiene_etiqueta() -> None:
    faltan = _quality_keys_in_sources() - set(CALIDAD)
    assert not faltan, f"Llaves de calidad sin etiqueta en español: {sorted(faltan)}"


def test_describir_calidad_omite_ceros_y_usa_espanol() -> None:
    lineas = describir_calidad({"rows_read": 1000, "null_values": 0, "duplicates_dropped": 3})
    assert lineas == ["Duplicados eliminados: 3", "Filas leídas: 1,000"]


def test_clave_desconocida_no_se_oculta() -> None:
    assert etiqueta(TIPOS_DE_SERIE, "algo_nuevo") == "algo_nuevo"


def test_series_guardan_su_etiqueta(admin_dsn: str, migrated: str) -> None:
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ingest")) as conn:
        source = LclSource([FIXTURES / "lcl_smoke.csv"])
        Loader(conn, source.dataset_info(version="etiquetas"), profile="smoke").load(source)
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as admin:
        fila = admin.execute(
            "SELECT attrs->>'etiqueta', attrs->>'unidad' FROM core.series WHERE source = 'lcl' LIMIT 1"
        ).fetchone()
    assert fila == ("Consumo eléctrico", "kWh por intervalo")
