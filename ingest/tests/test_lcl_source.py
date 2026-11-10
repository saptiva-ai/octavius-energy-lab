"""Low Carbon London (London Datastore, CC BY 4.0)."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from conftest import dsn_for
from energy_lab_ingest.loader import Loader
from energy_lab_ingest.sources.lcl import LclSource, TariffSource, excel_serial_to_utc, pick_files

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "lcl_smoke.csv"


def collect(source):
    return [(u.key, list(u.records), u.quality) for u in source.iter_units()]


def test_un_archivo_es_una_unidad_y_marcas_en_utc() -> None:
    units = collect(LclSource([FIXTURE]))
    assert [u[0] for u in units] == ["lcl_smoke"]
    records = units[0][1]
    assert ("MAC000002", datetime(2013, 3, 30, 0, 0, tzinfo=UTC), 0.102) in records


def test_calidad_null_y_fuera_de_malla() -> None:
    _, records, quality = collect(LclSource([FIXTURE]))[0]
    assert quality["rows_read"] == 484
    # La fila 12:37:27 con Null está fuera de la malla de media hora: se descarta.
    assert quality["off_grid_timestamps"] >= 1
    assert all(r[1].minute in (0, 30) and r[1].second == 0 for r in records)
    assert quality["null_values"] == quality["null_values"]  # se cuenta aunque sea 0


def test_spec_con_cohorte_de_tarifa() -> None:
    source = LclSource([FIXTURE])
    collect(source)
    std = source.spec_for("MAC000002")
    tou = source.spec_for("MAC002534")
    assert (std.kind, std.unit, std.freq, std.entity_kind) == (
        "consumption",
        "kWh",
        "30 minutes",
        "household",
    )
    assert std.cohorts == (("tariff", "Std"),)
    assert tou.cohorts == (("tariff", "ToU"),)


def test_lee_desde_zip_sin_extraer(tmp_path: Path) -> None:
    archive = tmp_path / "lcl.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURE, "Small LCL Data/LCL-June2015v2_7.csv")
    units = collect(LclSource.from_zip(archive, ["Small LCL Data/LCL-June2015v2_7.csv"]))
    assert [u[0] for u in units] == ["LCL-June2015v2_7"]
    assert len(units[0][1]) > 400


def test_pick_files_estratifica_por_tarifa() -> None:
    """Repartir por índice dejó 0 hogares ToU en el demo (los ToU están al final)."""
    names = [f"Small LCL Data/LCL-June2015v2_{i}.csv" for i in range(168)]
    tariffs = {n: ("ToU" if i >= 135 else "Std") for i, n in enumerate(names)}
    chosen = pick_files(names, 4, tariff_of=tariffs.get)
    assert {tariffs[n] for n in chosen} == {"Std", "ToU"}
    assert sum(tariffs[n] == "ToU" for n in chosen) == 1
    assert len(chosen) == 4
    # Sin información de tarifa, reparte por índice.
    assert [int(n.rsplit("_", 1)[1][:-4]) for n in pick_files(names, 4)] == [0, 42, 84, 126]


def test_first_tariff_lee_solo_el_inicio(tmp_path: Path) -> None:
    from energy_lab_ingest.sources.lcl import first_tariff

    archive = tmp_path / "lcl.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURE, "a.csv")
    with zipfile.ZipFile(archive) as zf:
        assert first_tariff(zf, "a.csv") == "Std"


def test_excel_serial() -> None:
    assert excel_serial_to_utc("41275") == datetime(2013, 1, 1, 0, 0, tzinfo=UTC)
    assert excel_serial_to_utc("41275.020833333336") == datetime(2013, 1, 1, 0, 30, tzinfo=UTC)


def test_tarifa_como_serie(tmp_path: Path) -> None:
    rows = [("TariffDateTime", "Tariff"), ("41275", "Normal"), ("41275.020833333336", "High")]
    path = _tariff_xlsx(tmp_path, rows)
    units = collect(TariffSource(path))
    records = units[0][1]
    assert records == [
        ("dToU-2013", datetime(2013, 1, 1, 0, 0, tzinfo=UTC), 11.76),
        ("dToU-2013", datetime(2013, 1, 1, 0, 30, tzinfo=UTC), 67.20),
    ]


def _tariff_xlsx(tmp_path: Path, rows) -> Path:
    cells = "".join(
        f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{a}</t></is></c>'
        f'<c r="B{i}" t="inlineStr"><is><t>{b}</t></is></c></row>'
        for i, (a, b) in enumerate(rows, start=1)
    )
    path = tmp_path / "Tariffs.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{cells}</sheetData></worksheet>",
        )
    return path


@pytest.fixture()
def conns(admin_dsn: str, migrated: str):
    with (
        psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ingest")) as ingest,
        psycopg.connect(dsn_for(admin_dsn, migrated), autocommit=True) as admin,
    ):
        admin.execute(
            "TRUNCATE core.observation, core.ingest_batch, core.entity_cohort, core.cohort, "
            "core.series, core.entity, core.dataset_version CASCADE"
        )
        yield ingest, admin


def test_carga_lcl_deduplica_y_asigna_cohortes(conns) -> None:
    ingest, admin = conns
    source = LclSource([FIXTURE])
    report = Loader(ingest, source.dataset_info(version="test"), profile="smoke").load(source)
    assert report.units_loaded == 1
    q = admin.execute("SELECT quality FROM core.ingest_batch").fetchone()[0]
    assert q["duplicates_dropped"] == 1
    assert q["duplicates_conflicting"] == 0
    total = admin.execute("SELECT count(*) FROM core.observation").fetchone()[0]
    assert total == report.rows_loaded == q["rows_read"] - q["off_grid_timestamps"] - 1
    cohortes = dict(
        admin.execute(
            "SELECT e.source_key, c.name FROM core.entity e "
            "JOIN core.entity_cohort ec ON ec.entity_id = e.id JOIN core.cohort c ON c.id = ec.cohort_id "
            "WHERE c.kind = 'tariff'"
        ).fetchall()
    )
    assert cohortes == {"MAC000002": "Std", "MAC000003": "Std", "MAC002534": "ToU"}
    # Segunda corrida: idempotente.
    again = Loader(ingest, source.dataset_info(version="test"), profile="smoke").load(LclSource([FIXTURE]))
    assert again.units_skipped == 1
