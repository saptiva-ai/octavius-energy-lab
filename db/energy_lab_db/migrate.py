"""Runner de migraciones SQL numeradas para la base energy_lab.

Reglas:
- Los archivos se llaman NNNN_nombre.sql y se aplican en orden de versión.
- Cada migración corre en su propia transacción: si falla, no deja nada.
- Una migración aplicada no se edita. Si su sha256 cambia, el runner se
  detiene; los cambios van en una migración nueva.
- Las contraseñas de los roles llegan por parámetro (desde variables de
  entorno en la CLI) y nunca se escriben en los archivos SQL.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

FILENAME_RE = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
LOGIN_ROLES = ("lab_ingest", "lab_agent", "lab_forecast", "lab_eval")
# Clave fija para pg_advisory_xact_lock: evita dos runners a la vez.
ADVISORY_LOCK_KEY = 7_202_611


class MigrationNameError(ValueError):
    """Nombre de archivo inválido o versión repetida."""


class MigrationChecksumError(RuntimeError):
    """Una migración ya aplicada cambió en disco."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    sha256: str

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover(directory: Path) -> list[Migration]:
    migrations: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = FILENAME_RE.match(path.name)
        if match is None:
            raise MigrationNameError(f"Nombre inválido: {path.name} (se espera NNNN_nombre.sql)")
        version = int(match["version"])
        if version in migrations:
            raise MigrationNameError(f"Versión repetida: {version:04d}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        migrations[version] = Migration(version, match["name"], path, digest)
    return [migrations[v] for v in sorted(migrations)]


def _with_database(dsn: str, database: str) -> str:
    params = conninfo_to_dict(dsn)
    params["dbname"] = database
    return make_conninfo(**params)


def ensure_database(admin_dsn: str, database: str) -> bool:
    """Crea la base si no existe. Devuelve True si la creó."""
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        return True


def _ensure_ledger(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            version    integer PRIMARY KEY,
            name       text        NOT NULL,
            sha256     char(64)    NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("REVOKE ALL ON public.schema_migrations FROM PUBLIC")


def _set_passwords(conn: psycopg.Connection, role_passwords: Mapping[str, str]) -> None:
    for role, password in role_passwords.items():
        if role not in LOGIN_ROLES:
            raise ValueError(f"Rol desconocido: {role}")
        if not password:
            continue
        conn.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )


def migrate(
    admin_dsn: str,
    database: str,
    migrations_dir: Path,
    role_passwords: Mapping[str, str] | None = None,
) -> list[Migration]:
    """Aplica las migraciones pendientes. Devuelve las que aplicó."""
    migrations = discover(migrations_dir)
    ensure_database(admin_dsn, database)
    applied_now: list[Migration] = []

    with psycopg.connect(_with_database(admin_dsn, database)) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            _ensure_ledger(conn)
            applied = {
                row[0]: row[1].strip()
                for row in conn.execute("SELECT version, sha256 FROM public.schema_migrations")
            }
        for migration in migrations:
            previous = applied.get(migration.version)
            if previous is not None:
                if previous != migration.sha256:
                    raise MigrationChecksumError(
                        f"La migración {migration.version:04d}_{migration.name} cambió después de "
                        "aplicarse; crea una migración nueva en lugar de editarla."
                    )
                continue
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
                conn.execute(migration.sql)
                conn.execute(
                    "INSERT INTO public.schema_migrations (version, name, sha256) VALUES (%s, %s, %s)",
                    (migration.version, migration.name, migration.sha256),
                )
            applied_now.append(migration)
        if role_passwords:
            with conn.transaction():
                _set_passwords(conn, role_passwords)
    return applied_now
