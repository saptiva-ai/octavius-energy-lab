"""Runner de migraciones: orden, idempotencia y detección de cambios."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from conftest import MIGRATIONS_DIR, ROLE_PASSWORDS, dsn_for
from energy_lab_db.migrate import (
    MigrationChecksumError,
    MigrationNameError,
    discover,
    migrate,
)


def test_discover_ordena_por_version_y_rechaza_nombres_invalidos(tmp_path: Path) -> None:
    (tmp_path / "0002_b.sql").write_text("SELECT 2;")
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    found = discover(tmp_path)
    assert [m.version for m in found] == [1, 2]
    assert [m.name for m in found] == ["a", "b"]

    (tmp_path / "3_sin_ceros.sql").write_text("SELECT 3;")
    with pytest.raises(MigrationNameError):
        discover(tmp_path)


def test_discover_rechaza_versiones_duplicadas(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationNameError):
        discover(tmp_path)


def test_migraciones_quedan_registradas(admin_dsn: str, migrated: str) -> None:
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        rows = conn.execute(
            "SELECT version, name, sha256 FROM public.schema_migrations ORDER BY version"
        ).fetchall()
    expected = discover(MIGRATIONS_DIR)
    assert [(r[0], r[1], r[2]) for r in rows] == [(m.version, m.name, m.sha256) for m in expected]


def test_segunda_corrida_no_aplica_nada(admin_dsn: str, migrated: str) -> None:
    applied = migrate(admin_dsn, migrated, MIGRATIONS_DIR, role_passwords=ROLE_PASSWORDS)
    assert applied == []


def test_migracion_aplicada_y_modificada_falla(admin_dsn: str, migrated: str, tmp_path: Path) -> None:
    copia = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copia)
    primera = sorted(copia.glob("*.sql"))[0]
    primera.write_text(primera.read_text() + "\n-- cambio posterior\n")
    with pytest.raises(MigrationChecksumError):
        migrate(admin_dsn, migrated, copia)


def test_migracion_que_falla_no_queda_a_medias(admin_dsn: str, migrated: str, tmp_path: Path) -> None:
    copia = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copia)
    (copia / "9999_rota.sql").write_text(
        "CREATE TABLE lab.tabla_huerfana (id int);\nSELECT * FROM tabla_que_no_existe;\n"
    )
    with pytest.raises(psycopg.errors.UndefinedTable):
        migrate(admin_dsn, migrated, copia)
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        assert conn.execute("SELECT to_regclass('lab.tabla_huerfana')").fetchone()[0] is None
        assert (
            conn.execute("SELECT count(*) FROM public.schema_migrations WHERE version = 9999").fetchone()[0]
            == 0
        )
