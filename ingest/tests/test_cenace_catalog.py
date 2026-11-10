"""Catálogo de Nodos P con un xlsx sintético del mismo formato."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import psycopg
import pytest

from conftest import dsn_for
from energy_lab_ingest.sources.cenace_catalog import load_catalog, parse_catalog

HEADER_1 = ["", "", "", "NODOP", "", "", "TIPO DE CARGA"]
HEADER_2 = [
    "SISTEMA", "CENTRO DE CONTROL REGIONAL", "ZONA DE CARGA", "CLAVE", "NOMBRE",
    "NIVEL DE TENSIÓN (kV)", "DIRECTAMENTE MODELADA", "INDIRECTAMENTE MODELADA",
    "DIRECTAMENTE MODELADA", "INDIRECTAMENTE MODELADA", "ZONA DE OPERACIÓN DE TRANSMISIÓN",
    "GERENCIA REGIONAL DE TRANSMISIÓN", "ZONA DE DISTRIBUCIÓN", "GERENCIA DIVISIONAL DE DISTRIBUCIÓN",
    "CLAVE DE ENTIDAD FEDERATIVA (INEGI)", "ENTIDAD FEDERATIVA (INEGI)", "CLAVE DE MUNICIPIO (INEGI)",
    "MUNICIPIO (INEGI)", "REGION DE TRANSMISION",
]  # fmt: skip


def node_row(system, ccr, zone, key, name, kv, state, municipality):
    row = [""] * 19
    row[0], row[1], row[2], row[3], row[4], row[5] = system, ccr, zone, key, name, kv
    row[15], row[17] = state, municipality
    return row


ROWS = [
    node_row("SIN", "ORIENTAL", "OAXACA", "01AAA-115", "Uno", "115", "OAXACA", "OAXACA"),
    node_row("SIN", "ORIENTAL", "OAXACA", "01AAB-115", "Dos", "115", "OAXACA", "TUXTEPEC"),
    node_row("SIN", "ORIENTAL", "PUEBLA", "01AAC-230", "Tres", "230", "PUEBLA", "PUEBLA"),
    node_row("SIN", "CENTRAL", "CENTRO ORIENTE", "01AAD-115", "Cuatro", "115", "MEXICO", "TEXCOCO"),
    node_row("SIN", "CENTRAL", "CENTRO SUR", "01AAE-115", "Cinco", "115", "MORELOS", "CUERNAVACA"),
    node_row("SIN", "CENTRAL", "No Aplica", "01AAF-400", "Seis", "400", "MEXICO", "TULA"),
    node_row(
        "BCA", "BAJA CALIFORNIA", "MEXICALI", "07AAG-161", "Siete", "161", "BAJA CALIFORNIA", "MEXICALI"
    ),
]


def write_xlsx(path: Path, rows: list[list[str]]) -> Path:
    def cell(ref: str, value: str) -> str:
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    def col(i: int) -> str:
        return chr(65 + i) if i < 26 else "A" + chr(65 + i - 26)

    sheet_rows = []
    for r, values in enumerate(rows, start=1):
        cells = "".join(cell(f"{col(i)}{r}", v) for i, v in enumerate(values) if v)
        sheet_rows.append(f'<row r="{r}">{cells}</row>')
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


@pytest.fixture()
def catalog_file(tmp_path: Path) -> Path:
    return write_xlsx(tmp_path / "catalogo.xlsx", [HEADER_1, HEADER_2, *ROWS])


def test_parse_nodos_y_zonas(catalog_file: Path) -> None:
    cat = parse_catalog(catalog_file, version="prueba")
    assert len(cat.nodes) == 7
    keys = {(z.system, z.key) for z in cat.zones}
    assert keys == {
        ("SIN", "OAXACA"),
        ("SIN", "PUEBLA"),
        ("SIN", "CENTRO-ORIENTE"),
        ("SIN", "CENTRO-SUR"),
        ("BCA", "MEXICALI"),
    }
    oaxaca = next(z for z in cat.zones if z.key == "OAXACA")
    assert (oaxaca.ccr, oaxaca.nodes, oaxaca.states) == ("ORIENTAL", 2, {"OAXACA"})
    sin_zona = next(n for n in cat.nodes if n.key == "01AAF-400")
    assert sin_zona.zone is None


def test_formato_inesperado_falla(tmp_path: Path) -> None:
    bad = write_xlsx(tmp_path / "malo.xlsx", [HEADER_1, ["OTRA", "COSA"], ROWS[0]])
    with pytest.raises(ValueError, match="formato esperado"):
        parse_catalog(bad)


def test_estratificacion_por_ccr(catalog_file: Path) -> None:
    cat = parse_catalog(catalog_file)
    chosen = cat.stratified_zones(per_ccr=1)
    assert {z.ccr for z in chosen} == {"ORIENTAL", "CENTRAL"}
    assert len(chosen) == 2
    assert len(cat.stratified_zones(per_ccr=5)) == 4


def test_carga_entidades_y_cohortes(admin_dsn: str, migrated: str, catalog_file: Path) -> None:
    cat = parse_catalog(catalog_file, version="prueba")
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ingest")) as conn:
        assert load_catalog(conn, cat) == {"zones": 5, "nodes": 7}
        load_catalog(conn, cat)  # idempotente
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as admin:
        zona = admin.execute(
            "SELECT name, attrs->>'ccr', attrs->>'catalog_version' FROM core.entity "
            "WHERE source = 'cenace_pend' AND source_key = 'SIN:CENTRO-ORIENTE'"
        ).fetchone()
        assert zona == ("CENTRO ORIENTE", "CENTRAL", "prueba")
        assert (
            admin.execute("SELECT count(*) FROM core.entity WHERE source LIKE 'cenace%%'").fetchone()[0] == 12
        )
        cohortes = admin.execute(
            "SELECT c.kind, c.name FROM core.entity_cohort ec JOIN core.cohort c ON c.id = ec.cohort_id "
            "JOIN core.entity e ON e.id = ec.entity_id WHERE e.source_key = 'SIN:OAXACA' ORDER BY 1"
        ).fetchall()
        assert cohortes == [("ccr", "ORIENTAL"), ("system", "SIN")]
