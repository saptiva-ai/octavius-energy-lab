"""energy-lab-ingest: carga fuentes a energy_lab por perfil.

  energy-lab-ingest uci --profile smoke
  energy-lab-ingest uci --profile demo --clients 20 --start 2013-01-01 --end 2015-01-01
  energy-lab-ingest uci --profile full            # muestra la estimación y se detiene
  energy-lab-ingest uci --profile full --yes      # carga completa
  energy-lab-ingest lcl --profile smoke
  energy-lab-ingest lcl --profile demo --files 4
  energy-lab-ingest lcl --profile full                       # estimación; --yes para cargar
  energy-lab-ingest cenace --profile smoke
  energy-lab-ingest cenace --profile demo --per-ccr 2 --start 2025-01-01 --end 2025-12-31
  energy-lab-ingest cenace --profile full --service pend   # estimación; --yes para cargar

Conexión: LAB_INGEST_DSN (rol lab_ingest).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg

from .download import data_dir, extract_member, fetch
from .etiquetas import describir_calidad
from .loader import Loader
from .profiles import FIXTURES, estimate, spread
from .sources import cenace, cenace_catalog, lcl, uci

EXIT_NEEDS_APPROVAL = 2


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _uci_file(profile: str) -> tuple[object, str]:
    if profile == "smoke":
        return FIXTURES / "uci_smoke.txt", "smoke-fixture"
    cache = data_dir() / "uci"
    archive = fetch(uci.URL, cache / "eld.zip", expected_sha256=uci.ZIP_SHA256)
    return extract_member(archive, uci.FILENAME, cache / "extracted"), f"zip-{uci.ZIP_SHA256[:12]}"


def resumen(fuente: str, perfil: str, report, **extra) -> dict:
    """Resumen de una carga con llaves en español."""
    return {
        "fuente": fuente,
        "perfil": perfil,
        **extra,
        "unidades_cargadas": report.units_loaded,
        "unidades_saltadas": report.units_skipped,
        "filas_leidas": report.rows_read,
        "filas_cargadas": report.rows_loaded,
        "segundos": round(report.seconds, 2),
        "filas_por_segundo": round(report.rows_per_second),
    }


def imprimir(datos: dict, report=None) -> None:
    print(json.dumps(datos, ensure_ascii=False))
    if report is not None and report.units:
        total: Counter = Counter()
        for unidad in report.units:
            total.update({k: v for k, v in unidad.items() if isinstance(v, int) and k != "rows_loaded"})
        lineas = describir_calidad(dict(total))
        if lineas:
            print("Calidad de los datos:")
            for linea in lineas:
                print(f"  - {linea}")


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

    imprimir(resumen("uci_eld", args.profile, report, clientes=len(source.clients)), report)
    return 0


def _connect() -> psycopg.Connection:
    dsn = os.environ.get("LAB_INGEST_DSN")
    if not dsn:
        sys.exit("Falta LAB_INGEST_DSN (conexión con el rol lab_ingest)")
    return psycopg.connect(dsn)


def _fixture_transport(fixture: Path) -> cenace.Transport:
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    def get(url: str) -> dict:
        return payload

    return get


def run_cenace(args: argparse.Namespace) -> int:
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    if args.profile == "smoke":
        fixture = FIXTURES / "cenace" / "pend_sin_mda_2zonas_7dias.json"
        source = cenace.CenaceSource(
            service="pend",
            system="SIN",
            process="MDA",
            keys=["OAXACA", "PUEBLA"],
            start=date(2024, 1, 1),
            end=date(2024, 1, 7),
            client=cenace.CenaceClient(transport=_fixture_transport(fixture), delay_s=0),
        )
        version = "smoke-fixture-sintetico"
        catalog = None
    else:
        cache = data_dir() / "cenace"
        catalog_file = fetch(
            cenace_catalog.CATALOG_URL,
            cache / f"catalogo-nodosp-v{cenace_catalog.CATALOG_VERSION}.xlsx",
            expected_sha256=cenace_catalog.CATALOG_SHA256,
        )
        catalog = cenace_catalog.parse_catalog(catalog_file)
        if args.zone:
            keys = [cenace.zone_key(z) for z in args.zone]
        elif args.service == "pend" and args.profile == "demo":
            keys = [z.key for z in catalog.stratified_zones(args.per_ccr, args.system)]
        elif args.service == "pend":
            keys = [z.key for z in catalog.zones if z.system == args.system]
        elif args.profile == "demo":
            nodes = sorted(n.key for n in catalog.nodes if n.system == args.system)
            keys = spread(nodes, args.nodes)
        else:
            keys = sorted(n.key for n in catalog.nodes if n.system == args.system)
        start = start or (date(2016, 1, 29) if args.profile == "full" else date(2025, 1, 1))
        end = end or (date.today() - timedelta(days=2) if args.profile == "full" else date(2025, 12, 31))
        version = f"api-{date.today():%Y-%m-%d}"

        if args.profile == "full" and not args.yes:
            days = (end - start).days + 1
            windows = -(-days // cenace.MAX_DAYS) * len(cenace.key_chunks(keys))
            rows = len(keys) * days * 24 * len(cenace.COMPONENTS)
            print(f"Perfil full: CENACE {args.service} {args.system} {args.process}, {len(keys)} claves.")
            print(f"Periodo: {start} a {end} ({days} días)")
            print(estimate(rows, -(-days // 30)).describe())
            print(f"llamadas al servicio: {windows:,} (~{windows * 2 / 3600:.1f} h con 1 s de pausa)")
            print("Vuelve a correr con --yes para cargar.")
            return EXIT_NEEDS_APPROVAL

        source = cenace.CenaceSource(
            service=args.service,
            system=args.system,
            process=args.process,
            keys=keys,
            start=start,
            end=end,
            client=cenace.CenaceClient(delay_s=args.delay),
        )

    with _connect() as conn:
        if catalog is not None:
            cenace_catalog.load_catalog(conn, catalog)
        report = Loader(conn, source.dataset_info(version=version), profile=args.profile).load(source)

    imprimir(
        resumen(
            source.name,
            args.profile,
            report,
            sistema=source.system,
            proceso=source.process,
            claves=len(source.keys),
            llamadas=source.client.calls,
        ),
        report,
    )
    return 0


def run_lcl(args: argparse.Namespace) -> int:
    tariff_file = None
    if args.profile == "smoke":
        source = lcl.LclSource([FIXTURES / "lcl_smoke.csv"])
        version = "smoke-fixture"
    else:
        if args.profile == "full" and not args.yes:
            rows = lcl.FILES_IN_FULL * lcl.ROWS_PER_FILE
            print("Perfil full: Low Carbon London completo (168 archivos, 5,567 hogares, 2011-2014).")
            print(estimate(rows, lcl.FILES_IN_FULL).describe().replace("meses", "archivos"))
            print("Descarga: ~759 MB (zip); se lee sin extraer (8.5 GB descomprimido).")
            print("Vuelve a correr con --yes para cargar.")
            return EXIT_NEEDS_APPROVAL
        cache = data_dir() / "lcl"
        archive = fetch(
            lcl.PARTITIONED_URL, cache / "lcl-partitioned.zip", expected_sha256=lcl.PARTITIONED_SHA256
        )
        tariff_file = fetch(lcl.TARIFFS_URL, cache / "Tariffs.xlsx", expected_sha256=lcl.TARIFFS_SHA256)
        import zipfile

        zf = zipfile.ZipFile(archive)
        members = [n for n in zf.namelist() if n.endswith(".csv")]
        if args.profile == "full":
            chosen = members
        else:
            tariffs = {m: lcl.first_tariff(zf, m) for m in members}
            chosen = lcl.pick_files(members, args.files, tariff_of=tariffs.get)
            mix = {t: sum(tariffs[m] == t for m in chosen) for t in sorted(set(tariffs.values()))}
            print(json.dumps({"archivos_lcl": len(chosen), "por_tarifa": mix}, ensure_ascii=False))
        source = lcl.LclSource.from_zip(archive, chosen)
        version = f"zip-{lcl.PARTITIONED_SHA256[:12]}"

    summaries = []
    with _connect() as conn:
        if tariff_file is not None:
            tariff = lcl.TariffSource(tariff_file)
            rep = Loader(
                conn, tariff.dataset_info(version=f"xlsx-{lcl.TARIFFS_SHA256[:12]}"), args.profile
            ).load(tariff)
            summaries.append((resumen(tariff.name, args.profile, rep), None))
        report = Loader(conn, source.dataset_info(version=version), profile=args.profile).load(source)
    summaries.append((resumen(source.name, args.profile, report), report))
    for datos, rep in summaries:
        imprimir(datos, rep)
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

    lp = sub.add_parser("lcl", help="Low Carbon London: hogares de Londres (CC BY 4.0)")
    lp.add_argument("--profile", choices=["smoke", "demo", "full"], required=True)
    lp.add_argument(
        "--files", type=int, default=4, help="demo: archivos repartidos (de 168, ~30 hogares c/u)"
    )
    lp.add_argument("--yes", action="store_true", help="aprueba el perfil full")
    lp.set_defaults(func=run_lcl)

    c = sub.add_parser("cenace", help="CENACE: precios por zona de carga (pend) o por nodo (pml)")
    c.add_argument("--profile", choices=["smoke", "demo", "full"], required=True)
    c.add_argument("--service", choices=["pend", "pml"], default="pend")
    c.add_argument("--system", choices=list(cenace.SYSTEMS), default="SIN")
    c.add_argument("--process", choices=list(cenace.PROCESSES), default="MDA")
    c.add_argument("--per-ccr", type=int, default=2, help="demo pend: zonas por centro de control")
    c.add_argument("--nodes", type=int, default=40, help="demo pml: nodos repartidos uniformemente")
    c.add_argument("--zone", action="append", help="zona explícita (repetible), p. ej. OAXACA")
    c.add_argument("--start", help="YYYY-MM-DD, inclusive")
    c.add_argument("--end", help="YYYY-MM-DD, inclusive")
    c.add_argument("--delay", type=float, default=1.0, help="segundos entre llamadas al servicio")
    c.add_argument("--yes", action="store_true", help="aprueba el perfil full")
    c.set_defaults(func=run_cenace)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
