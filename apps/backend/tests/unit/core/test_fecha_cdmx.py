"""La fecha de "hoy" del chat es la de Ciudad de México, no la del servidor.

Usuario simulado (SIM-17, 2026-11-06): a las 18:15 de CDMX el chat
dijo "hoy es 7 de noviembre" porque la EC2 corre en UTC y el prompt y el
aviso de datos viejos tomaban la fecha del sistema.
"""

import json
from datetime import date, datetime, timezone

import pytest

from src.core.fechas import hoy_cdmx
from src.core.prompt_registry import ModelParams, PromptEntry, PromptRegistry


@pytest.mark.unit
@pytest.mark.parametrize(
    ("utc", "esperado"),
    [
        (datetime(2026, 11, 7, 0, 15, tzinfo=timezone.utc), date(2026, 11, 6)),
        (datetime(2026, 11, 7, 5, 59, tzinfo=timezone.utc), date(2026, 11, 6)),
        (datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc), date(2026, 11, 7)),
    ],
)
def test_hoy_cdmx_cambia_de_dia_a_las_seis_utc(utc, esperado):
    assert hoy_cdmx(utc) == esperado


@pytest.mark.unit
def test_el_prompt_lleva_la_fecha_de_cdmx(monkeypatch):
    monkeypatch.setattr("src.core.prompt_registry.hoy_cdmx", lambda: date(2026, 11, 6))
    registry = PromptRegistry()
    registry.models["default"] = PromptEntry(
        system_base="Hoy es {CURRENT_DATE}.", params=ModelParams()
    )
    texto, _ = registry.resolve(model="default", tools_markdown="")
    assert "Hoy es 2026-11-06." in texto


@pytest.mark.unit
def test_el_aviso_de_datos_viejos_cuenta_desde_cdmx(monkeypatch):
    from src.services.streaming.function_calling import aviso_del_turno

    monkeypatch.setattr(
        "src.services.streaming.function_calling.hoy_cdmx", lambda: date(2026, 11, 6)
    )
    historial = [{"role": "user", "content": "que se me acaba mañana"}]
    datos = {"metric_name": "alerta", "series": [], "data_as_of": "2026-09-30"}
    aumentados = [*historial, {"role": "tool", "content": json.dumps(datos)}]
    aviso = aviso_del_turno(historial, aumentados, "ok", got_data=True)
    assert "37 días" in aviso["content"]
