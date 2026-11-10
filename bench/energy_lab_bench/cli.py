"""energy-lab-bench e1 [--repetitions N] [--source FUENTE] [--out ARCHIVO]

Conexiones (sin superusuario):
  LAB_AGENT_DSN  rol lab_agent: corre las consultas como lo haría el agente
  LAB_EVAL_DSN   rol lab_eval: conteos, tamaños e historial de ingesta
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .e1 import run_benchmark, to_json
from .resumen import resumen_markdown


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Falta la variable de entorno {name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="energy-lab-bench")
    sub = parser.add_subparsers(dest="experiment", required=True)
    e1 = sub.add_parser("e1", help="PostgreSQL a escala: filas, tamaños, ingesta, latencia y poda")
    e1.add_argument("--repetitions", type=int, default=20)
    e1.add_argument("--source", help="fuente para elegir la serie de las consultas, p. ej. lcl")
    e1.add_argument("--out", type=Path, help="archivo JSON de salida (por omisión, stdout)")
    e1.add_argument("--resumen", type=Path, help="archivo Markdown con el resumen en español")
    args = parser.parse_args(argv)

    report = run_benchmark(
        agent_dsn=_env("LAB_AGENT_DSN"),
        admin_dsn=_env("LAB_EVAL_DSN"),
        repetitions=args.repetitions,
        source=args.source,
    )
    text = to_json(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"E1 escrito en {args.out}")
    else:
        print(text)
    if args.resumen:
        args.resumen.parent.mkdir(parents=True, exist_ok=True)
        args.resumen.write_text(resumen_markdown(report), encoding="utf-8")
        print(f"Resumen en español escrito en {args.resumen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
