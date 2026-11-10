"""Vistas con nombres de negocio en agg y el rol lab_ontology."""

from __future__ import annotations

import psycopg
import pytest

from conftest import dsn_for

VISTAS = (
    "hogares",
    "consumo_hogar_media_hora",
    "consumo_hogar_diario",
    "consumo_cliente_cuarto_hora",
    "zonas_carga",
    "precio_zona_hora",
    "tarifa_dinamica",
)


@pytest.fixture()
def datos(admin_dsn: str, migrated: str):
    """Una zona de CENACE con sus 4 componentes, un hogar ToU y la tarifa."""
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        conn.execute("SELECT core.ensure_observation_partitions('2025-09-01', '2025-09-30')")
        zona = conn.execute(
            "INSERT INTO core.entity (source, kind, source_key, name, attrs) VALUES "
            "('cenace_pend', 'load_zone', 'SIN:OAXACA', 'OAXACA', "
            """'{"ccr": "ORIENTAL", "states": ["OAXACA"], "nodes": 2}') RETURNING id"""
        ).fetchone()[0]
        for kind, valor in (
            ("price", 300),
            ("price_energy", 270),
            ("price_losses", 20),
            ("price_congestion", 10),
        ):
            serie = conn.execute(
                "INSERT INTO core.series (entity_id, source, source_key, kind, unit, freq, attrs) "
                "VALUES (%s, 'cenace_pend', %s, %s, 'MXN/MWh', '1 hour', "
                """'{"system": "SIN", "process": "MDA"}') RETURNING id""",
                (zona, f"SIN:MDA:OAXACA:{kind}", kind),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO core.observation (series_id, ts, value) VALUES (%s, '2025-09-01T06:00Z', %s)",
                (serie, valor),
            )
        hogar = conn.execute(
            "INSERT INTO core.entity (source, kind, source_key) VALUES ('lcl', 'household', 'MAC000001') "
            "RETURNING id"
        ).fetchone()[0]
        cohorte = conn.execute(
            "INSERT INTO core.cohort (kind, name) VALUES ('tariff', 'ToU') RETURNING id"
        ).fetchone()[0]
        conn.execute("INSERT INTO core.entity_cohort VALUES (%s, %s)", (hogar, cohorte))
        serie = conn.execute(
            "INSERT INTO core.series (entity_id, source, source_key, kind, unit, freq) "
            "VALUES (%s, 'lcl', 'MAC000001', 'consumption', 'kWh', '30 minutes') RETURNING id",
            (hogar,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO core.observation (series_id, ts, value) VALUES "
            "(%s, '2025-09-01T00:00Z', 0.25), (%s, '2025-09-01T00:30Z', 0.5)",
            (serie, serie),
        )
        tarifa = conn.execute(
            "INSERT INTO core.series (source, source_key, kind, unit, freq) "
            "VALUES ('lcl_tariff', 'dToU-2013', 'tariff_price', 'p/kWh', '30 minutes') RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO core.observation (series_id, ts, value) VALUES (%s, '2025-09-01T00:00Z', 67.2)",
            (tarifa,),
        )
        conn.commit()
        yield conn
        conn.execute(
            "TRUNCATE core.observation, core.entity_cohort, core.cohort, core.series, core.entity CASCADE"
        )
        conn.commit()


def test_vistas_existen_con_comentario(admin_dsn: str, migrated: str) -> None:
    with psycopg.connect(dsn_for(admin_dsn, migrated)) as conn:
        rows = conn.execute(
            "SELECT c.relname, obj_description(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'agg' AND c.relkind = 'v'"
        ).fetchall()
    descritas = {nombre: comentario for nombre, comentario in rows}
    assert set(VISTAS) <= set(descritas)
    assert all(descritas[v] for v in VISTAS), "cada vista lleva una descripción en español"


def test_precio_zona_hora_pivotea_componentes(datos) -> None:
    fila = datos.execute(
        "SELECT zona_carga, sistema, proceso, centro_control, precio_total_mxn_mwh, "
        "componente_energia_mxn_mwh, componente_perdidas_mxn_mwh, componente_congestion_mxn_mwh "
        "FROM agg.precio_zona_hora"
    ).fetchone()
    assert fila == ("OAXACA", "SIN", "MDA", "ORIENTAL", 300, 270, 20, 10)


def test_consumo_hogar_trae_tarifa_y_diario_suma(datos) -> None:
    assert datos.execute("SELECT hogar, grupo_tarifa FROM agg.hogares").fetchall() == [("MAC000001", "ToU")]
    diario = datos.execute(
        "SELECT hogar, grupo_tarifa, consumo_kwh, lecturas FROM agg.consumo_hogar_diario"
    ).fetchone()
    assert diario == ("MAC000001", "ToU", 0.75, 2)


def test_tarifa_trae_banda(datos) -> None:
    assert datos.execute("SELECT banda, precio_p_kwh FROM agg.tarifa_dinamica").fetchone() == ("Alta", 67.2)


def test_lab_ontology_lee_agg_y_nada_mas(admin_dsn: str, migrated: str, datos) -> None:
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_ontology")) as conn:
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == "1min"
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        for vista in VISTAS:
            conn.execute(f"SELECT * FROM agg.{vista} LIMIT 1").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM core.observation LIMIT 1")


def test_lab_agent_tambien_lee_las_vistas(admin_dsn: str, migrated: str, datos) -> None:
    with psycopg.connect(dsn_for(admin_dsn, migrated, "lab_agent")) as conn:
        assert conn.execute("SELECT count(*) FROM agg.precio_zona_hora").fetchone()[0] == 1
