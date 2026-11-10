"""Conector CENACE (SW-PEND y SW-PML) con respuestas grabadas, sin red.

Los fixtures conservan la estructura real de las respuestas, pero sus valores
son sintéticos: los datos crudos de CENACE no se redistribuyen (ADR-0004).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from energy_lab_ingest.sources.cenace import (
    CenaceApiError,
    CenaceClient,
    CenaceSource,
    hour_to_utc,
    key_chunks,
    windows,
    zone_key,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cenace"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeTransport:
    """Responde con fixtures y registra las URLs pedidas."""

    def __init__(self, responses: dict[str, dict] | None = None, default: dict | None = None):
        self.responses = responses or {}
        self.default = default
        self.calls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        for fragment, payload in self.responses.items():
            if fragment in url:
                return payload
        if self.default is not None:
            return self.default
        raise AssertionError(f"URL inesperada: {url}")


def test_ventanas_de_7_dias_y_20_claves() -> None:
    keys = [f"Z{i}" for i in range(45)]
    result = list(windows(keys, date(2024, 1, 1), date(2024, 1, 20)))
    # 3 bloques de claves (20, 20, 5) x 3 ventanas (1-7, 8-14, 15-20).
    assert len(result) == 9
    assert all(len(k) <= 20 for k, _, _ in result)
    assert all((e - s).days <= 6 for _, s, e in result)
    assert {(s, e) for _, s, e in result} == {
        (date(2024, 1, 1), date(2024, 1, 7)),
        (date(2024, 1, 8), date(2024, 1, 14)),
        (date(2024, 1, 15), date(2024, 1, 20)),
    }


def test_bloques_respetan_largo_del_segmento() -> None:
    # Nombres largos: 20 zonas reales dieron HTTP 400 por el largo de la URL.
    keys = [f"ZONA-LARGA-{i:02d}" for i in range(20)]  # 13 caracteres cada una
    chunks = key_chunks(keys)
    assert all(len(",".join(c)) <= 100 for c in chunks)
    assert sum(len(c) for c in chunks) == 20
    assert len(chunks) == 3
    # Claves cortas (nodos) sí llenan bloques de 20 si caben en 100 caracteres.
    assert [len(c) for c in key_chunks([f"N{i:03d}" for i in range(25)])] == [20, 5]


def test_zone_key() -> None:
    assert zone_key("CENTRO ORIENTE") == "CENTRO-ORIENTE"
    assert zone_key("Lázaro  Cárdenas") == "LAZARO-CARDENAS"
    assert zone_key("OAXACA") == "OAXACA"


def test_hora_1_es_la_primera_hora_local_del_dia() -> None:
    # 2024 ya sin horario de verano: Centro es UTC-6 todo el año.
    assert hour_to_utc(date(2024, 1, 1), 1) == datetime(2024, 1, 1, 6, 0, tzinfo=UTC)
    assert hour_to_utc(date(2024, 1, 1), 24) == datetime(2024, 1, 2, 5, 0, tzinfo=UTC)


def test_hora_en_dias_de_cambio_de_horario_es_indice_desde_medianoche() -> None:
    # 2021-04-04 (entra horario de verano): la medianoche es UTC-6 y el día tiene 23 horas.
    assert hour_to_utc(date(2021, 4, 4), 1) == datetime(2021, 4, 4, 6, 0, tzinfo=UTC)
    assert hour_to_utc(date(2021, 4, 4), 23) == datetime(2021, 4, 5, 4, 0, tzinfo=UTC)
    # 2021-10-31 (sale del horario de verano): medianoche UTC-5, el día tiene 25 horas.
    assert hour_to_utc(date(2021, 10, 31), 1) == datetime(2021, 10, 31, 5, 0, tzinfo=UTC)
    assert hour_to_utc(date(2021, 10, 31), 25) == datetime(2021, 11, 1, 5, 0, tzinfo=UTC)


def test_mensaje_de_error_se_convierte_en_excepcion() -> None:
    client = CenaceClient(transport=FakeTransport(default=load("pend_error_rango.json")), delay_s=0)
    with pytest.raises(CenaceApiError, match="7 dias"):
        client.get("pend", "SIN", "MDA", ["OAXACA"], date(2024, 1, 1), date(2024, 1, 7))


def test_zero_results_no_es_error() -> None:
    client = CenaceClient(transport=FakeTransport(default=load("pend_zero_results.json")), delay_s=0)
    doc = client.get("pend", "SIN", "MDA", ["NOEXISTE"], date(2024, 1, 1), date(2024, 1, 1))
    assert doc["status"] == "ZERO_RESULTS"


def test_url_del_servicio() -> None:
    transport = FakeTransport(default=load("pend_zero_results.json"))
    CenaceClient(transport=transport, delay_s=0).get(
        "pml", "SIN", "MDA", ["01PLO-115", "07ACU-115"], date(2024, 1, 1), date(2024, 1, 2)
    )
    assert transport.calls == [
        "https://ws01.cenace.gob.mx:8082/SWPML/SIM/SIN/MDA/01PLO-115,07ACU-115/2024/01/01/2024/01/02/JSON"
    ]


def pend_source(**kw) -> CenaceSource:
    transport = FakeTransport(default=load("pend_sin_mda_2zonas_7dias.json"))
    return CenaceSource(
        service="pend",
        system="SIN",
        process="MDA",
        keys=["OAXACA", "PUEBLA"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 7),
        client=CenaceClient(transport=transport, delay_s=0),
        **kw,
    )


def test_series_por_componente() -> None:
    specs = {s.source_key: s for s in pend_source().series_specs()}
    assert set(specs) == {
        f"SIN:MDA:{zona}:{comp}"
        for zona in ("OAXACA", "PUEBLA")
        for comp in ("total", "energy", "losses", "congestion")
    }
    s = specs["SIN:MDA:OAXACA:total"]
    assert (s.kind, s.unit, s.freq, s.entity_kind, s.entity_key) == (
        "price",
        "MXN/MWh",
        "1 hour",
        "load_zone",
        "SIN:OAXACA",
    )
    assert specs["SIN:MDA:OAXACA:congestion"].kind == "price_congestion"


def test_registros_y_unidad_mensual() -> None:
    units = list(pend_source().iter_units())
    assert [u.key for u in units] == ["2024-01"]
    records = list(units[0].records)
    # 2 zonas x 168 horas x 4 componentes.
    assert len(records) == 2 * 168 * 4
    primero = next(r for r in records if r[0] == "SIN:MDA:OAXACA:total")
    assert primero[1] == datetime(2024, 1, 1, 6, 0, tzinfo=UTC)
    assert isinstance(primero[2], float)
    assert units[0].quality["hours_read"] == 2 * 168
    assert units[0].quality["api_calls"] == 1


def test_clave_sin_datos_se_cuenta() -> None:
    transport = FakeTransport(default=load("pml_sin_mda_2nodos_2dias.json"))
    source = CenaceSource(
        service="pml",
        system="SIN",
        process="MDA",
        keys=["01PLO-115", "07ACU-115"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 2),
        client=CenaceClient(transport=transport, delay_s=0),
    )
    unit = next(iter(source.iter_units()))
    keys = {r[0].split(":")[2] for r in unit.records}
    assert keys == {"01PLO-115"}
    assert unit.quality["keys_without_data"] == 1


def test_mes_que_cruza_ventanas_llama_por_ventana(tmp_path) -> None:
    transport = FakeTransport(default=load("pend_zero_results.json"))
    source = CenaceSource(
        service="pend",
        system="SIN",
        process="MDA",
        keys=["OAXACA"],
        start=date(2024, 1, 25),
        end=date(2024, 2, 3),
        client=CenaceClient(transport=transport, delay_s=0),
    )
    units = list(source.iter_units())
    assert [u.key for u in units] == ["2024-01", "2024-02"]
    # Las llamadas ocurren al consumir los registros, no al enumerar unidades.
    assert transport.calls == []
    for unit in units:
        list(unit.records)
    # Enero: 25-31 (1 ventana). Febrero: 1-3 (1 ventana).
    assert len(transport.calls) == 2


def test_parametros_invalidos() -> None:
    with pytest.raises(ValueError):
        CenaceSource(service="otro", system="SIN", process="MDA", keys=["X"], start=date(2024, 1, 1))
    with pytest.raises(ValueError):
        CenaceSource(service="pend", system="XYZ", process="MDA", keys=["X"], start=date(2024, 1, 1))


def test_zona_con_espacio_en_la_respuesta_se_normaliza() -> None:
    """Se pide CENTRO-ORIENTE, pero CENACE responde zona_carga "CENTRO ORIENTE"."""
    payload = load("pend_sin_mda_2zonas_7dias.json")
    payload["Resultados"][0]["zona_carga"] = "CENTRO ORIENTE"
    source = CenaceSource(
        service="pend",
        system="SIN",
        process="MDA",
        keys=["CENTRO-ORIENTE", "PUEBLA"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 7),
        client=CenaceClient(transport=FakeTransport(default=payload), delay_s=0),
    )
    specs = {s.source_key for s in source.series_specs()}
    unit = next(iter(source.iter_units()))
    keys = {r[0] for r in unit.records}
    assert keys <= specs
    assert "SIN:MDA:CENTRO-ORIENTE:total" in keys
    assert unit.quality["keys_without_data"] == 0


def test_clave_inesperada_en_la_respuesta_se_cuenta_y_no_se_carga() -> None:
    payload = load("pend_sin_mda_2zonas_7dias.json")
    payload["Resultados"][1]["zona_carga"] = "OTRA"
    source = CenaceSource(
        service="pend",
        system="SIN",
        process="MDA",
        keys=["OAXACA", "PUEBLA"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 7),
        client=CenaceClient(transport=FakeTransport(default=payload), delay_s=0),
    )
    unit = next(iter(source.iter_units()))
    assert {r[0].split(":")[2] for r in unit.records} == {"OAXACA"}
    assert unit.quality["unexpected_keys"] == 1
