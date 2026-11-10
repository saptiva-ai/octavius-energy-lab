"""Carga por unidades a core.observation.

Por cada unidad (p. ej. un mes o un archivo):
1. Si el lote (dataset_version, unit) ya está en 'done', se salta sin leer la
   unidad: la carga es reanudable e idempotente.
2. Los registros pasan en streaming por COPY a una tabla temporal con la
   llave de la fuente (source_key, ts, value). No se juntan en memoria.
3. Las series que aparecen y no existen se crean con source.spec_for(key).
4. Se eliminan duplicados (series, ts) dentro de la unidad y se cuentan,
   distinguiendo los que traen valores distintos.
5. Se crean las particiones que falten y se hace upsert sobre (series_id, ts).
6. Verificación: cada fila deduplicada debe existir con el mismo valor; si no
   cuadra, la unidad se revierte.
7. El lote queda en 'done' con filas leídas, cargadas y calidad.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

from .etiquetas import TIPOS_DE_SERIE, UNIDADES, etiqueta
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
        self._cohort_ids: dict[tuple[str, str], int] = {}

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

    def _cohort_id(self, kind: str, name: str) -> int:
        if (kind, name) not in self._cohort_ids:
            self._cohort_ids[(kind, name)] = self.conn.execute(
                "INSERT INTO core.cohort (kind, name) VALUES (%s, %s) "
                "ON CONFLICT (kind, name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (kind, name),
            ).fetchone()[0]
        return self._cohort_ids[(kind, name)]

    def _upsert_series(self, spec: SeriesSpec) -> int:
        """Crea o actualiza entidad, serie y cohortes. Debe correr dentro de una transacción."""
        entity_id = self.conn.execute(
            """
            INSERT INTO core.entity (source, kind, source_key, name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source, kind, source_key) DO UPDATE
                SET name = COALESCE(EXCLUDED.name, core.entity.name)
            RETURNING id
            """,
            (self.info.source, spec.entity_kind, spec.entity_key, spec.name),
        ).fetchone()[0]
        for kind, name in spec.cohorts:
            self.conn.execute(
                "INSERT INTO core.entity_cohort (entity_id, cohort_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (entity_id, self._cohort_id(kind, name)),
            )
        return self.conn.execute(
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
                Jsonb(
                    {
                        **spec.attrs,
                        "etiqueta": etiqueta(TIPOS_DE_SERIE, spec.kind),
                        "unidad": etiqueta(UNIDADES, spec.unit),
                    }
                ),
            ),
        ).fetchone()[0]

    # -- carga ------------------------------------------------------------------

    def load(self, source: Source) -> LoadReport:
        report = LoadReport()
        started = time.perf_counter()
        dv_id = self._dataset_version_id()
        known = {spec.source_key: spec for spec in source.series_specs()}
        with self.conn.transaction():
            for spec in known.values():
                self._upsert_series(spec)
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
                loaded = self._load_unit(dv_id, batch_unit, selection, unit, source, known)
            except Exception as exc:
                self.conn.rollback()
                self._mark_failed(dv_id, batch_unit, exc)
                raise
            report.units_loaded += 1
            report.rows_read += unit.quality.get("rows_read", unit.quality.get("hours_read", 0))
            report.rows_loaded += loaded
            report.units.append({"unit": batch_unit, "rows_loaded": loaded, **unit.quality})

        report.seconds = time.perf_counter() - started
        return report

    def _load_unit(
        self,
        dv_id: int,
        batch_unit: str,
        selection: str,
        unit: Unit,
        source: Source,
        known: dict[str, SeriesSpec],
    ) -> int:
        with self.conn.transaction():
            batch_id = self.conn.execute(
                """
                INSERT INTO core.ingest_batch
                    (dataset_version_id, profile, unit, status, started_at, selection)
                VALUES (%s, %s, %s, 'running', clock_timestamp(), %s)
                ON CONFLICT (dataset_version_id, unit) DO UPDATE
                    SET status = 'running', started_at = clock_timestamp(), error = NULL
                RETURNING id
                """,
                (dv_id, self.profile, batch_unit, selection),
            ).fetchone()[0]

            self.conn.execute(
                "CREATE TEMP TABLE tmp_raw (source_key text, ts timestamptz, value double precision) "
                "ON COMMIT DROP"
            )
            copied = 0
            with self.conn.cursor().copy("COPY tmp_raw (source_key, ts, value) FROM STDIN") as copy:
                for key, ts, value in unit.records:
                    copy.write_row((key, ts, value))
                    copied += 1

            if copied:
                missing = [
                    r[0]
                    for r in self.conn.execute(
                        "SELECT DISTINCT source_key FROM tmp_raw "
                        "EXCEPT SELECT source_key FROM core.series WHERE source = %s",
                        (self.info.source,),
                    )
                ]
                for key in missing:
                    spec = known.get(key) or source.spec_for(key)  # type: ignore[attr-defined]
                    self._upsert_series(spec)

                self.conn.execute(
                    """
                    CREATE TEMP TABLE tmp_obs ON COMMIT DROP AS
                    SELECT DISTINCT ON (s.id, r.ts) s.id AS series_id, r.ts, r.value
                    FROM tmp_raw r
                    JOIN core.series s ON s.source = %s AND s.source_key = r.source_key
                    ORDER BY s.id, r.ts, r.value NULLS LAST
                    """,
                    (self.info.source,),
                )
                distinct = self.conn.execute("SELECT count(*) FROM tmp_obs").fetchone()[0]
                conflicting = self.conn.execute(
                    """
                    SELECT count(*) FROM (
                        SELECT 1 FROM tmp_raw GROUP BY source_key, ts
                        HAVING count(*) > 1 AND count(DISTINCT coalesce(value, 'NaN')) > 1
                    ) d
                    """
                ).fetchone()[0]
                unit.quality["duplicates_dropped"] = copied - distinct
                unit.quality["duplicates_conflicting"] = conflicting

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
                if verified != distinct:
                    raise CountMismatchError(
                        f"{batch_unit}: {distinct} filas en la unidad, {verified} verificadas"
                    )
            else:
                distinct = 0

            self.conn.execute(
                """
                UPDATE core.ingest_batch
                SET status = 'done', finished_at = clock_timestamp(),
                    rows_read = %s, rows_loaded = %s, quality = %s
                WHERE id = %s
                """,
                (
                    unit.quality.get("rows_read", unit.quality.get("hours_read", copied)),
                    distinct,
                    Jsonb(dict(unit.quality)),
                    batch_id,
                ),
            )
        return distinct

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
