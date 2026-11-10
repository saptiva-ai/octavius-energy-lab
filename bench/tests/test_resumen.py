"""Resumen en español del reporte E1 (sin base de datos)."""

from __future__ import annotations

from energy_lab_bench.resumen import resumen_markdown

REPORTE = {
    "experiment": "E1",
    "measured_at": "2026-11-10T12:00:00+00:00",
    "postgres": "15.15",
    "repetitions": 20,
    "rows": {"core.observation": 5_000_000, "core.series": 100, "core.entity": 50},
    "rows_by_source": {"lcl": 4_000_000, "uci_eld": 1_000_000},
    "partitions": {"count": 41, "default_rows": 0},
    "sizes": {"core.observation": {"table_bytes": 300_000_000, "index_bytes": 160_000_000, "total_bytes": 460_000_000}},
    "bytes_per_row": 92.0,
    "ingest": [
        {"source": "lcl", "profile": "demo", "batches": 4, "rows_loaded": 4_000_000, "seconds": 70.0,
         "rows_per_second": 57143},
    ],
    "queries": [
        {"name": "series_window", "description": "Ventana de 7 días", "antipattern": False, "compare_with": None,
         "repetitions": 20, "rows_returned": 168, "p50_ms": 0.5, "p95_ms": 0.9, "partitions_scanned": 1},
        {"name": "series_window_antipattern", "description": "Con date_trunc", "antipattern": True,
         "compare_with": "series_window", "repetitions": 20, "rows_returned": 168, "p50_ms": 4.5, "p95_ms": 5.0,
         "partitions_scanned": 41},
    ],
}  # fmt: skip


def test_resumen_en_espanol_con_interpretacion() -> None:
    texto = resumen_markdown(REPORTE)
    assert texto.startswith("# E1: PostgreSQL a escala")
    assert "5,000,000 filas" in texto
    assert "92.0 bytes por fila" in texto
    assert "41 particiones mensuales" in texto
    assert "| lcl | demo | 4 | 4,000,000 | 70.0 | 57,143 |" in texto
    assert "9.0 veces más lenta" in texto
    assert "41 particiones en lugar de 1" in texto
    assert "Mismo resultado" in texto
    assert "una sola máquina" in texto


def test_resumen_sin_antipatron_no_inventa_comparaciones() -> None:
    reporte = {**REPORTE, "queries": REPORTE["queries"][:1]}
    assert "veces más lenta" not in resumen_markdown(reporte)
