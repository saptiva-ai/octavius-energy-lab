"""Roles: el agente solo lee y con límite de tiempo; cada rol escribe donde le toca."""

from __future__ import annotations

import psycopg
import pytest

from conftest import dsn_for


def connect(admin_dsn: str, database: str, role: str) -> psycopg.Connection:
    return psycopg.connect(dsn_for(admin_dsn, database, role))


def test_agente_puede_leer_core(admin_dsn: str, migrated: str) -> None:
    with connect(admin_dsn, migrated, "lab_agent") as conn:
        assert conn.execute("SELECT count(*) FROM core.observation").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM core.series").fetchone()[0] == 0


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO core.series (source, source_key, kind, unit, freq) VALUES ('x','x','x','x','1h')",
        "DELETE FROM core.observation",
        "CREATE TABLE core.intrusa (id int)",
        "CREATE TABLE public.intrusa (id int)",
        "INSERT INTO lab.experiment (id, name) VALUES ('e1', 'x')",
    ],
)
def test_agente_no_puede_escribir(admin_dsn: str, migrated: str, statement: str) -> None:
    with (
        connect(admin_dsn, migrated, "lab_agent") as conn,
        pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)),
    ):
        conn.execute(statement)


def test_agente_no_lee_raw_ni_lab(admin_dsn: str, migrated: str) -> None:
    with (
        connect(admin_dsn, migrated, "lab_agent") as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("SELECT * FROM lab.run")


def test_agente_tiene_limites_de_sesion(admin_dsn: str, migrated: str) -> None:
    with connect(admin_dsn, migrated, "lab_agent") as conn:
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == "5s"
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"


def test_statement_timeout_corta_consultas_largas(admin_dsn: str, migrated: str) -> None:
    with connect(admin_dsn, migrated, "lab_agent") as conn, pytest.raises(psycopg.errors.QueryCanceled):
        conn.execute("SELECT pg_sleep(6)")


def test_ingesta_escribe_en_core_pero_no_en_lab(admin_dsn: str, migrated: str) -> None:
    with connect(admin_dsn, migrated, "lab_ingest") as conn:
        conn.execute(
            "INSERT INTO core.series (source, source_key, kind, unit, freq) "
            "VALUES ('prueba', 'serie-ingesta', 'demand', 'MW', '1h')"
        )
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO lab.experiment (id, name) VALUES ('e1', 'x')")


def test_forecast_escribe_pronosticos_y_no_observaciones(admin_dsn: str, migrated: str) -> None:
    with (
        connect(admin_dsn, migrated, "lab_forecast") as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("DELETE FROM core.observation")


def test_eval_escribe_en_lab(admin_dsn: str, migrated: str) -> None:
    with connect(admin_dsn, migrated, "lab_eval") as conn:
        conn.execute("INSERT INTO lab.experiment (id, name) VALUES ('exp-prueba', 'prueba')")
        conn.rollback()
