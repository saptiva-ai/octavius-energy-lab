"""Benchmark E1 sobre una base pequeña cargada con el fixture smoke de UCI."""

from __future__ import annotations

import psycopg
import pytest

from conftest import dsn_for
from energy_lab_bench.e1 import QUERIES, explain_partitions, run_benchmark, table_sizes
from energy_lab_ingest.loader import Loader
from energy_lab_ingest.profiles import FIXTURES
from energy_lab_ingest.sources.uci import UciSource


@pytest.fixture(scope="module")
def loaded(admin_dsn: str, migrated: str) -> str:
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ingest")) as conn:
        source = UciSource(FIXTURES / "uci_smoke.txt")
        Loader(conn, source.dataset_info(version="bench"), profile="smoke").load(source)
    return migrated


def test_consultas_tienen_nombre_y_descripcion() -> None:
    names = [q.name for q in QUERIES]
    assert len(names) == len(set(names))
    assert all(q.description and q.sql for q in QUERIES)
    assert any(q.antipattern for q in QUERIES)


def test_explain_detecta_poda(admin_dsn: str, loaded: str) -> None:
    with psycopg.connect(dsn_for(admin_dsn, loaded, "lab_agent")) as conn:
        params = {"series_id": None, "start": "2011-10-29", "end": "2011-10-30"}
        params["series_id"] = conn.execute("SELECT min(id) FROM core.series").fetchone()[0]
        podada = explain_partitions(
            conn,
            "SELECT avg(value) FROM core.observation "
            "WHERE series_id = %(series_id)s AND ts >= %(start)s AND ts < %(end)s",
            params,
        )
        sin_poda = explain_partitions(
            conn,
            "SELECT avg(value) FROM core.observation "
            "WHERE series_id = %(series_id)s AND date_trunc('day', ts) >= %(start)s "
            "AND date_trunc('day', ts) < %(end)s",
            params,
        )
    assert podada == ["observation_2011_10"]
    assert len(sin_poda) > len(podada)


def test_reporte_completo(admin_dsn: str, loaded: str) -> None:
    report = run_benchmark(
        agent_dsn=dsn_for(admin_dsn, loaded, "lab_agent"),
        admin_dsn=dsn_for(admin_dsn, loaded),
        repetitions=3,
        source="uci_eld",
    )
    assert report["rows"]["core.observation"] > 0
    assert report["partitions"]["count"] >= 3
    assert report["sizes"]["core.observation"]["total_bytes"] > 0
    assert report["ingest"][0]["rows_loaded"] > 0
    by_name = {q["name"]: q for q in report["queries"]}
    assert set(by_name) == {q.name for q in QUERIES}
    for q in report["queries"]:
        assert q["p50_ms"] <= q["p95_ms"]
        assert q["repetitions"] == 3
        assert q["partitions_scanned"] >= 1
    anti = next(q for q in report["queries"] if q["antipattern"])
    buena = by_name[anti["compare_with"]]
    assert anti["partitions_scanned"] > buena["partitions_scanned"]


def test_table_sizes(admin_dsn: str, loaded: str) -> None:
    with psycopg.connect(dsn_for(admin_dsn, loaded)) as conn:
        sizes = table_sizes(conn)
    obs = sizes["core.observation"]
    assert obs["total_bytes"] == obs["table_bytes"] + obs["index_bytes"]
