"""E1: PostgreSQL a escala para el laboratorio.

Mide filas reales, tamaños de tablas e índices, throughput de ingesta,
latencia p50/p95 de consultas canónicas con el rol del agente (lab_agent) y
cuántas particiones toca cada consulta.

Las consultas marcadas como antipatrón son variantes que un agente podría
escribir y que dan el mismo resultado, pero rompen la poda de particiones.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg


@dataclass(frozen=True)
class Query:
    name: str
    description: str
    sql: str
    antipattern: bool = False
    compare_with: str | None = None


QUERIES: tuple[Query, ...] = (
    Query(
        "series_window",
        "Promedio horario de una serie en una ventana de 7 días (contexto para un pronóstico)",
        """
        SELECT date_trunc('hour', ts) AS hora, avg(value)
        FROM core.observation
        WHERE series_id = %(series_id)s AND ts >= %(week_start)s AND ts < %(end)s
        GROUP BY 1 ORDER BY 1
        """,
    ),
    Query(
        "series_window_antipattern",
        "La misma ventana filtrando por date_trunc(ts): mismo resultado, sin poda de particiones",
        """
        SELECT date_trunc('hour', ts) AS hora, avg(value)
        FROM core.observation
        WHERE series_id = %(series_id)s
          AND date_trunc('day', ts) >= %(week_start)s AND date_trunc('day', ts) < %(end)s
        GROUP BY 1 ORDER BY 1
        """,
        antipattern=True,
        compare_with="series_window",
    ),
    Query(
        "top_series_last_week",
        "Series con mayor consumo total en la última semana observada",
        """
        SELECT series_id, sum(value) AS total
        FROM core.observation
        WHERE ts >= %(week_start)s AND ts < %(end)s
        GROUP BY series_id ORDER BY total DESC LIMIT 10
        """,
    ),
    Query(
        "daily_by_cohort_month",
        "Agregado diario por cohorte en el último mes (comparación entre grupos)",
        """
        SELECT c.kind, c.name, date_trunc('day', o.ts) AS dia, avg(o.value)
        FROM core.observation o
        JOIN core.series s ON s.id = o.series_id
        LEFT JOIN core.entity_cohort ec ON ec.entity_id = s.entity_id
        LEFT JOIN core.cohort c ON c.id = ec.cohort_id
        WHERE o.ts >= %(month_start)s AND o.ts < %(end)s
        GROUP BY 1, 2, 3 ORDER BY 3
        """,
    ),
    Query(
        "forecast_context",
        "Últimos 2,048 puntos de una serie antes del corte (entrada típica de TimesFM)",
        """
        SELECT ts, value FROM core.observation
        WHERE series_id = %(series_id)s AND ts < %(end)s
        ORDER BY ts DESC LIMIT 2048
        """,
    ),
    Query(
        "series_full_history_count",
        "Conteo de la historia completa de una serie (recorre todas las particiones)",
        "SELECT count(*) FROM core.observation WHERE series_id = %(series_id)s",
    ),
)


def _walk(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def explain_partitions(conn: psycopg.Connection, sql: str, params: dict) -> list[str]:
    """Particiones de core.observation que el plan realmente escanea."""
    plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params).fetchone()[0][0]["Plan"]
    names = set()
    for node in _walk(plan):
        rel = node.get("Relation Name", "")
        if (
            rel.startswith("observation_")
            and not node.get("Subplans Removed")
            and node.get("Actual Loops", 1)
        ):
            names.add(rel)
    return sorted(names)


def table_sizes(conn: psycopg.Connection) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        """
        WITH parts AS (
            SELECT 'core.observation' AS parent, inhrelid AS oid
            FROM pg_inherits WHERE inhparent = 'core.observation'::regclass
            UNION ALL
            SELECT n.nspname || '.' || c.relname, c.oid
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('core', 'forecast', 'lab') AND c.relkind = 'r' AND NOT c.relispartition
        )
        SELECT parent, sum(pg_table_size(oid)), sum(pg_indexes_size(oid)), sum(pg_total_relation_size(oid))
        FROM parts GROUP BY parent
        """
    ).fetchall()
    return {
        name: {"table_bytes": int(t), "index_bytes": int(i), "total_bytes": int(total)}
        for name, t, i, total in rows
    }


def _params(conn: psycopg.Connection, source: str | None) -> dict:
    where = "WHERE s.source = %(source)s" if source else ""
    row = conn.execute(
        f"""
        SELECT s.id, max(o.ts)
        FROM core.series s JOIN core.observation o ON o.series_id = s.id
        {where}
        GROUP BY s.id ORDER BY count(*) DESC, s.id LIMIT 1
        """,
        {"source": source},
    ).fetchone()
    if row is None:
        raise RuntimeError("No hay observaciones para medir")
    series_id, last = row
    end = (last + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    day_end = datetime(end.year, end.month, end.day, tzinfo=UTC)
    return {
        "series_id": series_id,
        "end": day_end,
        "week_start": day_end - timedelta(days=7),
        "month_start": day_end - timedelta(days=30),
    }


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def run_benchmark(agent_dsn: str, admin_dsn: str, repetitions: int = 20, source: str | None = None) -> dict:
    report: dict = {
        "experiment": "E1",
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "repetitions": repetitions,
        "source_filter": source,
    }
    with psycopg.connect(admin_dsn) as admin:
        report["postgres"] = admin.execute("SHOW server_version").fetchone()[0]
        report["rows"] = {
            "core.observation": admin.execute("SELECT count(*) FROM core.observation").fetchone()[0],
            "core.series": admin.execute("SELECT count(*) FROM core.series").fetchone()[0],
            "core.entity": admin.execute("SELECT count(*) FROM core.entity").fetchone()[0],
        }
        report["rows_by_source"] = dict(
            admin.execute(
                "SELECT s.source, count(*) FROM core.observation o "
                "JOIN core.series s ON s.id = o.series_id GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
        report["partitions"] = {
            "count": admin.execute(
                "SELECT count(*) FROM pg_inherits WHERE inhparent = 'core.observation'::regclass"
            ).fetchone()[0],
            "default_rows": admin.execute("SELECT count(*) FROM core.observation_default").fetchone()[0],
        }
        report["sizes"] = table_sizes(admin)
        obs = report["sizes"]["core.observation"]
        report["bytes_per_row"] = (
            round(obs["total_bytes"] / report["rows"]["core.observation"], 1)
            if report["rows"]["core.observation"]
            else None
        )
        report["ingest"] = [
            {
                "source": src,
                "profile": profile,
                "batches": batches,
                "rows_loaded": int(rows),
                "seconds": round(float(seconds), 2),
                "rows_per_second": round(rows / seconds) if seconds else None,
            }
            for src, profile, batches, rows, seconds in admin.execute(
                """
                SELECT dv.source, b.profile, count(*), sum(b.rows_loaded),
                       sum(extract(epoch FROM b.finished_at - b.started_at))
                FROM core.ingest_batch b JOIN core.dataset_version dv ON dv.id = b.dataset_version_id
                WHERE b.status = 'done' AND b.started_at IS NOT NULL
                GROUP BY 1, 2 ORDER BY 1, 2
                """
            ).fetchall()
        ]

    results = []
    with psycopg.connect(agent_dsn) as conn:
        params = _params(conn, source)
        report["query_params"] = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in params.items()
        }
        for q in QUERIES:
            conn.execute(q.sql, params).fetchall()  # calentamiento
            timings = []
            rows = 0
            for _ in range(repetitions):
                t0 = time.perf_counter()
                rows = len(conn.execute(q.sql, params).fetchall())
                timings.append((time.perf_counter() - t0) * 1000)
            scanned = explain_partitions(conn, q.sql, params)
            results.append(
                {
                    "name": q.name,
                    "description": q.description,
                    "antipattern": q.antipattern,
                    "compare_with": q.compare_with,
                    "repetitions": repetitions,
                    "rows_returned": rows,
                    "p50_ms": round(_percentile(timings, 0.5), 3),
                    "p95_ms": round(_percentile(timings, 0.95), 3),
                    "partitions_scanned": len(scanned),
                }
            )
            conn.rollback()
    report["queries"] = results
    return report


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)
