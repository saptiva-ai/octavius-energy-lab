"""CLI: energy-lab-db migrate | status.

Variables de entorno:
  ENERGY_LAB_ADMIN_DSN   conexión de un rol con permisos de DDL y CREATEROLE
  ENERGY_LAB_DB          nombre de la base (por defecto energy_lab)
  LAB_INGEST_PASSWORD, LAB_AGENT_PASSWORD, LAB_FORECAST_PASSWORD, LAB_EVAL_PASSWORD
                         contraseñas de los roles con login; si falta una, no se
                         cambia la de ese rol (un rol nuevo sin contraseña no
                         puede iniciar sesión)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

from .migrate import LOGIN_ROLES, _with_database, discover, migrate

DEFAULT_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Falta la variable de entorno {name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="energy-lab-db")
    parser.add_argument("command", choices=["migrate", "status"])
    parser.add_argument("--migrations", type=Path, default=DEFAULT_MIGRATIONS)
    args = parser.parse_args(argv)

    admin_dsn = _env("ENERGY_LAB_ADMIN_DSN")
    database = os.environ.get("ENERGY_LAB_DB", "energy_lab")

    if args.command == "migrate":
        passwords = {role: os.environ.get(f"{role.upper()}_PASSWORD", "") for role in LOGIN_ROLES}
        applied = migrate(admin_dsn, database, args.migrations, role_passwords=passwords)
        for m in applied:
            print(f"aplicada {m.version:04d}_{m.name}")
        sin_password = [r for r, p in passwords.items() if not p]
        print(f"{len(applied)} migraciones nuevas en {database}")
        if sin_password:
            # Los roles son globales al clúster: pueden conservar una contraseña previa.
            print("sin variable de contraseña, no se cambió la contraseña de: " + ", ".join(sin_password))
        return 0

    disponibles = discover(args.migrations)
    try:
        with psycopg.connect(_with_database(admin_dsn, database)) as conn:
            aplicadas = {r[0] for r in conn.execute("SELECT version FROM public.schema_migrations")}
    except psycopg.Error as exc:
        print(f"No se pudo leer el estado: {exc}")
        return 1
    for m in disponibles:
        marca = "aplicada " if m.version in aplicadas else "pendiente"
        print(f"{marca} {m.version:04d}_{m.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
