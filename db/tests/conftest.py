"""Fixtures contra un PostgreSQL real.

Las pruebas necesitan ENERGY_LAB_TEST_ADMIN_DSN, una conexión con un
superusuario a la base de mantenimiento, por ejemplo
postgresql://postgres:postgres@127.0.0.1:55432/postgres. Sin ella se saltan.

Cada sesión crea una base nueva con nombre aleatorio y la borra al final. Los
roles son globales al clúster, por eso las migraciones deben ser idempotentes
respecto a ellos.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ADMIN_DSN_ENV = "ENERGY_LAB_TEST_ADMIN_DSN"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

# Contraseñas solo de prueba: se generan por sesión y nunca salen del proceso.
ROLE_PASSWORDS = {
    role: secrets.token_urlsafe(16) for role in ("lab_ingest", "lab_agent", "lab_forecast", "lab_eval")
}


@pytest.fixture(scope="session")
def admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        pytest.skip(f"{ADMIN_DSN_ENV} no está definida")
    return dsn


@pytest.fixture(scope="session")
def database(admin_dsn: str) -> Iterator[str]:
    name = f"energy_lab_test_{secrets.token_hex(4)}"
    yield name
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="session")
def migrated(admin_dsn: str, database: str) -> str:
    """Aplica las migraciones una vez por sesión y devuelve el nombre de la base."""
    from energy_lab_db.migrate import migrate

    migrate(admin_dsn, database, MIGRATIONS_DIR, role_passwords=ROLE_PASSWORDS)
    return database


def dsn_for(admin_dsn: str, database: str, role: str | None = None) -> str:
    params = conninfo_to_dict(admin_dsn)
    params["dbname"] = database
    if role is not None:
        params["user"] = role
        params["password"] = ROLE_PASSWORDS[role]
    return make_conninfo(**params)
