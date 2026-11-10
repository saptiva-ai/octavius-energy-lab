"""Carga por unidades a core.observation.

Por cada unidad (p. ej. un mes):
1. Si el lote (dataset_version, unit) ya está en 'done', se salta: la carga es
   reanudable e idempotente.
2. COPY a una tabla temporal, creación de particiones que falten y upsert a
   core.observation con ON CONFLICT (series_id, ts). Todo en una transacción.
3. Verificación de conteos: las filas de la unidad deben existir en
   core.observation con el mismo valor. Si no cuadran, la unidad se revierte.
4. El lote queda en 'done' con filas leídas, filas cargadas y calidad.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

from .model import DatasetInfo, SeriesSpec, Source, Unit


class CountMismatchError(RuntimeError):
    """Las filas verificadas en core.observation no cuadran con las de la unidad."""


@dataclass
class LoadReport:
    units_loaded: int = 0
    units_skipped: int = 0
    rows_read: int = 0
    rows_loaded: int = 0
    seconds: float = 0.0
    units: list[dict] = field(default_factory=list)

    @property
    def rows_per_second(self) -> float:
        return self.rows_loaded / self.seconds if self.seconds else 0.0


class Loader:
    def __init__(self, conn: psycopg.Connection, info: DatasetInfo, profile: str) -> None:
        if profile not in ("smoke", "demo", "full"):
            raise ValueError(f"Perfil inválido: {profile}")
        self.conn = conn
        self.info = info
        self.profile = profile

    # -- registro ---------------------------------------------------------------

    def _dataset_version_id(self) -> int:
        with self.conn.transaction():
            return self.conn.execute(
                """
                INSERT INTO core.dataset_version (source, version, license, url, sha256, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, version) DO UPDATE
                    SET sha256 = COALESCE(EXCLUDED.sha256, core.dataset_version.sha256)
                RETURNING id
                """,
                (
                    self.info.source,
                    self.info.version,
                    self.info.license,
                    self.info.url,
                    self.info.sha256,
                    self.info.notes,
                ),
            ).fetchone()[0]

    def _series_ids(self, specs: list[SeriesSpec]) -> dict[str, int]:
        ids: dict[str, int] = {}
        with self.conn.transaction():
            for spec in specs:
                entity_id = self.conn.execute(
                    """
                    INSERT INTO core.entity (source, kind, source_key, name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source, kind, source_key) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (self.info.source, spec.entity_kind, spec.entity_key, spec.name),
                ).fetchone()[0]
                ids[spec.source_key] = self.conn.execute(
                    """
                    INSERT INTO core.series (entity_id, source, source_key, kind, unit, freq, tz, attrs)
                    VALUES (%s, %s, %s, %s, %s, %s::interval, %s, %s)
                    ON CONFLICT (source, source_key, kind) DO UPDATE
                        SET entity_id = EXCLUDED.entity_id, unit = EXCLUDED.unit,
                            freq = EXCLUDED.freq, tz = EXCLUDED.tz, attrs = EXCLUDED.attrs
                    RETURNING id
                    """,
                    (
                        entity_id,
                        self.info.source,
                        spec.source_key,
                        spec.kind,
                        spec.unit,
                        spec.freq,
                        spec.tz,
                        Jsonb(spec.attrs),
                    ),
                ).fetchone()[0]
        return ids

    # -- carga ------------------------------------------------------------------

    def load(self, source: Source) -> LoadReport:
        report = LoadReport()
        started = time.perf_counter()
        dv_id = self._dataset_version_id()
        series_ids = self._series_ids(source.series_specs())
        selection = source.selection()

        for unit in source.iter_units():
            batch_unit = f"{self.profile}:{selection}:{unit.key}"
            status = self.conn.execute(
                "SELECT status FROM core.ingest_batch WHERE dataset_version_id = %s AND unit = %s",
                (dv_id, batch_unit),
            ).fetchone()
            self.conn.commit()
            if status and status[0] == "done":
                report.units_skipped += 1
                continue
            try:
                loaded = self._load_unit(dv_id, batch_unit, selection, unit, series_ids)
            except Exception as exc:
                self.conn.rollback()
                self._mark_failed(dv_id, batch_unit, exc)
                raise
            report.units_loaded += 1
            report.rows_read += unit.quality.get("rows_read", 0)
            report.rows_loaded += loaded
            report.units.append({"unit": batch_unit, "rows_loaded": loaded, **unit.quality})

        report.seconds = time.perf_counter() - started
        return report

    def _load_unit(
        self, dv_id: int, batch_unit: str, selection: str, unit: Unit, series_ids: dict[str, int]
    ) -> int:
        with self.conn.transaction():
            batch_id = self.conn.execute(
                """
                INSERT INTO core.ingest_batch
                    (dataset_version_id, profile, unit, status, started_at, selection)
                VALUES (%s, %s, %s, 'running', now(), %s)
                ON CONFLICT (dataset_version_id, unit) DO UPDATE
                    SET status = 'running', started_at = now(), error = NULL
                RETURNING id
                """,
                (dv_id, self.profile, batch_unit, selection),
            ).fetchone()[0]

            self.conn.execute(
                "CREATE TEMP TABLE tmp_obs (series_id bigint, ts timestamptz, value double precision) "
                "ON COMMIT DROP"
            )
            copied = 0
            with self.conn.cursor().copy("COPY tmp_obs (series_id, ts, value) FROM STDIN") as copy:
                for key, ts, value in unit.records:
                    copy.write_row((series_ids[key], ts, value))
                    copied += 1

            if copied:
                lo, hi = self.conn.execute("SELECT min(ts), max(ts) FROM tmp_obs").fetchone()
                self.conn.execute(
                    "SELECT core.ensure_observation_partitions(%s::date, %s::date)",
                    (lo.date(), hi.date()),
                )
                self.conn.execute(
                    """
                    INSERT INTO core.observation (series_id, ts, value, batch_id)
                    SELECT series_id, ts, value, %s FROM tmp_obs
                    ON CONFLICT (series_id, ts) DO UPDATE
                        SET value = EXCLUDED.value, batch_id = EXCLUDED.batch_id
                        WHERE core.observation.value IS DISTINCT FROM EXCLUDED.value
                    """,
                    (batch_id,),
                )
                verified = self.conn.execute(
                    """
                    SELECT count(*) FROM tmp_obs t
                    JOIN core.observation o ON o.series_id = t.series_id AND o.ts = t.ts
                    WHERE o.value IS NOT DISTINCT FROM t.value
                    """
                ).fetchone()[0]
                if verified != copied:
                    raise CountMismatchError(
                        f"{batch_unit}: {copied} filas en la unidad, {verified} verificadas"
                    )

            self.conn.execute(
                """
                UPDATE core.ingest_batch
                SET status = 'done', finished_at = now(), rows_read = %s, rows_loaded = %s, quality = %s
                WHERE id = %s
                """,
                (unit.quality.get("rows_read", 0), copied, Jsonb(dict(unit.quality)), batch_id),
            )
        return copied

    def _mark_failed(self, dv_id: int, batch_unit: str, exc: Exception) -> None:
        with self.conn.transaction():
            self.conn.execute(
                """
                INSERT INTO core.ingest_batch (dataset_version_id, profile, unit, status, error, finished_at)
                VALUES (%s, %s, %s, 'failed', %s, now())
                ON CONFLICT (dataset_version_id, unit) DO UPDATE
                    SET status = 'failed', error = EXCLUDED.error, finished_at = now()
                """,
                (dv_id, self.profile, batch_unit, f"{type(exc).__name__}: {exc}"[:2000]),
            )
