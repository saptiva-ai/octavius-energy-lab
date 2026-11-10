"""Carga en energy_lab: idempotencia, reanudación, conteos y calidad."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from conftest import dsn_for
from energy_lab_ingest.loader import Loader
from energy_lab_ingest.sources.uci import UciSource

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "uci_smoke.txt"


@pytest.fixture()
def ingest_conn(admin_dsn: str, migrated: str):
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ingest")) as conn:
        yield conn


@pytest.fixture()
def admin_conn(admin_dsn: str, migrated: str):
    with psycopg.connect(dsn_for(admin_dsn, migrated), autocommit=True) as conn:
        yield conn


def reset(admin_conn) -> None:
    admin_conn.execute(
        "TRUNCATE core.observation, core.ingest_batch, core.series, core.entity, core.dataset_version CASCADE"
    )


def run_smoke(conn, version: str = "test"):
    source = UciSource(FIXTURE)
    loader = Loader(conn, source.dataset_info(version=version), profile="smoke")
    return loader.load(source)


def test_carga_smoke_cuadra_conteos(ingest_conn, admin_conn) -> None:
    reset(admin_conn)
    report = run_smoke(ingest_conn)
    assert report.units_loaded == 3
    assert report.units_skipped == 0
    total = admin_conn.execute("SELECT count(*) FROM core.observation").fetchone()[0]
    assert total == report.rows_loaded > 0
    # Las filas de default deben quedar en cero: todo cae en particiones mensuales.
    assert admin_conn.execute("SELECT count(*) FROM core.observation_default").fetchone()[0] == 0
    estados = admin_conn.execute("SELECT DISTINCT status FROM core.ingest_batch").fetchall()
    assert estados == [("done",)]


def test_segunda_corrida_no_recarga(ingest_conn, admin_conn) -> None:
    reset(admin_conn)
    run_smoke(ingest_conn)
    antes = admin_conn.execute("SELECT count(*) FROM core.observation").fetchone()[0]
    report = run_smoke(ingest_conn)
    assert report.units_loaded == 0
    assert report.units_skipped == 3
    assert admin_conn.execute("SELECT count(*) FROM core.observation").fetchone()[0] == antes


def test_reanuda_tras_un_lote_fallido(ingest_conn, admin_conn) -> None:
    reset(admin_conn)
    run_smoke(ingest_conn)
    admin_conn.execute("UPDATE core.ingest_batch SET status = 'failed' WHERE unit LIKE '%%2011-10'")
    admin_conn.execute("DELETE FROM core.observation WHERE ts >= '2011-10-01' AND ts < '2011-11-01'")
    report = run_smoke(ingest_conn)
    assert report.units_loaded == 1
    assert report.units_skipped == 2
    octubre = admin_conn.execute(
        "SELECT count(*) FROM core.observation WHERE ts >= '2011-10-01' AND ts < '2011-11-01'"
    ).fetchone()[0]
    assert octubre > 0


def test_calidad_queda_registrada(ingest_conn, admin_conn) -> None:
    reset(admin_conn)
    run_smoke(ingest_conn)
    quality = admin_conn.execute(
        "SELECT quality FROM core.ingest_batch WHERE unit LIKE '%%2011-03'"
    ).fetchone()[0]
    assert quality["nonexistent_local_time"] == 12
    assert quality["rows_read"] > 0


def test_series_y_procedencia(ingest_conn, admin_conn) -> None:
    reset(admin_conn)
    run_smoke(ingest_conn, version="v-prueba")
    dv = admin_conn.execute("SELECT source, version, license FROM core.dataset_version").fetchone()
    assert dv == ("uci_eld", "v-prueba", "CC BY 4.0")
    series = admin_conn.execute(
        "SELECT s.source_key, s.unit, s.freq::text, e.kind FROM core.series s "
        "JOIN core.entity e ON e.id = s.entity_id ORDER BY 1"
    ).fetchall()
    assert [s[0] for s in series] == ["MT_001", "MT_124", "MT_131"]
    assert series[1][1:] == ("kW", "00:15:00", "client")


def test_seleccion_distinta_no_reusa_lotes(ingest_conn, admin_conn) -> None:
    """Un demo con otros clientes no debe saltarse meses que cargó otra selección."""
    reset(admin_conn)
    info = UciSource(FIXTURE).dataset_info(version="test")
    Loader(ingest_conn, info, profile="demo").load(UciSource(FIXTURE, clients=["MT_124"]))
    report = Loader(ingest_conn, info, profile="demo").load(UciSource(FIXTURE, clients=["MT_131"]))
    assert report.units_loaded == 3


def test_cenace_reanudar_no_vuelve_a_llamar_al_servicio(ingest_conn, admin_conn) -> None:
    import json
    from datetime import date

    from energy_lab_ingest.sources.cenace import CenaceClient, CenaceSource

    reset(admin_conn)
    payload = json.loads((FIXTURE.parent / "cenace" / "pend_sin_mda_2zonas_7dias.json").read_text())
    calls: list[str] = []

    def transport(url: str) -> dict:
        calls.append(url)
        return payload

    def source() -> CenaceSource:
        return CenaceSource(
            service="pend",
            system="SIN",
            process="MDA",
            keys=["OAXACA", "PUEBLA"],
            start=date(2024, 1, 1),
            end=date(2024, 1, 7),
            client=CenaceClient(transport=transport, delay_s=0),
        )

    info = source().dataset_info(version="test")
    first = Loader(ingest_conn, info, profile="smoke").load(source())
    assert first.rows_loaded == 2 * 168 * 4
    assert len(calls) == 1
    second = Loader(ingest_conn, info, profile="smoke").load(source())
    assert second.units_skipped == 1
    assert len(calls) == 1
