"""Parser de UCI ElectricityLoadDiagrams20112014 (sin base de datos)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from energy_lab_ingest.sources.uci import UciSource, parse_value

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "uci_smoke.txt"


def collect(source: UciSource):
    units = []
    for unit in source.iter_units():
        units.append((unit.key, list(unit.records), unit.quality))
    return units


def test_parse_value_con_coma_decimal() -> None:
    assert parse_value("334,928229665072") == pytest.approx(334.928229665072)
    assert parse_value("0") == 0.0
    assert parse_value("") is None


def test_series_declaradas() -> None:
    source = UciSource(FIXTURE)
    specs = {s.source_key: s for s in source.series_specs()}
    assert set(specs) == {"MT_001", "MT_124", "MT_131"}
    assert specs["MT_124"].unit == "kW"
    assert specs["MT_124"].freq == "15 minutes"
    assert specs["MT_124"].entity_kind == "client"


def test_filtro_de_clientes() -> None:
    source = UciSource(FIXTURE, clients=["MT_124"])
    assert [s.source_key for s in source.series_specs()] == ["MT_124"]
    for _, records, _ in collect(source):
        assert {r[0] for r in records} <= {"MT_124"}


def test_unidades_por_mes_utc_y_marcas_en_utc() -> None:
    units = collect(UciSource(FIXTURE))
    assert [u[0] for u in units] == ["2011-03", "2011-10", "2011-11"]
    primero = units[0][1][0]
    # 2011-03-26 00:00 en Lisboa es WET (UTC+0).
    assert primero[1] == datetime(2011, 3, 26, 0, 0, tzinfo=UTC)
    # En verano (WEST, UTC+1) la etiqueta local 00:00 del 28 es 27 23:00 UTC.
    ts_marzo = {r[1] for r in units[0][1] if r[0] == "MT_124"}
    assert datetime(2011, 3, 27, 23, 0, tzinfo=UTC) in ts_marzo


def test_hora_inexistente_de_marzo_se_descarta() -> None:
    units = collect(UciSource(FIXTURE))
    calidad_marzo = units[0][2]
    # 01:00, 01:15, 01:30 y 01:45 del 27 de marzo no existen en Lisboa: 4 etiquetas x 3 clientes.
    assert calidad_marzo["nonexistent_local_time"] == 12


def test_hora_ambigua_de_octubre_se_marca() -> None:
    units = collect(UciSource(FIXTURE))
    calidad_octubre = units[1][2]
    # 01:00-01:45 del 30 de octubre existen dos veces; UCI las suma en una sola etiqueta.
    assert calidad_octubre["ambiguous_local_time"] == 12


def test_ceros_previos_al_alta_no_se_cargan() -> None:
    units = collect(UciSource(FIXTURE))
    cargados = {r[0] for _, records, _ in units for r in records}
    assert "MT_001" not in cargados
    assert sum(q["leading_zeros_skipped"] for _, _, q in units) >= 1


def test_sin_duplicados_por_serie() -> None:
    for _, records, _ in collect(UciSource(FIXTURE)):
        claves = [(r[0], r[1]) for r in records]
        assert len(claves) == len(set(claves))


def test_rango_de_fechas() -> None:
    source = UciSource(FIXTURE, start=datetime(2011, 10, 1, tzinfo=UTC))
    assert [u[0] for u in collect(source)] == ["2011-10", "2011-11"]
