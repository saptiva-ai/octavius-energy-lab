"""Fixtures contra PostgreSQL real (ver db/tests/conftest.py).

Sin ENERGY_LAB_TEST_ADMIN_DSN, las pruebas que necesitan base se saltan.
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
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
ROLE_PASSWORDS = {
    role: secrets.token_urlsafe(16) for role in ("lab_ingest", "lab_agent", "lab_forecast", "lab_eval")
}


def _refuse_shared_cluster(dsn: str) -> None:
    """Las pruebas fijan contraseñas aleatorias a los roles lab_*, que son
    globales al clúster. Si el clúster ya tiene la base energy_lab, es de
    desarrollo y sus credenciales se romperían."""
    if os.environ.get("ENERGY_LAB_TEST_ALLOW_SHARED") == "1":
        return
    with psycopg.connect(dsn, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = 'energy_lab'").fetchone():
            pytest.exit(
                "El clúster de ENERGY_LAB_TEST_ADMIN_DSN tiene la base energy_lab: usa un PostgreSQL "
                "solo para pruebas (las pruebas cambian las contraseñas de los roles lab_*). "
                "ENERGY_LAB_TEST_ALLOW_SHARED=1 lo permite bajo tu responsabilidad.",
                returncode=2,
            )


@pytest.fixture(scope="session")
def admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        pytest.skip(f"{ADMIN_DSN_ENV} no está definida")
    _refuse_shared_cluster(dsn)
    return dsn


@pytest.fixture(scope="session")
def migrated(admin_dsn: str) -> Iterator[str]:
    from energy_lab_db.migrate import migrate

    name = f"energy_lab_bench_test_{secrets.token_hex(4)}"
    migrate(admin_dsn, name, MIGRATIONS_DIR, role_passwords=ROLE_PASSWORDS)
    yield name
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def dsn_for(admin_dsn: str, database: str, role: str | None = None) -> str:
    params = conninfo_to_dict(admin_dsn)
    params["dbname"] = database
    if role is not None:
        params["user"] = role
        params["password"] = ROLE_PASSWORDS[role]
    return make_conninfo(**params)
