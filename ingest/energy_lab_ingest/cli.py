"""energy-lab-ingest: carga fuentes a energy_lab por perfil.

  energy-lab-ingest uci --profile smoke
  energy-lab-ingest uci --profile demo --clients 20 --start 2013-01-01 --end 2015-01-01
  energy-lab-ingest uci --profile full            # muestra la estimación y se detiene
  energy-lab-ingest uci --profile full --yes      # carga completa

Conexión: LAB_INGEST_DSN (rol lab_ingest).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

import psycopg

from .download import data_dir, extract_member, fetch
from .loader import Loader
from .profiles import FIXTURES, estimate, spread
from .sources import uci

EXIT_NEEDS_APPROVAL = 2


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _uci_file(profile: str) -> tuple[object, str]:
    if profile == "smoke":
        return FIXTURES / "uci_smoke.txt", "smoke-fixture"
    cache = data_dir() / "uci"
    archive = fetch(uci.URL, cache / "eld.zip", expected_sha256=uci.ZIP_SHA256)
    return extract_member(archive, uci.FILENAME, cache / "extracted"), f"zip-{uci.ZIP_SHA256[:12]}"


def run_uci(args: argparse.Namespace) -> int:
    if args.profile == "full" and not args.yes:
        months = 48
        print("Perfil full: UCI completo (370 clientes, 2011-2014).")
        print(estimate(uci.UciSource.estimate_full_rows(), months).describe())
        print("Descarga: ~261 MB (zip) + ~711 MB (texto) en " + str(data_dir() / "uci"))
        print("Vuelve a correr con --yes para cargar.")
        return EXIT_NEEDS_APPROVAL

    path, version = _uci_file(args.profile)
    clients = None
    if args.profile == "demo":
        header = uci.UciSource(path).clients
        clients = args.client or spread(header, args.clients)
    elif args.client:
        clients = args.client
    source = uci.UciSource(
        path,
        clients=clients,
        start=_date(args.start) if args.start else None,
        end=_date(args.end) if args.end else None,
    )

    dsn = os.environ.get("LAB_INGEST_DSN")
    if not dsn:
        sys.exit("Falta LAB_INGEST_DSN (conexión con el rol lab_ingest)")
    with psycopg.connect(dsn) as conn:
        report = Loader(conn, source.dataset_info(version=version), profile=args.profile).load(source)

    summary = {
        "source": "uci_eld",
        "profile": args.profile,
        "clients": len(source.clients),
        "units_loaded": report.units_loaded,
        "units_skipped": report.units_skipped,
        "rows_read": report.rows_read,
        "rows_loaded": report.rows_loaded,
        "seconds": round(report.seconds, 2),
        "rows_per_second": round(report.rows_per_second),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="energy-lab-ingest")
    sub = parser.add_subparsers(dest="source", required=True)
    p = sub.add_parser("uci", help="UCI ElectricityLoadDiagrams20112014 (CC BY 4.0)")
    p.add_argument("--profile", choices=["smoke", "demo", "full"], required=True)
    p.add_argument("--clients", type=int, default=20, help="demo: clientes repartidos uniformemente")
    p.add_argument("--client", action="append", help="cliente explícito (repetible), p. ej. MT_124")
    p.add_argument("--start", help="YYYY-MM-DD, inclusive (UTC)")
    p.add_argument("--end", help="YYYY-MM-DD, exclusivo (UTC)")
    p.add_argument("--yes", action="store_true", help="aprueba el perfil full")
    p.set_defaults(func=run_uci)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
