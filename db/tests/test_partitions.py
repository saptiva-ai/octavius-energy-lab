"""Particionamiento mensual de core.observation y poda en consultas por rango."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from conftest import dsn_for


@pytest.fixture()
def admin(admin_dsn: str, migrated: str):
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        yield conn
        conn.rollback()


def test_observation_esta_particionada_por_rango(admin) -> None:
    strategy = admin.execute(
        "SELECT partstrat FROM pg_partitioned_table WHERE partrelid = 'core.observation'::regclass"
    ).fetchone()[0]
    assert strategy == "r"


def test_ensure_partitions_crea_meses_y_es_idempotente(admin) -> None:
    creadas = admin.execute(
        "SELECT core.ensure_observation_partitions('2013-01-15', '2013-03-02')"
    ).fetchone()[0]
    assert creadas == 3
    otra_vez = admin.execute(
        "SELECT core.ensure_observation_partitions('2013-01-01', '2013-03-31')"
    ).fetchone()[0]
    assert otra_vez == 0
    nombres = {
        r[0]
        for r in admin.execute(
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = 'core.observation'::regclass"
        )
    }
    assert {"observation_2013_01", "observation_2013_02", "observation_2013_03"} <= nombres
    assert "observation_default" in nombres


def test_poda_de_particiones(admin) -> None:
    admin.execute("SELECT core.ensure_observation_partitions('2013-01-01', '2013-03-31')")
    serie = admin.execute(
        "INSERT INTO core.series (source, source_key, kind, unit, freq) "
        "VALUES ('prueba', 'poda', 'demand', 'MW', '1h') RETURNING id"
    ).fetchone()[0]
    admin.execute(
        "INSERT INTO core.observation (series_id, ts, value) "
        "SELECT %s, t, 1.0 FROM generate_series("
        "'2013-01-01'::timestamptz, '2013-03-31'::timestamptz, '1 hour') t",
        (serie,),
    )
    plan = "\n".join(
        r[0]
        for r in admin.execute(
            "EXPLAIN SELECT sum(value) FROM core.observation WHERE series_id = %s AND ts >= %s AND ts < %s",
            (
                serie,
                datetime(2013, 2, 1, tzinfo=UTC),
                datetime(2013, 2, 15, tzinfo=UTC),
            ),
        )
    )
    assert "observation_2013_02" in plan
    assert "observation_2013_01" not in plan
    assert "observation_2013_03" not in plan


def test_observacion_duplicada_se_rechaza(admin) -> None:
    serie = admin.execute(
        "INSERT INTO core.series (source, source_key, kind, unit, freq) "
        "VALUES ('prueba', 'duplicado', 'demand', 'MW', '1h') RETURNING id"
    ).fetchone()[0]
    admin.execute(
        "INSERT INTO core.observation (series_id, ts, value) VALUES (%s, '2013-01-01T00:00Z', 1)",
        (serie,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin.execute(
            "INSERT INTO core.observation (series_id, ts, value) VALUES (%s, '2013-01-01T00:00Z', 2)",
            (serie,),
        )
