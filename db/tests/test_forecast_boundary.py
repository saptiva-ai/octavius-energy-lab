"""Frontera temporal en la base: un pronóstico no puede caer en o antes del corte."""

from __future__ import annotations

import psycopg
import pytest

from conftest import dsn_for


@pytest.fixture()
def run_id(admin_dsn: str, migrated: str):
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        serie = conn.execute(
            "INSERT INTO core.series (source, source_key, kind, unit, freq) "
            "VALUES ('prueba', 'frontera', 'demand', 'MW', '1h') RETURNING id"
        ).fetchone()[0]
        run = conn.execute(
            "INSERT INTO forecast.forecast_run (series_id, cutoff, horizon, freq, model, model_version) "
            "VALUES (%s, '2013-06-01T00:00Z', '24 hours', '1 hour', 'seasonal_naive', '0') RETURNING id",
            (serie,),
        ).fetchone()[0]
        yield conn, run
        conn.rollback()


def test_punto_despues_del_corte_se_acepta(run_id) -> None:
    conn, run = run_id
    conn.execute(
        "INSERT INTO forecast.forecast_point (run_id, ts, point) VALUES (%s, '2013-06-01T01:00Z', 1)",
        (run,),
    )


@pytest.mark.parametrize("ts", ["2013-06-01T00:00Z", "2013-05-31T23:00Z", "2013-06-02T01:00Z"])
def test_punto_fuera_de_la_ventana_se_rechaza(run_id, ts: str) -> None:
    conn, run = run_id
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO forecast.forecast_point (run_id, ts, point) VALUES (%s, %s, 1)", (run, ts))
