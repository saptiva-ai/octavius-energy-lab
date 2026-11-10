"""Resumen en español del reporte E1, con la interpretación de cada medida."""

from __future__ import annotations


def _n(valor) -> str:
    return f"{valor:,}" if isinstance(valor, int) else str(valor)


def resumen_markdown(r: dict) -> str:
    filas = r["rows"]["core.observation"]
    obs = r["sizes"]["core.observation"]
    partes = r["partitions"]
    lineas = [
        "# E1: PostgreSQL a escala",
        "",
        f"Medido el {r['measured_at']} en PostgreSQL {r['postgres']}, con {r['repetitions']} repeticiones "
        "por consulta después de un calentamiento.",
        "",
        "## Volumen",
        "",
        f"- La base tiene **{_n(filas)} filas** de observaciones en {_n(r['rows']['core.series'])} series "
        f"y {_n(r['rows']['core.entity'])} entidades.",
        f"- Ocupan {obs['total_bytes'] / 1e6:,.1f} MB con índices ({obs['index_bytes'] / 1e6:,.1f} MB son "
        f"índices), unos **{r['bytes_per_row']} bytes por fila**.",
        f"- Están repartidas en **{partes['count']} particiones mensuales**; la partición por omisión tiene "
        f"{_n(partes['default_rows'])} filas.",
        "",
        "| Fuente | Filas |",
        "|---|---|",
        *[f"| {fuente} | {_n(n)} |" for fuente, n in r["rows_by_source"].items()],
        "",
        "## Ingesta",
        "",
        "| Fuente | Perfil | Lotes | Filas cargadas | Segundos | Filas por segundo |",
        "|---|---|---|---|---|---|",
        *[
            f"| {i['source']} | {i['profile']} | {i['batches']} | {_n(i['rows_loaded'])} | {i['seconds']} | "
            f"{_n(i['rows_per_second']) if i['rows_per_second'] else 'sin medir'} |"
            for i in r["ingest"]
        ],
        "",
        "## Consultas con el rol del agente",
        "",
        "| Consulta | Qué responde | p50 (ms) | p95 (ms) | Particiones leídas | Filas |",
        "|---|---|---|---|---|---|",
        *[
            f"| `{q['name']}` | {q['description']} | {q['p50_ms']} | {q['p95_ms']} | "
            f"{q['partitions_scanned']} | {_n(q['rows_returned'])} |"
            for q in r["queries"]
        ],
    ]

    por_nombre = {q["name"]: q for q in r["queries"]}
    comparaciones = [
        (q, por_nombre[q["compare_with"]])
        for q in r["queries"]
        if q.get("antipattern") and q.get("compare_with") in por_nombre
    ]
    if comparaciones:
        lineas += ["", "## Interpretación", ""]
        for mala, buena in comparaciones:
            veces = mala["p50_ms"] / buena["p50_ms"] if buena["p50_ms"] else float("inf")
            lineas.append(
                f"- `{mala['name']}` es {veces:.1f} veces más lenta que `{buena['name']}` (p50) y lee "
                f"{mala['partitions_scanned']} particiones en lugar de {buena['partitions_scanned']}. "
                "Mismo resultado: el filtro sobre una expresión de `ts` impide la poda de particiones. "
                "Es el tipo de consulta que un agente puede generar si el harness no la valida."
            )

    lineas += [
        "",
        "## Límites de esta medición",
        "",
        "- Son medidas de una sola máquina y una sola corrida; no se comparan entre equipos.",
        "- Las latencias excluyen la red y el modelo de lenguaje: miden solo PostgreSQL.",
    ]
    if any(i["source"].startswith("cenace") for i in r["ingest"]):
        lineas.append(
            "- La ingesta de CENACE incluye las llamadas al servicio web y la pausa entre ellas; "
            "su throughput no mide PostgreSQL."
        )
    return "\n".join(lineas) + "\n"
